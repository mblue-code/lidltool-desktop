from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from lidltool.ai.config import (
    get_ai_api_key,
    get_ai_oauth_access_token,
    get_item_categorizer_api_key,
    get_local_text_model_api_key,
)
from lidltool.ai.runtime.models import (
    ModelRuntime,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimePolicyMode,
    RuntimeProviderKind,
    RuntimeResolution,
    RuntimeTask,
)
from lidltool.ai.runtime.providers import (
    BundledLocalTextRuntimeAdapter,
    OpenAICompatibleRuntimeAdapter,
    is_local_endpoint,
)

LOGGER = logging.getLogger(__name__)

_DEFAULT_LOCAL_TEXT_MODEL = "qwen3.5:0.8b"


@dataclass(slots=True)
class _RuntimeSelection:
    runtime: ModelRuntime | None
    provider_kind: RuntimeProviderKind | None
    status_code: str
    reason_code: str | None = None
    warnings: list[str] | None = None
    details: dict[str, Any] | None = None


def resolve_runtime(
    config: Any,
    *,
    task: RuntimeTask,
    policy_mode: RuntimePolicyMode = RuntimePolicyMode.LOCAL_PREFERRED,
    api_key_override: str | None = None,
) -> RuntimeResolution:
    if task == RuntimeTask.ITEM_CATEGORIZATION:
        selection = _resolve_item_categorization_runtime(
            config=config,
            policy_mode=policy_mode,
            api_key_override=api_key_override,
        )
    elif task == RuntimeTask.PI_AGENT:
        selection = _resolve_pi_agent_runtime(
            config=config,
            policy_mode=policy_mode,
            api_key_override=api_key_override,
        )
    else:
        selection = _resolve_remote_text_runtime(
            config=config,
            task=task,
            policy_mode=policy_mode,
            api_key_override=api_key_override,
        )

    health = selection.runtime.health() if selection.runtime is not None else _missing_health(
        task=task,
        policy_mode=policy_mode,
        provider_kind=selection.provider_kind,
        status_code=selection.status_code,
        reason_code=selection.reason_code,
        details=selection.details or {},
    )
    capabilities = selection.runtime.capabilities() if selection.runtime is not None else health.capabilities
    resolution = RuntimeResolution(
        task=task,
        policy_mode=policy_mode,
        provider_kind=selection.provider_kind,
        status_code=selection.status_code,
        reason_code=selection.reason_code,
        selected=selection.runtime is not None,
        runtime=selection.runtime,
        health=health,
        capabilities=capabilities,
        warnings=selection.warnings or [],
        details=selection.details or {},
    )
    LOGGER.info(
        "runtime.resolve task=%s policy=%s status=%s provider=%s reason=%s selected=%s",
        task.value,
        policy_mode.value,
        resolution.status_code,
        selection.provider_kind.value if selection.provider_kind else "none",
        resolution.reason_code or "-",
        resolution.selected,
    )
    return resolution


def resolve_runtime_client(
    config: Any,
    *,
    task: RuntimeTask,
    policy_mode: RuntimePolicyMode = RuntimePolicyMode.LOCAL_PREFERRED,
    api_key_override: str | None = None,
) -> ModelRuntime | None:
    return resolve_runtime(
        config,
        task=task,
        policy_mode=policy_mode,
        api_key_override=api_key_override,
    ).runtime


def describe_runtime_capabilities(
    config: Any,
    *,
    task: RuntimeTask,
    policy_mode: RuntimePolicyMode = RuntimePolicyMode.LOCAL_PREFERRED,
    api_key_override: str | None = None,
) -> RuntimeCapabilities | None:
    return resolve_runtime(
        config,
        task=task,
        policy_mode=policy_mode,
        api_key_override=api_key_override,
    ).capabilities


