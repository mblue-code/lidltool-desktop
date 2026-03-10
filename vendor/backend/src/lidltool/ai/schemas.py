from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

AI_MEDIATION_CONTRACT_VERSION = "1"

AiPolicyLevel = Literal["none", "extract_only", "limited_reasoning", "agentic_experimental"]
AiTaskType = Literal[
    "structured_extraction",
    "document_classification",
    "offer_flyer_parsing",
    "product_alias_matching",
    "schema_repair",
]
AiInputKind = Literal["raw_text", "sanitized_text", "artifact_ref"]
AiRequestSizeClass = Literal["small", "medium", "large"]
AiMediationErrorCode = Literal[
    "invalid_request",
    "unsupported_task",
    "policy_denied",
    "budget_exceeded",
    "payload_too_large",
    "provider_not_configured",
    "provider_failure",
    "timeout",
    "invalid_output",
    "artifact_unsupported",
]
AiSchemaType = Literal["object", "array", "string", "integer", "number", "boolean"]


class AiStructuredSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AiSchemaType
    description: str | None = None
    properties: dict[str, AiStructuredSchema] = Field(default_factory=dict)
    required: tuple[str, ...] = ()
    items: AiStructuredSchema | None = None
    enum: tuple[str, ...] = ()
    max_length: int | None = Field(default=None, ge=1)
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_shape(self) -> AiStructuredSchema:
        if self.type == "object":
            missing = set(self.required) - set(self.properties)
            if missing:
                raise ValueError(
                    f"required object fields must be declared in properties: {', '.join(sorted(missing))}"
                )
            if self.items is not None:
                raise ValueError("object schemas must not declare items")
        elif self.properties:
            raise ValueError("only object schemas may declare properties")

        if self.type == "array":
            if self.items is None:
                raise ValueError("array schemas must declare an items schema")
        elif self.items is not None:
            raise ValueError("only array schemas may declare items")

        if self.type not in {"string", "integer", "number", "boolean"} and self.enum:
            raise ValueError("enum is only supported for scalar schema types")
        if self.type != "string" and self.max_length is not None:
            raise ValueError("max_length is only supported for string schemas")
        if self.type != "array" and (self.min_items is not None or self.max_items is not None):
            raise ValueError("min_items and max_items are only supported for array schemas")
        if self.max_items is not None and self.min_items is not None and self.max_items < self.min_items:
            raise ValueError("max_items must be greater than or equal to min_items")
        return self


AiStructuredSchema.model_rebuild()


class AiInputPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AiInputKind
    text: str | None = None
    artifact_ref: str | None = None
    media_type: str | None = None
    file_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_part(self) -> AiInputPart:
        if self.kind in {"raw_text", "sanitized_text"}:
            if not isinstance(self.text, str) or not self.text.strip():
                raise ValueError("text inputs must include non-empty text")
            if self.artifact_ref is not None:
                raise ValueError("text inputs must not include artifact_ref")
        elif not isinstance(self.artifact_ref, str) or not self.artifact_ref.strip():
            raise ValueError("artifact_ref inputs must include a non-empty artifact_ref")

        if self.kind == "artifact_ref" and not self.media_type:
            raise ValueError("artifact_ref inputs must include media_type")
        return self


class AiMediationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    task_type: AiTaskType
    requested_policy_level: AiPolicyLevel = "extract_only"
    instructions: str | None = None
    output_schema: AiStructuredSchema
    inputs: list[AiInputPart]
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_request(self) -> AiMediationRequest:
        if not self.inputs:
            raise ValueError("AI mediation requests must include at least one input part")
        if self.instructions is not None and not self.instructions.strip():
            raise ValueError("instructions must be a non-empty string when provided")
        return self


class AiMediationError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: AiMediationErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AiUsageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)


class AiMediationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    request_size_class: AiRequestSizeClass
    duration_ms: int = Field(ge=0)
    redaction_applied: bool = False
    usage: AiUsageMetadata = Field(default_factory=AiUsageMetadata)


class AiMediationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    request_id: str
    ok: bool
    task_type: AiTaskType
    policy_level: AiPolicyLevel
    output: Any | None = None
    error: AiMediationError | None = None
    warnings: tuple[str, ...] = ()
    metadata: AiMediationMetadata | None = None

    @model_validator(mode="after")
    def _validate_state(self) -> AiMediationResponse:
        if self.ok:
            if self.output is None:
                raise ValueError("successful AI mediation responses must include output")
            if self.error is not None:
                raise ValueError("successful AI mediation responses must not include error")
        else:
            if self.error is None:
                raise ValueError("failed AI mediation responses must include error")
            if self.output is not None:
                raise ValueError("failed AI mediation responses must not include output")
        return self


_REQUEST_ADAPTER: TypeAdapter[AiMediationRequest] = TypeAdapter(AiMediationRequest)
_RESPONSE_ADAPTER: TypeAdapter[AiMediationResponse] = TypeAdapter(AiMediationResponse)


def validate_ai_mediation_request(
    payload: AiMediationRequest | Mapping[str, Any],
) -> AiMediationRequest:
    if isinstance(payload, AiMediationRequest):
        return payload
    return _REQUEST_ADAPTER.validate_python(payload)


def validate_ai_mediation_response(
    payload: AiMediationResponse | Mapping[str, Any],
) -> AiMediationResponse:
    if isinstance(payload, AiMediationResponse):
        return payload
    return _RESPONSE_ADAPTER.validate_python(payload)


def estimate_request_text_bytes(request: AiMediationRequest) -> int:
    total = len((request.instructions or "").encode("utf-8"))
    for part in request.inputs:
        if part.text is not None:
            total += len(part.text.encode("utf-8"))
        if part.artifact_ref is not None:
            total += len(part.artifact_ref.encode("utf-8"))
    return total


def classify_request_size(request: AiMediationRequest) -> AiRequestSizeClass:
    size = estimate_request_text_bytes(request)
    if size <= 4_096:
        return "small"
    if size <= 32_768:
        return "medium"
    return "large"


def validate_structured_output(*, schema: AiStructuredSchema, value: Any, path: str = "$") -> None:
    if schema.type == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        extra_keys = set(value) - set(schema.properties)
        if extra_keys:
            raise ValueError(f"{path} contains unexpected fields: {', '.join(sorted(extra_keys))}")
        missing_keys = set(schema.required) - set(value)
        if missing_keys:
            raise ValueError(f"{path} is missing required fields: {', '.join(sorted(missing_keys))}")
        for key, property_schema in schema.properties.items():
            if key in value:
                validate_structured_output(
                    schema=property_schema,
                    value=value[key],
                    path=f"{path}.{key}",
                )
        return

    if schema.type == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        if schema.min_items is not None and len(value) < schema.min_items:
            raise ValueError(f"{path} must contain at least {schema.min_items} items")
        if schema.max_items is not None and len(value) > schema.max_items:
            raise ValueError(f"{path} must contain at most {schema.max_items} items")
        if schema.items is None:
            raise ValueError(f"{path} array schema is missing items")
        for index, item in enumerate(value):
            validate_structured_output(
                schema=schema.items,
                value=item,
                path=f"{path}[{index}]",
            )
        return

    if schema.type == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
        if schema.max_length is not None and len(value) > schema.max_length:
            raise ValueError(f"{path} must be at most {schema.max_length} characters")
        if schema.enum and value not in schema.enum:
            raise ValueError(f"{path} must be one of: {', '.join(schema.enum)}")
        return

    if schema.type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path} must be an integer")
        if schema.enum and str(value) not in schema.enum:
            raise ValueError(f"{path} must be one of: {', '.join(schema.enum)}")
        return

    if schema.type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ValueError(f"{path} must be a number")
        return

    if schema.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be a boolean")
        return

    raise ValueError(f"{path} uses unsupported schema type {schema.type!r}")
