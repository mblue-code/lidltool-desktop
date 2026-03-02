from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterable

_REDACTION_LOCK = threading.Lock()
_REDACTION_HITS = 0


class SecretRedactionFilter(logging.Filter):
    def __init__(self, patterns: Iterable[str] | None = None) -> None:
        super().__init__()
        default_patterns = [
            r"(refresh[_-]?token\s*[=:]\s*)([^\s,;]+)",
            r"(access[_-]?token\s*[=:]\s*)([^\s,;]+)",
            r"(password\s*[=:]\s*)([^\s,;]+)",
            r"(authorization\s*:\s*bearer\s+)([^\s,;]+)",
            r"((?:api|secret|private)[_-]?key\s*[=:]\s*)([^\s,;]+)",
            r"(x-api-key\s*:\s*)([^\s,;]+)",
            r"(client_secret\s*[=:]\s*)([^\s,;]+)",
        ]
        self._patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in (patterns or default_patterns)
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern in self._patterns:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
            _increment_redaction_hits()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    root = logging.getLogger()
    redaction_filter = SecretRedactionFilter()
    for handler in root.handlers:
        handler.addFilter(redaction_filter)


def redaction_hit_count() -> int:
    with _REDACTION_LOCK:
        return _REDACTION_HITS


def reset_redaction_hit_count() -> None:
    global _REDACTION_HITS
    with _REDACTION_LOCK:
        _REDACTION_HITS = 0


def _increment_redaction_hits() -> None:
    global _REDACTION_HITS
    with _REDACTION_LOCK:
        _REDACTION_HITS += 1