def _resolve_item_categorization_runtime(
    *,
    config: Any,
    policy_mode: RuntimePolicyMode,
    api_key_override: str | None,
) -> _RuntimeSelection:
    enabled = (
        bool(getattr(config, "local_text_model_enabled"))
        if getattr(config, "local_text_model_enabled", None) is not None
        else bool(getattr(config, "item_categorizer_enabled", False))
    )
    base_url = _normalize_text(getattr(config, "local_text_model_base_url", None)) or _normalize_text(
        getattr(config, "item_categorizer_base_url", None)
    )
    api_key = (
        api_key_override
        or get_local_text_model_api_key(config)
        or get_item_categorizer_api_key(config)
        or get_ai_oauth_access_token(config)
        or get_ai_api_key(config)
    )
    model_name = _normalize_text(getattr(config, "local_text_model_name", None)) or _normalize_text(
        getattr(config, "item_categorizer_model", None)
    ) or _DEFAULT_LOCAL_TEXT_MODEL
    timeout_s = (
        float(getattr(config, "local_text_model_timeout_s"))
        if getattr(config, "local_text_model_timeout_s", None) is not None
        else float(getattr(config, "item_categorizer_timeout_s", 5.0) or 5.0)
    )
    max_retries = (
        int(getattr(config, "local_text_model_max_retries"))
        if getattr(config, "local_text_model_max_retries", None) is not None
        else int(getattr(config, "item_categorizer_max_retries", 0) or 0)
    )
    allow_remote = (
        bool(getattr(config, "local_text_model_allow_remote"))
        if getattr(config, "local_text_model_allow_remote", None) is not None
        else bool(getattr(config, "item_categorizer_allow_remote", False))
    )
    allow_insecure_transport = bool(getattr(config, "allow_insecure_transport", False))

    if not enabled:
        return _RuntimeSelection(
            runtime=None,
            provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
            status_code="disabled",
            reason_code="local_text_runtime_disabled",
            details={"task": RuntimeTask.ITEM_CATEGORIZATION.value},
        )

    local_runtime = BundledLocalTextRuntimeAdapter(
        task=RuntimeTask.ITEM_CATEGORIZATION,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        timeout_s=timeout_s,
        max_retries=max_retries,
        allow_remote=allow_remote,
        allow_insecure_transport=allow_insecure_transport,
    )
    local_health = local_runtime.health()
    if local_health.healthy:
        return _RuntimeSelection(
            runtime=local_runtime,
            provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
            status_code="ready",
            details={"selected": "bundled_local_text"},
        )

    if policy_mode == RuntimePolicyMode.LOCAL_ONLY:
        return _RuntimeSelection(
            runtime=None,
            provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
            status_code=local_health.status_code,
            reason_code=local_health.reason_code or "local_runtime_unavailable",
            warnings=[local_health.message] if local_health.message else None,
            details={"selected": "bundled_local_text", "health": local_health.model_dump(mode="python")},
        )

    remote_runtime = _build_remote_runtime(
        task=RuntimeTask.ITEM_CATEGORIZATION,
        config=config,
        api_key_override=api_key_override,
    )
    if remote_runtime is not None and policy_mode in {
        RuntimePolicyMode.LOCAL_PREFERRED,
        RuntimePolicyMode.REMOTE_ALLOWED,
    }:
        remote_health = remote_runtime.health()
        if remote_health.healthy:
            return _RuntimeSelection(
                runtime=remote_runtime,
                provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
                status_code="ready",
                reason_code="remote_overlay_selected",
                warnings=[local_health.message] if local_health.message else None,
                details={
                    "selected": "openai_compatible",
                    "fallback_from": "bundled_local_text",
                },
            )

    return _RuntimeSelection(
        runtime=None,
        provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
        status_code=local_health.status_code,
        reason_code=local_health.reason_code or "runtime_unavailable",
        warnings=[local_health.message] if local_health.message else None,
        details={"selected": "bundled_local_text", "health": local_health.model_dump(mode="python")},
    )


