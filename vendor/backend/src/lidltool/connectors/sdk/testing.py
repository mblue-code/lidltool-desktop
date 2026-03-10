from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from lidltool.connectors._sdk_compat import coerce_receipt_connector
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.offer import (
    DiscoverOffersInput,
    DiscoverOffersRequest,
    DiscoverOffersResponse,
    FetchOfferDetailInput,
    FetchOfferDetailRequest,
    FetchOfferDetailResponse,
    GetManifestRequest as GetOfferManifestRequest,
    GetManifestResponse as GetOfferManifestResponse,
    GetOfferDiagnosticsRequest,
    GetOfferDiagnosticsResponse,
    GetOfferScopeRequest,
    GetOfferScopeResponse,
    HealthcheckRequest as OfferHealthcheckRequest,
    HealthcheckResponse as OfferHealthcheckResponse,
    NormalizeOfferInput,
    NormalizeOfferRequest,
    NormalizeOfferResponse,
    OfferActionRequest,
    OfferActionResponse,
    validate_offer_action_request,
    validate_offer_action_response,
)
from lidltool.connectors.sdk.receipt import (
    CancelAuthRequest,
    ConfirmAuthRequest,
    DiscoverRecordsInput,
    DiscoverRecordsRequest,
    DiscoverRecordsResponse,
    ExtractDiscountsInput,
    ExtractDiscountsRequest,
    ExtractDiscountsResponse,
    FetchRecordInput,
    FetchRecordRequest,
    FetchRecordResponse,
    GetAuthStatusRequest,
    GetDiagnosticsRequest,
    GetDiagnosticsResponse,
    GetManifestRequest,
    GetManifestResponse,
    HealthcheckRequest,
    HealthcheckResponse,
    NormalizeRecordInput,
    NormalizeRecordRequest,
    NormalizeRecordResponse,
    ReceiptActionRequest,
    ReceiptActionResponse,
    StartAuthRequest,
    validate_receipt_action_request,
    validate_receipt_action_response,
)


@dataclass(slots=True, frozen=True)
class ReceiptConnectorContractFixture:
    expect_records: bool = True
    expect_discounts: bool | None = None
    discovery_limit: int | None = 5


@dataclass(slots=True, frozen=True)
class OfferConnectorContractFixture:
    expect_offers: bool = True
    discovery_limit: int | None = 5


def assert_receipt_connector_contract(
    connector: object,
    *,
    manifest: ConnectorManifest | dict[str, Any] | None = None,
    fixture: ReceiptConnectorContractFixture | None = None,
) -> None:
    contract_fixture = fixture or ReceiptConnectorContractFixture()
    runtime = coerce_receipt_connector(connector, manifest=manifest)

    manifest_response = cast(GetManifestResponse, _invoke(runtime, GetManifestRequest()))
    if manifest_response.output is None:
        raise AssertionError("get_manifest must return a manifest payload")
    contract_manifest = manifest_response.output.manifest

    if contract_manifest.plugin_family != "receipt":
        raise AssertionError(
            f"receipt contract harness expected plugin_family='receipt', got {contract_manifest.plugin_family!r}"
        )
    if contract_manifest.actions is None:
        raise AssertionError("receipt connector manifest must declare receipt actions")

    health_response = cast(HealthcheckResponse, _invoke(runtime, HealthcheckRequest()))
    if health_response.output is None:
        raise AssertionError("healthcheck must return an output payload")

    auth_response = _invoke(runtime, GetAuthStatusRequest())
    if auth_response.output is None:
        raise AssertionError("get_auth_status must return an output payload")

    for request in (StartAuthRequest(), CancelAuthRequest(), ConfirmAuthRequest()):
        response = _invoke(runtime, request)
        if response.output is None:
            raise AssertionError(f"{request.action} must return an output payload")

    discover_response = cast(
        DiscoverRecordsResponse,
        _invoke(
            runtime,
            DiscoverRecordsRequest(
                input=DiscoverRecordsInput(limit=contract_fixture.discovery_limit),
            ),
        ),
    )
    if discover_response.output is None:
        raise AssertionError("discover_records must return an output payload")

    records = discover_response.output.records
    if contract_fixture.expect_records and not records:
        raise AssertionError("discover_records returned no records but the contract fixture expects one")
    if not records:
        diagnostics_response = _invoke(runtime, GetDiagnosticsRequest())
        if diagnostics_response.output is None:
            raise AssertionError("get_diagnostics must return an output payload")
        return

    first_record_ref = records[0].record_ref

    fetch_response = cast(
        FetchRecordResponse,
        _invoke(runtime, FetchRecordRequest(input=FetchRecordInput(record_ref=first_record_ref))),
    )
    if fetch_response.output is None:
        raise AssertionError("fetch_record must return an output payload")

    normalize_response = cast(
        NormalizeRecordResponse,
        _invoke(
            runtime,
            NormalizeRecordRequest(input=NormalizeRecordInput(record=fetch_response.output.record)),
        ),
    )
    if normalize_response.output is None:
        raise AssertionError("normalize_record must return an output payload")

    discounts_response = cast(
        ExtractDiscountsResponse,
        _invoke(
            runtime,
            ExtractDiscountsRequest(input=ExtractDiscountsInput(record=fetch_response.output.record)),
        ),
    )
    if discounts_response.output is None:
        raise AssertionError("extract_discounts must return an output payload")
    if contract_fixture.expect_discounts and not discounts_response.output.discounts:
        raise AssertionError(
            "extract_discounts returned no discount rows but the contract fixture expects one"
        )

    diagnostics_response = cast(GetDiagnosticsResponse, _invoke(runtime, GetDiagnosticsRequest()))
    if diagnostics_response.output is None:
        raise AssertionError("get_diagnostics must return an output payload")


