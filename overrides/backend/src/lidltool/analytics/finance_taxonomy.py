from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import Category


FINANCE_TAXONOMY_VERSION = "finance-taxonomy-v1"


@dataclass(frozen=True, slots=True)
class TaxonomyCategory:
    category_id: str
    parent_category_id: str | None = None


FINANCE_CATEGORIES: tuple[TaxonomyCategory, ...] = (
    TaxonomyCategory("groceries"),
    TaxonomyCategory("dining"),
    TaxonomyCategory("housing"),
    TaxonomyCategory("insurance"),
    TaxonomyCategory("credit"),
    TaxonomyCategory("mobility"),
    TaxonomyCategory("car"),
    TaxonomyCategory("investment"),
    TaxonomyCategory("health"),
    TaxonomyCategory("personal_care"),
    TaxonomyCategory("subscriptions"),
    TaxonomyCategory("communication"),
    TaxonomyCategory("shopping"),
    TaxonomyCategory("entertainment"),
    TaxonomyCategory("travel"),
    TaxonomyCategory("education"),
    TaxonomyCategory("fees"),
    TaxonomyCategory("tax"),
    TaxonomyCategory("income"),
    TaxonomyCategory("transfer"),
    TaxonomyCategory("other"),
    TaxonomyCategory("uncategorized"),
    TaxonomyCategory("housing:rent", "housing"),
    TaxonomyCategory("housing:electricity", "housing"),
    TaxonomyCategory("housing:heating", "housing"),
    TaxonomyCategory("housing:water", "housing"),
    TaxonomyCategory("housing:utilities", "housing"),
    TaxonomyCategory("housing:internet", "housing"),
    TaxonomyCategory("housing:repairs", "housing"),
    TaxonomyCategory("housing:tradespeople", "housing"),
    TaxonomyCategory("housing:furniture", "housing"),
    TaxonomyCategory("housing:appliances", "housing"),
    TaxonomyCategory("housing:other", "housing"),
    TaxonomyCategory("insurance:health", "insurance"),
    TaxonomyCategory("insurance:liability", "insurance"),
    TaxonomyCategory("insurance:household", "insurance"),
    TaxonomyCategory("insurance:legal", "insurance"),
    TaxonomyCategory("insurance:car", "insurance"),
    TaxonomyCategory("insurance:travel", "insurance"),
    TaxonomyCategory("insurance:life", "insurance"),
    TaxonomyCategory("insurance:other", "insurance"),
    TaxonomyCategory("credit:repayment", "credit"),
    TaxonomyCategory("credit:interest", "credit"),
    TaxonomyCategory("credit:fees", "credit"),
    TaxonomyCategory("credit:other", "credit"),
    TaxonomyCategory("mobility:public_transit", "mobility"),
    TaxonomyCategory("mobility:train", "mobility"),
    TaxonomyCategory("mobility:taxi_rideshare", "mobility"),
    TaxonomyCategory("mobility:bike", "mobility"),
    TaxonomyCategory("mobility:parking_tolls", "mobility"),
    TaxonomyCategory("mobility:other", "mobility"),
    TaxonomyCategory("car:fuel", "car"),
    TaxonomyCategory("car:charging", "car"),
    TaxonomyCategory("car:maintenance", "car"),
    TaxonomyCategory("car:repairs", "car"),
    TaxonomyCategory("car:parking", "car"),
    TaxonomyCategory("car:tax", "car"),
    TaxonomyCategory("car:wash", "car"),
    TaxonomyCategory("car:other", "car"),
    TaxonomyCategory("investment:broker_transfer", "investment"),
    TaxonomyCategory("investment:savings_transfer", "investment"),
    TaxonomyCategory("investment:pension", "investment"),
    TaxonomyCategory("investment:crypto", "investment"),
    TaxonomyCategory("investment:other", "investment"),
    TaxonomyCategory("income:salary", "income"),
    TaxonomyCategory("income:refund", "income"),
    TaxonomyCategory("income:reimbursement", "income"),
    TaxonomyCategory("income:interest", "income"),
    TaxonomyCategory("income:gift", "income"),
    TaxonomyCategory("income:other", "income"),
    TaxonomyCategory("subscriptions:software", "subscriptions"),
    TaxonomyCategory("subscriptions:streaming", "subscriptions"),
    TaxonomyCategory("subscriptions:fitness", "subscriptions"),
    TaxonomyCategory("subscriptions:news", "subscriptions"),
    TaxonomyCategory("subscriptions:cloud", "subscriptions"),
    TaxonomyCategory("subscriptions:other", "subscriptions"),
    TaxonomyCategory("shopping:online_retail", "shopping"),
    TaxonomyCategory("shopping:convenience", "shopping"),
    TaxonomyCategory("shopping:other", "shopping"),
    TaxonomyCategory("personal_care:drugstore", "personal_care"),
    TaxonomyCategory("personal_care:other", "personal_care"),
    TaxonomyCategory("education:publications", "education"),
    TaxonomyCategory("education:courses", "education"),
    TaxonomyCategory("education:books", "education"),
    TaxonomyCategory("education:other", "education"),
    TaxonomyCategory("fees:bank", "fees"),
    TaxonomyCategory("fees:service", "fees"),
    TaxonomyCategory("fees:shipping", "fees"),
    TaxonomyCategory("fees:late_payment", "fees"),
    TaxonomyCategory("tax:income_tax", "tax"),
    TaxonomyCategory("tax:vehicle_tax", "tax"),
    TaxonomyCategory("tax:property_tax", "tax"),
    TaxonomyCategory("tax:other", "tax"),
)


def finance_parent_category(category_id: str | None) -> str | None:
    if not category_id:
        return None
    return category_id.split(":", 1)[0]


def ensure_finance_taxonomy(session: Session) -> dict[str, Category]:
    existing = session.execute(select(Category)).scalars().all()
    by_id = {row.category_id: row for row in existing}
    for entry in FINANCE_CATEGORIES:
        parent_id = entry.parent_category_id
        row = by_id.get(entry.category_id)
        if row is None:
            row = Category(
                category_id=entry.category_id,
                name=entry.category_id,
                parent_category_id=parent_id,
            )
            session.add(row)
            session.flush()
            by_id[entry.category_id] = row
        else:
            row.name = entry.category_id
            row.parent_category_id = parent_id
    return by_id

