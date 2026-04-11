from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from lidltool.ai.mediation import PluginAiMediationService
from lidltool.connectors._sdk_compat import coerce_receipt_connector
from lidltool.connectors.base import Connector
from lidltool.connectors.runtime.bridge import (
    DirectPluginAiRuntimeClient,
    bind_plugin_ai_runtime_client,
)
from lidltool.connectors.runtime.errors import (
    ConnectorRuntimeCanceledError,
    ConnectorRuntimeError,
    ConnectorRuntimeLaunchError,
)
from lidltool.connectors.runtime.protocol import (
    ConnectorActionRequest,
    ConnectorActionResponse,
    RuntimeInvocationDiagnostics,
    build_runtime_request_envelope,
    validate_connector_action_response,
)
from lidltool.connectors.runtime.subprocess import SubprocessConnectorRuntime
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.offer import (
    DiscoverOffersRequest,
    DiscoverOffersResponse,
    EmptyInput as OfferEmptyInput,
    FetchOfferDetailInput,
    FetchOfferDetailRequest,
    FetchOfferDetailResponse,
    GetOfferDiagnosticsRequest,
    GetOfferDiagnosticsResponse,
    GetOfferScopeRequest,
    GetOfferScopeResponse,
    HealthcheckRequest as OfferHealthcheckRequest,
    HealthcheckResponse as OfferHealthcheckResponse,
    NormalizeOfferInput,
    NormalizeOfferRequest,
    NormalizeOfferResponse,
    OfferActionName,
    OfferActionRequest,
    OfferActionResponse,
    validate_offer_action_request,
    validate_offer_action_response,
)
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    CancelAuthRequest,
    CancelAuthResponse,
    ConnectorError,
    ConfirmAuthRequest,
    ConfirmAuthResponse,
    DiscoverRecordsRequest,
    DiscoverRecordsResponse,
    EmptyInput,
    ExtractDiscountsInput,
    ExtractDiscountsRequest,
    ExtractDiscountsResponse,
    FetchRecordInput,
    FetchRecordRequest,
    FetchRecordResponse,
    GetAuthStatusRequest,
    GetAuthStatusResponse,
    HealthcheckRequest,
    HealthcheckResponse,
    NormalizeRecordInput,
    NormalizeRecordRequest,
    NormalizeRecordResponse,
    ReceiptActionName,
    ReceiptActionRequest,
    ReceiptActionResponse,
    StartAuthRequest,
    StartAuthResponse,
    validate_receipt_action_request,
    validate_receipt_action_response,
)


@dataclass(slots=True, frozen=True)
class ConnectorRuntimeTarget:
    manifest: ConnectorManifest
    working_directory: Path | None = None
    environment: dict[str, str] | None = None
    connector: object | None = None
    legacy_auth_delegate: Connector | None = None


@dataclass(slots=True, frozen=True)
class RuntimeInvocationResult:
    response: ConnectorActionResponse
    diagnostics: RuntimeInvocationDiagnostics


ReceiptConnectorRuntimeTarget = ConnectorRuntimeTarget
OfferConnectorRuntimeTarget = ConnectorRuntimeTarget