def _invoke(connector: object, request: ReceiptActionRequest) -> ReceiptActionResponse:
    try:
        validated_request = validate_receipt_action_request(request)
    except ValidationError as exc:
        raise AssertionError(f"{request.action} request fixture is invalid: {exc}") from exc

    if not hasattr(connector, "invoke_action"):
        raise AssertionError("connector does not implement the public invoke_action(request) contract")

    raw_response = connector.invoke_action(validated_request)
    try:
        response = validate_receipt_action_response(raw_response)
    except ValidationError as exc:
        raise AssertionError(f"{request.action} returned an invalid response payload: {exc}") from exc

    if response.action != validated_request.action:
        raise AssertionError(
            f"{validated_request.action} returned mismatched action {response.action!r} in its response envelope"
        )
    if not response.ok:
        message = response.error.message if response.error is not None else "unknown error"
        raise AssertionError(f"{validated_request.action} failed the connector contract: {message}")
    if response.output is None:
        raise AssertionError(f"{validated_request.action} must include an output payload when ok=true")
    return response


def assert_offer_connector_contract(
    connector: object,
    *,
    fixture: OfferConnectorContractFixture | None = None,
) -> None:
    contract_fixture = fixture or OfferConnectorContractFixture()

    manifest_response = cast(GetOfferManifestResponse, _invoke_offer(connector, GetOfferManifestRequest()))
    if manifest_response.output is None:
        raise AssertionError("get_manifest must return a manifest payload")
    contract_manifest = manifest_response.output.manifest
    if contract_manifest.plugin_family != "offer":
        raise AssertionError(
            f"offer contract harness expected plugin_family='offer', got {contract_manifest.plugin_family!r}"
        )

    health_response = cast(OfferHealthcheckResponse, _invoke_offer(connector, OfferHealthcheckRequest()))
    if health_response.output is None:
        raise AssertionError("healthcheck must return an output payload")

    discover_response = cast(
        DiscoverOffersResponse,
        _invoke_offer(
            connector,
            DiscoverOffersRequest(input=DiscoverOffersInput(limit=contract_fixture.discovery_limit)),
        ),
    )
    if discover_response.output is None:
        raise AssertionError("discover_offers must return an output payload")
    offers = discover_response.output.offers
    if contract_fixture.expect_offers and not offers:
        raise AssertionError("discover_offers returned no offers but the contract fixture expects one")

    scope_response = cast(GetOfferScopeResponse, _invoke_offer(connector, GetOfferScopeRequest()))
    if scope_response.output is None:
        raise AssertionError("get_offer_scope must return an output payload")

    diagnostics_response = cast(
        GetOfferDiagnosticsResponse,
        _invoke_offer(connector, GetOfferDiagnosticsRequest()),
    )
    if diagnostics_response.output is None:
        raise AssertionError("get_offer_diagnostics must return an output payload")

    if not offers:
        return

    first_offer_ref = offers[0].offer_ref
    fetch_response = cast(
        FetchOfferDetailResponse,
        _invoke_offer(
            connector,
            FetchOfferDetailRequest(input=FetchOfferDetailInput(offer_ref=first_offer_ref)),
        ),
    )
    if fetch_response.output is None:
        raise AssertionError("fetch_offer_detail must return an output payload")

    normalize_response = cast(
        NormalizeOfferResponse,
        _invoke_offer(
            connector,
            NormalizeOfferRequest(input=NormalizeOfferInput(offer=fetch_response.output.offer)),
        ),
    )
    if normalize_response.output is None:
        raise AssertionError("normalize_offer must return an output payload")


def _invoke_offer(connector: object, request: OfferActionRequest) -> OfferActionResponse:
    try:
        validated_request = validate_offer_action_request(request)
    except ValidationError as exc:
        raise AssertionError(f"{request.action} request fixture is invalid: {exc}") from exc

    if not hasattr(connector, "invoke_action"):
        raise AssertionError("connector does not implement the public invoke_action(request) contract")

    raw_response = connector.invoke_action(validated_request)
    try:
        response = validate_offer_action_response(raw_response)
    except ValidationError as exc:
        raise AssertionError(f"{request.action} returned an invalid response payload: {exc}") from exc

    if response.action != validated_request.action:
        raise AssertionError(
            f"{validated_request.action} returned mismatched action {response.action!r} in its response envelope"
        )
    if not response.ok:
        message = response.error.message if response.error is not None else "unknown error"
        raise AssertionError(f"{validated_request.action} failed the connector contract: {message}")
    if response.output is None:
        raise AssertionError(f"{validated_request.action} must include an output payload when ok=true")
    return response
