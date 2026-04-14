from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lidltool.connectors.auth.auth_capabilities import (
    AuthKind,
    AuthLifecycleCapabilityAction,
    ConnectorAuthCapabilities,
    infer_auth_capabilities,
)
from lidltool.connectors.sdk.version import (
    MANIFEST_SCHEMA_VERSION,
    OFFER_CONNECTOR_API_VERSION,
    RECEIPT_CONNECTOR_API_VERSION,
)

PluginFamily = Literal["receipt", "offer"]
RuntimeKind = Literal[
    "builtin",
    "subprocess_python",
    "subprocess_binary",
    "local_http",
    "sidecar_http",
]
TrustClass = Literal["official", "community_verified", "community_unsigned", "local_custom"]
PluginOrigin = Literal["builtin", "external", "desktop_bundle", "local_path"]
InstallStatus = Literal["bundled", "installed", "available", "disabled", "blocked"]
SupportedHostKind = Literal["self_hosted", "electron"]

ReceiptRequiredAction = Literal[
    "get_manifest",
    "healthcheck",
    "get_auth_status",
    "discover_records",
    "fetch_record",
    "normalize_record",
    "extract_discounts",
    "get_diagnostics",
]
ReceiptReservedAction = AuthLifecycleCapabilityAction
ReceiptActionName = Literal[
    "get_manifest",
    "healthcheck",
    "get_auth_status",
    "start_auth",
    "cancel_auth",
    "confirm_auth",
    "discover_records",
    "fetch_record",
    "normalize_record",
    "extract_discounts",
    "get_diagnostics",
]

DEFAULT_RECEIPT_REQUIRED_ACTIONS: tuple[ReceiptRequiredAction, ...] = (
    "get_manifest",
    "healthcheck",
    "get_auth_status",
    "discover_records",
    "fetch_record",
    "normalize_record",
    "extract_discounts",
    "get_diagnostics",
)
DEFAULT_RECEIPT_RESERVED_ACTIONS: tuple[ReceiptReservedAction, ...] = (
    "start_auth",
    "cancel_auth",
    "confirm_auth",
)

OfferRequiredAction = Literal[
    "get_manifest",
    "healthcheck",
    "discover_offers",
    "fetch_offer_detail",
    "normalize_offer",
    "get_offer_scope",
    "get_offer_diagnostics",
]
OfferActionName = Literal[
    "get_manifest",
    "healthcheck",
    "discover_offers",
    "fetch_offer_detail",
    "normalize_offer",
    "get_offer_scope",
    "get_offer_diagnostics",
]

DEFAULT_OFFER_REQUIRED_ACTIONS: tuple[OfferRequiredAction, ...] = (
    "get_manifest",
    "healthcheck",
    "discover_offers",
    "fetch_offer_detail",
    "normalize_offer",
    "get_offer_scope",
    "get_offer_diagnostics",
)


class ManifestValidationError(ValueError):
    """Raised when a connector manifest or registry definition is invalid."""


class ConnectorCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_core_version: str | None = None
    max_core_version: str | None = None
    supported_host_kinds: tuple[SupportedHostKind, ...] = ("self_hosted", "electron")

    @field_validator("supported_host_kinds", mode="before")
    @classmethod
    def _normalize_supported_host_kinds(cls, value: Any) -> tuple[SupportedHostKind, ...]:
        if value is None:
            return ("self_hosted", "electron")
        if not isinstance(value, (list, tuple)):
            raise ValueError("supported_host_kinds must be a list or tuple")
        normalized: list[SupportedHostKind] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("supported_host_kinds entries must be strings")
            candidate = item.strip()
            if not candidate:
                raise ValueError("supported_host_kinds entries must be non-empty")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)  # type: ignore[arg-type]
        if not normalized:
            raise ValueError("supported_host_kinds must contain at least one host kind")
        return tuple(normalized)


