from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from lidltool.ai.schemas import (
    AiInputPart,
    AiMediationRequest,
    AiPolicyLevel,
    AiStructuredSchema,
    AiTaskType,
)

TrustClass = Literal["official", "community_verified", "community_unsigned", "local_custom"]


class PluginAiManifestLike(Protocol):
    plugin_id: str
    trust_class: TrustClass
    policy: Any

_POLICY_ORDER: dict[AiPolicyLevel, int] = {
    "none": 0,
    "extract_only": 1,
    "limited_reasoning": 2,
    "agentic_experimental": 3,
}

_THIRD_PARTY_TRUST_CLASSES: set[TrustClass] = {
    "community_verified",
    "community_unsigned",
    "local_custom",
}

_EXTRACT_ONLY_TASKS: set[AiTaskType] = {
    "structured_extraction",
    "document_classification",
    "offer_flyer_parsing",
    "product_alias_matching",
    "schema_repair",
}


class PluginAiTrustClassPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    max_policy_level: AiPolicyLevel | None = None


class PluginAiPluginOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    max_policy_level: AiPolicyLevel | None = None
    max_requests_per_process: int | None = Field(default=None, ge=1)
    max_payload_bytes: int | None = Field(default=None, ge=1)
    max_timeout_s: float | None = Field(default=None, gt=0.0)


class PluginAiLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_payload_bytes: int = Field(default=24_576, ge=1)
    max_artifact_count: int = Field(default=4, ge=0)
    max_image_count: int = Field(default=4, ge=0)
    max_pdf_count: int = Field(default=1, ge=0)
    timeout_s: float = Field(default=30.0, gt=0.0)
    retry_ceiling: int = Field(default=0, ge=0)
    max_schema_depth: int = Field(default=6, ge=1)


class PluginAiBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_requests_per_process: int | None = Field(default=250, ge=1)
    max_requests_per_plugin_process: int | None = Field(default=100, ge=1)
    max_cost_usd_per_request: float | None = Field(default=None, ge=0.0)
    max_cost_usd_per_plugin_process: float | None = Field(default=None, ge=0.0)
    future_daily_cost_usd: float | None = Field(default=None, ge=0.0)
    future_monthly_cost_usd: float | None = Field(default=None, ge=0.0)


class PluginAiMediationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    default_policy_level: AiPolicyLevel = "none"
    trust_defaults: dict[str, PluginAiTrustClassPolicy] = Field(
        default_factory=lambda: {
            "official": PluginAiTrustClassPolicy(enabled=False, max_policy_level="none"),
            "community_verified": PluginAiTrustClassPolicy(enabled=False, max_policy_level="none"),
            "community_unsigned": PluginAiTrustClassPolicy(enabled=False, max_policy_level="none"),
            "local_custom": PluginAiTrustClassPolicy(enabled=False, max_policy_level="none"),
        }
    )
    plugin_overrides: dict[str, PluginAiPluginOverride] = Field(default_factory=dict)
    limits: PluginAiLimits = Field(default_factory=PluginAiLimits)
    budgets: PluginAiBudgets = Field(default_factory=PluginAiBudgets)


class EffectivePluginAiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    max_policy_level: AiPolicyLevel
    max_payload_bytes: int
    timeout_s: float
    max_requests_per_process: int | None = None


class PluginAiPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str | None = None
    effective: EffectivePluginAiSettings
    task_type: AiTaskType


