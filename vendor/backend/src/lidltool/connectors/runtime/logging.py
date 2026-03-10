from __future__ import annotations

import logging

from lidltool.connectors.runtime.protocol import RuntimeInvocationDiagnostics


def log_runtime_invocation(
    logger: logging.Logger,
    diagnostics: RuntimeInvocationDiagnostics,
    *,
    level: int = logging.INFO,
    error: str | None = None,
) -> None:
    logger.log(
        level,
        (
            "connector.runtime request_id=%s source_id=%s plugin_id=%s action=%s "
            "transport=%s runtime_kind=%s duration_ms=%s exit_code=%s timed_out=%s "
            "canceled=%s cleanup_attempted=%s error=%s stderr_excerpt=%s"
        ),
        diagnostics.request_id,
        diagnostics.source_id,
        diagnostics.plugin_id,
        diagnostics.action,
        diagnostics.transport,
        diagnostics.runtime_kind,
        diagnostics.duration_ms,
        diagnostics.exit_code,
        diagnostics.timed_out,
        diagnostics.canceled,
        diagnostics.cleanup_attempted,
        error,
        diagnostics.stderr_excerpt,
    )
