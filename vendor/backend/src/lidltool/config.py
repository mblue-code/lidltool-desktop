from __future__ import annotations

import ipaddress
import json
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lidltool.ai.policy import PluginAiMediationConfig
from lidltool.deployment_policy import (
    HttpExposureMode,
    evaluate_deployment_policy,
    normalize_http_exposure_mode,
)

DEFAULT_SOURCE = "lidl_plus_de"
DEFAULT_CONFIG_DIR = "~/.config/lidltool"
DEFAULT_CONFIG_FILE_NAME = "config.toml"
DEFAULT_TOKEN_FILE_NAME = "token.json"
MIN_SECRET_LENGTH = 32
MIN_SECRET_UNIQUE_CHARACTERS = 8
_KNOWN_PLACEHOLDER_SECRET_VALUES = {
    "changeme",
    "changeit",
    "change-this",
    "change-me",
    "replaceit",
    "replace-this",
    "replace-me",
    "default",
    "secret",
    "password",
    "example",
    "examplekey",
    "exampletoken",
    "placeholder",
    "yourkeyhere",
    "yoursecrethere",
    "yourtokenhere",
}
_NORMALIZED_PLACEHOLDER_SECRET_VALUES = {
    "".join(ch for ch in value.strip().lower() if ch.isalnum())
    for value in _KNOWN_PLACEHOLDER_SECRET_VALUES
}


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _normalize_secret_marker(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


def _validate_secret_value(
    value: str | None,
    *,
    env_name: str,
    purpose: str,
    generation_hint: str,
    required: bool,
) -> None:
    raw = (value or "").strip()
    if not raw:
        if required:
            raise RuntimeError(
                f"FATAL: {env_name} is not set.\n"
                f"Generate one with: {generation_hint}"
            )
        return

    normalized = _normalize_secret_marker(raw)
    if (
        normalized in _NORMALIZED_PLACEHOLDER_SECRET_VALUES
        or normalized.startswith("replacewith")
        or normalized.startswith("setme")
        or normalized.startswith("insert")
    ):
        raise RuntimeError(
            f"FATAL: {env_name} uses a rejected placeholder value.\n"
            f"{purpose} must be at least {MIN_SECRET_LENGTH} characters, not a placeholder such as "
            "'changeme'/'change-me'/'replace-me', and not trivially repetitive.\n"
            f"Generate one with: {generation_hint}"
        )
    if len(raw) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"FATAL: {env_name} is too short.\n"
            f"{purpose} must be at least {MIN_SECRET_LENGTH} characters of high-entropy secret material.\n"
            f"Generate one with: {generation_hint}"
        )
    if len(set(raw)) < MIN_SECRET_UNIQUE_CHARACTERS:
        raise RuntimeError(
            f"FATAL: {env_name} is too weak.\n"
            f"{purpose} must not be trivially repetitive and should contain at least "
            f"{MIN_SECRET_UNIQUE_CHARACTERS} distinct characters.\n"
            f"Generate one with: {generation_hint}"
        )


def resolve_config_dir(value: str | Path | None = None) -> Path:
    raw = value if value is not None else os.getenv("LIDLTOOL_CONFIG_DIR", DEFAULT_CONFIG_DIR)
    return _expand_path(raw)


def default_config_file(config_dir: str | Path | None = None) -> Path:
    return resolve_config_dir(config_dir) / DEFAULT_CONFIG_FILE_NAME


