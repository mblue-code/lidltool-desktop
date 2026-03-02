from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_SOURCE = "lidl_plus_de"
DEFAULT_CONFIG_DIR = "~/.config/lidltool"
DEFAULT_CONFIG_FILE_NAME = "config.toml"
DEFAULT_TOKEN_FILE_NAME = "token.json"


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


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
    openclaw_auth_mode: str = "warn_only"
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
    ocr_default_provider: str = "external_api"
    ocr_fallback_enabled: bool = True
    ocr_request_timeout_s: float = 30.0
    ocr_request_retries: int = 1
    ocr_review_confidence_threshold: float = 0.80
    ocr_external_api_url: str | None = None
    ocr_external_api_key: str | None = None
    allow_insecure_transport: bool = False
    allow_insecure_tls_verify: bool = False
    automations_scheduler_enabled: bool = True
    automations_scheduler_poll_seconds: int = 60
    automations_scheduler_max_rules_per_tick: int = 20
    connector_live_sync_enabled: bool = True
    connector_live_sync_interval_seconds: int = 7200  # 2 hours
    ai_base_url: str | None = None
    ai_api_key_encrypted: str | None = None
    ai_model: str = "grok-3-mini"
    ai_enabled: bool = False
    ai_oauth_provider: str | None = None
    ai_oauth_access_token_encrypted: str | None = None
    ai_oauth_refresh_token_encrypted: str | None = None
    ai_oauth_expires_at: str | None = None

    @field_validator("db_path", "config_dir", "token_file", "document_storage_path", mode="before")
    @classmethod
    def _validate_path(cls, value: Any) -> Path:
        return _expand_path(value)

    @model_validator(mode="after")
    def _derive_token_file_from_config_dir(self) -> AppConfig:
        if "token_file" not in self.model_fields_set:
            self.token_file = self.config_dir / DEFAULT_TOKEN_FILE_NAME
        return self

    @model_validator(mode="after")
    def _default_ocr_provider(self) -> AppConfig:
        if (
            "ocr_default_provider" not in self.model_fields_set
            and not self.ocr_external_api_url
        ):
            self.ocr_default_provider = "tesseract"
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
    if os.getenv("LIDLTOOL_OCR_REQUEST_TIMEOUT_S"):
        env_overrides["ocr_request_timeout_s"] = float(
            os.getenv("LIDLTOOL_OCR_REQUEST_TIMEOUT_S", "30.0")
        )
    if os.getenv("LIDLTOOL_OCR_REQUEST_RETRIES"):
        env_overrides["ocr_request_retries"] = int(os.getenv("LIDLTOOL_OCR_REQUEST_RETRIES", "1"))
    if os.getenv("LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD"):
        env_overrides["ocr_review_confidence_threshold"] = float(
            os.getenv("LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD", "0.80")
        )
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
    if os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_ENABLED"):
        env_overrides["connector_live_sync_enabled"] = (
            os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_ENABLED", "true").lower() == "true"
        )
    if os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_INTERVAL_SECONDS"):
        env_overrides["connector_live_sync_interval_seconds"] = int(
            os.getenv("LIDLTOOL_CONNECTOR_LIVE_SYNC_INTERVAL_SECONDS", "7200")
        )
    if os.getenv("LIDLTOOL_AI_BASE_URL"):
        env_overrides["ai_base_url"] = os.getenv("LIDLTOOL_AI_BASE_URL")
    if os.getenv("LIDLTOOL_AI_MODEL"):
        env_overrides["ai_model"] = os.getenv("LIDLTOOL_AI_MODEL")

    if db_override is not None:
        env_overrides["db_path"] = db_override

    merged = {**data, **env_overrides}
    cfg = AppConfig(**merged)
    if env_ai_api_key:
        from lidltool.ai.config import set_ai_api_key

        set_ai_api_key(cfg, env_ai_api_key)
        cfg.ai_enabled = True
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.document_storage_path.mkdir(parents=True, exist_ok=True)
    return cfg


def validate_config(config: AppConfig) -> None:
    has_key = bool((config.credential_encryption_key or "").strip())
    if config.credential_encryption_required and not has_key:
        raise RuntimeError(
            "FATAL: LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY is not set.\n"
            "Generate one with: openssl rand -hex 32"
        )


def sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def database_url(config: AppConfig) -> str:
    if config.db_url:
        return config.db_url
    return sqlite_url(config.db_path)
