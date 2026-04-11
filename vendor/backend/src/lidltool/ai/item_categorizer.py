from __future__ import annotations

from dataclasses import dataclass

from lidltool.ai.config import get_ai_api_key, get_ai_oauth_access_token, get_item_categorizer_api_key, get_local_text_model_api_key
from lidltool.ai.runtime import (
    BundledLocalTextRuntimeAdapter,
    ModelRuntime,
    RuntimePolicyMode,
    RuntimeProviderKind,
    RuntimeTask,
    describe_runtime_capabilities,
    is_local_endpoint,
    resolve_runtime,
    resolve_runtime_client,
    validate_runtime_endpoint,
)
from lidltool.config import AppConfig

_DEFAULT_MODEL = "qwen3.5:0.8b"


@dataclass(slots=True)
class ItemCategorizerSettings:
    enabled: bool
    base_url: str | None
    api_key: str | None
    model: str
    timeout_s: float
    max_retries: int
    max_batch_size: int
    confidence_threshold: float
    ocr_confidence_threshold: float
    allow_remote: bool

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.base_url and self.model)

    @property
    def is_local_endpoint(self) -> bool:
        return is_local_endpoint(self.base_url)


@dataclass(slots=True)
class TaskRuntimeSettings:
    task: RuntimeTask
    policy_mode: RuntimePolicyMode
    provider_kind: RuntimeProviderKind | None
    enabled: bool
    base_url: str | None
    model_name: str
    api_key: str | None
    timeout_s: float
    max_retries: int
    max_batch_size: int | None = None
    allow_remote: bool = False
    runtime: ModelRuntime | None = None

    @property
    def local(self) -> bool:
        return bool(self.base_url and is_local_endpoint(self.base_url))


def resolve_item_categorizer_settings(config: AppConfig) -> ItemCategorizerSettings:
    base_url = _normalize_text(config.local_text_model_base_url) or _normalize_text(
        config.item_categorizer_base_url
    )
    api_key = (
        get_local_text_model_api_key(config)
        or get_item_categorizer_api_key(config)
        or get_ai_oauth_access_token(config)
        or get_ai_api_key(config)
    )
    model = (
        _normalize_text(config.local_text_model_name)
        or _normalize_text(config.item_categorizer_model)
        or _DEFAULT_MODEL
    )
    enabled = (
        bool(config.local_text_model_enabled)
        if config.local_text_model_enabled is not None
        else bool(config.item_categorizer_enabled)
    )
    timeout_s = (
        float(config.local_text_model_timeout_s)
        if config.local_text_model_timeout_s is not None
        else float(config.item_categorizer_timeout_s)
    )
    max_retries = (
        int(config.local_text_model_max_retries)
        if config.local_text_model_max_retries is not None
        else int(config.item_categorizer_max_retries)
    )
    allow_remote = (
        bool(config.local_text_model_allow_remote)
        if config.local_text_model_allow_remote is not None
        else bool(config.item_categorizer_allow_remote)
    )
    return ItemCategorizerSettings(
        enabled=enabled,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_s=timeout_s,
        max_retries=max_retries,
        max_batch_size=int(config.item_categorizer_max_batch_size),
        confidence_threshold=float(config.item_categorizer_confidence_threshold),
        ocr_confidence_threshold=float(config.item_categorizer_ocr_confidence_threshold),
        allow_remote=allow_remote,
    )


def resolve_item_categorizer_runtime_settings(
    config: AppConfig,
    *,
    policy_mode: RuntimePolicyMode | None = None,
    api_key_override: str | None = None,
) -> TaskRuntimeSettings:
    settings = resolve_item_categorizer_settings(config)
    effective_policy = policy_mode or _default_policy_mode(
        config,
        task=RuntimeTask.ITEM_CATEGORIZATION,
    )
    resolution = resolve_runtime(
        config,
        task=RuntimeTask.ITEM_CATEGORIZATION,
        policy_mode=effective_policy,
        api_key_override=api_key_override,
    )
    return TaskRuntimeSettings(
        task=RuntimeTask.ITEM_CATEGORIZATION,
        policy_mode=effective_policy,
        provider_kind=resolution.provider_kind,
        enabled=settings.enabled,
        base_url=settings.base_url,
        model_name=settings.model,
        api_key=api_key_override or settings.api_key,
        timeout_s=settings.timeout_s,
        max_retries=settings.max_retries,
        max_batch_size=settings.max_batch_size,
        allow_remote=settings.allow_remote,
        runtime=resolution.runtime,
    )


