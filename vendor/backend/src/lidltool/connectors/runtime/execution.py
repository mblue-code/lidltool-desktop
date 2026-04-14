from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from lidltool.amazon.client_playwright import AmazonClientError, AmazonPlaywrightClient
from lidltool.amazon.session import default_amazon_state_file
from lidltool.auth.token_store import TokenStore
from lidltool.config import AppConfig
from lidltool.connectors.amazon_adapter import AmazonConnectorAdapter
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.base import (
    Connector,
    require_connector_action_scope,
    validate_connector_scope_contract,
)
from lidltool.connectors.kaufland_adapter import KauflandConnectorAdapter
from lidltool.connectors.lidl_adapter import LidlConnectorAdapter
from lidltool.connectors.lifecycle import connector_runtime_options
from lidltool.connectors.netto_adapter import NettoConnectorAdapter
from lidltool.connectors.offer_file_feed_adapter import OfferFileFeedConnectorAdapter
from lidltool.connectors.plugin_policy import evaluate_plugin_policy
from lidltool.connectors.plugin_status import PluginRegistryEntry
from lidltool.connectors.registry import ConnectorRegistry, get_connector_registry
from lidltool.connectors.rossmann_adapter import RossmannConnectorAdapter
from lidltool.connectors.runtime.context import build_plugin_runtime_environment
from lidltool.connectors.runtime.host import (
    ConnectorRuntimeHost,
    OfferConnectorRuntimeTarget,
    ReceiptConnectorRuntimeTarget,
    RuntimeHostedOfferConnector,
    RuntimeHostedReceiptConnector,
    default_offer_runtime_action_timeouts,
    default_runtime_action_timeouts,
)
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.offer import OfferConnector
from lidltool.kaufland.client_playwright import KauflandClientError, KauflandPlaywrightClient
from lidltool.kaufland.session import default_kaufland_state_file
from lidltool.lidl.client import LidlClientError, create_lidl_client
from lidltool.rossmann.client_playwright import RossmannClientError, RossmannPlaywrightClient
from lidltool.rossmann.session import default_rossmann_state_file

RUNTIME_CONNECTOR_SCOPES = {
    "auth.session",
    "read.health",
    "read.receipts",
    "read.receipt_detail",
    "transform.normalize",
    "transform.discounts",
}

ConnectorOperation = Literal["bootstrap", "sync"]


def _plugin_host_kind() -> str:
    return "electron" if os.getenv("LIDLTOOL_CONNECTOR_HOST_KIND", "").strip().lower() == "electron" else "self_hosted"


def _resolve_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _resolve_optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, str):
        return Path(value).expanduser().resolve()
    raise TypeError(f"expected path-like value, got {type(value).__name__}")


