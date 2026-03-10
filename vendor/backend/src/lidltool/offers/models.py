from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OfferIngestItemResult:
    fingerprint: str
    offer_id: str | None
    status: str
    issue_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OfferIngestResult:
    offers_seen: int = 0
    inserted: int = 0
    updated: int = 0
    blocked: int = 0
    matched: int = 0
    alerts_created: int = 0
    warnings: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    blocked_outputs: list[dict[str, Any]] = field(default_factory=list)
    items: list[OfferIngestItemResult] = field(default_factory=list)


@dataclass(slots=True)
class OfferMatchResult:
    created: int = 0
    existing: int = 0
    alerts_created: int = 0