def _resolve_remote_text_runtime(
    *,
    config: Any,
    task: RuntimeTask,
    policy_mode: RuntimePolicyMode,
    api_key_override: str | None,
) -> _RuntimeSelection:
    runtime = _build_remote_runtime(task=task, config=config, api_key_override=api_key_override)
    if runtime is None:
        return _RuntimeSelection(
            runtime=None,
            provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
            status_code="not_configured",
            reason_code="remote_runtime_missing",
            details={"task": task.value},
        )
    health = runtime.health()
    if policy_mode == RuntimePolicyMode.LOCAL_ONLY and not health.capabilities.local:
        return _RuntimeSelection(
            runtime=None,
            provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
            status_code="policy_blocked",
            reason_code="local_only_requires_local_endpoint",
            warnings=[health.message] if health.message else None,
            details={"selected": "openai_compatible", "health": health.model_dump(mode="python")},
        )
    if health.healthy or policy_mode == RuntimePolicyMode.REMOTE_ALLOWED:
        return _RuntimeSelection(
            runtime=runtime,
            provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
            status_code="ready" if health.healthy else health.status_code,
            reason_code=None if health.healthy else health.reason_code,
            warnings=[health.message] if health.message else None,
            details={"selected": "openai_compatible"},
        )
    return _RuntimeSelection(
        runtime=None,
        provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
        status_code=health.status_code,
        reason_code=health.reason_code,
        warnings=[health.message] if health.message else None,
        details={"selected": "openai_compatible", "health": health.model_dump(mode="python")},
    )


def _resolve_pi_agent_runtime(
    *,
    config: Any,
    policy_mode: RuntimePolicyMode,
    api_key_override: str | None,
) -> _RuntimeSelection:
    local_runtime = _build_shared_local_runtime(
        task=RuntimeTask.PI_AGENT,
        config=config,
        api_key_override=api_key_override,
    )
    if local_runtime is not None:
        local_health = local_runtime.health()
        if local_health.healthy and policy_mode in {
            RuntimePolicyMode.LOCAL_ONLY,
            RuntimePolicyMode.LOCAL_PREFERRED,
        }:
            return _RuntimeSelection(
                runtime=local_runtime,
                provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
                status_code="ready",
                details={"selected": "bundled_local_text"},
            )
        if local_health.healthy and policy_mode == RuntimePolicyMode.REMOTE_ALLOWED:
            return _RuntimeSelection(
                runtime=local_runtime,
                provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
                status_code="ready",
                reason_code="local_runtime_selected",
                details={"selected": "bundled_local_text"},
            )
        if policy_mode == RuntimePolicyMode.LOCAL_ONLY:
            return _RuntimeSelection(
                runtime=None,
                provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
                status_code=local_health.status_code,
                reason_code=local_health.reason_code or "local_runtime_unavailable",
                warnings=[local_health.message] if local_health.message else None,
                details={
                    "selected": "bundled_local_text",
                    "health": local_health.model_dump(mode="python"),
                },
            )

    remote_runtime = _build_remote_runtime(
        task=RuntimeTask.PI_AGENT,
        config=config,
        api_key_override=api_key_override,
    )
    if remote_runtime is not None and policy_mode in {
        RuntimePolicyMode.LOCAL_PREFERRED,
        RuntimePolicyMode.REMOTE_ALLOWED,
    }:
        remote_health = remote_runtime.health()
        if remote_health.healthy:
            return _RuntimeSelection(
                runtime=remote_runtime,
                provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
                status_code="ready",
                reason_code=(
                    "remote_overlay_selected" if local_runtime is not None else "remote_runtime_selected"
                ),
                warnings=[
                    local_runtime.health().message  # type: ignore[union-attr]
                ]
                if local_runtime is not None and local_runtime.health().message
                else None,
                details={
                    "selected": "openai_compatible",
                    "fallback_from": "bundled_local_text" if local_runtime is not None else None,
                },
            )
        if policy_mode == RuntimePolicyMode.REMOTE_ALLOWED:
            return _RuntimeSelection(
                runtime=remote_runtime,
                provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
                status_code=remote_health.status_code,
                reason_code=remote_health.reason_code,
                warnings=[remote_health.message] if remote_health.message else None,
                details={"selected": "openai_compatible"},
            )

    if local_runtime is not None:
        local_health = local_runtime.health()
        return _RuntimeSelection(
            runtime=None,
            provider_kind=RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
            status_code=local_health.status_code,
            reason_code=local_health.reason_code or "runtime_unavailable",
            warnings=[local_health.message] if local_health.message else None,
            details={"selected": "bundled_local_text", "health": local_health.model_dump(mode="python")},
        )

    return _RuntimeSelection(
        runtime=None,
        provider_kind=RuntimeProviderKind.OPENAI_COMPATIBLE,
        status_code="not_configured",
        reason_code="runtime_missing",
        details={"task": RuntimeTask.PI_AGENT.value},
    )


