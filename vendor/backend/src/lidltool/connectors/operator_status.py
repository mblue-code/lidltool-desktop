from __future__ import annotations

from typing import Any

from lidltool.connectors.market_catalog import support_policy_payload

_STATE_LABELS: dict[str, str] = {
    "built_in_available": "Built in",
    "catalog_listed": "Available in catalog",
    "discovered_locally": "Discovered locally",
    "installed": "Installed",
    "enabled": "Enabled",
    "disabled": "Disabled",
    "blocked_by_policy": "Blocked by policy",
    "invalid": "Invalid",
    "incompatible": "Incompatible",
    "revoked": "Revoked",
    "quarantined_activity_present": "Quarantine activity present",
}

_STATE_DESCRIPTIONS: dict[str, str] = {
    "built_in_available": "Shipped with the product and available without a manual install.",
    "catalog_listed": "Listed in the curated catalog but not installed locally.",
    "discovered_locally": "Found on local plugin search paths.",
    "installed": "Present in local plugin storage or search paths.",
    "enabled": "Active and allowed to run.",
    "disabled": "Present but not active.",
    "blocked_by_policy": "Present, but blocked by an explicit safety or approval policy.",
    "invalid": "Rejected because required plugin files or metadata are not valid.",
    "incompatible": "Rejected because the plugin does not support this product or version.",
    "revoked": "Explicitly revoked and not allowed to run.",
    "quarantined_activity_present": "Recent validation or review activity exists for this plugin or source.",
}

_BLOCK_REASON_LABELS: dict[str, str] = {
    "external_receipt_plugins_disabled": "External receipt plugins are turned off",
    "external_offer_plugins_disabled": "External offer plugins are turned off",
    "trust_class_not_allowed": "This plugin trust class is not approved",
    "external_runtime_disabled": "External plugin runtimes are turned off",
    "host_kind_not_supported": "This plugin does not support this product",
    "core_version_below_minimum": "This plugin needs a newer lidltool version",
    "core_version_above_maximum": "This plugin only supports an older lidltool version",
    "manifest_validation_failed": "The plugin manifest is invalid",
    "invalid_plugin_origin": "The plugin origin declaration is not allowed",
    "unsupported_external_runtime_kind": "The plugin runtime kind is not allowed",
    "missing_entrypoint": "The plugin is missing its runtime entrypoint",
    "duplicate_source_id": "Another plugin already uses this source id",
    "duplicate_plugin_id": "Another plugin already uses this plugin id",
}

_BLOCK_REASON_SUMMARIES: dict[str, str] = {
    "external_receipt_plugins_disabled": "An operator has not enabled external receipt plugins on this server.",
    "external_offer_plugins_disabled": "An operator has not enabled external offer plugins on this server.",
    "trust_class_not_allowed": "The server trust policy does not allow this plugin's trust class.",
    "external_runtime_disabled": "The server is not allowing external plugin runtimes to execute.",
    "host_kind_not_supported": "The plugin manifest does not list this product as a supported host.",
    "core_version_below_minimum": "The running lidltool version is below the plugin's declared minimum.",
    "core_version_above_maximum": "The running lidltool version is above the plugin's declared maximum.",
    "manifest_validation_failed": "The plugin could not pass manifest validation before it was considered for use.",
    "invalid_plugin_origin": "External plugins must declare an external or local-path origin.",
    "unsupported_external_runtime_kind": "The plugin asked for a runtime kind that is not approved for external plugins.",
    "missing_entrypoint": "The plugin declared an external runtime but did not provide an entrypoint.",
    "duplicate_source_id": "Another registry entry already owns this source id, so this plugin is ignored.",
    "duplicate_plugin_id": "Another registry entry already owns this plugin id, so this plugin is ignored.",
}


def state_legend_payload() -> list[dict[str, str]]:
    return [
        {
            "code": code,
            "label": _STATE_LABELS[code],
            "description": _STATE_DESCRIPTIONS[code],
        }
        for code in (
            "built_in_available",
            "catalog_listed",
            "discovered_locally",
            "installed",
            "enabled",
            "disabled",
            "blocked_by_policy",
            "invalid",
            "incompatible",
            "revoked",
            "quarantined_activity_present",
        )
    ]


def block_reason_payload(
    *,
    block_reason: str | None,
    status_detail: str | None = None,
) -> dict[str, str | None] | None:
    if not block_reason:
        return None
    return {
        "code": block_reason,
        "label": _BLOCK_REASON_LABELS.get(block_reason, block_reason.replace("_", " ")),
        "summary": _BLOCK_REASON_SUMMARIES.get(block_reason, status_detail or block_reason),
        "detail": status_detail,
    }


def support_summary_payload(trust_class: str | None) -> dict[str, Any]:
    policy = support_policy_payload(trust_class)
    if policy is None:
        label = trust_class.replace("_", " ").title() if isinstance(trust_class, str) else "Unknown"
        return {
            "trust_class": trust_class,
            "label": label,
            "summary": label,
            "support_policy": None,
        }

    summary = " ".join(
        item
        for item in (
            policy.get("display_name"),
            policy.get("maintainer_support"),
            policy.get("update_expectations"),
        )
        if isinstance(item, str) and item
    )
    return {
        "trust_class": trust_class,
        "label": policy["ui_label"],
        "summary": summary,
        "support_policy": policy,
    }


