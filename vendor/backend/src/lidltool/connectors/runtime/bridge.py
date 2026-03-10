from __future__ import annotations

import contextlib
import contextvars
import json
import secrets
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from lidltool.ai.mediation import PluginAiMediationService
from lidltool.ai.schemas import (
    AiMediationError,
    AiMediationMetadata,
    AiMediationRequest,
    AiMediationResponse,
    AiUsageMetadata,
    validate_ai_mediation_response,
)
from lidltool.connectors.sdk.manifest import ConnectorManifest

PLUGIN_AI_BRIDGE_URL_ENV = "LIDLTOOL_PLUGIN_AI_BRIDGE_URL"
PLUGIN_AI_BRIDGE_TOKEN_ENV = "LIDLTOOL_PLUGIN_AI_BRIDGE_TOKEN"

_BOUND_PLUGIN_AI_CLIENT: contextvars.ContextVar[PluginAiRuntimeClient | None] = contextvars.ContextVar(
    "plugin_ai_runtime_client",
    default=None,
)


class PluginAiBridgeUnavailableError(RuntimeError):
    """Raised when plugin AI mediation is requested outside an approved runtime bridge."""


@runtime_checkable
class PluginAiRuntimeClient(Protocol):
    def mediate(self, request: AiMediationRequest | Mapping[str, Any]) -> AiMediationResponse:
        ...


class DirectPluginAiRuntimeClient:
    def __init__(
        self,
        *,
        service: PluginAiMediationService,
        manifest: ConnectorManifest,
    ) -> None:
        self._service = service
        self._manifest = manifest

    def mediate(self, request: AiMediationRequest | Mapping[str, Any]) -> AiMediationResponse:
        return self._service.mediate(manifest=self._manifest, request=request)


class HttpPluginAiRuntimeClient:
    def __init__(
        self,
        *,
        url: str,
        token: str,
    ) -> None:
        self._url = url
        self._token = token

    def mediate(self, request: AiMediationRequest | Mapping[str, Any]) -> AiMediationResponse:
        payload = request.model_dump(mode="python") if isinstance(request, AiMediationRequest) else dict(request)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        http_request = Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(http_request, timeout=30.0) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
        except URLError as exc:
            raise PluginAiBridgeUnavailableError(f"plugin AI bridge is unavailable: {exc}") from exc
        return validate_ai_mediation_response(json.loads(raw))


class PluginAiBridgeServer:
    def __init__(
        self,
        *,
        service: PluginAiMediationService,
        manifest: ConnectorManifest,
    ) -> None:
        self._service = service
        self._manifest = manifest
        self._token = secrets.token_urlsafe(24)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"plugin-ai-bridge-{manifest.plugin_id}",
        )

    @property
    def environment(self) -> dict[str, str]:
        address = self._server.server_address
        host = str(address[0])
        port = int(address[1])
        return {
            PLUGIN_AI_BRIDGE_URL_ENV: f"http://{host}:{port}/v1/plugin-ai/mediate",
            PLUGIN_AI_BRIDGE_TOKEN_ENV: self._token,
        }

    def __enter__(self) -> PluginAiBridgeServer:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1.0)

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        service = self._service
        manifest = self._manifest
        expected_token = self._token

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/plugin-ai/mediate":
                    self.send_error(404)
                    return
                if self.headers.get("Authorization") != f"Bearer {expected_token}":
                    self.send_error(403)
                    return
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                try:
                    payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                except json.JSONDecodeError as exc:
                    response = AiMediationResponse(
                        request_id="bridge-invalid-json",
                        ok=False,
                        task_type="structured_extraction",
                        policy_level="none",
                        error=AiMediationError(
                            code="invalid_request",
                            message=str(exc),
                            retryable=False,
                            details={},
                        ),
                        metadata=AiMediationMetadata(
                            provider="core",
                            model="core",
                            request_size_class="small",
                            duration_ms=0,
                            redaction_applied=False,
                            usage=AiUsageMetadata(),
                        ),
                    )
                else:
                    response = service.mediate(manifest=manifest, request=payload)
                body = response.model_dump_json(exclude_none=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        return Handler


@contextmanager
def bind_plugin_ai_runtime_client(client: PluginAiRuntimeClient) -> Iterator[None]:
    token = _BOUND_PLUGIN_AI_CLIENT.set(client)
    try:
        yield
    finally:
        _BOUND_PLUGIN_AI_CLIENT.reset(token)


def resolve_plugin_ai_runtime_client() -> PluginAiRuntimeClient:
    bound = _BOUND_PLUGIN_AI_CLIENT.get()
    if bound is not None:
        return bound

    from os import getenv

    url = getenv(PLUGIN_AI_BRIDGE_URL_ENV)
    token = getenv(PLUGIN_AI_BRIDGE_TOKEN_ENV)
    if url and token:
        return HttpPluginAiRuntimeClient(url=url, token=token)
    raise PluginAiBridgeUnavailableError(
        "plugin AI bridge is unavailable; requests must run inside a core-hosted connector runtime"
    )


@contextmanager
def maybe_plugin_ai_bridge_server(
    *,
    service: PluginAiMediationService | None,
    manifest: ConnectorManifest,
) -> Iterator[dict[str, str]]:
    if service is None:
        yield {}
        return
    with contextlib.ExitStack() as stack:
        bridge = stack.enter_context(PluginAiBridgeServer(service=service, manifest=manifest))
        yield bridge.environment
