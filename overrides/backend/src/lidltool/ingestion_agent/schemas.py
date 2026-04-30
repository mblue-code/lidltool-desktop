from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

ProposalType = Literal[
    "create_transaction",
    "create_cashflow_entry",
    "link_existing_transaction",
    "already_covered",
    "create_recurring_bill",
    "create_recurring_bill_candidate",
    "link_recurring_occurrence",
    "ignore",
    "needs_review",
]

ProposalStatus = Literal[
    "draft",
    "pending_review",
    "auto_approved",
    "approved",
    "committing",
    "committed",
    "rejected",
    "failed",
]


class CreateTransactionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["create_transaction"] = "create_transaction"
    purchased_at: datetime
    merchant_name: str = Field(min_length=1)
    total_gross_cents: int = Field(ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=8)
    source_id: str = Field(default="agent_ingest", min_length=1)
    source_display_name: str = Field(default="Agent Ingestion", min_length=1)
    source_account_ref: str | None = "cash"
    source_transaction_id: str | None = None
    idempotency_key: str = Field(min_length=16)
    confidence: float = Field(ge=0, le=1)
    items: list[dict[str, Any]] = Field(default_factory=list)
    discounts: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_currency(self) -> "CreateTransactionPayload":
        self.currency = self.currency.strip().upper() or "EUR"
        self.merchant_name = self.merchant_name.strip()
        self.source_id = self.source_id.strip()
        self.source_display_name = self.source_display_name.strip()
        if self.source_account_ref is not None:
            self.source_account_ref = self.source_account_ref.strip() or None
        if self.source_transaction_id is not None:
            self.source_transaction_id = self.source_transaction_id.strip() or None
        return self


class NeedsReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["needs_review"] = "needs_review"
    reason: str = Field(min_length=1)
    evidence: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class IgnorePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ignore"] = "ignore"
    statement_row_id: str | None = None
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class AlreadyCoveredPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["already_covered"] = "already_covered"
    statement_row_id: str | None = None
    transaction_id: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    match_score: float = Field(ge=0, le=1)


class LinkExistingTransactionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["link_existing_transaction"] = "link_existing_transaction"
    statement_row_id: str | None = None
    transaction_id: str = Field(min_length=1)
    match_score: float = Field(ge=0, le=1)
    match_reason: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)


class CreateCashflowEntryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["create_cashflow_entry"] = "create_cashflow_entry"
    effective_date: date
    direction: Literal["inflow", "outflow"] = "outflow"
    category: str = Field(default="uncategorized", min_length=1)
    amount_cents: int = Field(ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=8)
    description: str | None = None
    source_type: str = Field(default="agent_ingest", min_length=1)
    linked_transaction_id: str | None = None
    linked_recurring_occurrence_id: str | None = None
    notes: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class CreateRecurringBillCandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["create_recurring_bill_candidate"] = "create_recurring_bill_candidate"
    name: str = Field(min_length=1)
    merchant_canonical: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=8)
    frequency: Literal["weekly", "biweekly", "monthly", "quarterly", "yearly"] = "monthly"
    first_seen_date: date
    evidence: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


ProposalPayload = (
    CreateTransactionPayload
    | CreateCashflowEntryPayload
    | AlreadyCoveredPayload
    | LinkExistingTransactionPayload
    | CreateRecurringBillCandidatePayload
    | IgnorePayload
    | NeedsReviewPayload
)
ProposalPayloadAdapter: TypeAdapter[ProposalPayload] = TypeAdapter(ProposalPayload)


def validate_proposal_payload(payload: dict[str, Any]) -> ProposalPayload:
    return ProposalPayloadAdapter.validate_python(payload)