def resolve_pi_agent_runtime_settings(
    config: AppConfig,
    *,
    policy_mode: RuntimePolicyMode | None = None,
    api_key_override: str | None = None,
) -> TaskRuntimeSettings:
    effective_policy = policy_mode or _default_policy_mode(config, task=RuntimeTask.PI_AGENT)
    resolution = resolve_runtime(
        config,
        task=RuntimeTask.PI_AGENT,
        policy_mode=effective_policy,
        api_key_override=api_key_override,
    )
    model_name = _normalize_text(config.ai_model) or "gpt-5.2-codex"
    return TaskRuntimeSettings(
        task=RuntimeTask.PI_AGENT,
        policy_mode=effective_policy,
        provider_kind=resolution.provider_kind,
        enabled=bool(config.ai_enabled or config.ai_base_url),
        base_url=_normalize_text(config.ai_base_url),
        model_name=model_name,
        api_key=api_key_override or get_ai_oauth_access_token(config) or get_ai_api_key(config),
        timeout_s=float(config.request_timeout_s),
        max_retries=int(config.retry_attempts),
        runtime=resolution.runtime,
    )


def resolve_item_categorizer_client_kwargs(config: AppConfig) -> dict[str, object] | None:
    settings = resolve_item_categorizer_settings(config)
    if not settings.base_url:
        return None
    kwargs: dict[str, object] = {
        "base_url": settings.base_url,
        "timeout": settings.timeout_s,
        "max_retries": settings.max_retries,
    }
    if settings.api_key is not None:
        kwargs["api_key"] = settings.api_key
    return kwargs


def build_item_categorizer_runtime(
    config: AppConfig,
    *,
    policy_mode: RuntimePolicyMode | None = None,
    api_key_override: str | None = None,
) -> ModelRuntime | None:
    settings = resolve_item_categorizer_runtime_settings(
        config,
        policy_mode=policy_mode,
        api_key_override=api_key_override,
    )
    if not settings.enabled:
        return None
    if settings.runtime is not None:
        return settings.runtime
    if settings.base_url and settings.model_name:
        return BundledLocalTextRuntimeAdapter(
            task=RuntimeTask.ITEM_CATEGORIZATION,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model_name=settings.model_name,
            timeout_s=settings.timeout_s,
            max_retries=settings.max_retries,
            allow_remote=settings.allow_remote,
            allow_insecure_transport=bool(getattr(config, "allow_insecure_transport", False)),
        )
    return resolve_runtime_client(
        config,
        task=RuntimeTask.ITEM_CATEGORIZATION,
        policy_mode=settings.policy_mode,
        api_key_override=settings.api_key,
    )


def validate_item_categorizer_runtime(
    *,
    config: AppConfig,
    policy_mode: RuntimePolicyMode | None = None,
) -> None:
    settings = resolve_item_categorizer_runtime_settings(config, policy_mode=policy_mode)
    validate_runtime_endpoint(
        base_url=settings.base_url,
        allow_remote=settings.allow_remote,
        allow_insecure_transport=bool(getattr(config, "allow_insecure_transport", False)),
        purpose="item_categorizer",
    )


def describe_item_categorizer_runtime(
    config: AppConfig,
    *,
    policy_mode: RuntimePolicyMode | None = None,
):
    effective_policy = policy_mode or _default_policy_mode(
        config,
        task=RuntimeTask.ITEM_CATEGORIZATION,
    )
    return describe_runtime_capabilities(
        config,
        task=RuntimeTask.ITEM_CATEGORIZATION,
        policy_mode=effective_policy,
    )


def _default_policy_mode(config: AppConfig, *, task: RuntimeTask) -> RuntimePolicyMode:
    if task is RuntimeTask.PI_AGENT:
        return RuntimePolicyMode(str(config.pi_agent_runtime_policy))
    if task is RuntimeTask.ITEM_CATEGORIZATION:
        return RuntimePolicyMode(str(config.item_categorization_runtime_policy))
    return RuntimePolicyMode.LOCAL_PREFERRED


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
