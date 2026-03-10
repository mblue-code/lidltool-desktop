from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.offer import (
    DiscoverOffersInput,
    DiscoverOffersRequest,
    DiscoverOffersResponse,
    FetchOfferDetailInput,
    FetchOfferDetailRequest,
    FetchOfferDetailResponse,
    NormalizedOfferRecord,
    NormalizeOfferInput,
    NormalizeOfferRequest,
    NormalizeOfferResponse,
    OfferConnector,
    validate_offer_action_response,
)
from lidltool.db.models import Offer, OfferItem, OfferSource
from lidltool.ingest.json_payloads import make_json_safe
from lidltool.offers.matching import evaluate_offer_matches
from lidltool.offers.models import OfferIngestItemResult, OfferIngestResult
from lidltool.offers.validation import validate_normalized_offer_payload


def ingest_normalized_offers(
    session: Session,
    *,
    plugin_id: str,
    source_id: str,
    offers: Sequence[NormalizedOfferRecord | Mapping[str, Any]],
    run_matching: bool = True,
) -> OfferIngestResult:
    result = OfferIngestResult()
    validation_outcomes: Counter[str] = Counter()
    validation_issue_codes: Counter[str] = Counter()

    for raw_offer in offers:
        payload = (
            raw_offer
            if isinstance(raw_offer, NormalizedOfferRecord)
            else NormalizedOfferRecord.model_validate(dict(raw_offer))
        )
        result.offers_seen += 1
        report = validate_normalized_offer_payload(
            source_offer_ref=payload.source_offer_id,
            source_offer_detail=payload.raw_payload,
            connector_normalized=payload.model_dump(mode="python"),
        )
        validation_outcomes[report.outcome.value] += 1
        for issue in report.issues:
            validation_issue_codes[issue.code] += 1

        if report.outcome.value in {"quarantine", "reject"}:
            result.blocked += 1
            result.blocked_outputs.append(
                {
                    "source_offer_id": payload.source_offer_id,
                    "fingerprint": payload.fingerprint,
                    "outcome": report.outcome.value,
                    "issue_codes": [issue.code for issue in report.issues],
                }
            )
            result.items.append(
                OfferIngestItemResult(
                    fingerprint=payload.fingerprint,
                    offer_id=None,
                    status=report.outcome.value,
                    issue_codes=[issue.code for issue in report.issues],
                )
            )
            continue

        if report.outcome.value == "warn":
            result.warnings.append(
                f"offer {payload.source_offer_id} ingested with warnings: "
                + ", ".join(issue.code for issue in report.issues)
            )

        source_row = _upsert_offer_source(
            session,
            plugin_id=plugin_id,
            source_id=source_id,
            offer=payload,
        )
        offer_row, created = _upsert_offer(
            session,
            source_row=source_row,
            plugin_id=plugin_id,
            source_id=source_id,
            offer=payload,
        )
        if created:
            result.inserted += 1
        else:
            result.updated += 1

        match_result = evaluate_offer_matches(session, offer_id=offer_row.offer_id) if run_matching else None
        if match_result is not None:
            result.matched += match_result.created + match_result.existing
            result.alerts_created += match_result.alerts_created

        result.items.append(
            OfferIngestItemResult(
                fingerprint=payload.fingerprint,
                offer_id=offer_row.offer_id,
                status="inserted" if created else "updated",
                issue_codes=[issue.code for issue in report.issues],
            )
        )

    result.validation = {
        "outcomes": dict(validation_outcomes),
        "issue_codes": dict(validation_issue_codes),
    }
    return result


def ingest_offers_from_connector(
    session: Session,
    *,
    connector: OfferConnector,
    manifest: ConnectorManifest,
    discovery_limit: int | None = None,
    run_matching: bool = True,
) -> OfferIngestResult:
    discover_response = validate_offer_action_response(
        connector.invoke_action(
            DiscoverOffersRequest(input=DiscoverOffersInput(limit=discovery_limit))
        )
    )
    discover_payload = DiscoverOffersResponse.model_validate(discover_response)
    if discover_payload.output is None:
        return OfferIngestResult()

    normalized_offers: list[NormalizedOfferRecord] = []
    for offer_ref in discover_payload.output.offers:
        detail_response = validate_offer_action_response(
            connector.invoke_action(
                FetchOfferDetailRequest(input=FetchOfferDetailInput(offer_ref=offer_ref.offer_ref))
            )
        )
        fetch_payload = FetchOfferDetailResponse.model_validate(detail_response)
        if fetch_payload.output is None:
            continue
        normalize_response = validate_offer_action_response(
            connector.invoke_action(
                NormalizeOfferRequest(
                    input=NormalizeOfferInput(offer=fetch_payload.output.offer)
                )
            )
        )
        normalized_payload = NormalizeOfferResponse.model_validate(normalize_response)
        if normalized_payload.output is None:
            continue
        normalized_offers.append(normalized_payload.output.normalized_offer)

    return ingest_normalized_offers(
        session,
        plugin_id=manifest.plugin_id,
        source_id=manifest.source_id,
        offers=normalized_offers,
        run_matching=run_matching,
    )