def evaluate_plugin_ai_policy(
    *,
    config: PluginAiMediationConfig,
    manifest: PluginAiManifestLike,
    request: AiMediationRequest,
) -> PluginAiPolicyDecision:
    plugin_override = config.plugin_overrides.get(manifest.plugin_id)
    trust_policy = config.trust_defaults.get(manifest.trust_class, PluginAiTrustClassPolicy())

    effective = EffectivePluginAiSettings(
        enabled=_effective_enabled(config=config, trust_policy=trust_policy, plugin_override=plugin_override),
        max_policy_level=_effective_policy_level(
            config=config,
            manifest=manifest,
            trust_policy=trust_policy,
            plugin_override=plugin_override,
        ),
        max_payload_bytes=plugin_override.max_payload_bytes
        if plugin_override is not None and plugin_override.max_payload_bytes is not None
        else config.limits.max_payload_bytes,
        timeout_s=plugin_override.max_timeout_s
        if plugin_override is not None and plugin_override.max_timeout_s is not None
        else config.limits.timeout_s,
        max_requests_per_process=plugin_override.max_requests_per_process
        if plugin_override is not None and plugin_override.max_requests_per_process is not None
        else config.budgets.max_requests_per_plugin_process,
    )

    if not manifest.policy.ai.allow_model_mediation:
        return PluginAiPolicyDecision(
            allowed=False,
            reason="manifest_declares_no_model_mediation",
            effective=effective,
            task_type=request.task_type,
        )
    if not config.enabled:
        return PluginAiPolicyDecision(
            allowed=False,
            reason="plugin_ai_mediation_disabled",
            effective=effective,
            task_type=request.task_type,
        )
    if not effective.enabled:
        return PluginAiPolicyDecision(
            allowed=False,
            reason="plugin_or_trust_class_disabled",
            effective=effective,
            task_type=request.task_type,
        )
    if effective.max_policy_level == "none":
        return PluginAiPolicyDecision(
            allowed=False,
            reason="effective_policy_level_is_none",
            effective=effective,
            task_type=request.task_type,
        )
    if request.requested_policy_level == "agentic_experimental":
        return PluginAiPolicyDecision(
            allowed=False,
            reason="agentic_experimental_is_reserved",
            effective=effective,
            task_type=request.task_type,
        )
    if _POLICY_ORDER[request.requested_policy_level] > _POLICY_ORDER[effective.max_policy_level]:
        return PluginAiPolicyDecision(
            allowed=False,
            reason="requested_policy_level_exceeds_effective_maximum",
            effective=effective,
            task_type=request.task_type,
        )
    if request.task_type not in _allowed_tasks_for_level(request.requested_policy_level):
        return PluginAiPolicyDecision(
            allowed=False,
            reason="task_not_allowed_for_requested_policy_level",
            effective=effective,
            task_type=request.task_type,
        )
    return PluginAiPolicyDecision(
        allowed=True,
        effective=effective,
        task_type=request.task_type,
    )


def _effective_enabled(
    *,
    config: PluginAiMediationConfig,
    trust_policy: PluginAiTrustClassPolicy,
    plugin_override: PluginAiPluginOverride | None,
) -> bool:
    if not config.enabled:
        return False
    if plugin_override is not None and plugin_override.enabled is not None:
        return plugin_override.enabled
    if trust_policy.enabled is not None:
        return trust_policy.enabled
    return True


def _effective_policy_level(
    *,
    config: PluginAiMediationConfig,
    manifest: PluginAiManifestLike,
    trust_policy: PluginAiTrustClassPolicy,
    plugin_override: PluginAiPluginOverride | None,
) -> AiPolicyLevel:
    level = config.default_policy_level
    if trust_policy.max_policy_level is not None:
        level = trust_policy.max_policy_level
    if plugin_override is not None and plugin_override.max_policy_level is not None:
        level = plugin_override.max_policy_level

    if level == "agentic_experimental":
        return "none"
    if manifest.trust_class in _THIRD_PARTY_TRUST_CLASSES and _POLICY_ORDER[level] > _POLICY_ORDER["extract_only"]:
        return "extract_only"
    return level


def _allowed_tasks_for_level(level: AiPolicyLevel) -> set[AiTaskType]:
    if level == "none":
        return set()
    if level in {"extract_only", "limited_reasoning"}:
        return set(_EXTRACT_ONLY_TASKS)
    return set()


def is_plugin_ai_enabled_for_manifest(
    *,
    config: PluginAiMediationConfig,
    manifest: PluginAiManifestLike,
    requested_policy_level: AiPolicyLevel = "extract_only",
    task_type: AiTaskType = "structured_extraction",
) -> bool:
    request = AiMediationRequest(
        task_type=task_type,
        requested_policy_level=requested_policy_level,
        output_schema=AiStructuredSchema(type="object", properties={}, required=()),
        inputs=[AiInputPart(kind="sanitized_text", text="probe")],
    )
    return evaluate_plugin_ai_policy(config=config, manifest=manifest, request=request).allowed