def operator_state_payload(
    *,
    status: str | None,
    enabled: bool,
    discovered: bool,
    plugin_origin: str | None,
    catalog_listed: bool,
    has_quarantine_activity: bool = False,
    block_reason: str | None = None,
    status_detail: str | None = None,
    revoked: bool = False,
) -> dict[str, Any]:
    built_in_available = plugin_origin == "builtin"
    installed = discovered and plugin_origin != "builtin"
    flags = {
        "built_in_available": built_in_available,
        "catalog_listed": catalog_listed,
        "discovered_locally": discovered,
        "installed": installed,
        "enabled": enabled,
        "disabled": status == "disabled",
        "blocked_by_policy": status == "blocked_by_policy",
        "invalid": status == "invalid",
        "incompatible": status == "incompatible",
        "revoked": revoked,
        "quarantined_activity_present": has_quarantine_activity,
    }
    visible_states = [code for code, value in flags.items() if value]
    primary_state = _primary_state(status=status, enabled=enabled, installed=installed, catalog_listed=catalog_listed)
    if revoked:
        primary_state = "revoked"

    return {
        "primary_state": primary_state,
        "label": _STATE_LABELS[primary_state],
        "summary": _state_summary(
            primary_state=primary_state,
            built_in_available=built_in_available,
            installed=installed,
            catalog_listed=catalog_listed,
            status_detail=status_detail,
            block_reason=block_reason,
            has_quarantine_activity=has_quarantine_activity,
        ),
        "visible_states": visible_states,
        "flags": flags,
        "block": block_reason_payload(block_reason=block_reason, status_detail=status_detail),
    }


def market_context_payload(catalog_entry: dict[str, Any] | None) -> dict[str, Any]:
    if catalog_entry is None:
        return {
            "official_bundle_ids": [],
            "market_profile_ids": [],
            "release_variant_ids": [],
            "summary": "Not listed in the curated catalog for this product profile.",
        }

    bundle_ids = [str(item) for item in catalog_entry.get("official_bundle_ids", []) if isinstance(item, str)]
    profile_ids = [str(item) for item in catalog_entry.get("market_profile_ids", []) if isinstance(item, str)]
    release_variant_ids = [
        str(item) for item in catalog_entry.get("release_variant_ids", []) if isinstance(item, str)
    ]

    summary_parts: list[str] = []
    if bundle_ids:
        summary_parts.append(f"Bundled or referenced by: {', '.join(bundle_ids)}.")
    if profile_ids:
        summary_parts.append(f"Shown for market profiles: {', '.join(profile_ids)}.")
    if not summary_parts:
        summary_parts.append("Listed in the catalog, but not part of a default official bundle.")

    return {
        "official_bundle_ids": bundle_ids,
        "market_profile_ids": profile_ids,
        "release_variant_ids": release_variant_ids,
        "summary": " ".join(summary_parts),
    }


def _primary_state(
    *,
    status: str | None,
    enabled: bool,
    installed: bool,
    catalog_listed: bool,
) -> str:
    if status == "invalid":
        return "invalid"
    if status == "blocked_by_policy":
        return "blocked_by_policy"
    if status == "incompatible":
        return "incompatible"
    if enabled or status == "enabled":
        return "enabled"
    if status == "disabled":
        return "disabled"
    if installed or status in {"discovered", "valid"}:
        return "installed"
    if catalog_listed:
        return "catalog_listed"
    return "discovered_locally"


def _state_summary(
    *,
    primary_state: str,
    built_in_available: bool,
    installed: bool,
    catalog_listed: bool,
    status_detail: str | None,
    block_reason: str | None,
    has_quarantine_activity: bool,
) -> str:
    if primary_state == "enabled":
        if built_in_available:
            summary = "Built-in plugin is available and active."
        elif installed:
            summary = "Installed plugin is active."
        else:
            summary = "Plugin is active."
    elif primary_state == "disabled":
        summary = "Plugin is present but not active."
    elif primary_state == "blocked_by_policy":
        block = block_reason_payload(block_reason=block_reason, status_detail=status_detail)
        summary = (
            str(block["summary"])
            if isinstance(block, dict) and isinstance(block.get("summary"), str)
            else "Plugin is blocked by policy."
        )
    elif primary_state == "invalid":
        summary = "Plugin files or manifest are invalid and were rejected."
    elif primary_state == "incompatible":
        summary = status_detail or "Plugin compatibility requirements are not satisfied."
    elif primary_state == "catalog_listed":
        summary = "Plugin is available in the curated catalog but is not installed locally."
    elif primary_state == "installed":
        summary = "Plugin is installed locally but not active yet."
    else:
        summary = "Plugin was discovered locally."

    if catalog_listed and primary_state not in {"catalog_listed", "enabled"}:
        summary = f"{summary} It is also listed in the curated catalog."
    if has_quarantine_activity:
        summary = f"{summary} Recent quarantine activity needs review."
    return summary
