from __future__ import annotations

from lidltool.connectors.runtime.protocol import (
    RuntimeErrorCode,
    RuntimeErrorPayload,
    RuntimeInvocationDiagnostics,
)


class ConnectorRuntimeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: RuntimeErrorCode,
        diagnostics: RuntimeInvocationDiagnostics,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics
        self.retryable = retryable
        self.diagnostics.failure_stage = "runtime"
        self.diagnostics.failure_code = code
        self.diagnostics.failure_retryable = retryable
        self.diagnostics.failure_detail = message

    def to_payload(self) -> RuntimeErrorPayload:
        return RuntimeErrorPayload(
            code=self.code,
            message=str(self),
            retryable=self.retryable,
            details=self.diagnostics.model_dump(mode="python"),
        )


class ConnectorRuntimeLaunchError(ConnectorRuntimeError):
    def __init__(self, message: str, *, diagnostics: RuntimeInvocationDiagnostics) -> None:
        super().__init__(message, code="launch_failure", diagnostics=diagnostics, retryable=False)


class ConnectorRuntimeTimeoutError(ConnectorRuntimeError):
    def __init__(self, message: str, *, diagnostics: RuntimeInvocationDiagnostics) -> None:
        super().__init__(message, code="timeout", diagnostics=diagnostics, retryable=True)


class ConnectorRuntimeProtocolError(ConnectorRuntimeError):
    def __init__(self, message: str, *, diagnostics: RuntimeInvocationDiagnostics) -> None:
        super().__init__(message, code="protocol_violation", diagnostics=diagnostics, retryable=False)


class ConnectorRuntimeMalformedResponseError(ConnectorRuntimeError):
    def __init__(self, message: str, *, diagnostics: RuntimeInvocationDiagnostics) -> None:
        super().__init__(message, code="malformed_response", diagnostics=diagnostics, retryable=False)


class ConnectorRuntimeNonZeroExitError(ConnectorRuntimeError):
    def __init__(self, message: str, *, diagnostics: RuntimeInvocationDiagnostics) -> None:
        super().__init__(message, code="non_zero_exit", diagnostics=diagnostics, retryable=True)


class ConnectorRuntimeCanceledError(ConnectorRuntimeError):
    def __init__(self, message: str, *, diagnostics: RuntimeInvocationDiagnostics) -> None:
        super().__init__(message, code="canceled", diagnostics=diagnostics, retryable=True)
