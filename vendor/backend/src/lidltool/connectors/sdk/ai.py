from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lidltool.ai.schemas import (
    AI_MEDIATION_CONTRACT_VERSION,
    AiInputPart,
    AiMediationError,
    AiMediationMetadata,
    AiMediationRequest,
    AiMediationResponse,
    AiPolicyLevel,
    AiStructuredSchema,
    AiTaskType,
    validate_ai_mediation_request,
    validate_ai_mediation_response,
)
from lidltool.connectors.runtime.bridge import (
    PluginAiBridgeUnavailableError,
    resolve_plugin_ai_runtime_client,
)


def request_ai_mediation(
    request: AiMediationRequest | Mapping[str, Any],
) -> AiMediationResponse:
    validated_request = validate_ai_mediation_request(request)
    client = resolve_plugin_ai_runtime_client()
    response = client.mediate(validated_request)
    return validate_ai_mediation_response(response)


__all__ = [
    "AI_MEDIATION_CONTRACT_VERSION",
    "AiInputPart",
    "AiMediationError",
    "AiMediationMetadata",
    "AiMediationRequest",
    "AiMediationResponse",
    "AiPolicyLevel",
    "AiStructuredSchema",
    "AiTaskType",
    "PluginAiBridgeUnavailableError",
    "request_ai_mediation",
]
