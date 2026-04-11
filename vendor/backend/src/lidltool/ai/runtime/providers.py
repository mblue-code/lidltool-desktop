from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from lidltool.ai.runtime.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    JsonCompletionRequest,
    JsonCompletionResponse,
    ModelRuntime,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeMessage,
    RuntimePolicyMode,
    RuntimeProviderKind,
    StreamChatEvent,
    StreamChatRequest,
    RuntimeTask,
)

LOGGER = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
_MODEL_RESPONSE_JSON_RE = re.compile(r"```(?:json)?\s*(?P<body>\{.*\})\s*```", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class _RuntimeConfig:
    base_url: str | None
    api_key: str | None
    model_name: str | None
    timeout_s: float | None
    max_retries: int | None
    allow_remote: bool
    allow_insecure_transport: bool
    local: bool


def normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def is_local_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.strip().lower()
    if normalized in _LOCAL_HOSTS or normalized.endswith(".local"):
        return True
    if "." not in normalized:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def is_local_endpoint(base_url: str | None) -> bool:
    parsed = urlparse(base_url or "")
    return is_local_hostname(parsed.hostname)


def validate_runtime_endpoint(
    *,
    base_url: str | None,
    allow_remote: bool,
    allow_insecure_transport: bool,
    purpose: str,
) -> str:
    normalized = normalize_base_url(base_url)
    if not normalized:
        raise RuntimeError(f"{purpose} base_url is not configured")
    parsed = urlparse(normalized)
    if not parsed.scheme:
        raise RuntimeError(f"{purpose} base_url must include a URL scheme")
    hostname = parsed.hostname or ""
    local = is_local_hostname(hostname)
    if parsed.scheme.lower() != "https" and not (allow_insecure_transport or local):
        raise RuntimeError(
            f"{purpose} base_url must use https "
            "(set LIDLTOOL_ALLOW_INSECURE_TRANSPORT=true only for local testing)"
        )
    if not allow_remote and not local:
        raise RuntimeError(
            f"{purpose} base_url must point to a local/private endpoint unless remote usage is allowed"
        )
    return normalized


def parse_completion_text(text: str) -> Any:
    stripped = _THINK_TAG_RE.sub("", text).strip()
    fenced = _MODEL_RESPONSE_JSON_RE.search(stripped)
    if fenced is not None:
        stripped = fenced.group("body").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        candidate = _extract_json_object_candidate(stripped)
        if candidate is not None:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        raise RuntimeError("runtime returned invalid JSON") from exc


def coerce_completion_text(response: object) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("runtime response did not include choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
                continue
            if isinstance(item, dict):
                raw_text = item.get("text")
                if isinstance(raw_text, str) and raw_text.strip():
                    chunks.append(raw_text.strip())
        joined = "\n".join(chunks).strip()
        if joined:
            return joined
    raise RuntimeError("runtime response did not include text content")


def _extract_json_object_candidate(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _message_dicts(messages: list[RuntimeMessage]) -> list[dict[str, Any]]:
    return [{"role": message.role, "content": message.content} for message in messages]


class OpenAICompatibleRuntimeAdapter(ModelRuntime):
    def __init__(
        self,
        *,
        task: RuntimeTask,
        base_url: str | None,
        api_key: str | None,
        model_name: str | None,
        timeout_s: float | None,
        max_retries: int | None,
        allow_remote: bool,
        allow_insecure_transport: bool = False,
    ) -> None:
        self.task = task
        self.provider_kind = RuntimeProviderKind.OPENAI_COMPATIBLE
        self.base_url = normalize_base_url(base_url)
        self.api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        self.model_name = model_name.strip() if isinstance(model_name, str) and model_name.strip() else None
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.allow_remote = allow_remote
        self.allow_insecure_transport = allow_insecure_transport
        self._configured = bool(self.base_url and self.model_name)
        self._local = is_local_endpoint(self.base_url)
        self._capabilities = RuntimeCapabilities(
            provider_kind=self.provider_kind,
            task=self.task,
            model_name=self.model_name,
            base_url=self.base_url,
            local=self._local,
            json_completion=True,
            chat_completion=True,
            structured_output=True,
            streaming=True,
            allow_remote=self.allow_remote,
        )

    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    def health(self) -> RuntimeHealth:
        status_code = "ready" if self._configured else "not_configured"
        reason_code = None
        message = None
        healthy = self._configured
        if not self._configured:
            message = "runtime is not fully configured"
        try:
            validate_runtime_endpoint(
                base_url=self.base_url,
                allow_remote=self.allow_remote,
                allow_insecure_transport=self.allow_insecure_transport,
                purpose=f"{self.provider_kind.value}.{self.task.value}",
            )
        except Exception as exc:  # noqa: BLE001
            healthy = False
            status_code = "endpoint_blocked"
            reason_code = "endpoint_validation_failed"
            message = str(exc)
        return RuntimeHealth(
            provider_kind=self.provider_kind,
            task=self.task,
            policy_mode=RuntimePolicyMode.REMOTE_ALLOWED if self.allow_remote else RuntimePolicyMode.LOCAL_PREFERRED,
            healthy=healthy,
            configured=self._configured,
            ready=healthy,
            status_code=status_code,
            reason_code=reason_code,
            message=message,
            base_url=self.base_url,
            model_name=self.model_name,
            capabilities=self._capabilities,
            checked_at_unix_ms=int(time.time() * 1000),
        )

    def complete_json(self, request: JsonCompletionRequest) -> JsonCompletionResponse:
        started = time.perf_counter()
        self._assert_ready(request.task)
        payload_messages = self._build_json_messages(request)
        response = self._call_chat_completion(
            request=request,
            messages=payload_messages,
            response_label="json",
        )
        raw_text = coerce_completion_text(response)
        data = parse_completion_text(raw_text)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = _usage_dict(response)
        result = JsonCompletionResponse(
            task=request.task,
            provider_kind=self.provider_kind,
            model_name=self.model_name or request.model_name,
            raw_text=raw_text,
            data=data,
            finish_reason=_finish_reason(response),
            latency_ms=latency_ms,
            usage=usage,
            request_id=str(getattr(response, "id", "") or "") or None,
            metadata=dict(request.metadata),
        )
        LOGGER.info(
            "runtime.json_completion.success task=%s provider=%s model=%s latency_ms=%s local=%s",
            request.task.value,
            self.provider_kind.value,
            result.model_name,
            result.latency_ms,
            self._local,
        )
        return result

    def complete_chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        started = time.perf_counter()
        self._assert_ready(request.task)
        response = self._call_chat_completion(
            request=request,
            messages=_message_dicts(request.messages),
            response_label="chat",
        )
        raw_text = coerce_completion_text(response)
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = ChatCompletionResponse(
            task=request.task,
            provider_kind=self.provider_kind,
            model_name=self.model_name or request.model_name,
            text=raw_text,
            finish_reason=_finish_reason(response),
            latency_ms=latency_ms,
            usage=_usage_dict(response),
            request_id=str(getattr(response, "id", "") or "") or None,
            metadata=dict(request.metadata),
        )
        LOGGER.info(
            "runtime.chat_completion.success task=%s provider=%s model=%s latency_ms=%s local=%s",
            request.task.value,
            self.provider_kind.value,
            result.model_name,
            result.latency_ms,
            self._local,
        )
        return result

    async def stream_chat(self, request: StreamChatRequest):
        self._assert_ready(request.task)
        try:
            from openai import AsyncOpenAI
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"openai SDK is unavailable: {exc}") from exc

        effective_timeout = request.timeout_s or self.timeout_s
        client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "local-token",
            timeout=effective_timeout,
            max_retries=request.max_retries if request.max_retries is not None else self.max_retries,
        )
        try:
            create_kwargs: dict[str, Any] = {
                "model": request.model_name,
                "messages": request.messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": True,
            }
            if not self._local:
                create_kwargs["stream_options"] = {"include_usage": True}
            effective_tools = request.tools
            if effective_tools:
                create_kwargs["tools"] = effective_tools
                create_kwargs["tool_choice"] = "auto"
            timeout_context = (
                asyncio.timeout(effective_timeout) if effective_timeout and effective_timeout > 0 else None
            )
            if timeout_context is None:
                stream = await client.chat.completions.create(**create_kwargs)
                async for event in self._iter_stream_events(stream):
                    yield event
            else:
                async with timeout_context:
                    stream = await client.chat.completions.create(**create_kwargs)
                    async for event in self._iter_stream_events(stream):
                        yield event
        except TimeoutError as exc:
            raise RuntimeError("runtime stream timed out") from exc
        finally:
            close_method = getattr(client, "close", None)
            if callable(close_method):
                maybe_awaitable = close_method()
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable

    async def _iter_stream_events(self, stream: Any):
        yield StreamChatEvent(type="start")
        yield StreamChatEvent(type="text_start", content_index=0)
        active_tool_indexes: set[int] = set()
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        finish_reason = "stop"
        async for chunk in stream:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                input_tokens = int(getattr(chunk_usage, "prompt_tokens", 0) or 0)
                output_tokens = int(getattr(chunk_usage, "completion_tokens", 0) or 0)
                total_tokens = int(getattr(chunk_usage, "total_tokens", 0) or 0)
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            if choice.finish_reason:
                finish_reason = str(choice.finish_reason)
            delta = choice.delta
            if getattr(delta, "content", None):
                yield StreamChatEvent(
                    type="text_delta",
                    content_index=0,
                    delta=str(delta.content),
                )
            tool_calls = getattr(delta, "tool_calls", None) or []
            for tool_call in tool_calls:
                index = int(getattr(tool_call, "index", 0) or 0)
                content_index = 1 + index
                tool_call_id = str(getattr(tool_call, "id", "") or f"toolcall_{index}")
                function_obj = getattr(tool_call, "function", None)
                function_name = str(getattr(function_obj, "name", "") or "") if function_obj else ""
                arguments_delta = (
                    str(getattr(function_obj, "arguments", "") or "")
                    if function_obj
                    else ""
                )
                if index not in active_tool_indexes:
                    active_tool_indexes.add(index)
                    yield StreamChatEvent(
                        type="toolcall_start",
                        content_index=content_index,
                        tool_call_id=tool_call_id,
                        tool_name=function_name,
                    )
                if arguments_delta:
                    yield StreamChatEvent(
                        type="toolcall_delta",
                        content_index=content_index,
                        delta=arguments_delta,
                    )
            if choice.finish_reason == "tool_calls":
                for index in sorted(active_tool_indexes):
                    yield StreamChatEvent(type="toolcall_end", content_index=1 + index)
                active_tool_indexes.clear()
        for index in sorted(active_tool_indexes):
            yield StreamChatEvent(type="toolcall_end", content_index=1 + index)
        yield StreamChatEvent(type="text_end", content_index=0)
        normalized_total = total_tokens or (input_tokens + output_tokens)
        normalized_reason = (
            "toolUse"
            if finish_reason == "tool_calls"
            else "length"
            if finish_reason == "length"
            else "stop"
        )
        yield StreamChatEvent(
            type="done",
            reason=normalized_reason,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": normalized_total,
                "cost": None,
            },
        )

    def _assert_ready(self, task: RuntimeTask) -> None:
        if task != self.task:
            LOGGER.warning(
                "runtime.task_mismatch selected_task=%s requested_task=%s provider=%s",
                self.task.value,
                task.value,
                self.provider_kind.value,
            )
        if not self._configured:
            raise RuntimeError("runtime is not configured")
        validate_runtime_endpoint(
            base_url=self.base_url,
            allow_remote=self.allow_remote,
            allow_insecure_transport=self.allow_insecure_transport,
            purpose=f"{self.provider_kind.value}.{self.task.value}",
        )

    def _build_json_messages(self, request: JsonCompletionRequest) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": request.system_prompt}]
        messages.extend(_message_dicts(request.messages))
        if request.user_json is not None:
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(request.user_json, ensure_ascii=False, separators=(",", ":")),
                }
            )
        elif request.user_text is not None:
            messages.append({"role": "user", "content": request.user_text})
        return messages

    def _call_chat_completion(
        self,
        *,
        request: JsonCompletionRequest | ChatCompletionRequest,
        messages: list[dict[str, Any]],
        response_label: str,
    ) -> object:
        try:
            from openai import OpenAI
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"openai SDK is unavailable: {exc}") from exc

        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "local-token",
            timeout=request.timeout_s or self.timeout_s,
            max_retries=request.max_retries if request.max_retries is not None else self.max_retries,
        )
        create_kwargs: dict[str, Any] = {
            "model": request.model_name,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": messages,
        }
        if isinstance(request, JsonCompletionRequest):
            create_kwargs["response_format"] = {"type": "json_object"}
            if self._local:
                create_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        try:
            completion = client.chat.completions.create(**create_kwargs)
        except Exception as exc:  # noqa: BLE001
            if isinstance(request, JsonCompletionRequest) and self._local and create_kwargs.get("extra_body") is not None:
                LOGGER.info(
                    "runtime.%s_completion.retry_without_disable_thinking task=%s provider=%s model=%s error=%s",
                    response_label,
                    request.task.value,
                    self.provider_kind.value,
                    request.model_name,
                    exc,
                )
                create_kwargs.pop("extra_body", None)
                try:
                    completion = client.chat.completions.create(**create_kwargs)
                except Exception as retry_exc:  # noqa: BLE001
                    LOGGER.warning(
                        "runtime.%s_completion.error task=%s provider=%s model=%s error=%s",
                        response_label,
                        request.task.value,
                        self.provider_kind.value,
                        request.model_name,
                        retry_exc,
                    )
                    raise
                return completion
            LOGGER.warning(
                "runtime.%s_completion.error task=%s provider=%s model=%s error=%s",
                response_label,
                request.task.value,
                self.provider_kind.value,
                request.model_name,
                exc,
            )
            raise
        return completion


