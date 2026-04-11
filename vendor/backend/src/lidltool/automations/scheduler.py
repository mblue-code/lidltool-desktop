from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from lidltool.automations.service import AutomationService
from lidltool.config import AppConfig

LOGGER = logging.getLogger(__name__)


class AutomationScheduler:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        config: AppConfig,
        service_factory: Callable[[sessionmaker[Session]], AutomationService] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._service_factory = service_factory or (
            lambda sessions: AutomationService(session_factory=sessions, config=config)
        )
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if not self._config.automations_scheduler_enabled:
            LOGGER.info("automation.scheduler disabled")
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run_loop, daemon=True, name="automation-scheduler"
        )
        self._worker.start()
        LOGGER.info("automation.scheduler started")

    def stop(self) -> None:
        self._stop_event.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=2.0)
        LOGGER.info("automation.scheduler stopped")

    def _run_loop(self) -> None:
        service = self._service_factory(self._session_factory)
        while not self._stop_event.is_set():
            try:
                result = service.run_due_rules(
                    limit=self._config.automations_scheduler_max_rules_per_tick
                )
                if result["count"] > 0:
                    LOGGER.info("automation.scheduler.executed count=%s", result["count"])
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("automation.scheduler.error error=%s", exc)
            self._stop_event.wait(max(self._config.automations_scheduler_poll_seconds, 1))
