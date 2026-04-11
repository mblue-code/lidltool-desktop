from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.automations.schemas import next_run_at
from lidltool.automations.templates import execute_template
from lidltool.config import AppConfig
from lidltool.db.audit import record_audit_event
from lidltool.db.models import AutomationExecution, AutomationRule


class AutomationEngine:
    def __init__(self, session: Session, *, config: AppConfig | None = None) -> None:
        self._session = session
        self._config = config

    def list_due_rules(self, *, now: datetime, limit: int) -> list[AutomationRule]:
        stmt = (
            select(AutomationRule)
            .where(
                AutomationRule.enabled.is_(True),
                AutomationRule.next_run_at.is_not(None),
                AutomationRule.next_run_at <= now,
            )
            .order_by(AutomationRule.next_run_at.asc(), AutomationRule.created_at.asc())
            .limit(max(limit, 1))
        )
        return list(self._session.execute(stmt).scalars().all())

    def run_rule(
        self,
        *,
        rule: AutomationRule,
        triggered_at: datetime | None = None,
        actor_id: str | None = None,
    ) -> AutomationExecution:
        triggered = triggered_at or datetime.now(tz=UTC)
        execution = AutomationExecution(
            rule_id=rule.id,
            status="running",
            triggered_at=triggered,
            created_at=datetime.now(tz=UTC),
        )
        self._session.add(execution)
        self._session.flush()
        try:
            result = execute_template(
                self._session,
                rule=rule,
                triggered_at=triggered,
                config=self._config,
            )
            execution.status = result.status
            execution.result = result.payload
            execution.executed_at = datetime.now(tz=UTC)
            execution.error = None
            if rule.enabled:
                rule.last_run_at = triggered
                rule.next_run_at = next_run_at(
                    trigger_config=rule.trigger_config or {}, from_time=triggered
                )
            action = (
                "automation.executed" if execution.status == "success" else "automation.skipped"
            )
            record_audit_event(
                self._session,
                action=action,
                actor_type="system",
                actor_id=actor_id,
                entity_type="automation_rule",
                entity_id=rule.id,
                details={"execution_id": execution.id, "result": result.payload},
            )
        except Exception as exc:  # noqa: BLE001
            execution.status = "failed"
            execution.error = str(exc)
            execution.executed_at = datetime.now(tz=UTC)
            record_audit_event(
                self._session,
                action="automation.failed",
                actor_type="system",
                actor_id=actor_id,
                entity_type="automation_rule",
                entity_id=rule.id,
                details={"execution_id": execution.id, "error": str(exc)},
            )
        return execution

    @staticmethod
    def serialize_rule(rule: AutomationRule) -> dict[str, Any]:
        return {
            "id": rule.id,
            "name": rule.name,
            "rule_type": rule.rule_type,
            "enabled": rule.enabled,
            "trigger_config": rule.trigger_config or {},
            "action_config": rule.action_config or {},
            "next_run_at": rule.next_run_at.isoformat() if rule.next_run_at is not None else None,
            "last_run_at": rule.last_run_at.isoformat() if rule.last_run_at is not None else None,
            "created_at": rule.created_at.isoformat(),
            "updated_at": rule.updated_at.isoformat(),
        }

    @staticmethod
    def serialize_execution(
        execution: AutomationExecution, *, rule: AutomationRule | None = None
    ) -> dict[str, Any]:
        return {
            "id": execution.id,
            "rule_id": execution.rule_id,
            "rule_name": rule.name if rule is not None else None,
            "rule_type": rule.rule_type if rule is not None else None,
            "status": execution.status,
            "triggered_at": execution.triggered_at.isoformat(),
            "executed_at": (
                execution.executed_at.isoformat() if execution.executed_at is not None else None
            ),
            "result": execution.result,
            "error": execution.error,
            "created_at": execution.created_at.isoformat(),
        }
