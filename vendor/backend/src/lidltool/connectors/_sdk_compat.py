from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from lidltool.connectors.base import Connector
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    CancelAuthResponse,
    ConfirmAuthResponse,
    ConnectorError,
    ConnectorErrorCode,
    DiagnosticsOutput,
    DiscoverRecordsOutput,
    DiscoverRecordsRequest,
    DiscoverRecordsResponse,
    ExtractDiscountsOutput,
    ExtractDiscountsResponse,
    FetchRecordOutput,
    FetchRecordResponse,
    GetAuthStatusOutput,
    GetAuthStatusResponse,
    GetDiagnosticsResponse,
    GetManifestOutput,
    GetManifestResponse,
    HealthcheckOutput,
    HealthcheckResponse,
    NormalizedDiscountRow,
    NormalizedReceiptRecord,
    NormalizeRecordOutput,
    NormalizeRecordResponse,
    ReceiptActionRequest,
    ReceiptActionResponse,
    ReceiptConnector,
    RecordReference,
    StartAuthResponse,
    validate_receipt_action_request,
)


class LegacyReceiptConnectorBridge:
    def __init__(self, *, connector: Connector, manifest: ConnectorManifest) -> None:
        self._connector = connector
        self._manifest = manifest

    def invoke_action(
        self,
        request: ReceiptActionRequest | Mapping[str, Any],
    ) -> ReceiptActionResponse | Mapping[str, Any]:
        validated = validate_receipt_action_request(request)
        try:
            if validated.action == "get_manifest":
                return GetManifestResponse(output=GetManifestOutput(manifest=self._manifest))
            if validated.action == "healthcheck":
                payload = self._connector.healthcheck()
                output = HealthcheckOutput.model_validate(
                    {
                        "healthy": bool(payload.get("healthy", False)),
                        "detail": str(payload["error"]) if payload.get("error") else None,
                        "sample_size": payload.get("sample_size"),
                        "diagnostics": payload,
                    }
                )
                return HealthcheckResponse(output=output)
            if validated.action == "get_auth_status":
                return self._get_auth_status()
            if validated.action == "start_auth":
                return StartAuthResponse(output=self._reserved_auth_output())
            if validated.action == "cancel_auth":
                return CancelAuthResponse(output=self._reserved_auth_output())
            if validated.action == "confirm_auth":
                return ConfirmAuthResponse(output=self._reserved_auth_output())
            if validated.action == "discover_records":
                return self._discover_records(validated)
            if validated.action == "fetch_record":
                detail = self._connector.fetch_record_detail(validated.input.record_ref)
                return FetchRecordResponse(
                    output=FetchRecordOutput(
                        record_ref=validated.input.record_ref,
                        record=detail,
                    )
                )
            if validated.action == "normalize_record":
                normalized = self._connector.normalize(validated.input.record)
                return NormalizeRecordResponse(
                    output=NormalizeRecordOutput(
                        normalized_record=self._normalize_record_payload(normalized),
                    )
                )
            if validated.action == "extract_discounts":
                discounts = self._connector.extract_discounts(validated.input.record)
                normalized_rows = [
                    NormalizedDiscountRow.model_validate(self._normalize_discount_row(row))
                    for row in discounts
                ]
                return ExtractDiscountsResponse(
                    output=ExtractDiscountsOutput(discounts=normalized_rows)
                )
            if validated.action == "get_diagnostics":
                return GetDiagnosticsResponse(
                    output=DiagnosticsOutput(
                        diagnostics={
                            "manifest_version": self._manifest.manifest_version,
                            "connector_api_version": self._manifest.connector_api_version,
                            "legacy_adapter_class": type(self._connector).__name__,
                            "reserved_auth_actions": list(
                                self._manifest.actions.reserved if self._manifest.actions else ()
                            ),
                        }
                    )
                )
        except Exception as exc:
            return cast(
                ReceiptActionResponse,
                {
                    "contract_version": validated.contract_version,
                    "plugin_family": validated.plugin_family,
                    "action": validated.action,
                    "ok": False,
                    "warnings": (),
                    "error": ConnectorError(
                        code=self._error_code(validated.action),
                        message=str(exc),
                        retryable=validated.action
                        in {"healthcheck", "discover_records", "fetch_record"},
                    ).model_dump(mode="python"),
                    "output": None,
                },
            )
        raise AssertionError(f"unsupported receipt connector action: {validated.action}")

    def _get_auth_status(self) -> ReceiptActionResponse:
        if self._manifest.auth_kind == "none":
            return GetAuthStatusResponse(
                output=GetAuthStatusOutput(
                    status="not_supported",
                    is_authenticated=True,
                    available_actions=(),
                    implemented_actions=(),
                    compatibility_actions=(),
                    reserved_actions=(),
                    detail="connector does not require authentication",
                )
            )
        try:
            payload = self._connector.authenticate()
            is_authenticated = bool(payload.get("authenticated", True))
            return GetAuthStatusResponse(
                output=GetAuthStatusOutput(
                    status="authenticated" if is_authenticated else "requires_auth",
                    is_authenticated=is_authenticated,
                    available_actions=(
                        self._manifest.auth.available_actions() if self._manifest.auth is not None else ()
                    ),
                    implemented_actions=(
                        self._manifest.auth.implemented_actions if self._manifest.auth is not None else ()
                    ),
                    compatibility_actions=(
                        self._manifest.auth.compatibility_actions if self._manifest.auth is not None else ()
                    ),
                    reserved_actions=(
                        self._manifest.auth.reserved_actions if self._manifest.auth is not None else ()
                    ),
                    detail=None,
                    metadata=payload,
                )
            )
        except Exception as exc:
            return GetAuthStatusResponse(
                output=GetAuthStatusOutput(
                    status="requires_auth",
                    is_authenticated=False,
                    available_actions=(
                        self._manifest.auth.available_actions() if self._manifest.auth is not None else ()
                    ),
                    implemented_actions=(
                        self._manifest.auth.implemented_actions if self._manifest.auth is not None else ()
                    ),
                    compatibility_actions=(
                        self._manifest.auth.compatibility_actions if self._manifest.auth is not None else ()
                    ),
                    reserved_actions=(
                        self._manifest.auth.reserved_actions if self._manifest.auth is not None else ()
                    ),
                    detail=str(exc),
                )
            )

    def _discover_records(self, request: DiscoverRecordsRequest) -> ReceiptActionResponse:
        refs = self._connector.discover_new_records()
        if request.input.limit is not None:
            refs = refs[: request.input.limit]
        return DiscoverRecordsResponse(
            output=DiscoverRecordsOutput(
                records=[RecordReference(record_ref=ref) for ref in refs],
                next_cursor=None,
            )
        )

    def _reserved_auth_output(self) -> AuthLifecycleOutput:
        detail = (
            "runtime-hosted connector auth actions remain reserved in connector API v1; "
            "built-in connectors currently expose auth through the central host orchestration layer"
        )
        return AuthLifecycleOutput(status="not_supported", detail=detail)

    def _normalize_discount_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        amount_cents = abs(int(row.get("amount_cents", 0) or 0))
        return {
            "line_no": row.get("line_no"),
            "type": str(row.get("type") or "unknown"),
            "promotion_id": str(row["promotion_id"]) if row.get("promotion_id") is not None else None,
            "amount_cents": amount_cents,
            "label": str(row.get("label") or row.get("type") or "discount"),
            "scope": "transaction"
            if str(row.get("scope") or "item") in {"basket", "transaction"}
            else "item",
            "subkind": str(row["subkind"]) if row.get("subkind") is not None else None,
            "funded_by": str(row["funded_by"]) if row.get("funded_by") is not None else None,
        }

    def _normalize_record_payload(self, normalized: Mapping[str, Any]) -> NormalizedReceiptRecord:
        payload = dict(normalized)
        if payload.get("discount_total_cents") is None:
            payload["discount_total_cents"] = 0
        return NormalizedReceiptRecord.model_validate(payload)

    def _error_code(self, action: str) -> ConnectorErrorCode:
        if action in {"get_auth_status", "start_auth", "cancel_auth", "confirm_auth"}:
            return "auth_required"
        if action in {"healthcheck", "discover_records", "fetch_record"}:
            return "upstream_error"
        return "internal_error"


def coerce_receipt_connector(
    connector: object,
    *,
    manifest: ConnectorManifest | dict[str, Any] | None = None,
) -> ReceiptConnector:
    if isinstance(connector, ReceiptConnector):
        return connector
    if manifest is None:
        raise ValueError("manifest is required when adapting a legacy in-process connector")
    manifest_model = (
        manifest
        if isinstance(manifest, ConnectorManifest)
        else ConnectorManifest.model_validate(manifest)
    )
    if not isinstance(connector, Connector):
        raise TypeError("connector must implement the public receipt protocol or the legacy Connector ABC")
    return LegacyReceiptConnectorBridge(connector=connector, manifest=manifest_model)
