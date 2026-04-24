from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    CancelAuthResponse,
    ConfirmAuthResponse,
    ConnectorError,
    DiagnosticsOutput,
    DiscoverRecordsOutput,
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
    NormalizeRecordOutput,
    NormalizeRecordResponse,
    NormalizedDiscountRow,
    NormalizedReceiptItem,
    NormalizedReceiptRecord,
    ReceiptActionRequest,
    ReceiptActionResponse,
    RecordReference,
    StartAuthResponse,
    validate_receipt_action_request,
)
from lidltool.connectors.sdk.runtime import load_plugin_runtime_context

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"

VAT_CODE_MAP = {
    "A": "19%",
    "B": "7%",
}
ITEM_LINE_RE = re.compile(r"^(?P<name>.+?)\s+(?P<amount>-?\d+,\d{2})\s+(?P<vat>[A-Z])$")
QTY_EXTENSION_RE = re.compile(r"^(?P<qty>\d+)\s*x\s+(?P<amount>\d+,\d{2})$")
WEIGHT_RE = re.compile(
    r"^(?P<qty>\d+,\d+)\s+(?P<unit>kg|g|l|ml)\s+(?P<unit_price>\d+,\d{2})\s+EUR/kg$",
    re.IGNORECASE,
)
DISCOUNT_LINE_RE = re.compile(r"^(?P<label>.+?)\s+(?P<amount>-\d+,\d{2})$")


class NettoPlusPluginError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(slots=True)
class ParsedDiscount:
    label: str
    amount_cents: int
    scope: str
    line_no: int | None
    type: str = "promotion"
    subkind: str | None = None
    funded_by: str | None = "retailer"


@dataclass(slots=True)
class ParsedItem:
    name: str
    qty: float
    unit: str
    unit_price_cents: int | None
    line_total_cents: int
    vat_rate: str | None
    source_name: str
    is_deposit: bool = False
    category: str | None = None
    discounts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PendingWeight:
    qty: float
    unit: str
    unit_price_cents: int


@dataclass(slots=True)
class PendingExtraQuantity:
    qty: int
    unit_price_cents: int


def _manifest_definition() -> dict[str, Any]:
    manifest_path = MANIFEST_PATH
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    packaged_manifest = ROOT.parent / "manifest.json"
    return json.loads(packaged_manifest.read_text(encoding="utf-8"))


def _resolve_optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        return Path(raw).expanduser().resolve()
    raise TypeError(f"expected path-like value, got {type(value).__name__}")


