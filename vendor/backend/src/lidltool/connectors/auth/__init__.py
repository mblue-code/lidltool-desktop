from lidltool.connectors.auth.auth_capabilities import (
    AuthKind,
    ConnectorAuthCapabilities,
)
from lidltool.connectors.auth.auth_status import (
    AuthActionResult,
    AuthBootstrapSnapshot,
    AuthStatusSnapshot,
)

__all__ = [
    "AuthActionResult",
    "AuthBootstrapSnapshot",
    "AuthKind",
    "AuthStatusSnapshot",
    "ConnectorAuthCapabilities",
    "ConnectorAuthOrchestrationService",
    "ConnectorAuthSessionRegistry",
    "ConnectorBootstrapSession",
    "any_connector_bootstrap_running",
    "connector_bootstrap_is_running",
    "serialize_connector_bootstrap",
    "start_connector_command_session",
    "stream_connector_bootstrap_output",
    "terminate_connector_bootstrap",
]


def __getattr__(name: str) -> object:
    if name in {
        "ConnectorAuthOrchestrationService",
        "ConnectorAuthSessionRegistry",
        "ConnectorBootstrapSession",
        "any_connector_bootstrap_running",
        "connector_bootstrap_is_running",
        "serialize_connector_bootstrap",
        "start_connector_command_session",
        "stream_connector_bootstrap_output",
        "terminate_connector_bootstrap",
    }:
        from lidltool.connectors.auth.auth_orchestration import (
            ConnectorAuthOrchestrationService,
            ConnectorAuthSessionRegistry,
            ConnectorBootstrapSession,
            any_connector_bootstrap_running,
            connector_bootstrap_is_running,
            serialize_connector_bootstrap,
            start_connector_command_session,
            stream_connector_bootstrap_output,
            terminate_connector_bootstrap,
        )

        exports = {
            "ConnectorAuthOrchestrationService": ConnectorAuthOrchestrationService,
            "ConnectorAuthSessionRegistry": ConnectorAuthSessionRegistry,
            "ConnectorBootstrapSession": ConnectorBootstrapSession,
            "any_connector_bootstrap_running": any_connector_bootstrap_running,
            "connector_bootstrap_is_running": connector_bootstrap_is_running,
            "serialize_connector_bootstrap": serialize_connector_bootstrap,
            "start_connector_command_session": start_connector_command_session,
            "stream_connector_bootstrap_output": stream_connector_bootstrap_output,
            "terminate_connector_bootstrap": terminate_connector_bootstrap,
        }
        return exports[name]
    raise AttributeError(name)
