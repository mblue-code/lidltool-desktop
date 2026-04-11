from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.automations.engine import AutomationEngine
from lidltool.automations.schemas import (
    next_run_at,
    normalize_rule_type,
    validate_action_config,
    validate_trigger_config,
)
from lidltool.config import AppConfig
from lidltool.db.audit import record_audit_event
from lidltool.db.engine import session_scope
from lidltool.db.models import AutomationExecution, AutomationRule


class AutomationService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        config: AppConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config

    def list_rules(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        clamped_limit = min(max(limit, 1), 200)
        clamped_offset = max(offset, 0)
        with session_scope(self._session_factory) as session:
            total = int(
                session.execute(select(func.count()).select_from(AutomationRule)).scalar_one()
            )
            rules = (
                session.execute(
                    select(AutomationRule)
                    .order_by(AutomationRule.created_at.desc(), AutomationRule.id.desc())
                    .offset(clamped_offset)
                    .limit(clamped_limit)
                )
                .scalars()
                .all()
            )
            return {
                "count": len(rules),
                "total": total,
                "limit": clamped_limit,
                "offset": clamped_offset,
                "items": [AutomationEngine.serialize_rule(rule) for rule in rules],
            }

    def get_rule(self, *, rule_id: str) -> dict[str, Any] | None:
        with session_scope(self._session_factory) as session:
            rule = session.get(AutomationRule, rule_id)
            if rule is None:
                return None
            return AutomationEngine.serialize_rule(rule)

    def create_rule(
        self,
        *,
        name: str,
        rule_type: str,
        enabled: bool = True,
        trigger_config: dict[str, Any] | None = None,
        action_config: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_type = normalize_rule_type(rule_type)
        normalized_trigger = validate_trigger_config(trigger_config)
        normalized_action = validate_action_config(normalized_type, action_config)
        now = datetime.now(tz=UTC)
        with session_scope(self._session_factory) as session:
            rule = AutomationRule(
                name=name.strip(),
                rule_type=normalized_type,
                enabled=enabled,
                trigger_config=normalized_trigger,
                action_config=normalized_action,
                next_run_at=(
                    next_run_at(trigger_config=normalized_trigger, from_time=now)
                    if enabled
                    else None
                ),
                last_run_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(rule)
            session.flush()
            record_audit_event(
                session,
                action="automation.rule_created",
                actor_type="user",
                actor_id=actor_id,
                entity_type="automation_rule",
                entity_id=rule.id,
                details={"rule_type": rule.rule_type, "enabled": rule.enabled},
            )
            return AutomationEngine.serialize_rule(rule)

    def update_rule(
        self,
        *,
        rule_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            rule = session.get(AutomationRule, rule_id)
            if rule is None:
                raise RuntimeError("automation rule not found")
            trigger_changed = False
            enabled_changed = False
            if "name" in payload and payload["name"] is not None:
                rule.name = str(payload["name"]).strip()
            if "rule_type" in payload and payload["rule_type"] is not None:
                normalized_type = normalize_rule_type(str(payload["rule_type"]))
                rule.rule_type = normalized_type
            normalized_type = rule.rule_type
            if "trigger_config" in payload:
                rule.trigger_config = validate_trigger_config(payload.get("trigger_config"))
                trigger_changed = True
            if "action_config" in payload:
                rule.action_config = validate_action_config(
                    normalized_type, payload.get("action_config")
                )
            if "enabled" in payload and payload["enabled"] is not None:
                next_enabled = bool(payload["enabled"])
                enabled_changed = rule.enabled != next_enabled
                rule.enabled = next_enabled
            rule.updated_at = datetime.now(tz=UTC)
            if rule.enabled and (trigger_changed or enabled_changed or rule.next_run_at is None):
                rule.next_run_at = next_run_at(
                    trigger_config=rule.trigger_config or {},
                    from_time=datetime.now(tz=UTC),
                )
            if not rule.enabled:
                rule.next_run_at = None
            session.flush()
            record_audit_event(
                session,
                action="automation.rule_updated",
                actor_type="user",
                actor_id=actor_id,
                entity_type="automation_rule",
                entity_id=rule.id,
                details={"enabled": rule.enabled},
            )
            return AutomationEngine.serialize_rule(rule)

    def delete_rule(self, *, rule_id: str, actor_id: str | None = None) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            rule = session.get(AutomationRule, rule_id)
            if rule is None:
                raise RuntimeError("automation rule not found")
            result = {"deleted": True, "id": rule.id, "name": rule.name}
            session.delete(rule)
            record_audit_event(
                session,
                action="automation.rule_deleted",
                actor_type="user",
                actor_id=actor_id,
                entity_type="automation_rule",
                entity_id=rule_id,
                details={"name": result["name"]},
            )
            return result

    def run_rule(self, *, rule_id: str, actor_id: str | None = None) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            rule = session.get(AutomationRule, rule_id)
            if rule is None:
                raise RuntimeError("automation rule not found")
            engine = AutomationEngine(session, config=self._config)
            execution = engine.run_rule(rule=rule, actor_id=actor_id)
            session.flush()
            return AutomationEngine.serialize_execution(execution, rule=rule)

    def run_due_rules(self, *, limit: int = 20) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            engine = AutomationEngine(session, config=self._config)
            now = datetime.now(tz=UTC)
            due_rules = engine.list_due_rules(now=now, limit=limit)
            executions: list[dict[str, Any]] = []
            for rule in due_rules:
                execution = engine.run_rule(rule=rule, triggered_at=now)
                executions.append(AutomationEngine.serialize_execution(execution, rule=rule))
            return {"count": len(executions), "items": executions}

    def list_executions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        rule_type: str | None = None,
    ) -> dict[str, Any]:
        clamped_limit = min(max(limit, 1), 200)
        clamped_offset = max(offset, 0)
        with session_scope(self._session_factory) as session:
            base_stmt = select(AutomationExecution, AutomationRule).join(
                AutomationRule, AutomationRule.id == AutomationExecution.rule_id
            )
            if status:
                base_stmt = base_stmt.where(AutomationExecution.status == status.strip().lower())
            if rule_type:
                base_stmt = base_stmt.where(AutomationRule.rule_type == rule_type.strip().lower())
            total = int(
                session.execute(
                    select(func.count()).select_from(base_stmt.order_by(None).subquery())
                ).scalar_one()
            )
            rows = session.execute(
                base_stmt.order_by(
                    AutomationExecution.triggered_at.desc(), AutomationExecution.id.desc()
                )
                .offset(clamped_offset)
                .limit(clamped_limit)
            ).all()
            items = [
                AutomationEngine.serialize_execution(execution, rule=rule)
                for execution, rule in rows
            ]
            return {
                "count": len(items),
                "total": total,
                "limit": clamped_limit,
                "offset": clamped_offset,
                "items": items,
            }
