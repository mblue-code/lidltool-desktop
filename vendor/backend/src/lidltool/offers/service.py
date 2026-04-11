from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from lidltool.config import AppConfig
from lidltool.db.models import (
    AlertEvent,
    Offer,
    OfferMatch,
    OfferRefreshRun,
    OfferSource,
    OfferSourceConfig,
    Product,
    ProductWatchlist,
    Transaction,
    TransactionItem,
)
from lidltool.offers.agent_runtime import discover_offers_from_source
from lidltool.offers.ingest import ingest_normalized_offers
from lidltool.offers.matching import create_watchlist_entry
from lidltool.offers.models import OfferIngestResult


def offer_overview(session: Session, *, config: AppConfig, user_id: str) -> dict[str, Any]:
    _refresh_offer_statuses(session)
    unread_alerts = int(
        session.execute(
            select(func.count(AlertEvent.id)).where(
                AlertEvent.user_id == user_id,
                AlertEvent.event_type == "offer_match",
                AlertEvent.read_at.is_(None),
            )
        ).scalar_one()
    )
    active_matches = int(
        session.execute(
            select(func.count(OfferMatch.id))
            .join(Offer, Offer.offer_id == OfferMatch.offer_id)
            .where(
                OfferMatch.user_id == user_id,
                Offer.status == "active",
                Offer.validity_end >= datetime.now(tz=UTC),
            )
        ).scalar_one()
    )
    watchlists = int(
        session.execute(
            select(func.count(ProductWatchlist.id)).where(
                ProductWatchlist.user_id == user_id,
                ProductWatchlist.active.is_(True),
            )
        ).scalar_one()
    )
    recent_runs = list_refresh_runs(session, user_id=user_id, limit=10)
    return {
        "counts": {
            "watchlists": watchlists,
            "active_matches": active_matches,
            "unread_alerts": unread_alerts,
        },
        "sources": list_offer_sources(session, user_id=user_id),
        "recent_refresh_runs": recent_runs["items"],
        "last_refresh_at": (
            recent_runs["items"][0]["finished_at"]
            if recent_runs["items"]
            else None
        ),
    }


def list_offer_sources(session: Session, *, user_id: str) -> list[dict[str, Any]]:
    _refresh_offer_statuses(session)
    counts = {
        source_id: {
            "active_offer_count": int(active_offer_count),
            "total_offer_count": int(total_offer_count),
        }
        for source_id, active_offer_count, total_offer_count in session.execute(
            select(
                Offer.source_id,
                func.sum(case((Offer.status == "active", 1), else_=0)),
                func.count(Offer.offer_id),
            ).group_by(Offer.source_id)
        ).all()
    }

    latest_by_source: dict[str, dict[str, Any]] = {}
    recent_runs = session.execute(
        select(OfferRefreshRun).order_by(OfferRefreshRun.created_at.desc()).limit(50)
    ).scalars().all()
    for run in recent_runs:
        run_payload = serialize_refresh_run(run)
        for source_result in run_payload.get("source_results", []):
            source_id = source_result.get("source_id")
            if not isinstance(source_id, str) or source_id in latest_by_source:
                continue
            latest_by_source[source_id] = source_result

    sources: list[dict[str, Any]] = []
    rows = session.execute(
        select(OfferSourceConfig)
        .where(OfferSourceConfig.user_id == user_id)
        .order_by(OfferSourceConfig.created_at.desc(), OfferSourceConfig.id.desc())
    ).scalars().all()
    for source in rows:
        source_counts = counts.get(source.source_id, {"active_offer_count": 0, "total_offer_count": 0})
        sources.append(
            {
                "id": source.id,
                "source_id": source.source_id,
                "plugin_id": "agent.user_defined",
                "display_name": source.display_name,
                "merchant_name": source.merchant_name,
                "country_code": source.country_code,
                "runtime_kind": "agent_url",
                "merchant_url": source.merchant_url,
                "active": source.active,
                "notes": source.notes,
                "active_offer_count": source_counts["active_offer_count"],
                "total_offer_count": source_counts["total_offer_count"],
                "latest_refresh": latest_by_source.get(source.source_id),
                "created_at": source.created_at.isoformat(),
                "updated_at": source.updated_at.isoformat(),
            }
        )
    return sources


