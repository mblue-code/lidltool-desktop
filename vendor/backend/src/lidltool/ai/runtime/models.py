from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeTask(str, Enum):
    ITEM_CATEGORIZATION = "item_categorization"
    PI_AGENT = "pi_agent"
    OCR_TEXT_FALLBACK = "ocr_text_fallback"


class RuntimePolicyMode(str, Enum):
    LOCAL_ONLY = "local_only"
    LOCAL_PREFERRED = "local_preferred"
    REMOTE_ALLOWED = "remote_allowed"


class RuntimeProviderKind(str, Enum):
    BUNDLED_LOCAL_TEXT = "bundled_local_text"
    OPENAI_COMPATIBLE = "openai_compatible"


class RuntimeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_message(self) -> RuntimeMessage:
        if not self.role.strip():
            raise ValueError("message role must be non-empty")
        if not self.content.strip():
            raise ValueError("message content must be non-empty")
        return self


class RuntimeCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_kind: RuntimeProviderKind
    task: RuntimeTask
    model_name: str | None = None
    base_url: str | None = None
    local: bool = False
    json_completion: bool = True
    chat_completion: bool = True
    structured_output: bool = True
    streaming: bool = False
    max_batch_size: int | None = None
    allow_remote: bool = False


class RuntimeHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_kind: RuntimeProviderKind
    task: RuntimeTask
    policy_mode: RuntimePolicyMode
    healthy: bool
    configured: bool
    ready: bool
    status_code: str
    reason_code: str | None = None
    message: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    capabilities: RuntimeCapabilities
    checked_at_unix_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class JsonCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: RuntimeTask
    model_name: str
    system_prompt: str
    user_text: str | None = None
    user_json: Any | None = None
    messages: list[RuntimeMessage] = Field(default_factory=list)
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_s: float | None = None
    max_retries: int | None = None
    strict_json: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_request(self) -> JsonCompletionRequest:
        if not self.system_prompt.strip():
            raise ValueError("system_prompt must be non-empty")
        if self.user_text is None and self.user_json is None and not self.messages:
            raise ValueError("json completion requests need user text, JSON input, or messages")
        return self


class JsonCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: RuntimeTask
    provider_kind: RuntimeProviderKind
    model_name: str
    raw_text: str
    data: Any | None = None
    finish_reason: str | None = None
    latency_ms: int = Field(ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: RuntimeTask
    model_name: str
    messages: list[RuntimeMessage]
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_s: float | None = None
    max_retries: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_request(self) -> ChatCompletionRequest:
        if not self.messages:
            raise ValueError("chat completion requests need at least one message")
        return self


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: RuntimeTask
    provider_kind: RuntimeProviderKind
    model_name: str
    text: str
    finish_reason: str | None = None
    latency_ms: int = Field(ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: RuntimeTask
    model_name: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_s: float | None = None
    max_retries: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_request(self) -> StreamChatRequest:
        if not self.messages:
            raise ValueError("stream chat requests need at least one message")
        return self


class StreamChatEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    content_index: int | None = None
    delta: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    reason: str | None = None
    usage: dict[str, int | float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: RuntimeTask
    policy_mode: RuntimePolicyMode
    provider_kind: RuntimeProviderKind | None = None
    status_code: str
    reason_code: str | None = None
    selected: bool = False
    runtime: Any | None = Field(default=None, exclude=True, repr=False)
    health: RuntimeHealth | None = None
    capabilities: RuntimeCapabilities | None = None
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ModelRuntime(Protocol):
    task: RuntimeTask
    provider_kind: RuntimeProviderKind
    model_name: str | None

    def health(self) -> RuntimeHealth:
        ...

    def capabilities(self) -> RuntimeCapabilities:
        ...

    def complete_json(self, request: JsonCompletionRequest) -> JsonCompletionResponse:
        ...

    def complete_chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        ...

    def stream_chat(self, request: StreamChatRequest) -> Any:
        ...


def _mapping_or_model_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"expected mapping or BaseModel, got {type(value)!r}")
