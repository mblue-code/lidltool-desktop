from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Protocol, cast, get_args
from urllib.parse import urlparse
from uuid import uuid4

from openai import OpenAI
from sqlalchemy.orm import Session, sessionmaker

from lidltool.ai.audit import record_plugin_ai_audit_event
from lidltool.ai.config import get_ai_api_key, get_ai_oauth_access_token
from lidltool.ai.policy import (
    PluginAiManifestLike,
    PluginAiMediationConfig,
    evaluate_plugin_ai_policy,
)
from lidltool.ai.schemas import (
    AiInputPart,
    AiMediationError,
    AiMediationErrorCode,
    AiMediationMetadata,
    AiMediationRequest,
    AiMediationResponse,
    AiPolicyLevel,
    AiRequestSizeClass,
    AiTaskType,
    AiUsageMetadata,
    classify_request_size,
    estimate_request_text_bytes,
    validate_ai_mediation_request,
    validate_structured_output,
)
from lidltool.config import AppConfig


class PluginAiManifestWithSource(PluginAiManifestLike, Protocol):
    source_id: str

_TASK_TYPES = set(get_args(AiMediationRequest.model_fields["task_type"].annotation))
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{12,}\b"), "[REDACTED_API_KEY]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9._\-]+\.[A-Za-z0-9._\-]+\b"),
        "[REDACTED_TOKEN]",
    ),
)


