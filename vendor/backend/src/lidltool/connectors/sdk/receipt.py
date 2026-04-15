from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.version import RECEIPT_CONNECTOR_CONTRACT_VERSION

ReceiptActionName = Literal[
    "get_manifest",
    "healthcheck",
    "get_auth_status",
    "start_auth",
    "cancel_auth",
    "confirm_auth",
    "discover_records",
    "fetch_record",
    "normalize_record",
    "extract_discounts",
    "get_diagnostics",
]
AuthLifecycleAction = Literal["start_auth", "cancel_auth", "confirm_auth"]
AuthStatusState = Literal[
    "authenticated",
    "requires_auth",
    "pending",
    "expired",
    "not_supported",
    "unknown",
]
AuthFlowStatus = Literal["started", "pending", "confirmed", "canceled", "not_supported", "no_op"]
ConnectorErrorCode = Literal[
    "invalid_request",
    "unsupported_action",
    "auth_required",
    "upstream_error",
    "contract_violation",
    "internal_error",
]


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ConnectorErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class RecordReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_ref: str
    discovered_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedReceiptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int = Field(ge=1)
    name: str
    qty: str
    unit: str | None = None
    unit_price_cents: int | None = None
    line_total_cents: int
    is_deposit: bool | None = None
    vat_rate: str | None = None
    category: str | None = None
    source_item_id: str | None = None
    discounts: list[dict[str, Any]] = Field(default_factory=list)


class NormalizedReceiptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    purchased_at: datetime
    date_source: str | None = None
    page_year: int | None = None
    store_id: str
    store_name: str
    store_address: str | None = None
    total_gross_cents: int
    currency: str
    discount_total_cents: int = 0
    fingerprint: str
    items: list[NormalizedReceiptItem]
    raw_json: dict[str, Any]

    @model_validator(mode="after")
    def _validate_items(self) -> NormalizedReceiptRecord:
        if not self.items:
            raise ValueError("normalized receipt record must contain at least one item")
        return self


class NormalizedDiscountRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int | None = Field(default=None, ge=1)
    type: str
    promotion_id: str | None = None
    amount_cents: int = Field(ge=1)
    label: str
    scope: Literal["item", "transaction"] = "item"
    subkind: str | None = None
    funded_by: str | None = None


class GetManifestOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: ConnectorManifest


class HealthcheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthy: bool
    detail: str | None = None
    sample_size: int | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class GetAuthStatusOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AuthStatusState
    is_authenticated: bool
    available_actions: tuple[AuthLifecycleAction, ...] = ()
    implemented_actions: tuple[AuthLifecycleAction, ...] = ()
    compatibility_actions: tuple[AuthLifecycleAction, ...] = ()
    reserved_actions: tuple[AuthLifecycleAction, ...] = ("start_auth", "cancel_auth", "confirm_auth")
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthLifecycleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AuthFlowStatus
    detail: str | None = None
    flow_id: str | None = None
    next_poll_after_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoverRecordsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    full_sync: bool = False
    window_start: datetime | None = None
    window_end: datetime | None = None


class DiscoverRecordsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[RecordReference]
    next_cursor: str | None = None


class FetchRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_ref: str


class FetchRecordOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_ref: str
    record: dict[str, Any]


class NormalizeRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: dict[str, Any]


class NormalizeRecordOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_record: NormalizedReceiptRecord


class ExtractDiscountsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: dict[str, Any]


class ExtractDiscountsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discounts: list[NormalizedDiscountRow]


class DiagnosticsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ReceiptActionRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = RECEIPT_CONNECTOR_CONTRACT_VERSION
    plugin_family: Literal["receipt"] = "receipt"


class GetManifestRequest(ReceiptActionRequestBase):
    action: Literal["get_manifest"] = "get_manifest"
    input: EmptyInput = Field(default_factory=EmptyInput)


class HealthcheckRequest(ReceiptActionRequestBase):
    action: Literal["healthcheck"] = "healthcheck"
    input: EmptyInput = Field(default_factory=EmptyInput)


class GetAuthStatusRequest(ReceiptActionRequestBase):
    action: Literal["get_auth_status"] = "get_auth_status"
    input: EmptyInput = Field(default_factory=EmptyInput)


class StartAuthRequest(ReceiptActionRequestBase):
    action: Literal["start_auth"] = "start_auth"
    input: EmptyInput = Field(default_factory=EmptyInput)


class CancelAuthRequest(ReceiptActionRequestBase):
    action: Literal["cancel_auth"] = "cancel_auth"
    input: EmptyInput = Field(default_factory=EmptyInput)


class ConfirmAuthRequest(ReceiptActionRequestBase):
    action: Literal["confirm_auth"] = "confirm_auth"
    input: EmptyInput = Field(default_factory=EmptyInput)


class DiscoverRecordsRequest(ReceiptActionRequestBase):
    action: Literal["discover_records"] = "discover_records"
    input: DiscoverRecordsInput = Field(default_factory=DiscoverRecordsInput)


