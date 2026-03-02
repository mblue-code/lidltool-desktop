from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ReceiptPage:
    receipts: list[dict[str, Any]]
    next_page_token: str | None