class ConnectorRuntimeHost:
    def __init__(self, *, plugin_ai_service: PluginAiMediationService | None = None) -> None:
        self._plugin_ai_service = plugin_ai_service

    def invoke_action(
        self,
        *,
        target: ConnectorRuntimeTarget,
        request: ConnectorActionRequest | dict[str, Any],
        timeout_s: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> RuntimeInvocationResult:
        validated_request = self._validate_request(request)
        if cancel_event is not None and cancel_event.is_set():
            diagnostics = RuntimeInvocationDiagnostics(
                request_id="not-started",
                plugin_id=target.manifest.plugin_id,
                source_id=target.manifest.source_id,
                runtime_kind=target.manifest.runtime_kind,
                transport=self._transport_name(target),
                entrypoint=target.manifest.entrypoint,
                action=validated_request.action,
                duration_ms=0,
                canceled=True,
            )
            raise ConnectorRuntimeCanceledError(
                "connector runtime canceled before start",
                diagnostics=diagnostics,
            )

        request_envelope = build_runtime_request_envelope(
            plugin_id=target.manifest.plugin_id,
            source_id=target.manifest.source_id,
            runtime_kind=target.manifest.runtime_kind,
            entrypoint=target.manifest.entrypoint,
            request=validated_request,
        )
        if target.manifest.runtime_kind == "builtin":
            return self._invoke_in_process(
                target=target,
                request=request_envelope.request,
                request_id=request_envelope.request_id,
            )
        if target.manifest.runtime_kind in {"subprocess_python", "subprocess_binary"}:
            runtime = SubprocessConnectorRuntime(
                manifest=target.manifest,
                working_directory=target.working_directory,
                extra_environment=target.environment,
                plugin_ai_service=self._plugin_ai_service,
            )
            result = runtime.invoke_action(
                request_envelope,
                timeout_s=timeout_s,
                cancel_event=cancel_event,
            )
            return RuntimeInvocationResult(response=result.response, diagnostics=result.diagnostics)
        diagnostics = RuntimeInvocationDiagnostics(
            request_id=request_envelope.request_id,
            plugin_id=target.manifest.plugin_id,
            source_id=target.manifest.source_id,
            runtime_kind=target.manifest.runtime_kind,
            transport=self._transport_name(target),
            entrypoint=target.manifest.entrypoint,
            action=validated_request.action,
            duration_ms=0,
        )
        raise ConnectorRuntimeLaunchError(
            f"unsupported connector runtime_kind: {target.manifest.runtime_kind}",
            diagnostics=diagnostics,
        )

    def _invoke_in_process(
        self,
        *,
        target: ConnectorRuntimeTarget,
        request: ConnectorActionRequest,
        request_id: str,
    ) -> RuntimeInvocationResult:
        if target.connector is None:
            diagnostics = RuntimeInvocationDiagnostics(
                request_id=request_id,
                plugin_id=target.manifest.plugin_id,
                source_id=target.manifest.source_id,
                runtime_kind=target.manifest.runtime_kind,
                transport="in_process",
                entrypoint=target.manifest.entrypoint,
                action=request.action,
                duration_ms=0,
            )
            raise ConnectorRuntimeLaunchError(
                "builtin connector runtime requires an in-process connector instance",
                diagnostics=diagnostics,
            )
        runtime = self._coerce_runtime(target=target)
        started = time.monotonic()
        if self._plugin_ai_service is None:
            raw_response = runtime.invoke_action(request)
        else:
            with bind_plugin_ai_runtime_client(
                DirectPluginAiRuntimeClient(
                    service=self._plugin_ai_service,
                    manifest=target.manifest,
                )
            ):
                raw_response = runtime.invoke_action(request)
        response = validate_connector_action_response(raw_response)
        diagnostics = RuntimeInvocationDiagnostics(
            request_id=request_id,
            plugin_id=target.manifest.plugin_id,
            source_id=target.manifest.source_id,
            runtime_kind=target.manifest.runtime_kind,
            transport="in_process",
            entrypoint=target.manifest.entrypoint,
            action=request.action,
            duration_ms=max(int((time.monotonic() - started) * 1000), 0),
            response_ok=response.ok,
        )
        return RuntimeInvocationResult(response=response, diagnostics=diagnostics)

    def _transport_name(self, target: ConnectorRuntimeTarget) -> str:
        if target.manifest.runtime_kind == "builtin":
            return "in_process"
        if target.manifest.runtime_kind in {"subprocess_python", "subprocess_binary"}:
            return "subprocess"
        return target.manifest.runtime_kind

    def _coerce_runtime(self, *, target: ConnectorRuntimeTarget) -> object:
        if target.manifest.plugin_family == "receipt":
            return coerce_receipt_connector(target.connector, manifest=target.manifest)
        if not hasattr(target.connector, "invoke_action"):
            raise TypeError("offer connector runtime entrypoint must define invoke_action(request)")
        return target.connector

    def _validate_request(
        self,
        request: ConnectorActionRequest | dict[str, Any],
    ) -> ConnectorActionRequest:
        if isinstance(request, dict):
            plugin_family = request.get("plugin_family", "receipt")
        else:
            plugin_family = getattr(request, "plugin_family", "receipt")
        if plugin_family == "offer":
            return validate_offer_action_request(request)
        return validate_receipt_action_request(request)


class RuntimeHostedReceiptConnector(Connector):
    def __init__(
        self,
        *,
        host: ConnectorRuntimeHost,
        target: ConnectorRuntimeTarget,
        action_timeouts_s: dict[ReceiptActionName, float] | None = None,
    ) -> None:
        self._host = host
        self._target = target
        self._action_timeouts_s = action_timeouts_s or {}
        self._latest_diagnostics: list[RuntimeInvocationDiagnostics] = []

    def latest_runtime_diagnostics(self) -> list[RuntimeInvocationDiagnostics]:
        return list(self._latest_diagnostics)

    def authenticate(self) -> dict[str, Any]:
        if self._target.legacy_auth_delegate is not None:
            return self._target.legacy_auth_delegate.authenticate()
        response = cast(
            GetAuthStatusResponse,
            self._invoke(GetAuthStatusRequest(input=EmptyInput())),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector get_auth_status returned no payload")
        if not output.is_authenticated:
            raise RuntimeError(output.detail or "connector requires authentication")
        return output.metadata

    def get_auth_status(self) -> dict[str, Any]:
        response = cast(
            GetAuthStatusResponse,
            self._invoke(GetAuthStatusRequest(input=EmptyInput())),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector get_auth_status returned no payload")
        return output.model_dump(mode="python")

    def refresh_auth(self) -> dict[str, Any]:
        if self._target.legacy_auth_delegate is not None:
            return self._target.legacy_auth_delegate.refresh_auth()
        return self.authenticate()

    def start_auth(self) -> dict[str, Any]:
        return self._invoke_auth_action(StartAuthRequest(input=EmptyInput()))

    def cancel_auth(self) -> dict[str, Any]:
        return self._invoke_auth_action(CancelAuthRequest(input=EmptyInput()))

    def confirm_auth(self) -> dict[str, Any]:
        return self._invoke_auth_action(ConfirmAuthRequest(input=EmptyInput()))

    def healthcheck(self) -> dict[str, Any]:
        response = cast(
            HealthcheckResponse,
            self._invoke(HealthcheckRequest(input=EmptyInput())),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector healthcheck returned no payload")
        return output.model_dump(mode="python")

    def discover_new_records(self) -> list[str]:
        response = cast(DiscoverRecordsResponse, self._invoke(DiscoverRecordsRequest()))
        output = response.output
        if output is None:
            raise RuntimeError("connector discover_records returned no payload")
        return [record.record_ref for record in output.records]

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        response = cast(
            FetchRecordResponse,
            self._invoke(FetchRecordRequest(input=FetchRecordInput(record_ref=record_ref))),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector fetch_record returned no payload")
        return output.record

    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        response = cast(
            NormalizeRecordResponse,
            self._invoke(NormalizeRecordRequest(input=NormalizeRecordInput(record=record_detail))),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector normalize_record returned no payload")
        return output.normalized_record.model_dump(mode="python")

    def extract_discounts(self, record_detail: dict[str, Any]) -> list[dict[str, Any]]:
        response = cast(
            ExtractDiscountsResponse,
            self._invoke(ExtractDiscountsRequest(input=ExtractDiscountsInput(record=record_detail))),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector extract_discounts returned no payload")
        return [row.model_dump(mode="python") for row in output.discounts]

    def get_runtime_diagnostics(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="python") for item in self._latest_diagnostics]

    def runtime_identity(self) -> dict[str, Any]:
        manifest = self._target.manifest
        return {
            "plugin_id": manifest.plugin_id,
            "source_id": manifest.source_id,
            "manifest_version": manifest.manifest_version,
            "connector_api_version": manifest.connector_api_version,
            "runtime_kind": manifest.runtime_kind,
            "entrypoint": manifest.entrypoint,
        }

    def _invoke(self, request: ReceiptActionRequest) -> ReceiptActionResponse:
        validated_request = validate_receipt_action_request(request)
        try:
            result = self._host.invoke_action(
                target=self._target,
                request=validated_request,
                timeout_s=self._action_timeouts_s.get(validated_request.action),
            )
        except ConnectorRuntimeError as exc:
            self._append_diagnostics(exc.diagnostics)
            raise
        response = validate_receipt_action_response(result.response)
        if response.ok:
            self._append_diagnostics(result.diagnostics)
            return response
        if response.error is not None:
            result.diagnostics.failure_stage = "connector_action"
            result.diagnostics.failure_code = response.error.code
            result.diagnostics.failure_retryable = response.error.retryable
            result.diagnostics.failure_detail = response.error.message
        self._append_diagnostics(result.diagnostics)
        raise RuntimeError(self._connector_error_message(response.error, action=response.action))

    def _append_diagnostics(self, diagnostics: RuntimeInvocationDiagnostics) -> None:
        self._latest_diagnostics.append(diagnostics)
        self._latest_diagnostics = self._latest_diagnostics[-20:]

    def _connector_error_message(
        self,
        error: ConnectorError | None,
        *,
        action: str,
    ) -> str:
        if error is None:
            return f"connector action failed: {action}"
        return f"{action} failed: {error.message}"

    def _invoke_auth_action(
        self,
        request: StartAuthRequest | CancelAuthRequest | ConfirmAuthRequest,
    ) -> dict[str, Any]:
        response = self._invoke(request)
        typed_response = cast(
            StartAuthResponse | CancelAuthResponse | ConfirmAuthResponse,
            response,
        )
        output = typed_response.output
        if output is None:
            raise RuntimeError(f"connector {typed_response.action} returned no payload")
        return output.model_dump(mode="python")


class RuntimeHostedOfferConnector:
    def __init__(
        self,
        *,
        host: ConnectorRuntimeHost,
        target: ConnectorRuntimeTarget,
        action_timeouts_s: dict[OfferActionName, float] | None = None,
    ) -> None:
        self._host = host
        self._target = target
        self._action_timeouts_s = action_timeouts_s or {}
        self._latest_diagnostics: list[RuntimeInvocationDiagnostics] = []

    def latest_runtime_diagnostics(self) -> list[RuntimeInvocationDiagnostics]:
        return list(self._latest_diagnostics)

    def healthcheck(self) -> dict[str, Any]:
        response = cast(
            OfferHealthcheckResponse,
            self._invoke(OfferHealthcheckRequest(input=OfferEmptyInput())),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector healthcheck returned no payload")
        return output.model_dump(mode="python")

    def discover_offers(self) -> list[str]:
        response = cast(DiscoverOffersResponse, self._invoke(DiscoverOffersRequest()))
        output = response.output
        if output is None:
            raise RuntimeError("connector discover_offers returned no payload")
        return [offer.offer_ref for offer in output.offers]

    def fetch_offer_detail(self, offer_ref: str) -> dict[str, Any]:
        response = cast(
            FetchOfferDetailResponse,
            self._invoke(FetchOfferDetailRequest(input=FetchOfferDetailInput(offer_ref=offer_ref))),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector fetch_offer_detail returned no payload")
        return output.offer

    def normalize_offer(self, offer_detail: dict[str, Any]) -> dict[str, Any]:
        response = cast(
            NormalizeOfferResponse,
            self._invoke(NormalizeOfferRequest(input=NormalizeOfferInput(offer=offer_detail))),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector normalize_offer returned no payload")
        return output.normalized_offer.model_dump(mode="python")

    def get_offer_scope(self) -> dict[str, Any]:
        response = cast(GetOfferScopeResponse, self._invoke(GetOfferScopeRequest(input=OfferEmptyInput())))
        output = response.output
        if output is None:
            raise RuntimeError("connector get_offer_scope returned no payload")
        return output.model_dump(mode="python")

    def get_offer_diagnostics(self) -> dict[str, Any]:
        response = cast(
            GetOfferDiagnosticsResponse,
            self._invoke(GetOfferDiagnosticsRequest(input=OfferEmptyInput())),
        )
        output = response.output
        if output is None:
            raise RuntimeError("connector get_offer_diagnostics returned no payload")
        return output.model_dump(mode="python")

    def get_runtime_diagnostics(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="python") for item in self._latest_diagnostics]

    def runtime_identity(self) -> dict[str, Any]:
        manifest = self._target.manifest
        return {
            "plugin_id": manifest.plugin_id,
            "source_id": manifest.source_id,
            "manifest_version": manifest.manifest_version,
            "connector_api_version": manifest.connector_api_version,
            "runtime_kind": manifest.runtime_kind,
            "entrypoint": manifest.entrypoint,
        }

    def _invoke(self, request: OfferActionRequest) -> OfferActionResponse:
        validated_request = validate_offer_action_request(request)
        try:
            result = self._host.invoke_action(
                target=self._target,
                request=validated_request,
                timeout_s=self._action_timeouts_s.get(validated_request.action),
            )
        except ConnectorRuntimeError as exc:
            self._append_diagnostics(exc.diagnostics)
            raise
        response = validate_offer_action_response(result.response)
        if response.ok:
            self._append_diagnostics(result.diagnostics)
            return response
        if response.error is not None:
            result.diagnostics.failure_stage = "connector_action"
            result.diagnostics.failure_code = response.error.code
            result.diagnostics.failure_retryable = response.error.retryable
            result.diagnostics.failure_detail = response.error.message
        self._append_diagnostics(result.diagnostics)
        raise RuntimeError(self._connector_error_message(response.error, action=response.action))

    def _append_diagnostics(self, diagnostics: RuntimeInvocationDiagnostics) -> None:
        self._latest_diagnostics.append(diagnostics)
        self._latest_diagnostics = self._latest_diagnostics[-20:]

    def _connector_error_message(
        self,
        error: ConnectorError | None,
        *,
        action: str,
    ) -> str:
        if error is None:
            return f"connector action failed: {action}"
        return f"{action} failed: {error.message}"


def default_runtime_action_timeouts(request_timeout_s: float) -> dict[ReceiptActionName, float]:
    timeout = max(request_timeout_s, 1.0)
    return {
        "get_manifest": min(timeout, 5.0),
        "healthcheck": timeout,
        "get_auth_status": timeout,
        "start_auth": timeout,
        "cancel_auth": timeout,
        "confirm_auth": timeout,
        "discover_records": timeout,
        "fetch_record": timeout,
        "normalize_record": timeout,
        "extract_discounts": timeout,
        "get_diagnostics": timeout,
    }


def default_offer_runtime_action_timeouts(request_timeout_s: float) -> dict[OfferActionName, float]:
    timeout = max(request_timeout_s, 1.0)
    return {
        "get_manifest": min(timeout, 5.0),
        "healthcheck": timeout,
        "discover_offers": timeout,
        "fetch_offer_detail": timeout,
        "normalize_offer": timeout,
        "get_offer_scope": timeout,
        "get_offer_diagnostics": timeout,
    }
