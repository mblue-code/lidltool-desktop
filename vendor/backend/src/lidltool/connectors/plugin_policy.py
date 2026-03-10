from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import lidltool
from lidltool.config import AppConfig
from lidltool.connectors.plugin_status import PluginCompatibilitySnapshot, PluginLoadStatus
from lidltool.connectors.sdk.manifest import ConnectorManifest

HostKind = Literal["self_hosted", "electron"]


@dataclass(frozen=True, slots=True)
class PluginPolicyDecision:
    status: PluginLoadStatus
    enabled: bool
    block_reason: str | None
    detail: str | None
    compatibility: PluginCompatibilitySnapshot


def evaluate_plugin_compatibility(
    manifest: ConnectorManifest,
    *,
    host_kind: HostKind = "self_hosted",
    core_version: str = lidltool.__version__,
) -> PluginCompatibilitySnapshot:
    compatibility = manifest.compatibility
    supported_host_kinds = tuple(compatibility.supported_host_kinds)
    if host_kind not in supported_host_kinds:
        return PluginCompatibilitySnapshot(
            compatible=False,
            host_kind=host_kind,
            core_version=core_version,
            reason="host_kind_not_supported",
            min_core_version=compatibility.min_core_version,
            max_core_version=compatibility.max_core_version,
            supported_host_kinds=supported_host_kinds,
        )
    if compatibility.min_core_version is not None and _compare_versions(
        core_version, compatibility.min_core_version
    ) < 0:
        return PluginCompatibilitySnapshot(
            compatible=False,
            host_kind=host_kind,
            core_version=core_version,
            reason="core_version_below_minimum",
            min_core_version=compatibility.min_core_version,
            max_core_version=compatibility.max_core_version,
            supported_host_kinds=supported_host_kinds,
        )
    if compatibility.max_core_version is not None and _compare_versions(
        core_version, compatibility.max_core_version
    ) > 0:
        return PluginCompatibilitySnapshot(
            compatible=False,
            host_kind=host_kind,
            core_version=core_version,
            reason="core_version_above_maximum",
            min_core_version=compatibility.min_core_version,
            max_core_version=compatibility.max_core_version,
            supported_host_kinds=supported_host_kinds,
        )
    return PluginCompatibilitySnapshot(
        compatible=True,
        host_kind=host_kind,
        core_version=core_version,
        min_core_version=compatibility.min_core_version,
        max_core_version=compatibility.max_core_version,
        supported_host_kinds=supported_host_kinds,
    )


def evaluate_plugin_policy(
    manifest: ConnectorManifest,
    *,
    config: AppConfig,
    host_kind: HostKind = "self_hosted",
    core_version: str = lidltool.__version__,
) -> PluginPolicyDecision:
    compatibility = evaluate_plugin_compatibility(
        manifest,
        host_kind=host_kind,
        core_version=core_version,
    )
    if not compatibility.compatible:
        detail = _compatibility_detail(compatibility)
        return PluginPolicyDecision(
            status="incompatible",
            enabled=False,
            block_reason=compatibility.reason,
            detail=detail,
            compatibility=compatibility,
        )

    if manifest.plugin_origin == "builtin":
        return PluginPolicyDecision(
            status="enabled",
            enabled=True,
            block_reason=None,
            detail=None,
            compatibility=compatibility,
        )

    if manifest.plugin_family == "receipt" and not config.connector_external_receipt_plugins_enabled:
        return PluginPolicyDecision(
            status="disabled",
            enabled=False,
            block_reason="external_receipt_plugins_disabled",
            detail=(
                "external receipt plugins are disabled; enable "
                "LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED for approved plugins"
            ),
            compatibility=compatibility,
        )
    if manifest.plugin_family == "offer" and not config.connector_external_offer_plugins_enabled:
        return PluginPolicyDecision(
            status="disabled",
            enabled=False,
            block_reason="external_offer_plugins_disabled",
            detail=(
                "external offer plugins are disabled; enable "
                "LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED for approved plugins"
            ),
            compatibility=compatibility,
        )
    if manifest.trust_class not in config.connector_external_allowed_trust_classes:
        return PluginPolicyDecision(
            status="blocked_by_policy",
            enabled=False,
            block_reason="trust_class_not_allowed",
            detail=(
                f"trust class {manifest.trust_class!r} is not allowed; configure "
                "LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES for approved plugins"
            ),
            compatibility=compatibility,
        )
    if not config.connector_external_runtime_enabled:
        return PluginPolicyDecision(
            status="blocked_by_policy",
            enabled=False,
            block_reason="external_runtime_disabled",
            detail=(
                "external connector runtimes are disabled; enable "
                "LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED for approved registry entries"
            ),
            compatibility=compatibility,
        )
    return PluginPolicyDecision(
        status="enabled",
        enabled=True,
        block_reason=None,
        detail=None,
        compatibility=compatibility,
    )


def _compatibility_detail(compatibility: PluginCompatibilitySnapshot) -> str:
    if compatibility.reason == "host_kind_not_supported":
        supported = ", ".join(compatibility.supported_host_kinds) or "none"
        return f"plugin does not support host kind {compatibility.host_kind!r}; supported host kinds: {supported}"
    if compatibility.reason == "core_version_below_minimum":
        return (
            f"plugin requires lidltool>={compatibility.min_core_version}; "
            f"running {compatibility.core_version}"
        )
    if compatibility.reason == "core_version_above_maximum":
        return (
            f"plugin supports lidltool<={compatibility.max_core_version}; "
            f"running {compatibility.core_version}"
        )
    return "plugin compatibility requirements are not satisfied"


def _compare_versions(left: str, right: str) -> int:
    left_parts = _normalize_version(left)
    right_parts = _normalize_version(right)
    width = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (width - len(left_parts))
    padded_right = right_parts + (0,) * (width - len(right_parts))
    if padded_left < padded_right:
        return -1
    if padded_left > padded_right:
        return 1
    return 0


def _normalize_version(value: str) -> tuple[int, ...]:
    segments = [segment.strip() for segment in value.split(".")]
    normalized: list[int] = []
    for segment in segments:
        if not segment:
            normalized.append(0)
            continue
        numeric = []
        for char in segment:
            if not char.isdigit():
                break
            numeric.append(char)
        if not numeric:
            raise ValueError(f"unsupported version segment: {segment!r}")
        normalized.append(int("".join(numeric)))
    return tuple(normalized)
