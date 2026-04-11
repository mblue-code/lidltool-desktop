from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from lidltool.ai.mediation import PluginAiMediationService
from lidltool.connectors.runtime.bridge import maybe_plugin_ai_bridge_server
from lidltool.connectors.runtime.errors import (
    ConnectorRuntimeCanceledError,
    ConnectorRuntimeLaunchError,
    ConnectorRuntimeMalformedResponseError,
    ConnectorRuntimeNonZeroExitError,
    ConnectorRuntimeProtocolError,
    ConnectorRuntimeTimeoutError,
)
from lidltool.connectors.runtime.protocol import (
    ConnectorActionResponse,
    RuntimeInvocationDiagnostics,
    RuntimeRequestEnvelope,
    RuntimeResponseEnvelope,
    compact_json_excerpt,
    dump_runtime_envelope_json,
    parse_runtime_response_envelope,
    validate_runtime_response_request_match,
)
from lidltool.connectors.sdk.manifest import ConnectorManifest

_POLL_INTERVAL_S = 0.05


@dataclass(slots=True)
class SubprocessRuntimeResult:
    response: ConnectorActionResponse
    diagnostics: RuntimeInvocationDiagnostics


class SubprocessConnectorRuntime:
    def __init__(
        self,
        *,
        manifest: ConnectorManifest,
        working_directory: Path | None = None,
        python_executable: str | None = None,
        extra_environment: dict[str, str] | None = None,
        plugin_ai_service: PluginAiMediationService | None = None,
    ) -> None:
        self._manifest = manifest
        self._working_directory = working_directory
        self._python_executable = python_executable or sys.executable
        self._extra_environment = dict(extra_environment or {})
        self._plugin_ai_service = plugin_ai_service

    def invoke_action(
        self,
        request_envelope: RuntimeRequestEnvelope,
        *,
        timeout_s: float | None,
        cancel_event: threading.Event | None,
    ) -> SubprocessRuntimeResult:
        started = time.monotonic()
        diagnostics = RuntimeInvocationDiagnostics(
            request_id=request_envelope.request_id,
            plugin_id=self._manifest.plugin_id,
            source_id=self._manifest.source_id,
            runtime_kind=self._manifest.runtime_kind,
            transport="subprocess",
            entrypoint=self._manifest.entrypoint,
            action=request_envelope.request.action,
            duration_ms=0,
        )
        try:
            command = self._build_command()
        except ValueError as exc:
            raise ConnectorRuntimeLaunchError(
                str(exc),
                diagnostics=diagnostics,
            ) from exc
        with maybe_plugin_ai_bridge_server(
            service=self._plugin_ai_service if self._manifest.policy.ai.allow_model_mediation else None,
            manifest=self._manifest,
        ) as bridge_env:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(self._working_directory) if self._working_directory is not None else None,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    start_new_session=os.name == "posix",
                    env=_runtime_environment(extra=self._merged_environment(bridge_env)),
                )
            except OSError as exc:
                diagnostics.duration_ms = _duration_ms(started)
                raise ConnectorRuntimeLaunchError(
                    f"failed to launch connector runtime: {exc}",
                    diagnostics=diagnostics,
                ) from exc

            stdout_buffer: list[str] = []
            stderr_buffer: list[str] = []
            stdout_thread = threading.Thread(
                target=_read_stream,
                args=(process.stdout, stdout_buffer),
                name=f"connector-runtime-stdout-{process.pid}",
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_read_stream,
                args=(process.stderr, stderr_buffer),
                name=f"connector-runtime-stderr-{process.pid}",
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            cleanup_attempted = False
            try:
                self._write_request(process=process, request_envelope=request_envelope)
                while True:
                    exit_code = process.poll()
                    if exit_code is not None:
                        break
                    if cancel_event is not None and cancel_event.is_set():
                        cleanup_attempted = self._terminate_process(process)
                        diagnostics.duration_ms = _duration_ms(started)
                        diagnostics.canceled = True
                        diagnostics.cleanup_attempted = cleanup_attempted
                        diagnostics.exit_code = process.poll()
                        diagnostics.stderr_excerpt = compact_json_excerpt("".join(stderr_buffer))
                        diagnostics.stdout_excerpt = compact_json_excerpt("".join(stdout_buffer))
                        raise ConnectorRuntimeCanceledError(
                            "connector runtime canceled",
                            diagnostics=diagnostics,
                        )
                    if timeout_s is not None and timeout_s > 0 and time.monotonic() - started > timeout_s:
                        cleanup_attempted = self._terminate_process(process)
                        diagnostics.duration_ms = _duration_ms(started)
                        diagnostics.timed_out = True
                        diagnostics.cleanup_attempted = cleanup_attempted
                        diagnostics.exit_code = process.poll()
                        diagnostics.stderr_excerpt = compact_json_excerpt("".join(stderr_buffer))
                        diagnostics.stdout_excerpt = compact_json_excerpt("".join(stdout_buffer))
                        raise ConnectorRuntimeTimeoutError(
                            f"connector runtime timed out after {timeout_s:.2f}s",
                            diagnostics=diagnostics,
                        )
                    time.sleep(_POLL_INTERVAL_S)
            finally:
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                with contextlib.suppress(OSError):
                    if process.stdin is not None:
                        process.stdin.close()

            stdout_payload = "".join(stdout_buffer)
            stderr_payload = "".join(stderr_buffer)
            diagnostics.duration_ms = _duration_ms(started)
            diagnostics.exit_code = process.returncode
            diagnostics.cleanup_attempted = cleanup_attempted
            diagnostics.stderr_excerpt = compact_json_excerpt(stderr_payload)
            diagnostics.stdout_excerpt = compact_json_excerpt(stdout_payload)

            if process.returncode not in (0, None):
                raise ConnectorRuntimeNonZeroExitError(
                    f"connector runtime exited with status {process.returncode}",
                    diagnostics=diagnostics,
                )

            envelope = self._parse_response(stdout_payload=stdout_payload, diagnostics=diagnostics)
            if not envelope.ok or envelope.response is None:
                message = envelope.error.message if envelope.error is not None else "runtime returned no response"
                raise ConnectorRuntimeProtocolError(message, diagnostics=diagnostics)
            response = validate_runtime_response_request_match(
                request=request_envelope,
                response=envelope,
            )
            diagnostics.response_ok = response.ok
            return SubprocessRuntimeResult(response=response, diagnostics=diagnostics)

    def _build_command(self) -> list[str]:
        entrypoint = self._manifest.entrypoint
        if entrypoint is None:
            raise ValueError("subprocess connector runtime requires manifest.entrypoint")
        if self._manifest.runtime_kind == "subprocess_python":
            return [
                self._python_executable,
                "-m",
                "lidltool.connectors.runtime.runner",
                "--entrypoint",
                entrypoint,
            ]
        if self._manifest.runtime_kind == "subprocess_binary":
            return [entrypoint]
        raise ValueError(f"unsupported subprocess runtime kind: {self._manifest.runtime_kind}")

    def _write_request(
        self,
        *,
        process: subprocess.Popen[str],
        request_envelope: RuntimeRequestEnvelope,
    ) -> None:
        payload = dump_runtime_envelope_json(request_envelope)
        if process.stdin is None:
            return
        process.stdin.write(payload)
        process.stdin.flush()
        process.stdin.close()

    def _parse_response(
        self,
        *,
        stdout_payload: str,
        diagnostics: RuntimeInvocationDiagnostics,
    ) -> RuntimeResponseEnvelope:
        payload = stdout_payload.strip()
        if not payload:
            raise ConnectorRuntimeProtocolError(
                "connector runtime produced no stdout response",
                diagnostics=diagnostics,
            )
        try:
            return parse_runtime_response_envelope(payload)
        except Exception as exc:
            raise ConnectorRuntimeMalformedResponseError(
                f"connector runtime returned malformed JSON: {exc}",
                diagnostics=diagnostics,
            ) from exc

    def _terminate_process(self, process: subprocess.Popen[str]) -> bool:
        if process.poll() is not None:
            return False
        if os.name == "posix":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1.0)
                return True
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=1.0)
                return True
        process.terminate()
        try:
            process.wait(timeout=1.0)
            return True
        except subprocess.TimeoutExpired:
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=1.0)
            return True

    def _merged_environment(self, bridge_env: dict[str, str]) -> dict[str, str]:
        merged = dict(self._extra_environment)
        merged.update(bridge_env)
        return merged


def _read_stream(stream: TextIO | None, buffer: list[str]) -> None:
    if stream is None:
        return
    try:
        chunk = stream.read()
    finally:
        with contextlib.suppress(OSError):
            stream.close()
    if chunk:
        buffer.append(chunk)


def _duration_ms(started: float) -> int:
    return max(int((time.monotonic() - started) * 1000), 0)


def _runtime_environment(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    src_dir = Path(__file__).resolve().parents[3]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_dir}{os.pathsep}{existing}" if existing else str(src_dir)
    )
    if extra:
        env.update(extra)
    return env


SubprocessReceiptConnectorRuntime = SubprocessConnectorRuntime