def _string_option(options: Mapping[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    return str(value)


def _int_option(options: Mapping[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    return int(value)


def _bool_option(options: Mapping[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass(frozen=True, slots=True)
class ResolvedConnectorCommand:
    manifest: ConnectorManifest
    source_id: str
    operation: ConnectorOperation
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedReceiptConnector:
    manifest: ConnectorManifest
    source_config: AppConfig
    client: Any | None
    connector: RuntimeHostedReceiptConnector
    metadata: dict[str, Any] = field(default_factory=dict)
    handled_exceptions: tuple[type[Exception], ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedBootstrapExecution:
    manifest: ConnectorManifest
    source_id: str
    ok: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    handled_exceptions: tuple[type[Exception], ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedOfferConnector:
    manifest: ConnectorManifest
    source_config: AppConfig
    connector: OfferConnector
    metadata: dict[str, Any] = field(default_factory=dict)


class ConnectorExecutionService:
    def __init__(
        self,
        *,
        config: AppConfig,
        registry: ConnectorRegistry | None = None,
        runtime_host: ConnectorRuntimeHost | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or get_connector_registry(config)
        self._runtime_host = runtime_host or ConnectorRuntimeHost()

    def resolve_manifest(
        self,
        source_id: str,
        *,
        plugin_family: Literal["receipt", "offer"] | None = None,
    ) -> ConnectorManifest:
        entry = self._require_entry(source_id)
        manifest = entry.manifest
        if manifest is None:
            raise RuntimeError(f"connector source {source_id!r} is not registered")
        if plugin_family is not None and manifest.plugin_family != plugin_family:
            raise RuntimeError(
                f"connector source {source_id!r} is not registered for plugin_family={plugin_family!r}"
            )
        return manifest

    def build_command(
        self,
        *,
        source_id: str,
        operation: ConnectorOperation,
        extra_args: Sequence[str] = (),
    ) -> ResolvedConnectorCommand | None:
        manifest = self.resolve_manifest(source_id)
        builtin_cli = manifest.builtin_cli
        command_args: tuple[str, ...] | None = None
        if builtin_cli is not None:
            command_args = (
                builtin_cli.bootstrap_args if operation == "bootstrap" else builtin_cli.sync_args
            )
        if command_args is None and manifest.plugin_family == "receipt" and manifest.runtime_kind in {
            "subprocess_python",
            "subprocess_binary",
        }:
            command_args = (
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                source_id,
            ) if operation == "bootstrap" else (
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                source_id,
            )
        if command_args is None:
            return None
        command = (sys.executable, *command_args, *extra_args)
        return ResolvedConnectorCommand(
            manifest=manifest,
            source_id=source_id,
            operation=operation,
            command=tuple(command),
        )

    def build_receipt_connector(
        self,
        *,
        source_id: str | None = None,
        connector_options: Mapping[str, Any] | None = None,
        tracking_source_id: str | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> ResolvedReceiptConnector:
        resolved_source_id = source_id or self._config.source
        entry = self._require_entry(resolved_source_id, plugin_family="receipt")
        manifest = entry.manifest
        if manifest is None:
            raise RuntimeError(f"connector source {resolved_source_id!r} is not registered")
        self._assert_runtime_allowed(entry)
        source_config = self._config.model_copy(
            update={"source": tracking_source_id or manifest.source_id}
        )
        options = connector_runtime_options(
            source_id=resolved_source_id,
            config=self._config,
            registry=self._registry,
            allow_reconcile_writes=False,
        )
        options.update(dict(connector_options or {}))
        if manifest.runtime_kind == "builtin":
            return self._build_builtin_receipt_connector(
                manifest=manifest,
                source_config=source_config,
                connector_options=options,
            )
        if manifest.runtime_kind in {"subprocess_python", "subprocess_binary"}:
            return ResolvedReceiptConnector(
                manifest=manifest,
                source_config=source_config,
                client=None,
                connector=RuntimeHostedReceiptConnector(
                    host=self._runtime_host,
                    target=ReceiptConnectorRuntimeTarget(
                        manifest=manifest,
                        working_directory=self._working_directory_for(entry),
                        environment=build_plugin_runtime_environment(
                            source_config=source_config,
                            source_id=manifest.source_id,
                            tracking_source_id=tracking_source_id or manifest.source_id,
                            manifest=manifest,
                            working_directory=self._working_directory_for(entry),
                            connector_options=options,
                            runtime_context=runtime_context,
                        ),
                    ),
                    action_timeouts_s=default_runtime_action_timeouts(
                        source_config.request_timeout_s
                    ),
                ),
                metadata=self._runtime_metadata_for(entry),
            )
        raise RuntimeError(
            f"unsupported connector runtime kind for receipt execution: {manifest.runtime_kind}"
        )

    def build_offer_connector(
        self,
        *,
        source_id: str,
    ) -> ResolvedOfferConnector:
        entry = self._require_entry(source_id, plugin_family="offer")
        manifest = entry.manifest
        if manifest is None:
            raise RuntimeError(f"connector source {source_id!r} is not registered")
        self._assert_runtime_allowed(entry)
        if manifest.runtime_kind == "builtin":
            return self._build_builtin_offer_connector(
                manifest=manifest,
                source_config=self._config.model_copy(update={"source": manifest.source_id}),
            )
        if manifest.runtime_kind not in {"subprocess_python", "subprocess_binary"}:
            raise RuntimeError(
                f"unsupported connector runtime kind for offer execution: {manifest.runtime_kind}"
            )
        return ResolvedOfferConnector(
            manifest=manifest,
            source_config=self._config.model_copy(update={"source": manifest.source_id}),
            connector=RuntimeHostedOfferConnector(
                host=self._runtime_host,
                target=OfferConnectorRuntimeTarget(
                    manifest=manifest,
                    working_directory=self._working_directory_for(entry),
                    environment=build_plugin_runtime_environment(
                        source_config=self._config.model_copy(update={"source": manifest.source_id}),
                        source_id=manifest.source_id,
                        tracking_source_id=manifest.source_id,
                        manifest=manifest,
                        working_directory=self._working_directory_for(entry),
                    ),
                ),
                action_timeouts_s=default_offer_runtime_action_timeouts(
                    self._config.request_timeout_s
                ),
            ),
            metadata=self._runtime_metadata_for(entry),
        )

    def _build_builtin_offer_connector(
        self,
        *,
        manifest: ConnectorManifest,
        source_config: AppConfig,
    ) -> ResolvedOfferConnector:
        if manifest.source_id in {"dm_de_offers", "rossmann_de_offers"}:
            connector: OfferConnector = OfferFileFeedConnectorAdapter(
                manifest=manifest,
                source_config=source_config,
            )
            return ResolvedOfferConnector(
                manifest=manifest,
                source_config=source_config,
                connector=connector,
                metadata={"feed_path": str((source_config.config_dir / "offers" / f"{manifest.source_id}.json").resolve())},
            )
        raise RuntimeError(
            f"unsupported connector runtime kind for built-in offer execution: {manifest.source_id}"
        )

    def run_bootstrap(
        self,
        *,
        source_id: str,
        options: Mapping[str, Any] | None = None,
    ) -> ResolvedBootstrapExecution:
        result = self.auth_service().run_bootstrap(source_id=source_id, options=options)
        return ResolvedBootstrapExecution(
            manifest=result.manifest,
            source_id=result.source_id,
            ok=result.ok,
            metadata=result.metadata,
            handled_exceptions=result.handled_exceptions,
        )

    def auth_service(self) -> ConnectorAuthOrchestrationService:
        return ConnectorAuthOrchestrationService(
            config=self._config,
            registry=self._registry,
            connector_builder=self.build_receipt_connector,
        )

    def _build_builtin_receipt_connector(
        self,
        *,
        manifest: ConnectorManifest,
        source_config: AppConfig,
        connector_options: Mapping[str, Any],
    ) -> ResolvedReceiptConnector:
        tracking_source_id = source_config.source
        if manifest.source_id.startswith("lidl_plus_"):
            token_store = TokenStore.from_config(source_config)
            refresh_token = token_store.get_refresh_token()
            if not refresh_token:
                raise RuntimeError("auth token missing; run lidltool auth bootstrap")
            lidl_client = create_lidl_client(source_config, refresh_token, token_store=token_store)
            lidl_connector: Connector = LidlConnectorAdapter(
                client=lidl_client,
                page_size=source_config.page_size,
            )
            return self._resolved_receipt_connector(
                manifest=manifest,
                source_config=source_config,
                client=lidl_client,
                connector=lidl_connector,
                handled_exceptions=(LidlClientError,),
            )
        if manifest.source_id == "amazon_de":
            state_file = self._resolve_state_file(
                connector_options.get("state_file"),
                default_amazon_state_file(source_config),
            )
            domain = _string_option(connector_options, "domain", "amazon.de")
            headless = _bool_option(connector_options, "headless", True)
            dump_html = _resolve_optional_path(connector_options.get("dump_html"))
            years = _int_option(connector_options, "years", 2)
            max_pages_per_year = _int_option(connector_options, "max_pages_per_year", 8)
            store_name = _string_option(connector_options, "store_name", "Amazon")
            amazon_client = AmazonPlaywrightClient(
                state_file=state_file,
                domain=domain,
                headless=headless,
                dump_html_dir=dump_html,
            )
            amazon_connector: Connector = AmazonConnectorAdapter(
                client=amazon_client,
                source=tracking_source_id,
                store_name=store_name,
                years=years,
                max_pages_per_year=max_pages_per_year,
            )
            return self._resolved_receipt_connector(
                manifest=manifest,
                source_config=source_config,
                client=None,
                connector=amazon_connector,
                metadata={"state_file": str(state_file), "domain": domain},
                handled_exceptions=(AmazonClientError,),
            )
        if manifest.source_id == "kaufland_de":
            state_file = self._resolve_state_file(
                connector_options.get("state_file"),
                default_kaufland_state_file(source_config),
            )
            domain = _string_option(connector_options, "domain", "www.kaufland.de")
            headless = _bool_option(connector_options, "headless", True)
            max_pages = _int_option(connector_options, "max_pages", 10)
            store_name = _string_option(connector_options, "store_name", "Kaufland")
            kaufland_client = KauflandPlaywrightClient(
                state_file=state_file,
                domain=domain,
                headless=headless,
                max_pages=max_pages,
            )
            kaufland_connector: Connector = KauflandConnectorAdapter(
                client=kaufland_client,
                source=tracking_source_id,
                store_name=store_name,
            )
            return self._resolved_receipt_connector(
                manifest=manifest,
                source_config=source_config,
                client=None,
                connector=kaufland_connector,
                metadata={"state_file": str(state_file), "domain": domain},
                handled_exceptions=(KauflandClientError,),
            )
        if manifest.source_id == "netto_de":
            netto_connector: Connector = NettoConnectorAdapter(source=tracking_source_id)
            return self._resolved_receipt_connector(
                manifest=manifest,
                source_config=source_config,
                client=None,
                connector=netto_connector,
            )
        if manifest.source_id == "rossmann_de":
            state_file = self._resolve_state_file(
                connector_options.get("state_file"),
                default_rossmann_state_file(source_config),
            )
            domain = _string_option(connector_options, "domain", "www.rossmann.de")
            headless = _bool_option(connector_options, "headless", True)
            max_pages = _int_option(connector_options, "max_pages", 10)
            store_name = _string_option(connector_options, "store_name", "Rossmann")
            rossmann_client = RossmannPlaywrightClient(
                state_file=state_file,
                domain=domain,
                headless=headless,
                max_pages=max_pages,
            )
            rossmann_connector: Connector = RossmannConnectorAdapter(
                client=rossmann_client,
                source=tracking_source_id,
                store_name=store_name,
            )
            return self._resolved_receipt_connector(
                manifest=manifest,
                source_config=source_config,
                client=None,
                connector=rossmann_connector,
                metadata={"state_file": str(state_file), "domain": domain},
                handled_exceptions=(RossmannClientError,),
            )
        raise RuntimeError(f"connector runtime bridge is not registered for source: {manifest.source_id}")

    def _resolved_receipt_connector(
        self,
        *,
        manifest: ConnectorManifest,
        source_config: AppConfig,
        client: Any | None,
        connector: Connector,
        metadata: dict[str, Any] | None = None,
        handled_exceptions: tuple[type[Exception], ...] = (),
    ) -> ResolvedReceiptConnector:
        self._validate_connector_security(connector)
        return ResolvedReceiptConnector(
            manifest=manifest,
            source_config=source_config,
            client=client,
            connector=RuntimeHostedReceiptConnector(
                host=self._runtime_host,
                target=ReceiptConnectorRuntimeTarget(
                    manifest=manifest,
                    connector=connector,
                    legacy_auth_delegate=connector,
                ),
                action_timeouts_s=default_runtime_action_timeouts(
                    source_config.request_timeout_s
                ),
            ),
            metadata=metadata or {},
            handled_exceptions=handled_exceptions,
        )

    def _assert_runtime_allowed(self, entry: PluginRegistryEntry) -> None:
        manifest = entry.manifest
        if manifest is None:
            raise RuntimeError("connector manifest is not available")
        decision = evaluate_plugin_policy(manifest, config=self._config, host_kind=_plugin_host_kind())
        if decision.enabled:
            return
        if decision.detail:
            raise RuntimeError(decision.detail)
        if decision.block_reason is not None:
            raise RuntimeError(
                f"connector source {manifest.source_id!r} is blocked by policy: {decision.block_reason}"
            )
        raise RuntimeError(f"connector source {manifest.source_id!r} is not enabled")

    def _require_entry(
        self,
        source_id: str,
        *,
        plugin_family: Literal["receipt", "offer"] | None = None,
    ) -> PluginRegistryEntry:
        entry = self._registry.get_entry(source_id)
        if entry is None or entry.manifest is None:
            raise RuntimeError(f"connector source {source_id!r} is not registered")
        if plugin_family is not None and entry.manifest.plugin_family != plugin_family:
            raise RuntimeError(
                f"connector source {source_id!r} is not registered for plugin_family={plugin_family!r}"
            )
        return entry

    def _working_directory_for(self, entry: PluginRegistryEntry) -> Path:
        if entry.origin_directory is not None:
            return entry.origin_directory
        return self._config.config_dir

    def _runtime_metadata_for(self, entry: PluginRegistryEntry) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if entry.origin_path is not None:
            metadata["origin_path"] = str(entry.origin_path)
        if entry.origin_directory is not None:
            metadata["origin_directory"] = str(entry.origin_directory)
        return metadata

    def _validate_connector_security(self, connector: Connector) -> None:
        validate_connector_scope_contract(connector)
        for action in (
            "authenticate",
            "refresh_auth",
            "healthcheck",
            "discover_new_records",
            "fetch_record_detail",
            "normalize",
            "extract_discounts",
        ):
            require_connector_action_scope(
                connector,
                action=action,
                granted_scopes=RUNTIME_CONNECTOR_SCOPES,
            )

    def _resolve_state_file(self, value: object, default: Path) -> Path:
        resolved = _resolve_optional_path(value)
        if resolved is not None:
            return resolved
        return _resolve_path(default)
