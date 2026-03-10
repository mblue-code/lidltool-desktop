from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

from lidltool.connectors.runtime.protocol import (
    ConnectorActionRequest,
    ConnectorActionResponse,
    RuntimeErrorPayload,
    build_runtime_error_response,
    build_runtime_success_response,
    dump_runtime_envelope_json,
    parse_runtime_request_envelope,
)
from lidltool.connectors.sdk.offer import (
    OfferActionRequest,
    OfferActionResponse,
    validate_offer_action_response,
)
from lidltool.connectors.sdk.receipt import (
    ConnectorError,
    ConnectorErrorCode,
    ReceiptActionRequest,
    ReceiptActionResponse,
    validate_receipt_action_response,
)


def load_entrypoint(entrypoint: str) -> object:
    module_ref, _, attr_name = entrypoint.partition(":")
    if not module_ref or not attr_name:
        raise ValueError("entrypoint must use the format '<module-or-file>:<attribute>'")
    module = _load_module(module_ref)
    exported = getattr(module, attr_name)
    if callable(exported):
        return exported()
    return exported


def serve(entrypoint: str) -> int:
    raw_request = sys.stdin.read()
    request_envelope = parse_runtime_request_envelope(raw_request)
    started = time.monotonic()
    try:
        runtime = load_entrypoint(entrypoint)
        if not hasattr(runtime, "invoke_action"):
            raise TypeError("runtime entrypoint object must define invoke_action(request)")
        raw_response = runtime.invoke_action(request_envelope.request)
        response = _validate_response(raw_response)
    except Exception as exc:
        duration_ms = max(int((time.monotonic() - started) * 1000), 0)
        error_code: ConnectorErrorCode
        if isinstance(exc, ValueError):
            error_code = "invalid_request"
        else:
            error_code = "internal_error"
        response = _failure_response(
            request=request_envelope.request,
            error=ConnectorError(
                code=error_code,
                message=str(exc),
                retryable=False,
            ),
        )
        envelope = build_runtime_success_response(
            request_id=request_envelope.request_id,
            plugin_id=request_envelope.metadata.plugin_id,
            source_id=request_envelope.metadata.source_id,
            runtime_kind=request_envelope.metadata.runtime_kind,
            entrypoint=entrypoint,
            response=response,
            duration_ms=duration_ms,
        )
        sys.stdout.write(dump_runtime_envelope_json(envelope))
        sys.stdout.flush()
        return 0
    duration_ms = max(int((time.monotonic() - started) * 1000), 0)
    envelope = build_runtime_success_response(
        request_id=request_envelope.request_id,
        plugin_id=request_envelope.metadata.plugin_id,
        source_id=request_envelope.metadata.source_id,
        runtime_kind=request_envelope.metadata.runtime_kind,
        entrypoint=entrypoint,
        response=response,
        duration_ms=duration_ms,
    )
    sys.stdout.write(dump_runtime_envelope_json(envelope))
    sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a receipt connector runtime action")
    parser.add_argument("--entrypoint", required=True, help="Connector entrypoint module or file")
    args = parser.parse_args(argv)
    try:
        return serve(args.entrypoint)
    except Exception as exc:
        error = build_runtime_error_response(
            request_id="unknown",
            plugin_id="unknown",
            source_id="unknown",
            runtime_kind="subprocess_python",
            entrypoint=args.entrypoint,
            action="get_diagnostics",
            error=RuntimeErrorPayload(
                code="protocol_violation",
                message=str(exc),
                retryable=False,
            ),
        )
        sys.stdout.write(dump_runtime_envelope_json(error))
        sys.stdout.flush()
        return 1


def _load_module(module_ref: str) -> ModuleType:
    if module_ref.endswith(".py") or "/" in module_ref:
        path = Path(module_ref)
        if not path.is_absolute():
            path = Path.cwd() / path
        spec = importlib.util.spec_from_file_location(f"lidltool_runtime_{abs(hash(path))}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"unable to load module from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_ref)


def _failure_response(
    *,
    request: ConnectorActionRequest,
    error: ConnectorError,
) -> ConnectorActionResponse:
    response_payload = {
        "contract_version": request.contract_version,
        "plugin_family": request.plugin_family,
        "action": request.action,
        "ok": False,
        "warnings": (),
        "error": error.model_dump(mode="python"),
        "output": None,
    }
    if request.plugin_family == "offer":
        return validate_offer_action_response(response_payload)
    return validate_receipt_action_response(response_payload)


def _validate_response(value: object) -> ConnectorActionResponse:
    if isinstance(value, OfferActionResponse):
        return validate_offer_action_response(value)
    if isinstance(value, ReceiptActionResponse):
        return validate_receipt_action_response(value)
    if isinstance(value, dict) and value.get("plugin_family") == "offer":
        return validate_offer_action_response(value)
    return validate_receipt_action_response(value)


if __name__ == "__main__":
    raise SystemExit(main())
