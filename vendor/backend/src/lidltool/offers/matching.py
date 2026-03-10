from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from lidltool.db.models import Offer, OfferItem, OfferMatch, ProductWatchlist, Transaction, TransactionItem
from lidltool.offers.alerts import emit_alert_event_for_match
from lidltool.offers.models import OfferMatchResult


@dataclass(slots=True)
class _Candidate:
    user_id: str
    offer_id: str
    offer_item_id: str | None
    matched_product_id: str | None
    watchlist_id: str | None = None
    reasons: list[dict[str, Any]] = None  # type: ignore[assignment]
    methods: set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []
        if self.methods is None:
            self.methods = set()


def create_watchlist_entry(
    session: Session,
    *,
    user_id: str,
    product_id: str | None = None,
    query_text: str | None = None,
    source_id: str | None = None,
    min_discount_percent: float | None = None,
    max_price_cents: int | None = None,
    notes: str | None = None,
) -> ProductWatchlist:
    normalized_query = (query_text or "").strip() or None
    if product_id is None and normalized_query is None:
        raise ValueError("watchlist entries require either product_id or query_text")
    if min_discount_percent is not None and min_discount_percent < 0:
        raise ValueError("min_discount_percent must be non-negative")
    if max_price_cents is not None and max_price_cents < 0:
        raise ValueError("max_price_cents must be non-negative")
    watchlist = ProductWatchlist(
        user_id=user_id,
        product_id=product_id,
        query_text=normalized_query,
        source_id=source_id,
        min_discount_percent=min_discount_percent,
        max_price_cents=max_price_cents,
        notes=notes,
        active=True,
    )
    session.add(watchlist)
    session.flush()
    return watchlist