class PluginAiMediationService:
    def __init__(
        self,
        *,
        config: AppConfig,
        session_factory: sessionmaker[Session] | None = None,
        client_factory: type[OpenAI] = OpenAI,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._client_factory = client_factory
        self._usage_lock = threading.Lock()
        self._provider_request_count = 0
        self._provider_cost_total = 0.0
        self._plugin_request_counts: dict[str, int] = defaultdict(int)
        self._plugin_cost_totals: dict[str, float] = defaultdict(float)

    def mediate(
        self,
        *,
        manifest: PluginAiManifestWithSource,
        request: AiMediationRequest | Mapping[str, Any],
    ) -> AiMediationResponse:
        request_id = uuid4().hex
        started = time.monotonic()
        maybe_error = self._reject_unsupported_task(
            request=request,
            request_id=request_id,
        )
        if maybe_error is not None:
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type="structured_extraction",
                policy_level="none",
                success=False,
                error=maybe_error.error,
                request_size_class="small",
                duration_ms=0,
                usage=AiUsageMetadata(),
            )
            return maybe_error

        try:
            validated_request = validate_ai_mediation_request(request)
        except Exception as exc:
            response = self._failure(
                request_id=request_id,
                task_type=_task_type_from_payload(request) or "structured_extraction",
                policy_level="none",
                code="invalid_request",
                message=str(exc),
                duration_ms=0,
                request_size_class="small",
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=response.task_type,
                policy_level=response.policy_level,
                success=False,
                error=response.error,
                request_size_class="small",
                duration_ms=0,
                usage=AiUsageMetadata(),
            )
            return response

        plugin_ai_config = self._config.plugin_ai_mediation
        decision = evaluate_plugin_ai_policy(
            config=plugin_ai_config,
            manifest=manifest,
            request=validated_request,
        )
        request_size_class = classify_request_size(validated_request)
        request_bytes = estimate_request_text_bytes(validated_request)

        if not decision.allowed:
            response = self._failure(
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                code="policy_denied",
                message=decision.reason or "plugin AI mediation request denied by policy",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response

        maybe_error = self._validate_limits(
            request=validated_request,
            request_id=request_id,
            request_bytes=request_bytes,
            config=plugin_ai_config,
            manifest=manifest,
            max_payload_bytes=decision.effective.max_payload_bytes,
            timeout_s=decision.effective.timeout_s,
            request_size_class=request_size_class,
            started=started,
        )
        if maybe_error is not None:
            return maybe_error

        maybe_budget_error = self._reserve_budget(
            manifest=manifest,
            request_id=request_id,
            task_type=validated_request.task_type,
            policy_level=decision.effective.max_policy_level,
            request_size_class=request_size_class,
            duration_ms=self._duration_ms(started),
            plugin_ai_config=plugin_ai_config,
            max_requests_per_plugin=decision.effective.max_requests_per_process,
        )
        if maybe_budget_error is not None:
            return maybe_budget_error

        provider_config = self._provider_settings()
        if provider_config is None:
            response = self._failure(
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                code="provider_not_configured",
                message="core AI provider settings are not configured",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response

        prepared_parts, redaction_applied = _prepare_inputs(validated_request.inputs)
        prompt = _build_prompt(
            request=validated_request,
            prepared_parts=prepared_parts,
        )

        try:
            raw_response = self._call_provider(
                base_url=provider_config["base_url"],
                token=provider_config["token"],
                model=provider_config["model"],
                timeout_s=decision.effective.timeout_s,
                prompt=prompt,
            )
            output = _parse_provider_output(raw_response)
            validate_structured_output(schema=validated_request.output_schema, value=output)
        except json.JSONDecodeError as exc:
            response = self._failure(
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                code="invalid_output",
                message=f"provider returned invalid JSON: {exc}",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
                provider=provider_config["provider"],
                model=provider_config["model"],
                redaction_applied=redaction_applied,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
                provider=provider_config["provider"],
                model=provider_config["model"],
            )
            return response
        except TimeoutError as exc:
            response = self._failure(
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                code="timeout",
                message=str(exc),
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
                provider=provider_config["provider"],
                model=provider_config["model"],
                redaction_applied=redaction_applied,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
                provider=provider_config["provider"],
                model=provider_config["model"],
            )
            return response
        except Exception as exc:
            error_code: AiMediationErrorCode = (
                "invalid_output" if isinstance(exc, ValueError) else "provider_failure"
            )
            response = self._failure(
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                code=error_code,
                message=str(exc),
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
                provider=provider_config["provider"],
                model=provider_config["model"],
                redaction_applied=redaction_applied,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=validated_request.task_type,
                policy_level=decision.effective.max_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
                provider=provider_config["provider"],
                model=provider_config["model"],
            )
            return response

        usage = _usage_from_provider_response(raw_response)
        duration_ms = self._duration_ms(started)
        self._record_usage(manifest=manifest, usage=usage)
        response = AiMediationResponse(
            request_id=request_id,
            ok=True,
            task_type=validated_request.task_type,
            policy_level=decision.effective.max_policy_level,
            output=output,
            warnings=(),
            metadata=AiMediationMetadata(
                provider=provider_config["provider"],
                model=provider_config["model"],
                request_size_class=request_size_class,
                duration_ms=duration_ms,
                redaction_applied=redaction_applied,
                usage=usage,
            ),
        )
        self._audit(
            manifest=manifest,
            request_id=request_id,
            task_type=validated_request.task_type,
            policy_level=decision.effective.max_policy_level,
            success=True,
            error=None,
            request_size_class=request_size_class,
            duration_ms=duration_ms,
            usage=usage,
            provider=provider_config["provider"],
            model=provider_config["model"],
        )
        return response

    def _reject_unsupported_task(
        self,
        *,
        request: AiMediationRequest | Mapping[str, Any],
        request_id: str,
    ) -> AiMediationResponse | None:
        raw_task_type = _raw_task_type_from_payload(request)
        if raw_task_type is None:
            return None
        if raw_task_type in _TASK_TYPES:
            return None
        return self._failure(
            request_id=request_id,
            task_type="structured_extraction",
            policy_level="none",
            code="unsupported_task",
            message=f"unsupported AI mediation task type: {raw_task_type}",
            duration_ms=0,
            request_size_class="small",
        )

    def _validate_limits(
        self,
        *,
        request: AiMediationRequest,
        request_id: str,
        request_bytes: int,
        config: PluginAiMediationConfig,
        manifest: PluginAiManifestWithSource,
        max_payload_bytes: int,
        timeout_s: float,
        request_size_class: AiRequestSizeClass,
        started: float,
    ) -> AiMediationResponse | None:
        if request_bytes > max_payload_bytes:
            response = self._failure(
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                code="payload_too_large",
                message=f"request payload exceeds configured limit of {max_payload_bytes} bytes",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response

        artifact_parts = [part for part in request.inputs if part.kind == "artifact_ref"]
        if len(artifact_parts) > config.limits.max_artifact_count:
            response = self._failure(
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                code="payload_too_large",
                message="request exceeds configured artifact count limit",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response
        image_count = sum(
            1 for part in artifact_parts if isinstance(part.media_type, str) and part.media_type.startswith("image/")
        )
        pdf_count = sum(1 for part in artifact_parts if part.media_type == "application/pdf")
        if image_count > config.limits.max_image_count or pdf_count > config.limits.max_pdf_count:
            response = self._failure(
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                code="payload_too_large",
                message="request exceeds configured image/pdf limits",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response
        if artifact_parts:
            response = self._failure(
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                code="artifact_unsupported",
                message=(
                    "artifact references are reserved for a future core-managed resolver; "
                    "Sprint 3.5 supports text inputs only"
                ),
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response
        if timeout_s > config.limits.timeout_s:
            response = self._failure(
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                code="invalid_request",
                message="effective timeout exceeds configured plugin AI timeout ceiling",
                duration_ms=self._duration_ms(started),
                request_size_class=request_size_class,
            )
            self._audit(
                manifest=manifest,
                request_id=request_id,
                task_type=request.task_type,
                policy_level=request.requested_policy_level,
                success=False,
                error=response.error,
                request_size_class=request_size_class,
                duration_ms=response.metadata.duration_ms if response.metadata else 0,
                usage=AiUsageMetadata(),
            )
            return response
        return None

    def _reserve_budget(
        self,
        *,
        manifest: PluginAiManifestWithSource,
        request_id: str,
        task_type: AiTaskType,
        policy_level: AiPolicyLevel,
        request_size_class: AiRequestSizeClass,
        duration_ms: int,
        plugin_ai_config: PluginAiMediationConfig,
        max_requests_per_plugin: int | None,
    ) -> AiMediationResponse | None:
        with self._usage_lock:
            if (
                plugin_ai_config.budgets.max_requests_per_process is not None
                and self._provider_request_count >= plugin_ai_config.budgets.max_requests_per_process
            ):
                response = self._failure(
                    request_id=request_id,
                    task_type=task_type,
                    policy_level=policy_level,
                    code="budget_exceeded",
                    message="global plugin AI request budget exceeded for this process",
                    duration_ms=duration_ms,
                    request_size_class=request_size_class,
                )
                self._audit(
                    manifest=manifest,
                    request_id=request_id,
                    task_type=task_type,
                    policy_level=policy_level,
                    success=False,
                    error=response.error,
                    request_size_class=request_size_class,
                    duration_ms=duration_ms,
                    usage=AiUsageMetadata(),
                )
                return response
            if (
                max_requests_per_plugin is not None
                and self._plugin_request_counts[manifest.plugin_id] >= max_requests_per_plugin
            ):
                response = self._failure(
                    request_id=request_id,
                    task_type=task_type,
                    policy_level=policy_level,
                    code="budget_exceeded",
                    message=f"plugin AI request budget exceeded for {manifest.plugin_id}",
                    duration_ms=duration_ms,
                    request_size_class=request_size_class,
                )
                self._audit(
                    manifest=manifest,
                    request_id=request_id,
                    task_type=task_type,
                    policy_level=policy_level,
                    success=False,
                    error=response.error,
                    request_size_class=request_size_class,
                    duration_ms=duration_ms,
                    usage=AiUsageMetadata(),
                )
                return response
            self._provider_request_count += 1
            self._plugin_request_counts[manifest.plugin_id] += 1
        return None

    def _record_usage(self, *, manifest: PluginAiManifestWithSource, usage: AiUsageMetadata) -> None:
        if usage.cost_usd is None:
            return
        with self._usage_lock:
            self._provider_cost_total += usage.cost_usd
            self._plugin_cost_totals[manifest.plugin_id] += usage.cost_usd

    def _provider_settings(self) -> dict[str, str] | None:
        base_url = (self._config.ai_base_url or "").strip()
        token = get_ai_oauth_access_token(self._config) or get_ai_api_key(self._config)
        model = (self._config.ai_model or "").strip()
        if not self._config.ai_enabled or not base_url or not token or not model:
            return None
        return {
            "base_url": base_url,
            "token": token,
            "model": model,
            "provider": _provider_name(base_url=base_url, oauth_provider=self._config.ai_oauth_provider),
        }

    def _call_provider(
        self,
        *,
        base_url: str,
        token: str,
        model: str,
        timeout_s: float,
        prompt: str,
    ) -> Any:
        attempts = self._config.plugin_ai_mediation.limits.retry_ceiling + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                client = self._client_factory(base_url=base_url, api_key=token, timeout=timeout_s)
                return client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are the lidltool core AI mediation service. "
                                "Return only JSON that matches the requested schema."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                last_error = exc
                if "timeout" in str(exc).lower():
                    raise TimeoutError(str(exc)) from exc
                if attempt >= attempts:
                    raise
                time.sleep(min(0.2 * attempt, 1.0))
        if last_error is not None:
            raise last_error
        raise RuntimeError("provider call failed without an exception")

    def _failure(
        self,
        *,
        request_id: str,
        task_type: AiTaskType,
        policy_level: AiPolicyLevel,
        code: AiMediationErrorCode,
        message: str,
        duration_ms: int,
        request_size_class: AiRequestSizeClass,
        provider: str = "core",
        model: str = "core",
        redaction_applied: bool = False,
    ) -> AiMediationResponse:
        return AiMediationResponse(
            request_id=request_id,
            ok=False,
            task_type=task_type,
            policy_level=policy_level,
            error=AiMediationError(code=code, message=message, retryable=code in {"provider_failure", "timeout"}),
            metadata=AiMediationMetadata(
                provider=provider,
                model=model,
                request_size_class=request_size_class,
                duration_ms=duration_ms,
                redaction_applied=redaction_applied,
                usage=AiUsageMetadata(),
            ),
        )

    def _audit(
        self,
        *,
        manifest: PluginAiManifestWithSource,
        request_id: str,
        task_type: AiTaskType,
        policy_level: AiPolicyLevel,
        success: bool,
        error: AiMediationError | None,
        request_size_class: AiRequestSizeClass,
        duration_ms: int,
        usage: AiUsageMetadata,
        provider: str = "core",
        model: str = "core",
    ) -> None:
        record_plugin_ai_audit_event(
            session_factory=self._session_factory,
            plugin_id=manifest.plugin_id,
            source_id=manifest.source_id,
            details={
                "request_id": request_id,
                "plugin_id": manifest.plugin_id,
                "source_id": manifest.source_id,
                "trust_class": manifest.trust_class,
                "task_type": task_type,
                "policy_level": policy_level,
                "provider": provider,
                "model": model,
                "request_size_class": request_size_class,
                "duration_ms": duration_ms,
                "success": success,
                "error_code": error.code if error is not None else None,
                "error_message": error.message if error is not None else None,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "cost_usd": usage.cost_usd,
            },
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(int((time.monotonic() - started) * 1000), 0)


def _prepare_inputs(parts: list[AiInputPart]) -> tuple[list[dict[str, str]], bool]:
    prepared: list[dict[str, str]] = []
    redaction_applied = False
    for part in parts:
        text = part.text or ""
        sanitized = text
        for pattern, replacement in _SECRET_PATTERNS:
            sanitized, replacements = pattern.subn(replacement, sanitized)
            if replacements:
                redaction_applied = True
        prepared.append({"kind": part.kind, "text": sanitized})
    return prepared, redaction_applied


def _build_prompt(*, request: AiMediationRequest, prepared_parts: list[dict[str, str]]) -> str:
    payload = {
        "task_type": request.task_type,
        "requested_policy_level": request.requested_policy_level,
        "instructions": request.instructions or "",
        "output_schema": request.output_schema.model_dump(mode="python"),
        "inputs": prepared_parts,
        "metadata": request.metadata,
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _parse_provider_output(raw_response: Any) -> Any:
    choices = getattr(raw_response, "choices", None)
    if not choices:
        raise ValueError("provider returned no choices")
    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("provider returned empty content")
    return json.loads(content)


def _usage_from_provider_response(raw_response: Any) -> AiUsageMetadata:
    usage = getattr(raw_response, "usage", None)
    if usage is None:
        return AiUsageMetadata()
    prompt_tokens = _coerce_non_negative_int(getattr(usage, "prompt_tokens", None))
    completion_tokens = _coerce_non_negative_int(getattr(usage, "completion_tokens", None))
    total_tokens = _coerce_non_negative_int(getattr(usage, "total_tokens", None))
    return AiUsageMetadata(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=None,
    )


def _provider_name(*, base_url: str, oauth_provider: str | None) -> str:
    if oauth_provider:
        return oauth_provider
    host = urlparse(base_url).netloc or base_url
    return host.split(":")[0]


def _task_type_from_payload(payload: AiMediationRequest | Mapping[str, Any]) -> AiTaskType | None:
    raw_task_type = _raw_task_type_from_payload(payload)
    if raw_task_type in _TASK_TYPES:
        return cast(AiTaskType, raw_task_type)
    return None


def _raw_task_type_from_payload(payload: AiMediationRequest | Mapping[str, Any]) -> str | None:
    if isinstance(payload, AiMediationRequest):
        return payload.task_type
    task_type = payload.get("task_type")
    return task_type if isinstance(task_type, str) else None


def _coerce_non_negative_int(value: object) -> int | None:
    if not isinstance(value, int) or value < 0:
        return None
    return value