class BundledLocalTextRuntimeAdapter(OpenAICompatibleRuntimeAdapter):
    def __init__(
        self,
        *,
        task: RuntimeTask,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        allow_remote: bool = False,
        allow_insecure_transport: bool = False,
    ) -> None:
        resolved_base_url = normalize_base_url(base_url) or "http://item-categorizer:8000/v1"
        super().__init__(
            task=task,
            base_url=resolved_base_url,
            api_key=api_key,
            model_name=model_name or "qwen3.5:0.8b",
            timeout_s=timeout_s,
            max_retries=max_retries,
            allow_remote=allow_remote,
            allow_insecure_transport=allow_insecure_transport,
        )
        self.provider_kind = RuntimeProviderKind.BUNDLED_LOCAL_TEXT
        self._local = True
        self._capabilities = RuntimeCapabilities(
            provider_kind=self.provider_kind,
            task=self.task,
            model_name=self.model_name,
            base_url=self.base_url,
            local=True,
            json_completion=True,
            chat_completion=True,
            structured_output=True,
            streaming=False,
            allow_remote=False,
        )

    def health(self) -> RuntimeHealth:
        health = super().health()
        return health.model_copy(
            update={
                "provider_kind": self.provider_kind,
                "policy_mode": RuntimePolicyMode.LOCAL_PREFERRED,
                "capabilities": self._capabilities,
            }
        )


def _finish_reason(response: object) -> str | None:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    finish_reason = getattr(choices[0], "finish_reason", None)
    return str(finish_reason) if finish_reason is not None else None


def _usage_dict(response: object) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output": int(getattr(usage, "completion_tokens", 0) or 0),
        "totalTokens": int(getattr(usage, "total_tokens", 0) or 0),
    }
