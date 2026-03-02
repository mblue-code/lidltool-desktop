from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from lidltool.db.models import Product, ProductAlias, Source, Transaction, TransactionItem


@dataclass(slots=True)
class ProductMatch:
    product_id: str
    confidence: float
    method: str


def _normalized_name(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _extract_barcode(raw_payload: dict[str, object] | None) -> str | None:
    if not isinstance(raw_payload, dict):
        return None
    for key in ("ean", "gtin", "gtin_ean", "barcode"):
        value = raw_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_product_for_item(
    session: Session,
    *,
    item: TransactionItem,
    source: Source,
    fuzzy_threshold: float = 0.85,
) -> ProductMatch | None:
    barcode = _extract_barcode(item.raw_payload)
    if barcode:
        product = session.execute(
            select(Product).where(Product.gtin_ean == barcode).limit(1)
        ).scalar_one_or_none()
        if product is not None:
            return ProductMatch(product_id=product.product_id, confidence=1.0, method="ean")

    raw_name = item.name.strip()
    if raw_name:
        exact_alias = session.execute(
            select(ProductAlias)
            .where(
                func.lower(ProductAlias.raw_name) == raw_name.lower(),
                (ProductAlias.source_kind == source.kind) | ProductAlias.source_kind.is_(None),
            )
            .order_by(ProductAlias.source_kind.desc(), ProductAlias.match_confidence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if exact_alias is not None:
            return ProductMatch(
                product_id=exact_alias.product_id,
                confidence=float(exact_alias.match_confidence),
                method="alias",
            )

    products = session.execute(select(Product.product_id, Product.canonical_name)).all()
    needle = _normalized_name(item.name)
    best: tuple[str, float] | None = None
    for product_id, canonical_name in products:
        score = SequenceMatcher(None, needle, _normalized_name(canonical_name)).ratio()
        if best is None or score > best[1]:
            best = (str(product_id), score)

    if best is None or best[1] < fuzzy_threshold:
        return None
    return ProductMatch(product_id=best[0], confidence=best[1], method="fuzzy")


def auto_match_unmatched_items(session: Session) -> int:
    rows = session.execute(
        select(TransactionItem, Transaction, Source)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .join(Source, Source.id == Transaction.source_id)
        .where(TransactionItem.product_id.is_(None))
        .options(selectinload(TransactionItem.transaction))
    ).all()
    matched = 0
    for item, _, source in rows:
        match = resolve_product_for_item(session, item=item, source=source)
        if match is None:
            continue
        item.product_id = match.product_id
        if match.method in {"ean", "alias"}:
            continue
        existing_alias = session.execute(
            select(ProductAlias)
            .where(
                ProductAlias.product_id == match.product_id,
                ProductAlias.raw_name == item.name,
                ProductAlias.source_kind == source.kind,
            )
            .limit(1)
        ).scalar_one_or_none()
        if existing_alias is None:
            session.add(
                ProductAlias(
                    product_id=match.product_id,
                    source_kind=source.kind,
                    raw_name=item.name,
                    raw_sku=item.source_item_id,
                    match_confidence=Decimal(f"{match.confidence:.3f}"),
                    match_method=match.method,
                )
            )
        matched += 1
    return matched


def create_manual_product_alias(
    session: Session,
    *,
    product_id: str,
    raw_name: str,
    source_kind: str | None,
    raw_sku: str | None = None,
) -> ProductAlias:
    alias = session.execute(
        select(ProductAlias)
        .where(
            ProductAlias.product_id == product_id,
            ProductAlias.raw_name == raw_name,
            ProductAlias.source_kind == source_kind,
        )
        .limit(1)
    ).scalar_one_or_none()
    if alias is not None:
        alias.match_method = "manual"
        alias.match_confidence = Decimal("1.000")
        if raw_sku:
            alias.raw_sku = raw_sku
        return alias
    alias = ProductAlias(
        product_id=product_id,
        source_kind=source_kind,
        raw_name=raw_name,
        raw_sku=raw_sku,
        match_confidence=Decimal("1.000"),
        match_method="manual",
    )
    session.add(alias)
    return alias