def evaluate_offer_matches(
    session: Session,
    *,
    offer_id: str,
    lookback_days: int = 180,
    emit_alerts: bool = True,
) -> OfferMatchResult:
    offer = session.execute(
        select(Offer)
        .where(Offer.offer_id == offer_id)
        .options(selectinload(Offer.items), selectinload(Offer.offer_source))
    ).scalar_one()

    candidates: dict[tuple[str, str, str | None], _Candidate] = {}
    for item in offer.items:
        _collect_watchlist_candidates(session=session, offer=offer, item=item, candidates=candidates)
        _collect_history_candidates(
            session=session,
            offer=offer,
            item=item,
            candidates=candidates,
            lookback_days=lookback_days,
        )

    result = OfferMatchResult()
    for candidate in candidates.values():
        match_key = _match_key(candidate)
        existing = session.execute(
            select(OfferMatch).where(OfferMatch.match_key == match_key).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            existing.reason_json = _build_reason_payload(offer=offer, item_id=candidate.offer_item_id, candidate=candidate)
            existing.status = existing.status or "pending_alert"
            match = existing
            result.existing += 1
        else:
            match = OfferMatch(
                match_key=match_key,
                offer_id=candidate.offer_id,
                offer_item_id=candidate.offer_item_id,
                user_id=candidate.user_id,
                watchlist_id=candidate.watchlist_id,
                matched_product_id=candidate.matched_product_id,
                match_kind="watchlist"
                if any(reason.get("kind") == "watchlist" for reason in candidate.reasons)
                else "purchase_history",
                match_method="+".join(sorted(candidate.methods)) or "unknown",
                status="pending_alert",
                reason_json=_build_reason_payload(offer=offer, item_id=candidate.offer_item_id, candidate=candidate),
            )
            session.add(match)
            session.flush()
            result.created += 1
        if emit_alerts:
            _, created = emit_alert_event_for_match(session, match=match)
            if created:
                result.alerts_created += 1
    return result


def _collect_watchlist_candidates(
    *,
    session: Session,
    offer: Offer,
    item: OfferItem,
    candidates: dict[tuple[str, str, str | None], _Candidate],
) -> None:
    watchlists = session.execute(
        select(ProductWatchlist).where(ProductWatchlist.active.is_(True))
    ).scalars().all()
    normalized_title = _normalized_text(item.title)
    alias_candidates = {_normalized_text(alias) for alias in item.alias_candidates}
    alias_candidates.discard("")

    for watchlist in watchlists:
        if watchlist.source_id and watchlist.source_id != offer.source_id:
            continue
        matched = False
        method = "watchlist_name"
        if watchlist.product_id and item.canonical_product_id == watchlist.product_id:
            matched = True
            method = "watchlist_product"
        elif watchlist.query_text:
            query = _normalized_text(watchlist.query_text)
            if query and (query == normalized_title or query in alias_candidates):
                matched = True
        if not matched:
            continue
        effective_discount = _effective_discount_percent(offer=offer, item=item)
        effective_price = _effective_price_cents(offer=offer, item=item)
        if watchlist.min_discount_percent is not None and (
            effective_discount is None or effective_discount < watchlist.min_discount_percent
        ):
            continue
        if watchlist.max_price_cents is not None and (
            effective_price is None or effective_price > watchlist.max_price_cents
        ):
            continue
        candidate = _get_candidate(
            candidates=candidates,
            user_id=watchlist.user_id,
            offer_id=offer.offer_id,
            offer_item_id=item.id,
            matched_product_id=item.canonical_product_id or watchlist.product_id,
        )
        candidate.watchlist_id = watchlist.id
        candidate.methods.add(method)
        candidate.reasons.append(
            {
                "kind": "watchlist",
                "watchlist_id": watchlist.id,
                "query_text": watchlist.query_text,
                "product_id": watchlist.product_id,
                "min_discount_percent": watchlist.min_discount_percent,
                "max_price_cents": watchlist.max_price_cents,
            }
        )


def _collect_history_candidates(
    *,
    session: Session,
    offer: Offer,
    item: OfferItem,
    candidates: dict[tuple[str, str, str | None], _Candidate],
    lookback_days: int,
) -> None:
    if item.canonical_product_id is None:
        return
    cutoff = datetime.now(tz=UTC) - timedelta(days=max(lookback_days, 1))
    rows = session.execute(
        select(
            Transaction.user_id,
            func.count(func.distinct(Transaction.id)),
            func.max(Transaction.purchased_at),
        )
        .join(TransactionItem, TransactionItem.transaction_id == Transaction.id)
        .where(
            Transaction.user_id.is_not(None),
            TransactionItem.product_id == item.canonical_product_id,
            Transaction.purchased_at >= cutoff,
        )
        .group_by(Transaction.user_id)
    ).all()
    for user_id, purchase_count, last_purchased_at in rows:
        if user_id is None:
            continue
        candidate = _get_candidate(
            candidates=candidates,
            user_id=str(user_id),
            offer_id=offer.offer_id,
            offer_item_id=item.id,
            matched_product_id=item.canonical_product_id,
        )
        candidate.methods.add("purchase_history")
        candidate.reasons.append(
            {
                "kind": "purchase_history",
                "product_id": item.canonical_product_id,
                "purchase_count": int(purchase_count or 0),
                "last_purchased_at": last_purchased_at.isoformat() if last_purchased_at else None,
                "lookback_days": lookback_days,
            }
        )


def _get_candidate(
    *,
    candidates: dict[tuple[str, str, str | None], _Candidate],
    user_id: str,
    offer_id: str,
    offer_item_id: str | None,
    matched_product_id: str | None,
) -> _Candidate:
    key = (user_id, offer_item_id or offer_id, matched_product_id)
    candidate = candidates.get(key)
    if candidate is None:
        candidate = _Candidate(
            user_id=user_id,
            offer_id=offer_id,
            offer_item_id=offer_item_id,
            matched_product_id=matched_product_id,
        )
        candidates[key] = candidate
    return candidate


def _build_reason_payload(*, offer: Offer, item_id: str | None, candidate: _Candidate) -> dict[str, Any]:
    item = next((entry for entry in offer.items if entry.id == item_id), None)
    title = item.title if item is not None else offer.title
    summary = f"Matched {title} from {offer.offer_source.merchant_name}"
    return {
        "title": "Matched offer",
        "summary": summary,
        "offer_id": offer.offer_id,
        "offer_item_id": item_id,
        "offer_title": offer.title,
        "item_title": title,
        "merchant_name": offer.offer_source.merchant_name,
        "source_id": offer.source_id,
        "validity_end": offer.validity_end.isoformat(),
        "reasons": list(candidate.reasons),
    }


def _effective_discount_percent(*, offer: Offer, item: OfferItem) -> float | None:
    if item.discount_percent is not None:
        return float(item.discount_percent)
    if offer.discount_percent is not None:
        return float(offer.discount_percent)
    if item.price_cents is not None and item.original_price_cents:
        return round((1 - (item.price_cents / item.original_price_cents)) * 100, 3)
    if offer.price_cents is not None and offer.original_price_cents:
        return round((1 - (offer.price_cents / offer.original_price_cents)) * 100, 3)
    return None


def _effective_price_cents(*, offer: Offer, item: OfferItem) -> int | None:
    return item.price_cents if item.price_cents is not None else offer.price_cents


def _match_key(candidate: _Candidate) -> str:
    return "|".join(
        [
            candidate.user_id,
            candidate.offer_id,
            candidate.offer_item_id or "offer",
            candidate.matched_product_id or "unknown-product",
        ]
    )


def _normalized_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())