class FetchRecordRequest(ReceiptActionRequestBase):
    action: Literal["fetch_record"] = "fetch_record"
    input: FetchRecordInput


class NormalizeRecordRequest(ReceiptActionRequestBase):
    action: Literal["normalize_record"] = "normalize_record"
    input: NormalizeRecordInput


class ExtractDiscountsRequest(ReceiptActionRequestBase):
    action: Literal["extract_discounts"] = "extract_discounts"
    input: ExtractDiscountsInput


class GetDiagnosticsRequest(ReceiptActionRequestBase):
    action: Literal["get_diagnostics"] = "get_diagnostics"
    input: EmptyInput = Field(default_factory=EmptyInput)


ReceiptActionRequest = (
    GetManifestRequest
    | HealthcheckRequest
    | GetAuthStatusRequest
    | StartAuthRequest
    | CancelAuthRequest
    | ConfirmAuthRequest
    | DiscoverRecordsRequest
    | FetchRecordRequest
    | NormalizeRecordRequest
    | ExtractDiscountsRequest
    | GetDiagnosticsRequest
)


class ReceiptActionResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = RECEIPT_CONNECTOR_CONTRACT_VERSION
    plugin_family: Literal["receipt"] = "receipt"
    ok: bool = True
    warnings: tuple[str, ...] = ()
    error: ConnectorError | None = None

    @model_validator(mode="after")
    def _validate_result_state(self) -> ReceiptActionResponseBase:
        if self.ok and self.error is not None:
            raise ValueError("successful connector responses must not include an error payload")
        if not self.ok and self.error is None:
            raise ValueError("failed connector responses must include an error payload")
        return self


class GetManifestResponse(ReceiptActionResponseBase):
    action: Literal["get_manifest"] = "get_manifest"
    output: GetManifestOutput | None = None


class HealthcheckResponse(ReceiptActionResponseBase):
    action: Literal["healthcheck"] = "healthcheck"
    output: HealthcheckOutput | None = None


class GetAuthStatusResponse(ReceiptActionResponseBase):
    action: Literal["get_auth_status"] = "get_auth_status"
    output: GetAuthStatusOutput | None = None


class StartAuthResponse(ReceiptActionResponseBase):
    action: Literal["start_auth"] = "start_auth"
    output: AuthLifecycleOutput | None = None


class CancelAuthResponse(ReceiptActionResponseBase):
    action: Literal["cancel_auth"] = "cancel_auth"
    output: AuthLifecycleOutput | None = None


class ConfirmAuthResponse(ReceiptActionResponseBase):
    action: Literal["confirm_auth"] = "confirm_auth"
    output: AuthLifecycleOutput | None = None


class DiscoverRecordsResponse(ReceiptActionResponseBase):
    action: Literal["discover_records"] = "discover_records"
    output: DiscoverRecordsOutput | None = None


class FetchRecordResponse(ReceiptActionResponseBase):
    action: Literal["fetch_record"] = "fetch_record"
    output: FetchRecordOutput | None = None


class NormalizeRecordResponse(ReceiptActionResponseBase):
    action: Literal["normalize_record"] = "normalize_record"
    output: NormalizeRecordOutput | None = None


class ExtractDiscountsResponse(ReceiptActionResponseBase):
    action: Literal["extract_discounts"] = "extract_discounts"
    output: ExtractDiscountsOutput | None = None


class GetDiagnosticsResponse(ReceiptActionResponseBase):
    action: Literal["get_diagnostics"] = "get_diagnostics"
    output: DiagnosticsOutput | None = None


ReceiptActionResponse = (
    GetManifestResponse
    | HealthcheckResponse
    | GetAuthStatusResponse
    | StartAuthResponse
    | CancelAuthResponse
    | ConfirmAuthResponse
    | DiscoverRecordsResponse
    | FetchRecordResponse
    | NormalizeRecordResponse
    | ExtractDiscountsResponse
    | GetDiagnosticsResponse
)

_REQUEST_ADAPTER: TypeAdapter[ReceiptActionRequest] = TypeAdapter(ReceiptActionRequest)
_RESPONSE_ADAPTER: TypeAdapter[ReceiptActionResponse] = TypeAdapter(ReceiptActionResponse)


def validate_receipt_action_request(
    value: ReceiptActionRequest | Mapping[str, Any],
) -> ReceiptActionRequest:
    if isinstance(value, BaseModel):
        return _REQUEST_ADAPTER.validate_python(value.model_dump(mode="python"))
    return _REQUEST_ADAPTER.validate_python(value)


def validate_receipt_action_response(
    value: ReceiptActionResponse | Mapping[str, Any],
) -> ReceiptActionResponse:
    if isinstance(value, BaseModel):
        return _RESPONSE_ADAPTER.validate_python(value.model_dump(mode="python"))
    return _RESPONSE_ADAPTER.validate_python(value)


@runtime_checkable
class ReceiptConnector(Protocol):
    def invoke_action(
        self,
        request: ReceiptActionRequest | Mapping[str, Any],
    ) -> ReceiptActionResponse | Mapping[str, Any]:
        ...
