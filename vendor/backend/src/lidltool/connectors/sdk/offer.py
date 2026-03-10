from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import ConnectorError, EmptyInput
from lidltool.connectors.sdk.version import OFFER_CONNECTOR_CONTRACT_VERSION

OfferActionName = Literal[
    "get_manifest",
    "healthcheck",
    "discover_offers",
    "fetch_offer_detail",
    "normalize_offer",
    "get_offer_scope",
    "get_offer_diagnostics",
]


class OfferReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_ref: str
    discovered_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OfferScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: str
    region_code: str | None = None
    store_id: str | None = None
    store_name: str | None = None

    @field_validator("country_code")
    @classmethod
    def _normalize_country_code(cls, value: str) -> str:
        candidate = value.strip().upper()
        if len(candidate) != 2 or not candidate.isalpha():
            raise ValueError("country_code must be a two-letter ISO country code")
        return candidate


class NormalizedOfferItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int = Field(ge=1)
    title: str
    source_item_id: str | None = None
    brand: str | None = None
    canonical_product_id: str | None = None
    gtin_ean: str | None = None
    alias_candidates: tuple[str, ...] = ()
    quantity_text: str | None = None
    unit: str | None = None
    size_text: str | None = None
    price_cents: int | None = Field(default=None, ge=0)
    original_price_cents: int | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    bundle_terms: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alias_candidates", mode="before")
    @classmethod
    def _normalize_alias_candidates(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("alias_candidates must be a list or tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("alias_candidates entries must be strings")
            candidate = item.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_pricing(self) -> NormalizedOfferItem:
        if (
            self.price_cents is not None
            and self.original_price_cents is not None
            and self.price_cents > self.original_price_cents
        ):
            raise ValueError("price_cents must be less than or equal to original_price_cents")
        return self


class NormalizedOfferRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_offer_id: str
    fingerprint: str
    merchant_name: str
    merchant_id: str | None = None
    title: str
    summary: str | None = None
    offer_type: Literal["sale", "bundle", "multibuy", "coupon", "loyalty", "markdown", "unknown"] = (
        "unknown"
    )
    validity_start: datetime
    validity_end: datetime
    currency: str
    price_cents: int | None = Field(default=None, ge=0)
    original_price_cents: int | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    bundle_terms: str | None = None
    offer_url: str | None = None
    image_url: str | None = None
    scope: OfferScope
    items: list[NormalizedOfferItem]
    raw_payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        candidate = value.strip().upper()
        if len(candidate) != 3 or not candidate.isalpha():
            raise ValueError("currency must be a three-letter alphabetic code")
        return candidate

    @model_validator(mode="after")
    def _validate_offer(self) -> NormalizedOfferRecord:
        if self.validity_end < self.validity_start:
            raise ValueError("validity_end must be greater than or equal to validity_start")
        if not self.items:
            raise ValueError("normalized offer must contain at least one item")
        if (
            self.price_cents is not None
            and self.original_price_cents is not None
            and self.price_cents > self.original_price_cents
        ):
            raise ValueError("price_cents must be less than or equal to original_price_cents")
        if (
            self.price_cents is None
            and self.original_price_cents is None
            and self.discount_percent is None
            and not any(
                item.price_cents is not None
                or item.original_price_cents is not None
                or item.discount_percent is not None
                for item in self.items
            )
        ):
            raise ValueError("normalized offer must include at least one pricing or discount signal")
        return self


class HealthcheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthy: bool
    detail: str | None = None
    sample_size: int | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DiscoverOffersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    window_start: datetime | None = None
    window_end: datetime | None = None


class DiscoverOffersOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offers: list[OfferReference]
    next_cursor: str | None = None


class FetchOfferDetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_ref: str


class FetchOfferDetailOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_ref: str
    offer: dict[str, Any]


class NormalizeOfferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer: dict[str, Any]


class NormalizeOfferOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_offer: NormalizedOfferRecord


class OfferScopeStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: str
    store_name: str | None = None
    region_code: str | None = None


class OfferScopeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_name: str
    merchant_id: str | None = None
    country_code: str
    scope_kind: Literal["merchant", "region", "store", "mixed"] = "merchant"
    regions: tuple[str, ...] = ()
    stores: tuple[OfferScopeStore, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("regions", mode="before")
    @classmethod
    def _normalize_regions(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("regions must be a list or tuple")
        return tuple(str(item).strip() for item in value if str(item).strip())


class DiagnosticsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnostics: dict[str, Any] = Field(default_factory=dict)


class OfferActionRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = OFFER_CONNECTOR_CONTRACT_VERSION
    plugin_family: Literal["offer"] = "offer"


class GetManifestRequest(OfferActionRequestBase):
    action: Literal["get_manifest"] = "get_manifest"
    input: EmptyInput = Field(default_factory=EmptyInput)


class HealthcheckRequest(OfferActionRequestBase):
    action: Literal["healthcheck"] = "healthcheck"
    input: EmptyInput = Field(default_factory=EmptyInput)


class DiscoverOffersRequest(OfferActionRequestBase):
    action: Literal["discover_offers"] = "discover_offers"
    input: DiscoverOffersInput = Field(default_factory=DiscoverOffersInput)


class FetchOfferDetailRequest(OfferActionRequestBase):
    action: Literal["fetch_offer_detail"] = "fetch_offer_detail"
    input: FetchOfferDetailInput


class NormalizeOfferRequest(OfferActionRequestBase):
    action: Literal["normalize_offer"] = "normalize_offer"
    input: NormalizeOfferInput


class GetOfferScopeRequest(OfferActionRequestBase):
    action: Literal["get_offer_scope"] = "get_offer_scope"
    input: EmptyInput = Field(default_factory=EmptyInput)


class GetOfferDiagnosticsRequest(OfferActionRequestBase):
    action: Literal["get_offer_diagnostics"] = "get_offer_diagnostics"
    input: EmptyInput = Field(default_factory=EmptyInput)


OfferActionRequest = (
    GetManifestRequest
    | HealthcheckRequest
    | DiscoverOffersRequest
    | FetchOfferDetailRequest
    | NormalizeOfferRequest
    | GetOfferScopeRequest
    | GetOfferDiagnosticsRequest
)


class OfferActionResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = OFFER_CONNECTOR_CONTRACT_VERSION
    plugin_family: Literal["offer"] = "offer"
    ok: bool = True
    warnings: tuple[str, ...] = ()
    error: ConnectorError | None = None

    @model_validator(mode="after")
    def _validate_result_state(self) -> OfferActionResponseBase:
        if self.ok and self.error is not None:
            raise ValueError("successful connector responses must not include an error payload")
        if not self.ok and self.error is None:
            raise ValueError("failed connector responses must include an error payload")
        return self


class GetManifestOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: ConnectorManifest


class GetManifestResponse(OfferActionResponseBase):
    action: Literal["get_manifest"] = "get_manifest"
    output: GetManifestOutput | None = None


class HealthcheckResponse(OfferActionResponseBase):
    action: Literal["healthcheck"] = "healthcheck"
    output: HealthcheckOutput | None = None


class DiscoverOffersResponse(OfferActionResponseBase):
    action: Literal["discover_offers"] = "discover_offers"
    output: DiscoverOffersOutput | None = None


class FetchOfferDetailResponse(OfferActionResponseBase):
    action: Literal["fetch_offer_detail"] = "fetch_offer_detail"
    output: FetchOfferDetailOutput | None = None


class NormalizeOfferResponse(OfferActionResponseBase):
    action: Literal["normalize_offer"] = "normalize_offer"
    output: NormalizeOfferOutput | None = None


class GetOfferScopeResponse(OfferActionResponseBase):
    action: Literal["get_offer_scope"] = "get_offer_scope"
    output: OfferScopeOutput | None = None


class GetOfferDiagnosticsResponse(OfferActionResponseBase):
    action: Literal["get_offer_diagnostics"] = "get_offer_diagnostics"
    output: DiagnosticsOutput | None = None


OfferActionResponse = (
    GetManifestResponse
    | HealthcheckResponse
    | DiscoverOffersResponse
    | FetchOfferDetailResponse
    | NormalizeOfferResponse
    | GetOfferScopeResponse
    | GetOfferDiagnosticsResponse
)

_REQUEST_ADAPTER: TypeAdapter[OfferActionRequest] = TypeAdapter(OfferActionRequest)
_RESPONSE_ADAPTER: TypeAdapter[OfferActionResponse] = TypeAdapter(OfferActionResponse)


def validate_offer_action_request(
    value: OfferActionRequest | Mapping[str, Any],
) -> OfferActionRequest:
    if isinstance(value, BaseModel):
        return _REQUEST_ADAPTER.validate_python(value.model_dump(mode="python"))
    return _REQUEST_ADAPTER.validate_python(value)


def validate_offer_action_response(
    value: OfferActionResponse | Mapping[str, Any],
) -> OfferActionResponse:
    if isinstance(value, BaseModel):
        return _RESPONSE_ADAPTER.validate_python(value.model_dump(mode="python"))
    return _RESPONSE_ADAPTER.validate_python(value)


@runtime_checkable
class OfferConnector(Protocol):
    def invoke_action(
        self,
        request: OfferActionRequest | Mapping[str, Any],
    ) -> OfferActionResponse | Mapping[str, Any]:
        ...