def _build_shared_local_runtime(
    *,
    task: RuntimeTask,
    config: Any,
    api_key_override: str | None,
) -> ModelRuntime | None:
    enabled = (
        bool(getattr(config, "local_text_model_enabled"))
        if getattr(config, "local_text_model_enabled", None) is not None
        else bool(getattr(config, "item_categorizer_enabled", False))
    )
    if not enabled:
        return None

    base_url = _normalize_text(getattr(config, "local_text_model_base_url", None)) or _normalize_text(
        getattr(config, "item_categorizer_base_url", None)
    )
    model_name = _normalize_text(getattr(config, "local_text_model_name", None)) or _normalize_text(
        getattr(config, "item_categorizer_model", None)
    ) or _DEFAULT_LOCAL_TEXT_MODEL
    if not base_url:
        return None

    timeout_s = (
        float(getattr(config, "local_text_model_timeout_s"))
        if getattr(config, "local_text_model_timeout_s", None) is not None
        else _default_local_timeout_s(config=config, task=task)
    )
    max_retries = (
        int(getattr(config, "local_text_model_max_retries"))
        if getattr(config, "local_text_model_max_retries", None) is not None
        else (
            int(getattr(config, "retry_attempts", 4) or 4)
            if task == RuntimeTask.PI_AGENT
            else int(getattr(config, "item_categorizer_max_retries", 0) or 0)
        )
    )
    allow_remote = (
        bool(getattr(config, "local_text_model_allow_remote"))
        if getattr(config, "local_text_model_allow_remote", None) is not None
        else bool(getattr(config, "item_categorizer_allow_remote", False))
    )

    return BundledLocalTextRuntimeAdapter(
        task=task,
        base_url=base_url,
        api_key=(
            api_key_override
            or get_local_text_model_api_key(config)
            or get_item_categorizer_api_key(config)
            or get_ai_oauth_access_token(config)
            or get_ai_api_key(config)
        ),
        model_name=model_name,
        timeout_s=timeout_s,
        max_retries=max_retries,
        allow_remote=allow_remote,
        allow_insecure_transport=bool(getattr(config, "allow_insecure_transport", False)),
    )


def _default_local_timeout_s(*, config: Any, task: RuntimeTask) -> float:
    if task == RuntimeTask.PI_AGENT:
        request_timeout_s = float(getattr(config, "request_timeout_s", 30.0) or 30.0)
        return max(request_timeout_s, 120.0)
    return float(getattr(config, "item_categorizer_timeout_s", 5.0) or 5.0)


def _build_remote_runtime(
    *,
    task: RuntimeTask,
    config: Any,
    api_key_override: str | None,
) -> ModelRuntime | None:
    base_url = _normalize_text(getattr(config, "ai_base_url", None))
    if not base_url:
        return None
    return OpenAICompatibleRuntimeAdapter(
        task=task,
        base_url=base_url,
        api_key=api_key_override or get_ai_oauth_access_token(config) or get_ai_api_key(config),
        model_name=_normalize_text(getattr(config, "ai_model", None)) or "gpt-5.2-codex",
        timeout_s=float(getattr(config, "request_timeout_s", 30.0) or 30.0),
        max_retries=int(getattr(config, "retry_attempts", 4) or 4),
        allow_remote=not is_local_endpoint(base_url),
        allow_insecure_transport=bool(getattr(config, "allow_insecure_transport", False)),
    )


def _missing_health(
    *,
    task: RuntimeTask,
    policy_mode: RuntimePolicyMode,
    provider_kind: RuntimeProviderKind | None,
    status_code: str,
    reason_code: str | None,
    details: dict[str, Any],
) -> RuntimeHealth:
    effective_provider = provider_kind or RuntimeProviderKind.BUNDLED_LOCAL_TEXT
    capabilities = RuntimeCapabilities(
        provider_kind=effective_provider,
        task=task,
        local=effective_provider == RuntimeProviderKind.BUNDLED_LOCAL_TEXT,
        allow_remote=False,
    )
    return RuntimeHealth(
        provider_kind=effective_provider,
        task=task,
        policy_mode=policy_mode,
        healthy=False,
        configured=False,
        ready=False,
        status_code=status_code,
        reason_code=reason_code,
        message="runtime is not configured",
        capabilities=capabilities,
        details=details,
    )


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
