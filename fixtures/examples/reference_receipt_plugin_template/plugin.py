from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    ConnectorError,
    DiagnosticsOutput,
    DiscoverRecordsOutput,
    ExtractDiscountsOutput,
    FetchRecordOutput,
    GetAuthStatusOutput,
    GetManifestOutput,
    HealthcheckOutput,
    NormalizedDiscountRow,
    NormalizedReceiptItem,
    NormalizedReceiptRecord,
    NormalizeRecordOutput,
    ReceiptActionRequest,
    ReceiptActionResponse,
    ReceiptConnector,
    RecordReference,
    validate_receipt_action_request,
)
from lidltool.connectors.sdk.runtime import (
    AuthBrowserPlan,
    build_auth_browser_metadata,
    load_plugin_runtime_context,
    parse_auth_browser_runtime_context,
)

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
FIXTURE_PATH = ROOT / "fixtures" / "raw_records.json"


def _load_manifest() -> ConnectorManifest:
    return ConnectorManifest.model_validate(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))


def _load_fixture_records() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise RuntimeError("fixture file must provide a records list")
    return [dict(record) for record in records]


def _money_to_cents(value: Any) -> int:
    amount = Decimal(str(value or "0"))
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class ReferenceTemplateReceiptPlugin(ReceiptConnector):
    def __init__(self) -> None:
        self._manifest = _load_manifest()
        self._records = _load_fixture_records()

    def invoke_action(
        self,
        request: ReceiptActionRequest | Mapping[str, Any],
    ) -> ReceiptActionResponse | Mapping[str, Any]:
        validated = validate_receipt_action_request(request)
        handler = getattr(self, f"_handle_{validated.action}")
        return handler(validated)

    def _handle_get_manifest(self, request: ReceiptActionRequest) -> dict[str, Any]:
        return self._ok(
            request.action,
            GetManifestOutput(manifest=self._manifest).model_dump(mode="python"),
        )

    def _handle_healthcheck(self, request: ReceiptActionRequest) -> dict[str, Any]:
        session = self._load_session()
        return self._ok(
            request.action,
            HealthcheckOutput(
                healthy=session is not None,
                detail=(
                    "Reference template is ready."
                    if session is not None
                    else "Reference template requires authentication before sync."
                ),
                diagnostics={
                    "reference_template": True,
                    "authenticated": session is not None,
                    "fixture_records": len(self._records),
                },
            ).model_dump(mode="python"),
        )

    def _handle_get_auth_status(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        session = self._load_session()
        pending = self._load_pending()
        if session is not None:
            output = GetAuthStatusOutput(
                status="authenticated",
                is_authenticated=True,
                available_actions=("start_auth",),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Authenticated fixture session is stored in plugin-local runtime storage.",
                metadata={
                    "state_file": str(self._session_path(context)),
                    "authenticated_at": session.get("authenticated_at"),
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))
        if pending is not None:
            output = GetAuthStatusOutput(
                status="pending",
                is_authenticated=False,
                available_actions=("cancel_auth", "confirm_auth"),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Shared browser session is open; confirm_auth will finalize once callback data is available.",
                metadata={
                    "flow_id": pending.get("flow_id"),
                    "pending_file": str(self._pending_path(context)),
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))
        output = GetAuthStatusOutput(
            status="requires_auth",
            is_authenticated=False,
            available_actions=("start_auth",),
            implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
            compatibility_actions=("start_auth", "cancel_auth"),
            reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
            detail="No plugin-owned session is stored yet.",
            metadata={"state_file": str(self._session_path(context))},
        )
        return self._ok(request.action, output.model_dump(mode="python"))

    def _handle_start_auth(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        if self._load_session() is not None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="Plugin is already authenticated. Clear the session file if you want to rebootstrap.",
                ).model_dump(mode="python"),
            )

        flow_id = secrets.token_hex(12)
        pending = {
            "flow_id": flow_id,
            "started_at": datetime.now(tz=UTC).isoformat(),
        }
        self._write_json(self._pending_path(context), pending)
        timeout = int(context.connector_options.get("auth_timeout_seconds", 900))
        plan = AuthBrowserPlan(
            start_url="https://example.invalid/reference-login",
            callback_url_prefixes=("https://example.invalid/reference-callback",),
            timeout_seconds=timeout,
            capture_storage_state=True,
        )
        return self._ok(
            request.action,
            AuthLifecycleOutput(
                status="started",
                flow_id=flow_id,
                detail="Started reference browser-session bootstrap. Replace the fixture URLs with merchant-specific login pages.",
                metadata=build_auth_browser_metadata(flow_id=flow_id, plan=plan),
            ).model_dump(mode="python"),
        )

    def _handle_cancel_auth(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        pending_path = self._pending_path(context)
        if not pending_path.exists():
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="No pending browser-session bootstrap exists.",
                ).model_dump(mode="python"),
            )
        pending_path.unlink()
        return self._ok(
            request.action,
            AuthLifecycleOutput(
                status="canceled",
                detail="Pending browser-session bootstrap was canceled.",
            ).model_dump(mode="python"),
        )

    def _handle_confirm_auth(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        pending = self._load_pending()
        if pending is None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="No pending auth flow exists.",
                ).model_dump(mode="python"),
            )
        browser_result = parse_auth_browser_runtime_context(context.runtime_context)
        if browser_result is None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="pending",
                    flow_id=str(pending.get("flow_id") or ""),
                    next_poll_after_seconds=2,
                    detail="Waiting for shared browser callback data.",
                ).model_dump(mode="python"),
            )
        if browser_result.flow_id != str(pending.get("flow_id") or ""):
            return self._error(
                request.action,
                code="contract_violation",
                message="Browser callback flow_id did not match the pending plugin auth flow.",
            )
        session_payload = {
            "authenticated_at": datetime.now(tz=UTC).isoformat(),
            "callback_url": browser_result.callback_url,
            "storage_state": browser_result.storage_state or {"cookies": [], "origins": []},
        }
        self._write_json(self._session_path(context), session_payload)
        self._pending_path(context).unlink(missing_ok=True)
        return self._ok(
            request.action,
            AuthLifecycleOutput(
                status="confirmed",
                flow_id=browser_result.flow_id,
                detail="Stored plugin-owned browser session state.",
                metadata={
                    "state_file": str(self._session_path(context)),
                    "callback_url": browser_result.callback_url,
                },
            ).model_dump(mode="python"),
        )

    def _handle_discover_records(self, request: ReceiptActionRequest) -> dict[str, Any]:
        if self._load_session() is None:
            return self._error(
                request.action,
                code="auth_required",
                message="Run start_auth and confirm_auth before discovering records.",
            )
        limit = request.input.limit or len(self._records)
        output = DiscoverRecordsOutput(
            records=[
                RecordReference(record_ref=str(record["id"]), metadata={"fixture": True})
                for record in self._records[:limit]
            ],
            next_cursor=None,
        )
        return self._ok(request.action, output.model_dump(mode="python"))

    def _handle_fetch_record(self, request: ReceiptActionRequest) -> dict[str, Any]:
        record_ref = request.input.record_ref
        record = next((item for item in self._records if str(item.get("id")) == record_ref), None)
        if record is None:
            return self._error(
                request.action,
                code="invalid_request",
                message=f"Unknown fixture record_ref: {record_ref}",
            )
        return self._ok(
            request.action,
            FetchRecordOutput(record_ref=record_ref, record=record).model_dump(mode="python"),
        )

    def _handle_normalize_record(self, request: ReceiptActionRequest) -> dict[str, Any]:
        record = request.input.record
        merchant_label = str(
            load_plugin_runtime_context().connector_options.get("merchant_label")
            or record.get("store", {}).get("name")
            or "Reference Merchant"
        )
        items: list[NormalizedReceiptItem] = []
        discount_total = 0
        for index, raw_item in enumerate(record.get("items") or [], start=1):
            raw_discounts = list(raw_item.get("discounts") or [])
            discount_total += sum(int(discount.get("amount_cents", 0)) for discount in raw_discounts)
            items.append(
                NormalizedReceiptItem(
                    line_no=index,
                    source_item_id=f"{record.get('id')}:{index}",
                    name=str(raw_item.get("name") or f"Item {index}"),
                    qty=str(raw_item.get("qty") or "1"),
                    unit=str(raw_item.get("unit") or "pcs"),
                    unit_price_cents=_money_to_cents(raw_item.get("unitPrice") or raw_item.get("lineTotal")),
                    line_total_cents=_money_to_cents(raw_item.get("lineTotal")),
                    discounts=raw_discounts,
                )
            )
        normalized = NormalizedReceiptRecord(
            id=str(record.get("id") or ""),
            purchased_at=datetime.fromisoformat(str(record.get("purchasedAt"))),
            store_id=str(record.get("store", {}).get("id") or self._manifest.source_id),
            store_name=merchant_label,
            total_gross_cents=_money_to_cents(record.get("totalGross")),
            currency=str(record.get("currency") or "EUR"),
            discount_total_cents=discount_total,
            fingerprint=f"reference-template:{record.get('id')}",
            items=items,
            raw_json=record,
        )
        return self._ok(
            request.action,
            NormalizeRecordOutput(normalized_record=normalized).model_dump(mode="python"),
        )

    def _handle_extract_discounts(self, request: ReceiptActionRequest) -> dict[str, Any]:
        discounts: list[NormalizedDiscountRow] = []
        for index, raw_item in enumerate(request.input.record.get("items") or [], start=1):
            for raw_discount in raw_item.get("discounts") or []:
                discounts.append(
                    NormalizedDiscountRow(
                        line_no=index,
                        type=str(raw_discount.get("type") or "coupon"),
                        promotion_id=(
                            str(raw_discount.get("promotion_id"))
                            if raw_discount.get("promotion_id") is not None
                            else None
                        ),
                        amount_cents=int(raw_discount.get("amount_cents") or 0),
                        label=str(raw_discount.get("label") or "Discount"),
                        scope=str(raw_discount.get("scope") or "item"),
                        subkind=(
                            str(raw_discount.get("subkind"))
                            if raw_discount.get("subkind") is not None
                            else None
                        ),
                        funded_by=(
                            str(raw_discount.get("funded_by"))
                            if raw_discount.get("funded_by") is not None
                            else None
                        ),
                    )
                )
        return self._ok(
            request.action,
            ExtractDiscountsOutput(discounts=discounts).model_dump(mode="python"),
        )

    def _handle_get_diagnostics(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        diagnostics = {
            "reference_template": True,
            "fixture_records": len(self._records),
            "session_file": str(self._session_path(context)),
            "pending_file": str(self._pending_path(context)),
            "authenticated": self._load_session() is not None,
            "runtime_host_kind": context.runtime.host_kind,
        }
        return self._ok(
            request.action,
            DiagnosticsOutput(diagnostics=diagnostics).model_dump(mode="python"),
        )

    def _session_path(self, context: Any) -> Path:
        return context.storage.data_dir / "reference_session.json"

    def _pending_path(self, context: Any) -> Path:
        return context.storage.data_dir / "reference_pending_auth.json"

    def _load_session(self) -> dict[str, Any] | None:
        context = load_plugin_runtime_context()
        return self._read_json(self._session_path(context))

    def _load_pending(self) -> dict[str, Any] | None:
        context = load_plugin_runtime_context()
        return self._read_json(self._pending_path(context))

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected JSON object in {path}")
        return payload

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _ok(self, action: str, output: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": action,
            "ok": True,
            "output": output,
        }

    def _error(self, action: str, *, code: str, message: str) -> dict[str, Any]:
        return {
            "action": action,
            "ok": False,
            "error": ConnectorError(code=code, message=message).model_dump(mode="python"),
        }