class BuiltinConnectorCli(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bootstrap_args: tuple[str, ...] | None = None
    sync_args: tuple[str, ...] | None = None

    @field_validator("bootstrap_args", "sync_args", mode="before")
    @classmethod
    def _normalize_args(cls, value: Any) -> tuple[str, ...] | None:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)):
            raise ValueError("builtin CLI args must be a list or tuple")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("builtin CLI args must contain only strings")
            candidate = item.strip()
            if not candidate:
                raise ValueError("builtin CLI args must not contain empty strings")
            normalized.append(candidate)
        if not normalized:
            return None
        return tuple(normalized)


class ConnectorTrustPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_model: Literal["builtin_only", "sandboxed", "operator_review"] = "builtin_only"
    requires_operator_approval: bool = False
    notes: str | None = None


class ConnectorAiPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_model_mediation: bool = False
    allow_model_generated_actions: bool = False
    redacted_fields: tuple[str, ...] = ()

    @field_validator("redacted_fields", mode="before")
    @classmethod
    def _normalize_redacted_fields(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("redacted_fields must be a list or tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("redacted_fields entries must be strings")
            candidate = item.strip()
            if not candidate:
                raise ValueError("redacted_fields entries must be non-empty")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return tuple(normalized)


class ConnectorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust: ConnectorTrustPolicy = Field(default_factory=ConnectorTrustPolicy)
    ai: ConnectorAiPolicy = Field(default_factory=ConnectorAiPolicy)


class ConnectorConfigField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    description: str | None = None
    input_kind: Literal["text", "password", "url", "number", "boolean"] = "text"
    required: bool = False
    sensitive: bool = False
    placeholder: str | None = None
    default_value: str | int | float | bool | None = None
    operator_only: bool = False

    @field_validator("key", "label", "description", "placeholder", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("config field values must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("config field values must be non-empty strings")
        return normalized

    @field_validator("key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
        if any(char not in allowed for char in value):
            raise ValueError("config field keys must use lowercase letters, digits, '.', '_' or '-'")
        return value


class ConnectorConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: tuple[ConnectorConfigField, ...] = ()

    @field_validator("fields", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> tuple[ConnectorConfigField, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("config fields must be a list or tuple")
        normalized: list[ConnectorConfigField] = []
        seen: set[str] = set()
        for item in value:
            field = item if isinstance(item, ConnectorConfigField) else ConnectorConfigField.model_validate(item)
            if field.key in seen:
                raise ValueError(f"duplicate config field key: {field.key}")
            seen.add(field.key)
            normalized.append(field)
        return tuple(normalized)


class ConnectorOnboardingStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str

    @field_validator("title", "description", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("onboarding step fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("onboarding step fields must be non-empty strings")
        return normalized


class ConnectorOnboarding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    summary: str | None = None
    expected_speed: str | None = None
    caution: str | None = None
    steps: tuple[ConnectorOnboardingStep, ...] = ()

    @field_validator("title", "summary", "expected_speed", "caution", mode="before")
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("onboarding fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("onboarding fields must be non-empty strings")
        return normalized

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_steps(cls, value: Any) -> tuple[ConnectorOnboardingStep, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("onboarding steps must be a list or tuple")
        normalized: list[ConnectorOnboardingStep] = []
        for item in value:
            step = item if isinstance(item, ConnectorOnboardingStep) else ConnectorOnboardingStep.model_validate(item)
            normalized.append(step)
        return tuple(normalized)


class ReceiptActionDeclarations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: tuple[ReceiptRequiredAction, ...] = DEFAULT_RECEIPT_REQUIRED_ACTIONS
    optional: tuple[ReceiptReservedAction, ...] = ()
    reserved: tuple[ReceiptReservedAction, ...] = DEFAULT_RECEIPT_RESERVED_ACTIONS

    @field_validator("required", "optional", "reserved", mode="before")
    @classmethod
    def _normalize_actions(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("action declarations must be a list or tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("action declarations must contain only strings")
            candidate = item.strip()
            if not candidate:
                raise ValueError("action declarations must contain non-empty strings")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_action_sets(self) -> ReceiptActionDeclarations:
        required = set(self.required)
        if required != set(DEFAULT_RECEIPT_REQUIRED_ACTIONS):
            missing = sorted(set(DEFAULT_RECEIPT_REQUIRED_ACTIONS) - required)
            extras = sorted(required - set(DEFAULT_RECEIPT_REQUIRED_ACTIONS))
            problems: list[str] = []
            if missing:
                problems.append(f"missing required receipt actions: {', '.join(missing)}")
            if extras:
                problems.append(f"unknown required receipt actions: {', '.join(extras)}")
            raise ValueError("; ".join(problems))
        overlap = set(self.optional) & set(self.reserved)
        if overlap:
            raise ValueError(
                f"receipt optional and reserved actions must not overlap: {', '.join(sorted(overlap))}"
            )
        return self

    def supports(self, action: ReceiptActionName) -> bool:
        return action in self.required or action in self.optional or action in self.reserved


class OfferActionDeclarations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: tuple[OfferRequiredAction, ...] = DEFAULT_OFFER_REQUIRED_ACTIONS
    optional: tuple[str, ...] = ()
    reserved: tuple[str, ...] = ()

    @field_validator("required", "optional", "reserved", mode="before")
    @classmethod
    def _normalize_actions(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("action declarations must be a list or tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("action declarations must contain only strings")
            candidate = item.strip()
            if not candidate:
                raise ValueError("action declarations must contain non-empty strings")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_action_sets(self) -> OfferActionDeclarations:
        required = set(self.required)
        if required != set(DEFAULT_OFFER_REQUIRED_ACTIONS):
            missing = sorted(set(DEFAULT_OFFER_REQUIRED_ACTIONS) - required)
            extras = sorted(required - set(DEFAULT_OFFER_REQUIRED_ACTIONS))
            problems: list[str] = []
            if missing:
                problems.append(f"missing required offer actions: {', '.join(missing)}")
            if extras:
                problems.append(f"unknown required offer actions: {', '.join(extras)}")
            raise ValueError("; ".join(problems))
        if self.optional:
            raise ValueError("offer optional actions are not defined in connector API v1")
        if self.reserved:
            raise ValueError("offer reserved actions are not defined in connector API v1")
        return self

    def supports(self, action: OfferActionName) -> bool:
        return action in self.required


class ConnectorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal["1"] = MANIFEST_SCHEMA_VERSION
    plugin_id: str
    plugin_version: str
    connector_api_version: str
    plugin_family: PluginFamily = "receipt"
    source_id: str
    display_name: str
    merchant_name: str
    country_code: str
    maintainer: str | None = None
    homepage_url: str | None = None
    license: str | None = None
    runtime_kind: RuntimeKind
    entrypoint: str | None = None
    auth_kind: AuthKind
    auth: ConnectorAuthCapabilities | None = None
    capabilities: tuple[str, ...]
    actions: ReceiptActionDeclarations | OfferActionDeclarations | None = None
    trust_class: TrustClass
    plugin_origin: PluginOrigin
    install_status: InstallStatus
    compatibility: ConnectorCompatibility = Field(default_factory=ConnectorCompatibility)
    policy: ConnectorPolicy = Field(default_factory=ConnectorPolicy)
    config_schema: ConnectorConfigSchema | None = None
    onboarding: ConnectorOnboarding | None = None
    builtin_cli: BuiltinConnectorCli | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "plugin_id",
        "plugin_version",
        "connector_api_version",
        "source_id",
        "display_name",
        "merchant_name",
        "maintainer",
        "homepage_url",
        "license",
        "entrypoint",
        mode="before",
    )
    @classmethod
    def _normalize_optional_strings(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("manifest fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("manifest fields must be non-empty strings")
        return normalized

    @field_validator("connector_api_version")
    @classmethod
    def _validate_connector_api_version(cls, value: str, info: Any) -> str:
        plugin_family = info.data.get("plugin_family", "receipt")
        expected = (
            OFFER_CONNECTOR_API_VERSION
            if plugin_family == "offer"
            else RECEIPT_CONNECTOR_API_VERSION
        )
        if value != expected:
            raise ValueError(
                f"connector_api_version must be '{expected}' for plugin_family='{plugin_family}'"
            )
        return value

    @field_validator("plugin_id", "source_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
        if any(char not in allowed for char in value):
            raise ValueError("identifiers must use lowercase letters, digits, '.', '_' or '-'")
        return value

    @field_validator("country_code")
    @classmethod
    def _normalize_country_code(cls, value: str) -> str:
        candidate = value.strip().upper()
        if len(candidate) != 2 or not candidate.isalpha():
            raise ValueError("country_code must be a two-letter ISO country code")
        return candidate

    @field_validator("capabilities", mode="before")
    @classmethod
    def _normalize_capabilities(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("capabilities must be a list or tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("capabilities entries must be strings")
            capability = item.strip()
            if not capability:
                raise ValueError("capabilities entries must be non-empty")
            if capability in seen:
                continue
            seen.add(capability)
            normalized.append(capability)
        if not normalized:
            raise ValueError("capabilities must contain at least one value")
        return tuple(normalized)

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata must be an object")
        return {str(key): item for key, item in value.items()}

    @field_validator("actions", mode="before")
    @classmethod
    def _normalize_actions(cls, value: Any, info: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (ReceiptActionDeclarations, OfferActionDeclarations)):
            return value
        plugin_family = info.data.get("plugin_family", "receipt")
        if plugin_family == "offer":
            return OfferActionDeclarations.model_validate(value)
        return ReceiptActionDeclarations.model_validate(value)

    @field_validator("auth", mode="before")
    @classmethod
    def _normalize_auth(cls, value: Any) -> ConnectorAuthCapabilities | None:
        if value is None:
            return None
        if isinstance(value, ConnectorAuthCapabilities):
            return value
        return ConnectorAuthCapabilities.model_validate(value)

    @field_validator("config_schema", mode="before")
    @classmethod
    def _normalize_config_schema(cls, value: Any) -> ConnectorConfigSchema | None:
        if value is None:
            return None
        if isinstance(value, ConnectorConfigSchema):
            return value
        return ConnectorConfigSchema.model_validate(value)

    @field_validator("onboarding", mode="before")
    @classmethod
    def _normalize_onboarding(cls, value: Any) -> ConnectorOnboarding | None:
        if value is None:
            return None
        if isinstance(value, ConnectorOnboarding):
            return value
        return ConnectorOnboarding.model_validate(value)

    @model_validator(mode="after")
    def _validate_manifest(self) -> ConnectorManifest:
        if self.actions is None and self.plugin_family == "receipt":
            object.__setattr__(self, "actions", ReceiptActionDeclarations())
        if self.actions is None and self.plugin_family == "offer":
            object.__setattr__(self, "actions", OfferActionDeclarations())
        if self.builtin_cli is not None and self.runtime_kind != "builtin":
            raise ValueError("builtin_cli is only supported for runtime_kind='builtin'")
        if self.plugin_origin == "builtin" and self.runtime_kind != "builtin":
            raise ValueError("builtin plugins must use runtime_kind='builtin'")
        if self.plugin_family == "receipt" and not isinstance(self.actions, ReceiptActionDeclarations):
            raise ValueError("receipt connectors must declare receipt actions")
        if self.plugin_family == "offer" and not isinstance(self.actions, OfferActionDeclarations):
            raise ValueError("offer connectors must declare offer actions")
        if self.auth is None:
            inferred = infer_auth_capabilities(
                auth_kind=self.auth_kind,
                capabilities=self.capabilities,
                optional_actions=self.actions.optional if self.actions is not None else (),
                reserved_actions=self.actions.reserved if self.actions is not None else (),
            )
            object.__setattr__(self, "auth", inferred)
        elif self.auth.auth_kind != self.auth_kind:
            raise ValueError("auth.auth_kind must match manifest auth_kind")
        return self
