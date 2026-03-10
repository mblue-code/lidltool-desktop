from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from lidltool.connectors.sdk.offer import (
    OfferActionName,
    OfferActionRequest,
    OfferActionResponse,
    validate_offer_action_request,
    validate_offer_action_response,
)
from lidltool.connectors.sdk.receipt import (
    ReceiptActionName,
    ReceiptActionRequest,
    ReceiptActionResponse,
    validate_receipt_action_request,
    validate_receipt_action_response,
)

RuntimeErrorCode = Literal[
    "launch_failure",
    "timeout",
    "protocol_violation",
    "malformed_response",
    "non_zero_exit",
    "canceled",
]
ConnectorActionName = ReceiptActionName | OfferActionName
ConnectorActionRequest = ReceiptActionRequest | OfferActionRequest
ConnectorActionResponse = ReceiptActionResponse | OfferActionResponse


class RuntimeEnvelopeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    source_id: str
    runtime_kind: str
    entrypoint: str | None = None
    action: ConnectorActionName
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    duration_ms: int | None = Field(default=None, ge=0)


class RuntimeErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: RuntimeErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class RuntimeRequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    request: ConnectorActionRequest
    metadata: RuntimeEnvelopeMetadata


class RuntimeResponseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    ok: bool = True
    response: ConnectorActionResponse | None = None
    error: RuntimeErrorPayload | None = None
    metadata: RuntimeEnvelopeMetadata | None = None

    @model_validator(mode="after")
    def _validate_state(self) -> RuntimeResponseEnvelope:
        if self.ok:
            if self.response is None:
                raise ValueError("successful runtime responses must include a connector response")
            if self.error is not None:
                raise ValueError("successful runtime responses must not include a runtime error")
        else:
            if self.error is None:
                raise ValueError("failed runtime responses must include a runtime error")
            if self.response is not None:
                raise ValueError("failed runtime responses must not include a connector response")
        return self


class RuntimeInvocationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    plugin_id: str
    source_id: str
    runtime_kind: str
    transport: str
    entrypoint: str | None = None
    action: ConnectorActionName
    duration_ms: int = Field(ge=0)
    exit_code: int | None = None
    timed_out: bool = False
    canceled: bool = False
    cleanup_attempted: bool = False
    stderr_excerpt: str | None = None
    stdout_excerpt: str | None = None
    response_ok: bool | None = None


_REQUEST_ADAPTER: TypeAdapter[ConnectorActionRequest] = TypeAdapter(ConnectorActionRequest)
_RESPONSE_ADAPTER: TypeAdapter[ConnectorActionResponse] = TypeAdapter(ConnectorActionResponse)
_REQUEST_ENVELOPE_ADAPTER: TypeAdapter[RuntimeRequestEnvelope] = TypeAdapter(RuntimeRequestEnvelope)
_RESPONSE_ENVELOPE_ADAPTER: TypeAdapter[RuntimeResponseEnvelope] = TypeAdapter(
    RuntimeResponseEnvelope
)


def new_request_id() -> str:
    return uuid4().hex


def build_runtime_request_envelope(
    *,
    plugin_id: str,
    source_id: str,
    runtime_kind: str,
    entrypoint: str | None,
    request: ConnectorActionRequest | dict[str, Any],
    request_id: str | None = None,
) -> RuntimeRequestEnvelope:
    validated_request = validate_connector_action_request(request)
    return RuntimeRequestEnvelope(
        request_id=request_id or new_request_id(),
        request=validated_request,
        metadata=RuntimeEnvelopeMetadata(
            plugin_id=plugin_id,
            source_id=source_id,
            runtime_kind=runtime_kind,
            entrypoint=entrypoint,
            action=validated_request.action,
        ),
    )


def build_runtime_success_response(
    *,
    request_id: str,
    plugin_id: str,
    source_id: str,
    runtime_kind: str,
    entrypoint: str | None,
    response: ConnectorActionResponse | dict[str, Any],
    duration_ms: int | None = None,
) -> RuntimeResponseEnvelope:
    validated_response = validate_connector_action_response(response)
    return RuntimeResponseEnvelope(
        request_id=request_id,
        ok=True,
        response=validated_response,
        metadata=RuntimeEnvelopeMetadata(
            plugin_id=plugin_id,
            source_id=source_id,
            runtime_kind=runtime_kind,
            entrypoint=entrypoint,
            action=validated_response.action,
            duration_ms=duration_ms,
        ),
    )


def build_runtime_error_response(
    *,
    request_id: str,
    plugin_id: str,
    source_id: str,
    runtime_kind: str,
    entrypoint: str | None,
    action: ConnectorActionName,
    error: RuntimeErrorPayload,
    duration_ms: int | None = None,
) -> RuntimeResponseEnvelope:
    return RuntimeResponseEnvelope(
        request_id=request_id,
        ok=False,
        error=error,
        metadata=RuntimeEnvelopeMetadata(
            plugin_id=plugin_id,
            source_id=source_id,
            runtime_kind=runtime_kind,
            entrypoint=entrypoint,
            action=action,
            duration_ms=duration_ms,
        ),
    )


def dump_runtime_envelope_json(
    envelope: RuntimeRequestEnvelope | RuntimeResponseEnvelope,
) -> str:
    return envelope.model_dump_json(exclude_none=True)


def parse_runtime_request_envelope(payload: str) -> RuntimeRequestEnvelope:
    return _REQUEST_ENVELOPE_ADAPTER.validate_json(payload)


def parse_runtime_response_envelope(payload: str) -> RuntimeResponseEnvelope:
    return _RESPONSE_ENVELOPE_ADAPTER.validate_json(payload)


def validate_runtime_response_request_match(
    *,
    request: RuntimeRequestEnvelope,
    response: RuntimeResponseEnvelope,
) -> ConnectorActionResponse:
    if response.request_id != request.request_id:
        raise ValueError(
            "runtime response request_id mismatch: "
            f"expected {request.request_id!r}, got {response.request_id!r}"
        )
    if response.response is None:
        raise ValueError("runtime response is missing connector payload")
    validated_response = validate_connector_action_response(response.response)
    if validated_response.action != request.request.action:
        raise ValueError(
            "runtime response action mismatch: "
            f"expected {request.request.action!r}, got {validated_response.action!r}"
        )
    return validated_response


def validate_connector_action_request(
    value: ConnectorActionRequest | Mapping[str, Any],
) -> ConnectorActionRequest:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="python")
    else:
        payload = dict(value)
    if payload.get("plugin_family") == "offer":
        return validate_offer_action_request(payload)
    return validate_receipt_action_request(payload)


def validate_connector_action_response(
    value: ConnectorActionResponse | Mapping[str, Any],
) -> ConnectorActionResponse:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="python")
    else:
        payload = dict(value)
    if payload.get("plugin_family") == "offer":
        return validate_offer_action_response(payload)
    return validate_receipt_action_response(payload)


def compact_json_excerpt(payload: str | None, *, limit: int = 400) -> str | None:
    if payload is None:
        return None
    text = payload.strip()
    if not text:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."
