from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ValidationSeverity(StrEnum):
    WARN = "warn"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class ValidationOutcome(StrEnum):
    ACCEPT = "accept"
    WARN = "warn"
    QUARANTINE = "quarantine"
    REJECT = "reject"


_SEVERITY_ORDER: dict[ValidationSeverity, int] = {
    ValidationSeverity.WARN: 1,
    ValidationSeverity.QUARANTINE: 2,
    ValidationSeverity.REJECT: 3,
}


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    code: str
    severity: ValidationSeverity
    message: str
    path: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.path,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload


@dataclass(slots=True)
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    inspected_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    @property
    def outcome(self) -> ValidationOutcome:
        if not self.issues:
            return ValidationOutcome.ACCEPT
        highest = max(self.issues, key=lambda issue: _SEVERITY_ORDER[issue.severity]).severity
        if highest is ValidationSeverity.REJECT:
            return ValidationOutcome.REJECT
        if highest is ValidationSeverity.QUARANTINE:
            return ValidationOutcome.QUARANTINE
        return ValidationOutcome.WARN

    @property
    def warning_messages(self) -> list[str]:
        return [issue.message for issue in self.issues if issue.severity is ValidationSeverity.WARN]

    @property
    def blocking_messages(self) -> list[str]:
        return [
            issue.message
            for issue in self.issues
            if issue.severity in {ValidationSeverity.QUARANTINE, ValidationSeverity.REJECT}
        ]

    def add_issue(
        self,
        *,
        code: str,
        severity: ValidationSeverity,
        message: str,
        path: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                severity=severity,
                message=message,
                path=path,
                details=dict(details or {}),
            )
        )

    def issue_counts(self) -> dict[str, int]:
        counts = {
            ValidationOutcome.WARN.value: 0,
            ValidationOutcome.QUARANTINE.value: 0,
            ValidationOutcome.REJECT.value: 0,
        }
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts

    def to_payload(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "inspected_at": self.inspected_at.isoformat(),
            "counts": self.issue_counts(),
            "issues": [issue.to_payload() for issue in self.issues],
        }