def _string_option(options: Mapping[str, Any], key: str, default: str = "") -> str:
    value = options.get(key, default)
    return str(value).strip()


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _money_to_cents(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    text = str(value).strip()
    if not text:
        return 0
    normalized = (
        text.replace("EUR", "")
        .replace("€", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )
    return int(round(float(normalized) * 100))


def _amount_to_text(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    euros, remainder = divmod(absolute, 100)
    return f"{sign}{euros}.{remainder:02d}"


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        raise NettoPlusPluginError("Netto receipt is missing Einkaufsdatum", code="contract_violation")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise NettoPlusPluginError(
            f"invalid Netto receipt date: {text}",
            code="contract_violation",
        ) from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NettoPlusPluginError(
            f"invalid JSON object at {path}",
            code="contract_violation",
        )
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _state_file_for_context() -> Path:
    context = load_plugin_runtime_context()
    resolved = _resolve_optional_path(context.connector_options.get("state_file"))
    if resolved is not None:
        return resolved
    return (context.storage.data_dir / "netto_plus_state.json").expanduser().resolve()


def _bundle_file_for_context(options: Mapping[str, Any]) -> Path | None:
    fixture = _resolve_optional_path(options.get("fixture_file"))
    if fixture is not None:
        return fixture
    return _resolve_optional_path(options.get("session_bundle_file"))


def _store_address(summary: Mapping[str, Any]) -> str | None:
    store = summary.get("Filiale")
    if not isinstance(store, Mapping):
        return None
    parts = [
        str(store.get("Strasse") or "").strip(),
        " ".join(
            part
            for part in [str(store.get("Plz") or "").strip(), str(store.get("Ort") or "").strip()]
            if part
        ),
    ]
    joined = ", ".join(part for part in parts if part)
    return joined or None


def _extract_pdf_text_from_payload(pdf_payload: Mapping[str, Any]) -> str:
    encoded = str(pdf_payload.get("content") or "").strip()
    if not encoded:
        raise NettoPlusPluginError("Netto bundle PDF payload is missing content", code="contract_violation")
    pdf_bytes = base64.b64decode(encoded)
    reader = PdfReader(BytesIO(pdf_bytes))
    text_parts = [(page.extract_text() or "").strip() for page in reader.pages]
    extracted = "\n".join(part for part in text_parts if part).strip()
    if not extracted:
        raise NettoPlusPluginError("Netto PDF payload did not contain readable text", code="contract_violation")
    return extracted


def _normalize_bundle(bundle: Mapping[str, Any], *, source_path: Path | None) -> dict[str, Any]:
    receipts_raw = bundle.get("receipts")
    if not isinstance(receipts_raw, list) or not receipts_raw:
        raise NettoPlusPluginError(
            "Netto session bundle must contain at least one receipt",
            code="contract_violation",
        )
    account = bundle.get("account") if isinstance(bundle.get("account"), Mapping) else {}
    normalized_receipts: list[dict[str, Any]] = []
    for raw_receipt in receipts_raw:
        if not isinstance(raw_receipt, Mapping):
            raise NettoPlusPluginError(
                "Netto session bundle receipts must be objects",
                code="contract_violation",
            )
        summary = raw_receipt.get("summary")
        if not isinstance(summary, Mapping):
            raise NettoPlusPluginError(
                "Netto session bundle receipt is missing summary",
                code="contract_violation",
            )
        bon_id = str(summary.get("BonId") or "").strip()
        if not bon_id:
            raise NettoPlusPluginError(
                "Netto session bundle receipt is missing BonId",
                code="contract_violation",
            )
        pdf_text = str(raw_receipt.get("pdf_text") or "").strip()
        if not pdf_text:
            pdf_payload = raw_receipt.get("pdf_payload")
            if not isinstance(pdf_payload, Mapping):
                raise NettoPlusPluginError(
                    f"Netto receipt {bon_id} is missing pdf_text/pdf_payload",
                    code="contract_violation",
                )
            pdf_text = _extract_pdf_text_from_payload(pdf_payload)
        normalized_receipts.append(
            {
                "record_ref": bon_id,
                "summary": dict(summary),
                "pdf_text": pdf_text,
                "pdf_payload": (
                    dict(raw_receipt["pdf_payload"])
                    if isinstance(raw_receipt.get("pdf_payload"), Mapping)
                    else None
                ),
            }
        )
    return {
        "schema_version": str(bundle.get("schema_version") or "1"),
        "imported_at": _iso_now(),
        "bundle_source_path": str(source_path) if source_path is not None else None,
        "account": {
            "email": str(account.get("email") or bundle.get("email") or "").strip() or None,
        },
        "receipts": normalized_receipts,
    }


def _load_imported_state(state_file: Path) -> dict[str, Any] | None:
    if not state_file.exists():
        return None
    payload = _read_json(state_file)
    receipts = payload.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        return None
    return payload


def _parse_pdf_lines(pdf_text: str) -> list[str]:
    return [line.strip() for line in pdf_text.splitlines() if line.strip()]


def _line_discount(label: str, amount_cents: int) -> dict[str, Any]:
    lowered = label.casefold()
    if "gratis" in lowered:
        subkind = "freebie"
    elif "%" in label:
        subkind = "markdown"
    elif "rabatt" in lowered:
        subkind = "promotion"
    else:
        subkind = None
    return {
        "type": "promotion",
        "amount_cents": amount_cents,
        "label": label,
        "scope": "item",
        "subkind": subkind,
        "funded_by": "retailer",
    }


def _parse_receipt_lines(record: Mapping[str, Any]) -> tuple[list[ParsedItem], list[ParsedDiscount], dict[str, Any]]:
    pdf_text = str(record.get("pdf_text") or "").strip()
    if not pdf_text:
        raise NettoPlusPluginError("Netto record is missing pdf_text", code="contract_violation")
    lines = _parse_pdf_lines(pdf_text)
    try:
        items_start = lines.index("EUR") + 1
    except ValueError as exc:
        raise NettoPlusPluginError(
            "Netto PDF text does not contain the receipt items section",
            code="contract_violation",
        ) from exc
    sum_index = next((idx for idx, line in enumerate(lines) if line.startswith("SUMME [")), -1)
    if sum_index <= items_start:
        raise NettoPlusPluginError(
            "Netto PDF text does not contain SUMME [..] before the totals section",
            code="contract_violation",
        )
    item_lines = lines[items_start:sum_index]
    totals_lines = lines[sum_index + 1 :]

    items: list[ParsedItem] = []
    discounts: list[ParsedDiscount] = []
    pending_weight: PendingWeight | None = None
    pending_extra: PendingExtraQuantity | None = None
    last_item: ParsedItem | None = None
    pending_extra_target_name: str | None = None

    def flush_pending_extra(next_name: str | None = None) -> None:
        nonlocal pending_extra, pending_extra_target_name
        if pending_extra is None or last_item is None:
            return
        if next_name is not None and pending_extra_target_name == next_name:
            return
        last_item.qty += pending_extra.qty
        last_item.line_total_cents += pending_extra.qty * pending_extra.unit_price_cents
        pending_extra = None
        pending_extra_target_name = None

    for raw_line in item_lines:
        qty_match = QTY_EXTENSION_RE.match(raw_line)
        if qty_match:
            pending_extra = PendingExtraQuantity(
                qty=int(qty_match.group("qty")),
                unit_price_cents=_money_to_cents(qty_match.group("amount")),
            )
            pending_extra_target_name = last_item.source_name if last_item is not None else None
            continue

        weight_match = WEIGHT_RE.match(raw_line)
        if weight_match:
            pending_weight = PendingWeight(
                qty=float(weight_match.group("qty").replace(",", ".")),
                unit=weight_match.group("unit").lower(),
                unit_price_cents=_money_to_cents(weight_match.group("unit_price")),
            )
            continue

        discount_match = DISCOUNT_LINE_RE.match(raw_line)
        if discount_match and last_item is not None:
            label = discount_match.group("label").strip()
            amount_cents = abs(_money_to_cents(discount_match.group("amount")))
            if "warenkorb" not in label.casefold():
                item_discount = _line_discount(label, amount_cents)
                last_item.discounts.append(item_discount)
                if item_discount.get("subkind") == "freebie":
                    discounts.append(
                        ParsedDiscount(
                            label=label,
                            amount_cents=amount_cents,
                            scope="item",
                            line_no=len(items),
                            subkind=item_discount.get("subkind"),
                        )
                    )
                else:
                    last_item.line_total_cents -= amount_cents
                continue

        item_match = ITEM_LINE_RE.match(raw_line)
        if item_match:
            name = item_match.group("name").strip()
            amount_cents = _money_to_cents(item_match.group("amount"))
            vat_rate = VAT_CODE_MAP.get(item_match.group("vat"))

            if (
                pending_extra is not None
                and last_item is not None
                and pending_extra_target_name == name
                and amount_cents == pending_extra.qty * pending_extra.unit_price_cents
            ):
                last_item.qty += pending_extra.qty
                last_item.line_total_cents += amount_cents
                pending_extra = None
                pending_extra_target_name = None
                continue

            flush_pending_extra(next_name=name)

            qty = 1.0
            unit = "pcs"
            unit_price_cents: int | None = amount_cents
            if pending_weight is not None:
                qty = pending_weight.qty
                unit = pending_weight.unit
                unit_price_cents = pending_weight.unit_price_cents
                pending_weight = None
            is_deposit_line = "leergut" in name.casefold() or "pfand" in name.casefold()

            parsed = ParsedItem(
                name=name,
                qty=qty,
                unit=unit,
                unit_price_cents=unit_price_cents,
                line_total_cents=amount_cents,
                vat_rate=vat_rate,
                source_name=name,
                is_deposit=is_deposit_line,
                category=(
                    "deposit_return"
                    if is_deposit_line and amount_cents < 0
                    else ("deposit" if is_deposit_line else None)
                ),
            )
            items.append(parsed)
            last_item = parsed
            continue

    flush_pending_extra()

    final_total_section_index = next(
        (idx for idx, line in enumerate(totals_lines) if line == "SUMME"),
        len(totals_lines),
    )
    transaction_discount_lines = totals_lines[:final_total_section_index]
    for raw_line in transaction_discount_lines:
        discount_match = DISCOUNT_LINE_RE.match(raw_line)
        if not discount_match:
            continue
        label = discount_match.group("label").strip()
        amount_cents = abs(_money_to_cents(discount_match.group("amount")))
        if amount_cents <= 0:
            continue
        discounts.append(
            ParsedDiscount(
                label=label,
                amount_cents=amount_cents,
                scope="transaction",
                line_no=None,
                subkind="coupon" if "rabatt" in label.casefold() else None,
            )
        )

    derived = {
        "sum_before_transaction_discounts_cents": _money_to_cents(
            next(
                (
                    line.split()[-1]
                    for line in lines
                    if line.startswith("SUMME [")
                ),
                "0,00",
            )
        ),
        "explicit_discount_total_cents": sum(discount.amount_cents for discount in discounts),
    }
    return items, discounts, derived


def _normalized_items(record_id: str, parsed_items: list[ParsedItem]) -> list[NormalizedReceiptItem]:
    normalized: list[NormalizedReceiptItem] = []
    for index, item in enumerate(parsed_items, start=1):
        qty_text = str(int(item.qty)) if item.qty.is_integer() else f"{item.qty:.3f}".rstrip("0").rstrip(".")
        normalized.append(
            NormalizedReceiptItem(
                line_no=index,
                source_item_id=f"{record_id}:{index}",
                name=item.name,
                qty=qty_text,
                unit=item.unit,
                unit_price_cents=item.unit_price_cents,
                line_total_cents=item.line_total_cents,
                is_deposit=item.is_deposit,
                vat_rate=item.vat_rate,
                category=item.category,
                discounts=list(item.discounts),
            )
        )
    return normalized


def _normalized_discounts(parsed_discounts: list[ParsedDiscount]) -> list[NormalizedDiscountRow]:
    rows: list[NormalizedDiscountRow] = []
    for discount in parsed_discounts:
        rows.append(
            NormalizedDiscountRow(
                line_no=discount.line_no,
                type=discount.type,
                amount_cents=discount.amount_cents,
                label=discount.label,
                scope="transaction" if discount.scope == "transaction" else "item",
                subkind=discount.subkind,
                funded_by=discount.funded_by,
            )
        )
    return rows


def _resolved_store_name(summary: Mapping[str, Any], store_name_prefix: str = "Netto Plus") -> str:
    store = summary.get("Filiale") if isinstance(summary.get("Filiale"), Mapping) else {}
    store_name = str(store_name_prefix).strip() or "Netto Plus"
    store_label = str(store.get("Bezeichnung") or "").strip()
    if store_label:
        return f"{store_name} - {store_label}"
    return store_name


def _build_normalized_record(
    record: Mapping[str, Any],
    *,
    store_name_prefix: str = "Netto Plus",
    source_id: str = "netto_plus_de",
) -> tuple[NormalizedReceiptRecord, list[ParsedDiscount], dict[str, Any]]:
    summary = record.get("summary") if isinstance(record.get("summary"), Mapping) else {}
    bon_id = str(summary.get("BonId") or record.get("record_ref") or "").strip()
    if not bon_id:
        raise NettoPlusPluginError("Netto record is missing BonId", code="contract_violation")
    purchased_at = _parse_datetime(summary.get("Einkaufsdatum"))
    parsed_items, parsed_discounts, derived = _parse_receipt_lines(record)
    normalized_items = _normalized_items(bon_id, parsed_items)
    store = summary.get("Filiale") if isinstance(summary.get("Filiale"), Mapping) else {}
    store_name = _resolved_store_name(summary, store_name_prefix)
    fingerprint_basis = f"{bon_id}:{purchased_at.isoformat()}:{summary.get('Bonsumme')}"
    raw_json = {
        "summary": dict(summary),
        "derived": derived,
        "explicit_discounts": [asdict(discount) for discount in parsed_discounts],
        "pdf_text": record.get("pdf_text"),
    }
    return (
        NormalizedReceiptRecord(
            id=bon_id,
            purchased_at=purchased_at,
            store_id=str(store.get("FilialNummer") or source_id),
            store_name=store_name,
            store_address=_store_address(summary),
            total_gross_cents=_money_to_cents(summary.get("Bonsumme")),
            currency="EUR",
            discount_total_cents=_money_to_cents(summary.get("Ersparnis")),
            fingerprint=f"netto_plus_de:{hashlib.sha256(fingerprint_basis.encode('utf-8')).hexdigest()[:24]}",
            items=normalized_items,
            raw_json=raw_json,
        ),
        parsed_discounts,
        derived,
    )


def validate_session_bundle_file(
    bundle_path: str | Path,
    *,
    store_name: str = "Netto Plus",
) -> dict[str, Any]:
    resolved_bundle_path = Path(bundle_path).expanduser().resolve()
    bundle_payload = _read_json(resolved_bundle_path)
    normalized_state = _normalize_bundle(bundle_payload, source_path=resolved_bundle_path)
    receipts_report: list[dict[str, Any]] = []
    manifest = _manifest_definition()
    for record in normalized_state.get("receipts", []):
        normalized_record, parsed_discounts, _derived = _build_normalized_record(
            record,
            store_name_prefix=store_name,
            source_id=str(manifest.get("source_id") or "netto_plus_de"),
        )
        receipts_report.append(
            {
                "record_ref": str(record.get("record_ref")),
                "purchased_at": normalized_record.purchased_at.isoformat(),
                "store_name": normalized_record.store_name,
                "total_gross_cents": normalized_record.total_gross_cents,
                "discount_total_cents": normalized_record.discount_total_cents,
                "item_count": len(normalized_record.items),
                "discount_count": len(parsed_discounts),
                "has_pdf_payload": isinstance(record.get("pdf_payload"), Mapping),
            }
        )
    return {
        "ok": True,
        "bundle_path": str(resolved_bundle_path),
        "schema_version": str(normalized_state.get("schema_version") or "1"),
        "account_email": (
            normalized_state.get("account", {}).get("email")
            if isinstance(normalized_state.get("account"), Mapping)
            else None
        ),
        "receipt_count": len(receipts_report),
        "receipts": receipts_report,
    }


class NettoPlusReceiptPlugin:
    def __init__(self) -> None:
        self._manifest = ConnectorManifest.model_validate(_manifest_definition())

    def invoke_action(
        self,
        request: ReceiptActionRequest | Mapping[str, Any],
    ) -> ReceiptActionResponse | Mapping[str, Any]:
        validated = validate_receipt_action_request(request)
        try:
            if validated.action == "get_manifest":
                return GetManifestResponse(output=GetManifestOutput(manifest=self._manifest))
            if validated.action == "healthcheck":
                return HealthcheckResponse(output=self._healthcheck())
            if validated.action == "get_auth_status":
                return GetAuthStatusResponse(output=self._get_auth_status())
            if validated.action == "start_auth":
                return StartAuthResponse(output=self._start_auth())
            if validated.action == "cancel_auth":
                return CancelAuthResponse(output=self._cancel_auth())
            if validated.action == "confirm_auth":
                return ConfirmAuthResponse(output=self._confirm_auth())
            if validated.action == "discover_records":
                return DiscoverRecordsResponse(output=self._discover_records(validated.input))
            if validated.action == "fetch_record":
                return FetchRecordResponse(output=self._fetch_record(validated.input.record_ref))
            if validated.action == "normalize_record":
                return NormalizeRecordResponse(
                    output=NormalizeRecordOutput(normalized_record=self._normalize_record(validated.input.record))
                )
            if validated.action == "extract_discounts":
                return ExtractDiscountsResponse(
                    output=ExtractDiscountsOutput(discounts=self._extract_discounts(validated.input.record))
                )
            if validated.action == "get_diagnostics":
                return GetDiagnosticsResponse(output=DiagnosticsOutput(diagnostics=self._diagnostics()))
            raise NettoPlusPluginError(
                f"unsupported Netto action: {validated.action}",
                code="unsupported_action",
            )
        except NettoPlusPluginError as exc:
            return {
                "contract_version": validated.contract_version,
                "plugin_family": validated.plugin_family,
                "action": validated.action,
                "ok": False,
                "warnings": (),
                "error": ConnectorError(
                    code=exc.code,  # type: ignore[arg-type]
                    message=str(exc),
                    retryable=exc.retryable,
                ).model_dump(mode="python"),
                "output": None,
            }

    def _healthcheck(self) -> HealthcheckOutput:
        state = _load_imported_state(_state_file_for_context())
        return HealthcheckOutput(
            healthy=state is not None,
            detail=(
                "Netto Plus session bundle is imported."
                if state is not None
                else "Netto Plus requires a captured Android session bundle before sync."
            ),
            sample_size=len(state.get("receipts", [])) if state is not None else 0,
            diagnostics=self._diagnostics(),
        )

    def _get_auth_status(self) -> GetAuthStatusOutput:
        context = load_plugin_runtime_context()
        options = context.connector_options
        state_file = _state_file_for_context()
        state = _load_imported_state(state_file)
        bundle_file = _bundle_file_for_context(options)
        available_actions = ("start_auth",)
        implemented_actions = ("start_auth", "cancel_auth", "confirm_auth")
        reserved_actions = ("start_auth", "cancel_auth", "confirm_auth")
        metadata = {
            "state_file": str(state_file),
            "state_file_present": state is not None,
            "bundle_file": str(bundle_file) if bundle_file is not None else None,
            "bundle_file_present": bundle_file.exists() if bundle_file is not None else False,
        }
        if state is None:
            return GetAuthStatusOutput(
                status="requires_auth",
                is_authenticated=False,
                available_actions=available_actions,
                implemented_actions=implemented_actions,
                compatibility_actions=(),
                reserved_actions=reserved_actions,
                detail=(
                    "Configure a Netto Plus session bundle file and run Set up."
                    if bundle_file is None
                    else "Run Set up to import the configured Netto Plus session bundle."
                ),
                metadata=metadata,
            )
        metadata["receipt_count"] = len(state.get("receipts", []))
        metadata["account_email"] = state.get("account", {}).get("email")
        return GetAuthStatusOutput(
            status="authenticated",
            is_authenticated=True,
            available_actions=available_actions,
            implemented_actions=implemented_actions,
            compatibility_actions=(),
            reserved_actions=reserved_actions,
            detail="Netto Plus session bundle is stored locally.",
            metadata=metadata,
        )

    def _start_auth(self) -> AuthLifecycleOutput:
        context = load_plugin_runtime_context()
        bundle_file = _bundle_file_for_context(context.connector_options)
        if bundle_file is None:
            raise NettoPlusPluginError(
                "Netto Plus start_auth requires session_bundle_file to be configured first.",
                code="auth_required",
            )
        if not bundle_file.exists():
            raise NettoPlusPluginError(
                f"Netto Plus session bundle file does not exist: {bundle_file}",
                code="auth_required",
            )
        bundle_payload = _read_json(bundle_file)
        normalized_state = _normalize_bundle(bundle_payload, source_path=bundle_file)
        state_file = _state_file_for_context()
        _write_json(state_file, normalized_state)
        return AuthLifecycleOutput(
            status="confirmed",
            detail="Imported Netto Plus session bundle into plugin-local state.",
            metadata={
                "state_file": str(state_file),
                "bundle_file": str(bundle_file),
                "receipt_count": len(normalized_state["receipts"]),
            },
        )

    def _cancel_auth(self) -> AuthLifecycleOutput:
        return AuthLifecycleOutput(
            status="no_op",
            detail="Netto Plus session bundle import does not use a pending browser flow.",
        )

    def _confirm_auth(self) -> AuthLifecycleOutput:
        state = _load_imported_state(_state_file_for_context())
        if state is None:
            return AuthLifecycleOutput(
                status="no_op",
                detail="No imported Netto Plus bundle is stored yet.",
            )
        return AuthLifecycleOutput(
            status="confirmed",
            detail="Netto Plus bundle is already imported.",
            metadata={"receipt_count": len(state.get("receipts", []))},
        )

    def _discover_records(self, request_input: Any) -> DiscoverRecordsOutput:
        state = _load_imported_state(_state_file_for_context())
        if state is None:
            raise NettoPlusPluginError(
                "Run Set up to import a Netto Plus session bundle before syncing.",
                code="auth_required",
            )
        receipts = list(state.get("receipts", []))
        filtered: list[dict[str, Any]] = []
        for receipt in receipts:
            summary = receipt.get("summary") if isinstance(receipt.get("summary"), Mapping) else {}
            purchased_at = _parse_datetime(summary.get("Einkaufsdatum"))
            if request_input.window_start and purchased_at < request_input.window_start:
                continue
            if request_input.window_end and purchased_at > request_input.window_end:
                continue
            filtered.append(receipt)
        filtered.sort(
            key=lambda receipt: _parse_datetime(
                (receipt.get("summary") or {}).get("Einkaufsdatum")
            ),
            reverse=True,
        )
        start_index = int(str(request_input.cursor or "0"))
        limit = int(request_input.limit or len(filtered) or 1)
        page = filtered[start_index : start_index + limit]
        next_cursor = (
            str(start_index + limit) if start_index + limit < len(filtered) else None
        )
        records = [
            RecordReference(
                record_ref=str(receipt["record_ref"]),
                discovered_at=_parse_datetime(
                    (receipt.get("summary") or {}).get("Einkaufsdatum")
                ),
                metadata={
                    "store_address": _store_address(
                        receipt.get("summary") if isinstance(receipt.get("summary"), Mapping) else {}
                    ),
                    "source": "session_bundle",
                },
            )
            for receipt in page
        ]
        return DiscoverRecordsOutput(records=records, next_cursor=next_cursor)

    def _fetch_record(self, record_ref: str) -> FetchRecordOutput:
        state = _load_imported_state(_state_file_for_context())
        if state is None:
            raise NettoPlusPluginError(
                "Netto Plus bundle state is missing; run Set up again.",
                code="auth_required",
            )
        for receipt in state.get("receipts", []):
            if str(receipt.get("record_ref")) == record_ref:
                return FetchRecordOutput(record_ref=record_ref, record=dict(receipt))
        raise NettoPlusPluginError(
            f"unknown Netto record_ref: {record_ref}",
            code="invalid_request",
        )

    def _normalize_record(self, record: Mapping[str, Any]) -> NormalizedReceiptRecord:
        context = load_plugin_runtime_context()
        normalized_record, _parsed_discounts, _derived = _build_normalized_record(
            record,
            store_name_prefix=_string_option(context.connector_options, "store_name", "") or "Netto Plus",
            source_id=self._manifest.source_id,
        )
        return normalized_record

    def _extract_discounts(self, record: Mapping[str, Any]) -> list[NormalizedDiscountRow]:
        _items, parsed_discounts, _derived = _parse_receipt_lines(record)
        return _normalized_discounts(parsed_discounts)

    def _diagnostics(self) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        state_file = _state_file_for_context()
        state = _load_imported_state(state_file)
        bundle_file = _bundle_file_for_context(context.connector_options)
        return {
            "plugin_id": self._manifest.plugin_id,
            "source_id": self._manifest.source_id,
            "runtime_kind": self._manifest.runtime_kind,
            "host_kind": context.runtime.host_kind,
            "state_file": str(state_file),
            "state_file_present": state is not None,
            "bundle_file": str(bundle_file) if bundle_file is not None else None,
            "bundle_file_present": bundle_file.exists() if bundle_file is not None else False,
            "receipt_count": len(state.get("receipts", [])) if state is not None else 0,
            "account_email": (
                state.get("account", {}).get("email")
                if state is not None and isinstance(state.get("account"), Mapping)
                else None
            ),
        }