def _upsert_offer_source(
    session: Session,
    *,
    plugin_id: str,
    source_id: str,
    offer: NormalizedOfferRecord,
) -> OfferSource:
    scope_key = _scope_key(
        plugin_id=plugin_id,
        source_id=source_id,
        merchant_id=offer.merchant_id,
        country_code=offer.scope.country_code,
        region_code=offer.scope.region_code,
        store_id=offer.scope.store_id,
    )
    source_row = session.execute(
        select(OfferSource).where(OfferSource.scope_key == scope_key).limit(1)
    ).scalar_one_or_none()
    if source_row is None:
        source_row = OfferSource(
            plugin_id=plugin_id,
            source_id=source_id,
            merchant_name=offer.merchant_name,
            merchant_id=offer.merchant_id,
            country_code=offer.scope.country_code,
            region_code=offer.scope.region_code,
            store_id=offer.scope.store_id,
            store_name=offer.scope.store_name,
            scope_key=scope_key,
            raw_scope_payload=make_json_safe(offer.scope.model_dump(mode="python")),
        )
        session.add(source_row)
        session.flush()
        return source_row
    source_row.merchant_name = offer.merchant_name
    source_row.merchant_id = offer.merchant_id
    source_row.country_code = offer.scope.country_code
    source_row.region_code = offer.scope.region_code
    source_row.store_id = offer.scope.store_id
    source_row.store_name = offer.scope.store_name
    source_row.raw_scope_payload = make_json_safe(offer.scope.model_dump(mode="python"))
    return source_row


def _upsert_offer(
    session: Session,
    *,
    source_row: OfferSource,
    plugin_id: str,
    source_id: str,
    offer: NormalizedOfferRecord,
) -> tuple[Offer, bool]:
    existing = session.execute(
        select(Offer)
        .where(Offer.fingerprint == offer.fingerprint)
        .options(selectinload(Offer.items))
        .limit(1)
    ).scalar_one_or_none()
    created = existing is None
    offer_row = existing or Offer(
        offer_source_id=source_row.id,
        plugin_id=plugin_id,
        source_id=source_id,
        source_offer_id=offer.source_offer_id,
        fingerprint=offer.fingerprint,
        title=offer.title,
        summary=offer.summary,
        offer_type=offer.offer_type,
        status=_offer_status(offer.validity_end),
        currency=offer.currency,
        price_cents=offer.price_cents,
        original_price_cents=offer.original_price_cents,
        discount_percent=offer.discount_percent,
        bundle_terms=offer.bundle_terms,
        offer_url=offer.offer_url,
        image_url=offer.image_url,
        validity_start=offer.validity_start,
        validity_end=offer.validity_end,
        raw_payload=make_json_safe(offer.raw_payload),
        normalized_payload=make_json_safe(offer.model_dump(mode="python")),
        last_seen_at=datetime.now(tz=UTC),
    )
    if created:
        session.add(offer_row)
        session.flush()

    offer_row.offer_source_id = source_row.id
    offer_row.plugin_id = plugin_id
    offer_row.source_id = source_id
    offer_row.source_offer_id = offer.source_offer_id
    offer_row.title = offer.title
    offer_row.summary = offer.summary
    offer_row.offer_type = offer.offer_type
    offer_row.status = _offer_status(offer.validity_end)
    offer_row.currency = offer.currency
    offer_row.price_cents = offer.price_cents
    offer_row.original_price_cents = offer.original_price_cents
    offer_row.discount_percent = offer.discount_percent
    offer_row.bundle_terms = offer.bundle_terms
    offer_row.offer_url = offer.offer_url
    offer_row.image_url = offer.image_url
    offer_row.validity_start = offer.validity_start
    offer_row.validity_end = offer.validity_end
    offer_row.raw_payload = make_json_safe(offer.raw_payload)
    offer_row.normalized_payload = make_json_safe(offer.model_dump(mode="python"))
    offer_row.last_seen_at = datetime.now(tz=UTC)

    existing_items = {item.line_no: item for item in offer_row.items}
    seen_lines: set[int] = set()
    for item in offer.items:
        seen_lines.add(item.line_no)
        item_row = existing_items.get(item.line_no)
        if item_row is None:
            item_row = OfferItem(
                offer_id=offer_row.offer_id,
                line_no=item.line_no,
                alias_candidates=list(item.alias_candidates),
            )
            session.add(item_row)
            offer_row.items.append(item_row)
        item_row.source_item_id = item.source_item_id
        item_row.title = item.title
        item_row.brand = item.brand
        item_row.canonical_product_id = item.canonical_product_id
        item_row.gtin_ean = item.gtin_ean
        item_row.alias_candidates = list(item.alias_candidates)
        item_row.quantity_text = item.quantity_text
        item_row.unit = item.unit
        item_row.size_text = item.size_text
        item_row.price_cents = item.price_cents
        item_row.original_price_cents = item.original_price_cents
        item_row.discount_percent = item.discount_percent
        item_row.bundle_terms = item.bundle_terms
        item_row.raw_payload = make_json_safe(item.raw_payload)
    for line_no, item_row in list(existing_items.items()):
        if line_no not in seen_lines:
            offer_row.items.remove(item_row)
            session.delete(item_row)

    session.flush()
    return offer_row, created


def derive_offer_fingerprint(
    *,
    source_id: str,
    source_offer_id: str,
    merchant_name: str,
    title: str,
    validity_start: datetime,
    validity_end: datetime,
) -> str:
    payload = "|".join(
        [
            source_id.strip(),
            source_offer_id.strip(),
            merchant_name.strip().lower(),
            title.strip().lower(),
            validity_start.astimezone(UTC).isoformat(),
            validity_end.astimezone(UTC).isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scope_key(
    *,
    plugin_id: str,
    source_id: str,
    merchant_id: str | None,
    country_code: str,
    region_code: str | None,
    store_id: str | None,
) -> str:
    return "|".join(
        [
            plugin_id,
            source_id,
            merchant_id or "merchant",
            country_code,
            region_code or "region",
            store_id or "store",
        ]
    )


def _offer_status(validity_end: datetime) -> str:
    now = datetime.now(tz=UTC)
    if validity_end.tzinfo is None:
        validity_end = validity_end.replace(tzinfo=UTC)
    else:
        validity_end = validity_end.astimezone(UTC)
    return "expired" if validity_end < now else "active"