def create_offer_source(
    session: Session,
    *,
    user_id: str,
    merchant_name: str,
    merchant_url: str,
    display_name: str | None = None,
    country_code: str = "DE",
    notes: str | None = None,
) -> dict[str, Any]:
    normalized_name = merchant_name.strip()
    normalized_url = merchant_url.strip()
    if not normalized_name:
        raise RuntimeError("merchant_name is required")
    if not normalized_url:
        raise RuntimeError("merchant_url is required")
    normalized_country = (country_code or "DE").strip().upper() or "DE"
    source_id = _build_source_id(merchant_name=normalized_name, merchant_url=normalized_url)
    existing = session.execute(
        select(OfferSourceConfig)
        .where(OfferSourceConfig.user_id == user_id, OfferSourceConfig.source_id == source_id)
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        existing.display_name = (display_name or normalized_name).strip() or normalized_name
        existing.merchant_name = normalized_name
        existing.merchant_url = normalized_url
        existing.country_code = normalized_country
        existing.notes = (notes or "").strip() or None
        existing.active = True
        existing.updated_at = datetime.now(tz=UTC)
        session.flush()
        session.refresh(existing)
        return serialize_offer_source(existing)

    source = OfferSourceConfig(
        user_id=user_id,
        source_id=source_id,
        display_name=(display_name or normalized_name).strip() or normalized_name,
        merchant_name=normalized_name,
        merchant_url=normalized_url,
        country_code=normalized_country,
        notes=(notes or "").strip() or None,
        active=True,
    )
    session.add(source)
    session.flush()
    session.refresh(source)
    return serialize_offer_source(source)


def update_offer_source(
    session: Session,
    *,
    user_id: str,
    source_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    source = _owned_offer_source(session, user_id=user_id, source_id=source_id)
    if "display_name" in payload:
        source.display_name = str(payload.get("display_name") or "").strip() or source.display_name
    if "merchant_name" in payload:
        merchant_name = str(payload.get("merchant_name") or "").strip()
        if merchant_name:
            source.merchant_name = merchant_name
    if "merchant_url" in payload:
        merchant_url = str(payload.get("merchant_url") or "").strip()
        if not merchant_url:
            raise RuntimeError("merchant_url is required")
        source.merchant_url = merchant_url
    if "country_code" in payload:
        source.country_code = str(payload.get("country_code") or "DE").strip().upper() or "DE"
    if "notes" in payload:
        source.notes = str(payload.get("notes") or "").strip() or None
    if "active" in payload:
        source.active = bool(payload.get("active"))
    source.updated_at = datetime.now(tz=UTC)
    session.flush()
    session.refresh(source)
    return serialize_offer_source(source)


def delete_offer_source(
    session: Session,
    *,
    user_id: str,
    source_id: str,
) -> dict[str, Any]:
    source = _owned_offer_source(session, user_id=user_id, source_id=source_id)
    session.execute(
        delete(ProductWatchlist)
        .where(ProductWatchlist.user_id == user_id, ProductWatchlist.source_id == source.source_id)
    )
    session.execute(delete(Offer).where(Offer.source_id == source.source_id))
    session.execute(delete(OfferSource).where(OfferSource.source_id == source.source_id))
    session.delete(source)
    return {"deleted": True, "source_id": source_id}


def list_merchant_items(
    session: Session,
    *,
    user_id: str,
    merchant_name: str,
    limit: int = 100,
) -> dict[str, Any]:
    normalized = merchant_name.strip().lower()
    if not normalized:
        return {"count": 0, "items": []}
    clamped_limit = min(max(limit, 1), 200)
    rows = session.execute(
        select(
            Product.product_id,
            Product.canonical_name,
            TransactionItem.name,
            func.count(TransactionItem.id),
            func.max(Transaction.purchased_at),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .outerjoin(Product, Product.product_id == TransactionItem.product_id)
        .where(
            Transaction.user_id == user_id,
            func.lower(func.coalesce(Transaction.merchant_name, "")).like(f"%{normalized}%"),
        )
        .group_by(Product.product_id, Product.canonical_name, TransactionItem.name)
        .order_by(func.count(TransactionItem.id).desc(), func.max(Transaction.purchased_at).desc())
        .limit(clamped_limit)
    ).all()
    items = [
        {
            "product_id": product_id,
            "product_name": canonical_name,
            "item_name": item_name,
            "label": canonical_name or item_name,
            "purchase_count": int(purchase_count),
            "last_purchased_at": last_purchased_at.isoformat() if last_purchased_at is not None else None,
        }
        for product_id, canonical_name, item_name, purchase_count, last_purchased_at in rows
    ]
    return {"count": len(items), "items": items}


def create_watchlist(
    session: Session,
    *,
    user_id: str,
    product_id: str | None = None,
    query_text: str | None = None,
    source_id: str | None = None,
    min_discount_percent: float | None = None,
    max_price_cents: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if source_id:
        _owned_offer_source(session, user_id=user_id, source_id=source_id)
    watchlist = create_watchlist_entry(
        session,
        user_id=user_id,
        product_id=product_id,
        query_text=query_text,
        source_id=source_id,
        min_discount_percent=min_discount_percent,
        max_price_cents=max_price_cents,
        notes=notes,
    )
    session.refresh(watchlist)
    return serialize_watchlist(watchlist)


def list_watchlists(
    session: Session,
    *,
    user_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    clamped_limit = min(max(limit, 1), 200)
    clamped_offset = max(offset, 0)
    stmt = (
        select(ProductWatchlist)
        .where(ProductWatchlist.user_id == user_id)
        .options(selectinload(ProductWatchlist.product))
        .order_by(ProductWatchlist.created_at.desc(), ProductWatchlist.id.desc())
    )
    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = session.execute(stmt.limit(clamped_limit).offset(clamped_offset)).scalars().all()
    items = [serialize_watchlist(row) for row in rows]
    return {
        "count": len(rows),
        "limit": clamped_limit,
        "offset": clamped_offset,
        "total": total,
        "items": items,
        "watchlists": items,
        "pagination": {
            "count": len(rows),
            "total": total,
            "limit": clamped_limit,
            "offset": clamped_offset,
        },
    }


def update_watchlist(
    session: Session,
    *,
    user_id: str,
    watchlist_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    watchlist = _owned_watchlist(session, user_id=user_id, watchlist_id=watchlist_id)
    if "product_id" in payload:
        watchlist.product_id = payload.get("product_id")
    if "query_text" in payload:
        query = str(payload.get("query_text") or "").strip()
        watchlist.query_text = query or None
    if "source_id" in payload:
        source = str(payload.get("source_id") or "").strip()
        if source:
            _owned_offer_source(session, user_id=user_id, source_id=source)
        watchlist.source_id = source or None
    if "min_discount_percent" in payload:
        value = payload.get("min_discount_percent")
        watchlist.min_discount_percent = float(value) if value is not None else None
    if "max_price_cents" in payload:
        value = payload.get("max_price_cents")
        watchlist.max_price_cents = int(value) if value is not None else None
    if "notes" in payload:
        notes = str(payload.get("notes") or "").strip()
        watchlist.notes = notes or None
    if "active" in payload:
        watchlist.active = bool(payload.get("active"))
    if watchlist.product_id is None and not (watchlist.query_text or "").strip():
        raise RuntimeError("watchlist entries require either product_id or query_text")
    watchlist.updated_at = datetime.now(tz=UTC)
    session.flush()
    session.refresh(watchlist)
    return serialize_watchlist(watchlist)


def delete_watchlist(session: Session, *, user_id: str, watchlist_id: str) -> dict[str, Any]:
    watchlist = _owned_watchlist(session, user_id=user_id, watchlist_id=watchlist_id)
    result = {"deleted": True, "id": watchlist.id}
    session.delete(watchlist)
    return result


def list_matches(
    session: Session,
    *,
    user_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    _refresh_offer_statuses(session)
    clamped_limit = min(max(limit, 1), 200)
    clamped_offset = max(offset, 0)
    stmt = (
        select(OfferMatch)
        .join(Offer, Offer.offer_id == OfferMatch.offer_id)
        .where(
            OfferMatch.user_id == user_id,
            Offer.status == "active",
            Offer.validity_end >= datetime.now(tz=UTC),
        )
        .options(
            selectinload(OfferMatch.offer).selectinload(Offer.offer_source),
            selectinload(OfferMatch.offer_item),
            selectinload(OfferMatch.watchlist).selectinload(ProductWatchlist.product),
            selectinload(OfferMatch.matched_product),
            selectinload(OfferMatch.alert_events),
        )
        .order_by(Offer.validity_end.asc(), OfferMatch.created_at.desc())
    )
    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    matches = session.execute(stmt.limit(clamped_limit).offset(clamped_offset)).scalars().all()
    items = [serialize_match(match) for match in matches]
    return {
        "count": len(matches),
        "limit": clamped_limit,
        "offset": clamped_offset,
        "total": total,
        "items": items,
        "matches": items,
        "pagination": {
            "count": len(matches),
            "total": total,
            "limit": clamped_limit,
            "offset": clamped_offset,
        },
    }


def list_alerts(
    session: Session,
    *,
    user_id: str,
    unread_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    clamped_limit = min(max(limit, 1), 200)
    clamped_offset = max(offset, 0)
    stmt = (
        select(AlertEvent)
        .where(
            AlertEvent.user_id == user_id,
            AlertEvent.event_type == "offer_match",
        )
        .options(
            selectinload(AlertEvent.offer_match)
            .selectinload(OfferMatch.offer)
            .selectinload(Offer.offer_source),
            selectinload(AlertEvent.offer_match).selectinload(OfferMatch.offer_item),
            selectinload(AlertEvent.offer_match).selectinload(OfferMatch.alert_events),
            selectinload(AlertEvent.offer_match).selectinload(OfferMatch.watchlist),
            selectinload(AlertEvent.offer_match).selectinload(OfferMatch.matched_product),
        )
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
    )
    if unread_only:
        stmt = stmt.where(AlertEvent.read_at.is_(None))
    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    alerts = session.execute(stmt.limit(clamped_limit).offset(clamped_offset)).scalars().all()
    unread_count = int(
        session.execute(
            select(func.count(AlertEvent.id)).where(
                AlertEvent.user_id == user_id,
                AlertEvent.event_type == "offer_match",
                AlertEvent.read_at.is_(None),
            )
        ).scalar_one()
    )
    items = [serialize_alert(alert) for alert in alerts]
    return {
        "count": len(alerts),
        "limit": clamped_limit,
        "offset": clamped_offset,
        "total": total,
        "items": items,
        "alerts": items,
        "unread_count": unread_count,
        "pagination": {
            "count": len(alerts),
            "total": total,
            "limit": clamped_limit,
            "offset": clamped_offset,
        },
    }


def mark_alert_read(
    session: Session,
    *,
    user_id: str,
    alert_id: str,
    read: bool = True,
) -> dict[str, Any]:
    alert = session.get(AlertEvent, alert_id)
    if alert is None or alert.user_id != user_id or alert.event_type != "offer_match":
        raise RuntimeError("offer alert not found")
    alert.read_at = datetime.now(tz=UTC) if read else None
    alert.status = "read" if read else "pending"
    alert.updated_at = datetime.now(tz=UTC)
    session.flush()
    session.refresh(alert)
    return serialize_alert(alert)


def run_offer_refresh(
    session: Session,
    *,
    config: AppConfig,
    source_ids: list[str] | None = None,
    requested_by_user_id: str | None = None,
    trigger_kind: str = "manual",
    automation_rule_id: str | None = None,
    discovery_limit: int | None = None,
) -> dict[str, Any]:
    _refresh_offer_statuses(session)
    stmt = select(OfferSourceConfig).where(OfferSourceConfig.active.is_(True))
    if requested_by_user_id is not None:
        stmt = stmt.where(OfferSourceConfig.user_id == requested_by_user_id)
    available_sources = {
        source.source_id: source
        for source in session.execute(stmt).scalars().all()
    }
    selected_source_ids = list(source_ids or available_sources.keys())
    if not selected_source_ids:
        raise RuntimeError("no offer sources have been added yet")
    invalid_sources = sorted(source_id for source_id in selected_source_ids if source_id not in available_sources)
    if invalid_sources:
        raise RuntimeError(f"unknown offer source(s): {', '.join(invalid_sources)}")

    now = datetime.now(tz=UTC)
    run = OfferRefreshRun(
        user_id=requested_by_user_id,
        rule_id=automation_rule_id,
        trigger_kind=trigger_kind,
        status="running",
        source_count=len(selected_source_ids),
        source_ids_json=list(selected_source_ids),
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()

    results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0
    totals = {
        "offers_seen": 0,
        "inserted": 0,
        "updated": 0,
        "blocked": 0,
        "matched": 0,
        "alerts_created": 0,
    }
    for source_id in selected_source_ids:
        source = available_sources[source_id]
        try:
            normalized_offers = discover_offers_from_source(
                config=config,
                source=source,
                discovery_limit=discovery_limit,
            )
            ingest_result = ingest_normalized_offers(
                session,
                plugin_id="agent.user_defined",
                source_id=source_id,
                config=config,
                offers=normalized_offers,
                run_matching=True,
            )
            serialized = _serialize_ingest_result(source_id=source_id, result=ingest_result)
            serialized["status"] = "success"
            results.append(serialized)
            success_count += 1
            for key in totals:
                totals[key] += int(serialized.get(key, 0))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "source_id": source_id,
                    "status": "failed",
                    "error": str(exc),
                    "offers_seen": 0,
                    "inserted": 0,
                    "updated": 0,
                    "blocked": 0,
                    "matched": 0,
                    "alerts_created": 0,
                }
            )
            failure_count += 1

    if success_count and failure_count:
        status = "partial_success"
    elif success_count:
        status = "success"
    else:
        status = "failed"

    run.status = status
    run.finished_at = datetime.now(tz=UTC)
    run.updated_at = datetime.now(tz=UTC)
    run.error = None if failure_count == 0 else f"{failure_count} source refresh(es) failed"
    run.result_json = {
        "success_count": success_count,
        "failure_count": failure_count,
        "totals": totals,
        "sources": results,
    }
    session.flush()
    session.refresh(run)
    return serialize_refresh_run(run)


def list_refresh_runs(
    session: Session,
    *,
    user_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    clamped_limit = min(max(limit, 1), 100)
    clamped_offset = max(offset, 0)
    stmt = select(OfferRefreshRun).order_by(
        OfferRefreshRun.created_at.desc(),
        OfferRefreshRun.id.desc(),
    )
    if user_id is not None:
        stmt = stmt.where(
            or_(OfferRefreshRun.user_id == user_id, OfferRefreshRun.user_id.is_(None))
        )
    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    runs = session.execute(stmt.limit(clamped_limit).offset(clamped_offset)).scalars().all()
    items = [serialize_refresh_run(run) for run in runs]
    return {
        "count": len(runs),
        "limit": clamped_limit,
        "offset": clamped_offset,
        "total": total,
        "items": items,
        "refresh_runs": items,
        "pagination": {
            "count": len(runs),
            "total": total,
            "limit": clamped_limit,
            "offset": clamped_offset,
        },
    }


def serialize_watchlist(watchlist: ProductWatchlist) -> dict[str, Any]:
    return {
        "id": watchlist.id,
        "user_id": watchlist.user_id,
        "product_id": watchlist.product_id,
        "product_name": watchlist.product.canonical_name if watchlist.product is not None else None,
        "query_text": watchlist.query_text,
        "source_id": watchlist.source_id,
        "min_discount_percent": watchlist.min_discount_percent,
        "max_price_cents": watchlist.max_price_cents,
        "active": watchlist.active,
        "notes": watchlist.notes,
        "created_at": watchlist.created_at.isoformat(),
        "updated_at": watchlist.updated_at.isoformat(),
    }


def serialize_offer_source(source: OfferSourceConfig) -> dict[str, Any]:
    return {
        "id": source.id,
        "source_id": source.source_id,
        "plugin_id": "agent.user_defined",
        "display_name": source.display_name,
        "merchant_name": source.merchant_name,
        "country_code": source.country_code,
        "runtime_kind": "agent_url",
        "merchant_url": source.merchant_url,
        "active": source.active,
        "notes": source.notes,
        "active_offer_count": 0,
        "total_offer_count": 0,
        "latest_refresh": None,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
    }


def serialize_match(match: OfferMatch) -> dict[str, Any]:
    offer = match.offer
    item = match.offer_item
    unread_alert_count = sum(1 for alert in match.alert_events if alert.read_at is None)
    return {
        "id": match.id,
        "status": match.status,
        "match_kind": match.match_kind,
        "match_method": match.match_method,
        "matched_product_id": match.matched_product_id,
        "matched_product_name": (
            match.matched_product.canonical_name if match.matched_product is not None else None
        ),
        "watchlist": (
            serialize_watchlist(match.watchlist) if match.watchlist is not None else None
        ),
        "offer": {
            "offer_id": offer.offer_id,
            "source_id": offer.source_id,
            "merchant_name": offer.offer_source.merchant_name,
            "title": offer.title,
            "summary": offer.summary,
            "offer_type": offer.offer_type,
            "price_cents": item.price_cents if item is not None and item.price_cents is not None else offer.price_cents,
            "original_price_cents": (
                item.original_price_cents
                if item is not None and item.original_price_cents is not None
                else offer.original_price_cents
            ),
            "discount_percent": (
                item.discount_percent
                if item is not None and item.discount_percent is not None
                else offer.discount_percent
            ),
            "offer_url": offer.offer_url,
            "image_url": offer.image_url,
            "validity_start": offer.validity_start.isoformat(),
            "validity_end": offer.validity_end.isoformat(),
            "item_title": item.title if item is not None else None,
        },
        "reason": match.reason_json,
        "unread_alert_count": unread_alert_count,
        "created_at": match.created_at.isoformat(),
        "updated_at": match.updated_at.isoformat(),
    }


def serialize_alert(alert: AlertEvent) -> dict[str, Any]:
    return {
        "id": alert.id,
        "status": alert.status,
        "event_type": alert.event_type,
        "title": alert.title,
        "body": alert.body,
        "read_at": alert.read_at.isoformat() if alert.read_at is not None else None,
        "created_at": alert.created_at.isoformat(),
        "updated_at": alert.updated_at.isoformat(),
        "match": serialize_match(alert.offer_match),
    }


def serialize_refresh_run(run: OfferRefreshRun) -> dict[str, Any]:
    payload = dict(run.result_json or {})
    success_count = payload.get("success_count")
    failure_count = payload.get("failure_count")
    return {
        "id": run.id,
        "user_id": run.user_id,
        "rule_id": run.rule_id,
        "trigger_kind": run.trigger_kind,
        "status": run.status,
        "source_count": run.source_count,
        "source_ids": list(run.source_ids_json or []),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at is not None else None,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "error": run.error,
        "totals": payload.get("totals") or {},
        "source_results": payload.get("sources") or [],
        "success_count": int(success_count) if isinstance(success_count, (int, float)) else 0,
        "failure_count": int(failure_count) if isinstance(failure_count, (int, float)) else 0,
    }


def _serialize_ingest_result(*, source_id: str, result: OfferIngestResult) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "offers_seen": result.offers_seen,
        "inserted": result.inserted,
        "updated": result.updated,
        "blocked": result.blocked,
        "matched": result.matched,
        "alerts_created": result.alerts_created,
        "warnings": list(result.warnings),
        "validation": dict(result.validation),
        "blocked_outputs": list(result.blocked_outputs),
    }


def _owned_watchlist(session: Session, *, user_id: str, watchlist_id: str) -> ProductWatchlist:
    watchlist = session.get(ProductWatchlist, watchlist_id)
    if watchlist is None or watchlist.user_id != user_id:
        raise RuntimeError("watchlist not found")
    return watchlist


def _owned_offer_source(session: Session, *, user_id: str, source_id: str) -> OfferSourceConfig:
    source = session.execute(
        select(OfferSourceConfig)
        .where(OfferSourceConfig.user_id == user_id, OfferSourceConfig.source_id == source_id)
        .limit(1)
    ).scalar_one_or_none()
    if source is None:
        raise RuntimeError("offer source not found")
    return source


def _build_source_id(*, merchant_name: str, merchant_url: str) -> str:
    merchant_slug = "".join(
        character.lower() if character.isalnum() else "-"
        for character in merchant_name.strip()
    ).strip("-")
    merchant_slug = "-".join(part for part in merchant_slug.split("-") if part) or "merchant"
    suffix = sha256(merchant_url.strip().encode("utf-8")).hexdigest()[:8]
    return f"{merchant_slug}-{suffix}"


def _refresh_offer_statuses(session: Session) -> None:
    now = datetime.now(tz=UTC)
    expired = session.execute(
        select(Offer).where(Offer.status != "expired", Offer.validity_end < now)
    ).scalars().all()
    for offer in expired:
        offer.status = "expired"
    active = session.execute(
        select(Offer).where(Offer.status == "expired", Offer.validity_end >= now)
    ).scalars().all()
    for offer in active:
        offer.status = "active"
