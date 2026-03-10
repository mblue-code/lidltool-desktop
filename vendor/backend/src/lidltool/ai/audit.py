from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from lidltool.db.audit import record_audit_event
from lidltool.db.engine import session_scope


def record_plugin_ai_audit_event(
    *,
    session_factory: sessionmaker[Session] | None,
    plugin_id: str,
    source_id: str,
    details: dict[str, Any],
) -> None:
    if session_factory is None:
        return
    with session_scope(session_factory) as session:
        record_audit_event(
            session,
            action="plugin.ai_mediation",
            source=source_id,
            actor_type="plugin",
            actor_id=plugin_id,
            entity_type="plugin",
            entity_id=plugin_id,
            details=details,
        )