def default_token_file(config_dir: str | Path | None = None) -> Path:
    return resolve_config_dir(config_dir) / DEFAULT_TOKEN_FILE_NAME


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    db_path: Path = Field(default_factory=lambda: _expand_path("~/.local/share/lidltool/db.sqlite"))
    db_url: str | None = None
    config_dir: Path = Field(default_factory=resolve_config_dir)
    token_file: Path = Field(default_factory=default_token_file)
    credential_encryption_key: str | None = None
    credential_encryption_key_id: str = "v1"
    credential_encryption_required: bool = True
    log_level: str = "INFO"
    use_lidl_plus: bool = True
    api_base_url: str | None = None
    page_size: int = 50
    max_requests_per_second: float = 2.0
    request_timeout_s: float = 30.0
    retry_attempts: int = 4
    retry_base_delay_s: float = 0.5
    already_ingested_streak_threshold: int = 8
    full_sync_max_pages: int | None = None
    receipt_cutoff_days: int | None = None
    source: str = DEFAULT_SOURCE
    openclaw_api_key: str | None = None
    openclaw_auth_mode: str = "enforce"
    auth_bootstrap_token: str | None = None
    openclaw_rate_limit_enabled: bool = False
    openclaw_rate_limit_requests: int = 60
    openclaw_rate_limit_window_s: int = 60
    http_rate_limit_enabled: bool = True
    http_rate_limit_window_s: int = 60
    http_rate_limit_read_requests: int = 600
    http_rate_limit_write_requests: int = 180
    http_rate_limit_expensive_requests: int = 60
    http_cors_enabled: bool = True
    http_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    http_cors_allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    )
    http_cors_allowed_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type", "X-API-Key"]
    )
    http_cors_allow_credentials: bool = False
    mobile_push_enabled: bool = False
    mobile_push_apns_team_id: str | None = None
    mobile_push_apns_key_id: str | None = None
    mobile_push_apns_private_key_path: Path | None = None
    mobile_push_apns_topic: str | None = None
    mobile_push_apns_use_sandbox: bool = False
    mobile_push_fcm_project_id: str | None = None
    mobile_push_fcm_service_account_json: str | None = None
    mobile_push_fcm_service_account_path: Path | None = None
    http_exposure_mode: str = HttpExposureMode.LOCALHOST.value
    http_trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    http_tools_exec_enabled: bool = False
    openclaw_scope_mode: str = "off"
    openclaw_scope_allow_param_scopes: bool = False
    openclaw_scope_default_read_scopes: list[str] = Field(default_factory=lambda: ["read.core"])
    openclaw_scope_default_write_scopes: list[str] = Field(
        default_factory=lambda: ["write.sync", "write.auth", "write.ingest"]
    )
    retry_dead_letter_threshold: int = 3
    health_window_days: int = 7
    health_min_success_rate: float = 0.97
    health_alert_on_dead_letter: bool = True
    health_alert_dedupe_window_hours: int = 6
    health_escalation_failure_threshold: int = 3
    health_correlation_min_sources: int = 2
    document_storage_path: Path = Field(
        default_factory=lambda: _expand_path("~/.local/share/lidltool/documents")
    )
    max_upload_size_mb: int = 12
    allowed_upload_mime_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "application/pdf"]
    )
    ocr_default_provider: str = "glm_ocr_local"
    ocr_fallback_enabled: bool = False
    ocr_fallback_provider: str | None = "openai_compatible"
    ocr_request_timeout_s: float = 120.0
    ocr_request_retries: int = 1
    ocr_review_confidence_threshold: float = 0.80
    ocr_glm_local_base_url: str | None = None
    ocr_glm_local_api_mode: str = "openai_chat_completion"
    ocr_glm_local_api_key: str | None = None
    ocr_glm_local_model: str = "glm-ocr"
    ocr_openai_base_url: str | None = None
    ocr_openai_api_key: str | None = None
    ocr_openai_model: str | None = None
    ocr_external_api_url: str | None = None
    ocr_external_api_key: str | None = None
    allow_insecure_transport: bool = False
    allow_insecure_tls_verify: bool = False
    automations_scheduler_enabled: bool = True
    automations_scheduler_poll_seconds: int = 60
    automations_scheduler_max_rules_per_tick: int = 20
    offers_browser_enabled: bool = True
    offers_browser_headless: bool = True
    offers_browser_timeout_s: float = Field(default=45.0, gt=0.0)
    connector_live_sync_enabled: bool = True
    connector_live_sync_interval_seconds: int = 7200  # 2 hours
    connector_external_runtime_enabled: bool = False
    connector_plugin_search_paths: list[Path] = Field(default_factory=list)
    connector_external_receipt_plugins_enabled: bool = False
    connector_external_offer_plugins_enabled: bool = False
    connector_external_allowed_trust_classes: list[str] = Field(default_factory=list)
    connector_market_profile: str = "global_shell"
    ai_base_url: str | None = None
    ai_api_key_encrypted: str | None = None
    ai_model: str = "grok-3-mini"
    ai_enabled: bool = False
    ai_oauth_provider: str | None = None
    ai_oauth_access_token_encrypted: str | None = None
    ai_oauth_refresh_token_encrypted: str | None = None
    ai_oauth_expires_at: str | None = None
    local_text_model_enabled: bool | None = None
    local_text_model_provider: str | None = None
    local_text_model_base_url: str | None = None
    local_text_model_api_key_encrypted: str | None = None
    local_text_model_name: str | None = None
    local_text_model_timeout_s: float | None = Field(default=None, gt=0.0)
    local_text_model_max_retries: int | None = Field(default=None, ge=0)
    local_text_model_allow_remote: bool | None = None
    item_categorization_runtime_policy: str = "local_preferred"
    pi_agent_runtime_policy: str = "remote_allowed"
    item_categorizer_enabled: bool = False
    item_categorizer_base_url: str | None = None
    item_categorizer_api_key_encrypted: str | None = None
    item_categorizer_model: str = "qwen3.5:0.8b"
    item_categorizer_timeout_s: float = Field(default=5.0, gt=0.0)
    item_categorizer_max_retries: int = Field(default=0, ge=0)
    item_categorizer_max_batch_size: int = Field(default=16, ge=1, le=128)
    item_categorizer_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    item_categorizer_ocr_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    item_categorizer_allow_remote: bool = False
    plugin_ai_mediation: PluginAiMediationConfig = Field(default_factory=PluginAiMediationConfig)

    @field_validator(
        "db_path",
        "config_dir",
        "token_file",
        "document_storage_path",
        "mobile_push_apns_private_key_path",
        "mobile_push_fcm_service_account_path",
        mode="before",
    )
    @classmethod
    def _validate_path(cls, value: Any) -> Path | None:
        if value is None:
            return None
        return _expand_path(value)

    @field_validator("connector_plugin_search_paths", mode="before")
    @classmethod
    def _validate_plugin_search_paths(cls, value: Any) -> list[Path]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            raise ValueError("connector_plugin_search_paths must be a list or tuple")
        normalized: list[Path] = []
        seen: set[Path] = set()
        for item in value:
            candidate = _expand_path(item)
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    @field_validator("connector_external_allowed_trust_classes", mode="before")
    @classmethod
    def _validate_allowed_trust_classes(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple)):
            raw_items = [str(item).strip() for item in value]
        else:
            raise ValueError("connector_external_allowed_trust_classes must be a list or tuple")
        allowed = {"official", "community_verified", "community_unsigned", "local_custom"}
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            if not item:
                continue
            if item not in allowed:
                raise ValueError(
                    "connector_external_allowed_trust_classes entries must be one of: "
                    "official, community_verified, community_unsigned, local_custom"
                )
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    @field_validator("http_exposure_mode", mode="before")
    @classmethod
    def _validate_http_exposure_mode(cls, value: Any) -> str:
        return normalize_http_exposure_mode(value)

    @field_validator("ocr_default_provider", mode="before")
    @classmethod
    def _validate_ocr_default_provider(cls, value: Any) -> str:
        normalized = str(value or "glm_ocr_local").strip().lower()
        if normalized == "tesseract":
            raise ValueError(
                "tesseract OCR has been removed; use 'glm_ocr_local', 'openai_compatible', or 'external_api'"
            )
        if normalized not in {"glm_ocr_local", "external_api", "openai_compatible"}:
            raise ValueError(
                "ocr_default_provider must be 'glm_ocr_local', 'openai_compatible', or 'external_api'"
            )
        return normalized

    @field_validator("ocr_fallback_provider", mode="before")
    @classmethod
    def _validate_ocr_fallback_provider(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if normalized == "tesseract":
            raise ValueError("tesseract OCR has been removed")
        if normalized not in {"glm_ocr_local", "openai_compatible", "external_api"}:
            raise ValueError(
                "ocr_fallback_provider must be 'glm_ocr_local', 'openai_compatible', or 'external_api'"
            )
        return normalized

    @field_validator("ocr_glm_local_api_mode", mode="before")
    @classmethod
    def _validate_ocr_glm_local_api_mode(cls, value: Any) -> str:
        normalized = str(value or "openai_chat_completion").strip().lower()
        if normalized not in {"ollama_generate", "openai_chat_completion"}:
            raise ValueError(
                "ocr_glm_local_api_mode must be 'ollama_generate' or 'openai_chat_completion'"
            )
        return normalized

    @field_validator("local_text_model_provider", mode="before")
    @classmethod
    def _validate_local_text_model_provider(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if normalized not in {"bundled_local_text", "openai_compatible"}:
            raise ValueError(
                "local_text_model_provider must be 'bundled_local_text' or 'openai_compatible'"
            )
        return normalized

    @field_validator(
        "item_categorization_runtime_policy",
        "pi_agent_runtime_policy",
        mode="before",
    )
    @classmethod
    def _validate_runtime_policy_mode(cls, value: Any) -> str:
        normalized = str(value or "local_preferred").strip().lower()
        if normalized not in {"local_only", "local_preferred", "remote_allowed"}:
            raise ValueError(
                "runtime policy must be 'local_only', 'local_preferred', or 'remote_allowed'"
            )
        return normalized

    @field_validator("http_trusted_proxy_cidrs", mode="before")
    @classmethod
    def _validate_trusted_proxy_cidrs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple)):
            raw_items = [str(item).strip() for item in value]
        else:
            raise ValueError("http_trusted_proxy_cidrs must be a list or tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            if not item:
                continue
            network = str(ipaddress.ip_network(item, strict=False))
            if network in seen:
                continue
            seen.add(network)
            normalized.append(network)
        return normalized

    @model_validator(mode="after")
    def _derive_token_file_from_config_dir(self) -> AppConfig:
        if "token_file" not in self.model_fields_set:
            self.token_file = self.config_dir / DEFAULT_TOKEN_FILE_NAME
        return self

    @model_validator(mode="after")
    def _derive_plugin_search_paths_from_config_dir(self) -> AppConfig:
        if "connector_plugin_search_paths" not in self.model_fields_set:
            self.connector_plugin_search_paths = [self.config_dir / "plugins"]
        return self

    @model_validator(mode="after")
    def _default_ocr_provider(self) -> AppConfig:
        if (
            "ocr_default_provider" not in self.model_fields_set
            and not self.ocr_glm_local_base_url
            and (self.ocr_openai_base_url or self.ai_base_url)
        ):
            self.ocr_default_provider = "openai_compatible"
        if self.ocr_fallback_provider == self.ocr_default_provider:
            self.ocr_fallback_provider = None
        return self


def config_from_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def build_config(config_path: Path | None = None, db_override: Path | None = None) -> AppConfig:
    cfg_path = config_path or _expand_path(os.getenv("LIDLTOOL_CONFIG", str(default_config_file())))
    data = config_from_file(cfg_path)
    env_ai_api_key = os.getenv("LIDLTOOL_AI_API_KEY")
    env_item_categorizer_api_key = os.getenv("LIDLTOOL_ITEM_CATEGORIZER_API_KEY")
    env_local_text_model_api_key = os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_API_KEY")

    env_overrides: dict[str, Any] = {}
    if os.getenv("LIDLTOOL_CONFIG_DIR"):
        env_overrides["config_dir"] = os.getenv("LIDLTOOL_CONFIG_DIR")
    if os.getenv("LIDLTOOL_DB"):
        env_overrides["db_path"] = os.getenv("LIDLTOOL_DB")
    if os.getenv("LIDLTOOL_DB_URL"):
        env_overrides["db_url"] = os.getenv("LIDLTOOL_DB_URL")
    if os.getenv("LIDLTOOL_LOG_LEVEL"):
        env_overrides["log_level"] = os.getenv("LIDLTOOL_LOG_LEVEL")
    if os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"):
        env_overrides["credential_encryption_key"] = os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY")
    if os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY_ID"):
        env_overrides["credential_encryption_key_id"] = os.getenv(
            "LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY_ID"
        )
    if os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_REQUIRED"):
        env_overrides["credential_encryption_required"] = (
            os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_REQUIRED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_USE_LIDL_PLUS"):
        env_overrides["use_lidl_plus"] = (
            os.getenv("LIDLTOOL_USE_LIDL_PLUS", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_API_BASE_URL"):
        env_overrides["api_base_url"] = os.getenv("LIDLTOOL_API_BASE_URL")
    if os.getenv("LIDLTOOL_OPENCLAW_API_KEY"):
        env_overrides["openclaw_api_key"] = os.getenv("LIDLTOOL_OPENCLAW_API_KEY")
    if os.getenv("LIDLTOOL_AUTH_BOOTSTRAP_TOKEN"):
        env_overrides["auth_bootstrap_token"] = os.getenv("LIDLTOOL_AUTH_BOOTSTRAP_TOKEN")
    if os.getenv("LIDLTOOL_OPENCLAW_AUTH_MODE"):
        env_overrides["openclaw_auth_mode"] = os.getenv("LIDLTOOL_OPENCLAW_AUTH_MODE")
    if os.getenv("LIDLTOOL_OPENCLAW_RATE_LIMIT_ENABLED"):
        env_overrides["openclaw_rate_limit_enabled"] = (
            os.getenv("LIDLTOOL_OPENCLAW_RATE_LIMIT_ENABLED", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_OPENCLAW_RATE_LIMIT_REQUESTS"):
        env_overrides["openclaw_rate_limit_requests"] = int(
            os.getenv("LIDLTOOL_OPENCLAW_RATE_LIMIT_REQUESTS", "60")
        )
    if os.getenv("LIDLTOOL_OPENCLAW_RATE_LIMIT_WINDOW_S"):
        env_overrides["openclaw_rate_limit_window_s"] = int(
            os.getenv("LIDLTOOL_OPENCLAW_RATE_LIMIT_WINDOW_S", "60")
        )
    if os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_ENABLED"):
        env_overrides["http_rate_limit_enabled"] = (
            os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_WINDOW_S"):
        env_overrides["http_rate_limit_window_s"] = int(
            os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_WINDOW_S", "60")
        )
    if os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_READ_REQUESTS"):
        env_overrides["http_rate_limit_read_requests"] = int(
            os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_READ_REQUESTS", "600")
        )
    if os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_WRITE_REQUESTS"):
        env_overrides["http_rate_limit_write_requests"] = int(
            os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_WRITE_REQUESTS", "180")
        )
    if os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_EXPENSIVE_REQUESTS"):
        env_overrides["http_rate_limit_expensive_requests"] = int(
            os.getenv("LIDLTOOL_HTTP_RATE_LIMIT_EXPENSIVE_REQUESTS", "60")
        )
    if os.getenv("LIDLTOOL_HTTP_CORS_ENABLED"):
        env_overrides["http_cors_enabled"] = (
            os.getenv("LIDLTOOL_HTTP_CORS_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_HTTP_CORS_ALLOWED_ORIGINS"):
        env_overrides["http_cors_allowed_origins"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_HTTP_CORS_ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_HTTP_CORS_ALLOWED_METHODS"):
        env_overrides["http_cors_allowed_methods"] = [
            item.strip().upper()
            for item in os.getenv("LIDLTOOL_HTTP_CORS_ALLOWED_METHODS", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_HTTP_CORS_ALLOWED_HEADERS"):
        env_overrides["http_cors_allowed_headers"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_HTTP_CORS_ALLOWED_HEADERS", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_HTTP_CORS_ALLOW_CREDENTIALS"):
        env_overrides["http_cors_allow_credentials"] = (
            os.getenv("LIDLTOOL_HTTP_CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_MOBILE_PUSH_ENABLED"):
        env_overrides["mobile_push_enabled"] = (
            os.getenv("LIDLTOOL_MOBILE_PUSH_ENABLED", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_TEAM_ID"):
        env_overrides["mobile_push_apns_team_id"] = os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_TEAM_ID")
    if os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_KEY_ID"):
        env_overrides["mobile_push_apns_key_id"] = os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_KEY_ID")
    if os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_PRIVATE_KEY_PATH"):
        env_overrides["mobile_push_apns_private_key_path"] = os.getenv(
            "LIDLTOOL_MOBILE_PUSH_APNS_PRIVATE_KEY_PATH"
        )
    if os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_TOPIC"):
        env_overrides["mobile_push_apns_topic"] = os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_TOPIC")
    if os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_USE_SANDBOX"):
        env_overrides["mobile_push_apns_use_sandbox"] = (
            os.getenv("LIDLTOOL_MOBILE_PUSH_APNS_USE_SANDBOX", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_MOBILE_PUSH_FCM_PROJECT_ID"):
        env_overrides["mobile_push_fcm_project_id"] = os.getenv("LIDLTOOL_MOBILE_PUSH_FCM_PROJECT_ID")
    if os.getenv("LIDLTOOL_MOBILE_PUSH_FCM_SERVICE_ACCOUNT_JSON"):
        env_overrides["mobile_push_fcm_service_account_json"] = os.getenv(
            "LIDLTOOL_MOBILE_PUSH_FCM_SERVICE_ACCOUNT_JSON"
        )
    if os.getenv("LIDLTOOL_MOBILE_PUSH_FCM_SERVICE_ACCOUNT_PATH"):
        env_overrides["mobile_push_fcm_service_account_path"] = os.getenv(
            "LIDLTOOL_MOBILE_PUSH_FCM_SERVICE_ACCOUNT_PATH"
        )
    if os.getenv("LIDLTOOL_HTTP_EXPOSURE_MODE"):
        env_overrides["http_exposure_mode"] = os.getenv("LIDLTOOL_HTTP_EXPOSURE_MODE")
    if os.getenv("LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS"):
        env_overrides["http_trusted_proxy_cidrs"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_HTTP_TOOLS_EXEC_ENABLED"):
        env_overrides["http_tools_exec_enabled"] = (
            os.getenv("LIDLTOOL_HTTP_TOOLS_EXEC_ENABLED", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_OPENCLAW_SCOPE_MODE"):
        env_overrides["openclaw_scope_mode"] = os.getenv("LIDLTOOL_OPENCLAW_SCOPE_MODE")
    if os.getenv("LIDLTOOL_OPENCLAW_SCOPE_ALLOW_PARAM_SCOPES"):
        env_overrides["openclaw_scope_allow_param_scopes"] = (
            os.getenv("LIDLTOOL_OPENCLAW_SCOPE_ALLOW_PARAM_SCOPES", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_OPENCLAW_SCOPE_DEFAULT_READ_SCOPES"):
        env_overrides["openclaw_scope_default_read_scopes"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_OPENCLAW_SCOPE_DEFAULT_READ_SCOPES", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_OPENCLAW_SCOPE_DEFAULT_WRITE_SCOPES"):
        env_overrides["openclaw_scope_default_write_scopes"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_OPENCLAW_SCOPE_DEFAULT_WRITE_SCOPES", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_RETRY_DEAD_LETTER_THRESHOLD"):
        env_overrides["retry_dead_letter_threshold"] = int(
            os.getenv("LIDLTOOL_RETRY_DEAD_LETTER_THRESHOLD", "3")
        )
    if os.getenv("LIDLTOOL_HEALTH_WINDOW_DAYS"):
        env_overrides["health_window_days"] = int(os.getenv("LIDLTOOL_HEALTH_WINDOW_DAYS", "7"))
    if os.getenv("LIDLTOOL_HEALTH_MIN_SUCCESS_RATE"):
        env_overrides["health_min_success_rate"] = float(
            os.getenv("LIDLTOOL_HEALTH_MIN_SUCCESS_RATE", "0.97")
        )
    if os.getenv("LIDLTOOL_HEALTH_ALERT_ON_DEAD_LETTER"):
        env_overrides["health_alert_on_dead_letter"] = (
            os.getenv("LIDLTOOL_HEALTH_ALERT_ON_DEAD_LETTER", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_HEALTH_ALERT_DEDUPE_WINDOW_HOURS"):
        env_overrides["health_alert_dedupe_window_hours"] = int(
            os.getenv("LIDLTOOL_HEALTH_ALERT_DEDUPE_WINDOW_HOURS", "6")
        )
    if os.getenv("LIDLTOOL_HEALTH_ESCALATION_FAILURE_THRESHOLD"):
        env_overrides["health_escalation_failure_threshold"] = int(
            os.getenv("LIDLTOOL_HEALTH_ESCALATION_FAILURE_THRESHOLD", "3")
        )
    if os.getenv("LIDLTOOL_HEALTH_CORRELATION_MIN_SOURCES"):
        env_overrides["health_correlation_min_sources"] = int(
            os.getenv("LIDLTOOL_HEALTH_CORRELATION_MIN_SOURCES", "2")
        )
    if os.getenv("LIDLTOOL_DOCUMENT_STORAGE_PATH"):
        env_overrides["document_storage_path"] = os.getenv("LIDLTOOL_DOCUMENT_STORAGE_PATH")
    if os.getenv("LIDLTOOL_MAX_UPLOAD_SIZE_MB"):
        env_overrides["max_upload_size_mb"] = int(os.getenv("LIDLTOOL_MAX_UPLOAD_SIZE_MB", "12"))
    if os.getenv("LIDLTOOL_OCR_DEFAULT_PROVIDER"):
        env_overrides["ocr_default_provider"] = os.getenv("LIDLTOOL_OCR_DEFAULT_PROVIDER")
    if os.getenv("LIDLTOOL_OCR_FALLBACK_ENABLED"):
        env_overrides["ocr_fallback_enabled"] = (
            os.getenv("LIDLTOOL_OCR_FALLBACK_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_OCR_FALLBACK_PROVIDER"):
        env_overrides["ocr_fallback_provider"] = os.getenv("LIDLTOOL_OCR_FALLBACK_PROVIDER")
    if os.getenv("LIDLTOOL_OCR_REQUEST_TIMEOUT_S"):
        env_overrides["ocr_request_timeout_s"] = float(
            os.getenv("LIDLTOOL_OCR_REQUEST_TIMEOUT_S", "120.0")
        )
    if os.getenv("LIDLTOOL_OCR_REQUEST_RETRIES"):
        env_overrides["ocr_request_retries"] = int(os.getenv("LIDLTOOL_OCR_REQUEST_RETRIES", "1"))
    if os.getenv("LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD"):
        env_overrides["ocr_review_confidence_threshold"] = float(
            os.getenv("LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD", "0.80")
        )
    if os.getenv("LIDLTOOL_OCR_GLM_LOCAL_BASE_URL"):
        env_overrides["ocr_glm_local_base_url"] = os.getenv("LIDLTOOL_OCR_GLM_LOCAL_BASE_URL")
    if os.getenv("LIDLTOOL_OCR_GLM_LOCAL_API_MODE"):
        env_overrides["ocr_glm_local_api_mode"] = os.getenv("LIDLTOOL_OCR_GLM_LOCAL_API_MODE")
    if os.getenv("LIDLTOOL_OCR_GLM_LOCAL_API_KEY"):
        env_overrides["ocr_glm_local_api_key"] = os.getenv("LIDLTOOL_OCR_GLM_LOCAL_API_KEY")
    if os.getenv("LIDLTOOL_OCR_GLM_LOCAL_MODEL"):
        env_overrides["ocr_glm_local_model"] = os.getenv("LIDLTOOL_OCR_GLM_LOCAL_MODEL")
    if os.getenv("LIDLTOOL_OCR_OPENAI_BASE_URL"):
        env_overrides["ocr_openai_base_url"] = os.getenv("LIDLTOOL_OCR_OPENAI_BASE_URL")
    if os.getenv("LIDLTOOL_OCR_OPENAI_API_KEY"):
        env_overrides["ocr_openai_api_key"] = os.getenv("LIDLTOOL_OCR_OPENAI_API_KEY")
    if os.getenv("LIDLTOOL_OCR_OPENAI_MODEL"):
        env_overrides["ocr_openai_model"] = os.getenv("LIDLTOOL_OCR_OPENAI_MODEL")
    if os.getenv("LIDLTOOL_OCR_EXTERNAL_API_URL"):
        env_overrides["ocr_external_api_url"] = os.getenv("LIDLTOOL_OCR_EXTERNAL_API_URL")
    if os.getenv("LIDLTOOL_OCR_EXTERNAL_API_KEY"):
        env_overrides["ocr_external_api_key"] = os.getenv("LIDLTOOL_OCR_EXTERNAL_API_KEY")
    if os.getenv("LIDLTOOL_ALLOW_INSECURE_TRANSPORT"):
        env_overrides["allow_insecure_transport"] = (
            os.getenv("LIDLTOOL_ALLOW_INSECURE_TRANSPORT", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_ALLOW_INSECURE_TLS_VERIFY"):
        env_overrides["allow_insecure_tls_verify"] = (
            os.getenv("LIDLTOOL_ALLOW_INSECURE_TLS_VERIFY", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_AUTOMATIONS_SCHEDULER_ENABLED"):
        env_overrides["automations_scheduler_enabled"] = (
            os.getenv("LIDLTOOL_AUTOMATIONS_SCHEDULER_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_AUTOMATIONS_SCHEDULER_POLL_SECONDS"):
        env_overrides["automations_scheduler_poll_seconds"] = int(
            os.getenv("LIDLTOOL_AUTOMATIONS_SCHEDULER_POLL_SECONDS", "60")
        )
    if os.getenv("LIDLTOOL_AUTOMATIONS_SCHEDULER_MAX_RULES_PER_TICK"):
        env_overrides["automations_scheduler_max_rules_per_tick"] = int(
            os.getenv("LIDLTOOL_AUTOMATIONS_SCHEDULER_MAX_RULES_PER_TICK", "20")
        )
    if os.getenv("LIDLTOOL_OFFERS_BROWSER_ENABLED"):
        env_overrides["offers_browser_enabled"] = (
            os.getenv("LIDLTOOL_OFFERS_BROWSER_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_OFFERS_BROWSER_HEADLESS"):
        env_overrides["offers_browser_headless"] = (
            os.getenv("LIDLTOOL_OFFERS_BROWSER_HEADLESS", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_OFFERS_BROWSER_TIMEOUT_S"):
        env_overrides["offers_browser_timeout_s"] = float(
            os.getenv("LIDLTOOL_OFFERS_BROWSER_TIMEOUT_S", "45.0")
        )
    if os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_ENABLED"):
        env_overrides["connector_live_sync_enabled"] = (
            os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_INTERVAL_SECONDS"):
        env_overrides["connector_live_sync_interval_seconds"] = int(
            os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_INTERVAL_SECONDS", "7200")
        )
    if os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED"):
        env_overrides["connector_external_runtime_enabled"] = (
            os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED", "false").lower()
            == "true"
        )
    if os.getenv("LIDLTOOL_CONNECTOR_PLUGIN_PATHS"):
        env_overrides["connector_plugin_search_paths"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_CONNECTOR_PLUGIN_PATHS", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED"):
        env_overrides["connector_external_receipt_plugins_enabled"] = (
            os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED", "false").lower()
            == "true"
        )
    if os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED"):
        env_overrides["connector_external_offer_plugins_enabled"] = (
            os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED", "false").lower()
            == "true"
        )
    if os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES"):
        env_overrides["connector_external_allowed_trust_classes"] = [
            item.strip()
            for item in os.getenv("LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES", "").split(",")
            if item.strip()
        ]
    if os.getenv("LIDLTOOL_CONNECTOR_MARKET_PROFILE"):
        env_overrides["connector_market_profile"] = os.getenv(
            "LIDLTOOL_CONNECTOR_MARKET_PROFILE"
        )
    if os.getenv("LIDLTOOL_AI_BASE_URL"):
        env_overrides["ai_base_url"] = os.getenv("LIDLTOOL_AI_BASE_URL")
    if os.getenv("LIDLTOOL_AI_MODEL"):
        env_overrides["ai_model"] = os.getenv("LIDLTOOL_AI_MODEL")
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_ENABLED"):
        env_overrides["item_categorizer_enabled"] = (
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_ENABLED", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_BASE_URL"):
        env_overrides["item_categorizer_base_url"] = os.getenv(
            "LIDLTOOL_ITEM_CATEGORIZER_BASE_URL"
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_MODEL"):
        env_overrides["item_categorizer_model"] = os.getenv("LIDLTOOL_ITEM_CATEGORIZER_MODEL")
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_TIMEOUT_S"):
        env_overrides["item_categorizer_timeout_s"] = float(
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_TIMEOUT_S", "5.0")
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_MAX_RETRIES"):
        env_overrides["item_categorizer_max_retries"] = int(
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_MAX_RETRIES", "0")
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_MAX_BATCH_SIZE"):
        env_overrides["item_categorizer_max_batch_size"] = int(
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_MAX_BATCH_SIZE", "16")
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_CONFIDENCE_THRESHOLD"):
        env_overrides["item_categorizer_confidence_threshold"] = float(
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_CONFIDENCE_THRESHOLD", "0.65")
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_OCR_CONFIDENCE_THRESHOLD"):
        env_overrides["item_categorizer_ocr_confidence_threshold"] = float(
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_OCR_CONFIDENCE_THRESHOLD", "0.60")
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZER_ALLOW_REMOTE"):
        env_overrides["item_categorizer_allow_remote"] = (
            os.getenv("LIDLTOOL_ITEM_CATEGORIZER_ALLOW_REMOTE", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_ENABLED"):
        env_overrides["local_text_model_enabled"] = (
            os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_ENABLED", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_PROVIDER"):
        env_overrides["local_text_model_provider"] = os.getenv(
            "LIDLTOOL_LOCAL_TEXT_MODEL_PROVIDER"
        )
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_BASE_URL"):
        env_overrides["local_text_model_base_url"] = os.getenv(
            "LIDLTOOL_LOCAL_TEXT_MODEL_BASE_URL"
        )
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_NAME"):
        env_overrides["local_text_model_name"] = os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_NAME")
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_TIMEOUT_S"):
        env_overrides["local_text_model_timeout_s"] = float(
            os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_TIMEOUT_S", "5.0")
        )
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_MAX_RETRIES"):
        env_overrides["local_text_model_max_retries"] = int(
            os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_MAX_RETRIES", "0")
        )
    if os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_ALLOW_REMOTE"):
        env_overrides["local_text_model_allow_remote"] = (
            os.getenv("LIDLTOOL_LOCAL_TEXT_MODEL_ALLOW_REMOTE", "false").lower() == "true"
        )
    if os.getenv("LIDLTOOL_ITEM_CATEGORIZATION_RUNTIME_POLICY"):
        env_overrides["item_categorization_runtime_policy"] = os.getenv(
            "LIDLTOOL_ITEM_CATEGORIZATION_RUNTIME_POLICY"
        )
    if os.getenv("LIDLTOOL_PI_AGENT_RUNTIME_POLICY"):
        env_overrides["pi_agent_runtime_policy"] = os.getenv("LIDLTOOL_PI_AGENT_RUNTIME_POLICY")
    if os.getenv("LIDLTOOL_PLUGIN_AI_ENABLED"):
        plugin_ai = dict(data.get("plugin_ai_mediation") or {})
        plugin_ai["enabled"] = os.getenv("LIDLTOOL_PLUGIN_AI_ENABLED", "false").lower() == "true"
        env_overrides["plugin_ai_mediation"] = plugin_ai
    if os.getenv("LIDLTOOL_PLUGIN_AI_DEFAULT_POLICY_LEVEL"):
        plugin_ai = dict(env_overrides.get("plugin_ai_mediation") or data.get("plugin_ai_mediation") or {})
        plugin_ai["default_policy_level"] = os.getenv("LIDLTOOL_PLUGIN_AI_DEFAULT_POLICY_LEVEL")
        env_overrides["plugin_ai_mediation"] = plugin_ai
    if os.getenv("LIDLTOOL_PLUGIN_AI_TRUST_DEFAULTS"):
        plugin_ai = dict(env_overrides.get("plugin_ai_mediation") or data.get("plugin_ai_mediation") or {})
        plugin_ai["trust_defaults"] = json.loads(os.getenv("LIDLTOOL_PLUGIN_AI_TRUST_DEFAULTS", "{}"))
        env_overrides["plugin_ai_mediation"] = plugin_ai
    if os.getenv("LIDLTOOL_PLUGIN_AI_PLUGIN_OVERRIDES"):
        plugin_ai = dict(env_overrides.get("plugin_ai_mediation") or data.get("plugin_ai_mediation") or {})
        plugin_ai["plugin_overrides"] = json.loads(
            os.getenv("LIDLTOOL_PLUGIN_AI_PLUGIN_OVERRIDES", "{}")
        )
        env_overrides["plugin_ai_mediation"] = plugin_ai
    if os.getenv("LIDLTOOL_PLUGIN_AI_LIMITS"):
        plugin_ai = dict(env_overrides.get("plugin_ai_mediation") or data.get("plugin_ai_mediation") or {})
        plugin_ai["limits"] = json.loads(os.getenv("LIDLTOOL_PLUGIN_AI_LIMITS", "{}"))
        env_overrides["plugin_ai_mediation"] = plugin_ai
    if os.getenv("LIDLTOOL_PLUGIN_AI_BUDGETS"):
        plugin_ai = dict(env_overrides.get("plugin_ai_mediation") or data.get("plugin_ai_mediation") or {})
        plugin_ai["budgets"] = json.loads(os.getenv("LIDLTOOL_PLUGIN_AI_BUDGETS", "{}"))
        env_overrides["plugin_ai_mediation"] = plugin_ai

    if db_override is not None:
        env_overrides["db_path"] = db_override

    merged = {**data, **env_overrides}
    if "config_dir" not in merged:
        merged["config_dir"] = cfg_path.parent
    cfg = AppConfig(**merged)
    if env_ai_api_key:
        from lidltool.ai.config import set_ai_api_key

        set_ai_api_key(cfg, env_ai_api_key)
        cfg.ai_enabled = True
    if env_item_categorizer_api_key:
        from lidltool.ai.config import set_item_categorizer_api_key

        set_item_categorizer_api_key(cfg, env_item_categorizer_api_key)
    if env_local_text_model_api_key:
        from lidltool.ai.config import set_local_text_model_api_key

        set_local_text_model_api_key(cfg, env_local_text_model_api_key)
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.document_storage_path.mkdir(parents=True, exist_ok=True)
    return cfg


def validate_config(config: AppConfig, *, bind_host: str | None = None) -> None:
    _validate_secret_value(
        config.credential_encryption_key,
        env_name="LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY",
        purpose="The credential encryption and session signing secret",
        generation_hint="openssl rand -hex 32",
        required=bool(config.credential_encryption_required),
    )
    _validate_secret_value(
        config.openclaw_api_key,
        env_name="LIDLTOOL_OPENCLAW_API_KEY",
        purpose="The service/OpenClaw API key",
        generation_hint="openssl rand -hex 32",
        required=False,
    )
    _validate_secret_value(
        config.auth_bootstrap_token,
        env_name="LIDLTOOL_AUTH_BOOTSTRAP_TOKEN",
        purpose="The one-time bootstrap token",
        generation_hint="openssl rand -hex 32",
        required=False,
    )
    evaluate_deployment_policy(config, bind_host=bind_host)


def sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def database_url(config: AppConfig) -> str:
    if config.db_url:
        return config.db_url
    return sqlite_url(config.db_path)
