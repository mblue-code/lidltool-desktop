from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lidltool.connectors.sdk.manifest import ConnectorManifest

ConnectorMaturity = Literal["verified", "working", "preview", "stub"]
ConnectorSurfaceVisibility = Literal["default", "operator_only"]


@dataclass(frozen=True, slots=True)
class ConnectorReleasePolicy:
    maturity: ConnectorMaturity
    label: str
    support_posture: str
    description: str
    default_visibility: ConnectorSurfaceVisibility
    graduation_requirements: tuple[str, ...]


_RELEASE_POLICIES: dict[ConnectorMaturity, ConnectorReleasePolicy] = {
    "verified": ConnectorReleasePolicy(
        maturity="verified",
        label="Verified",
        support_posture="Supported for normal self-hosted use.",
        description="This connector has passed the current graduation bar for regular use.",
        default_visibility="default",
        graduation_requirements=(
            "Auth/bootstrap works in the maintained self-hosted path.",
            "Receipt sync is exercised by regression coverage.",
            "Operator lifecycle and diagnostics are maintained in-product.",
        ),
    ),
    "working": ConnectorReleasePolicy(
        maturity="working",
        label="Working",
        support_posture="Usable on the maintained path, but not yet fully graduated.",
        description="This connector is expected to work, with less release confidence than Verified.",
        default_visibility="default",
        graduation_requirements=(
            "Bootstrap and sync work in the intended runtime path.",
            "Known operator workflow gaps are documented and bounded.",
            "Regression coverage exists for the current maintained behavior.",
        ),
    ),
    "preview": ConnectorReleasePolicy(
        maturity="preview",
        label="Preview",
        support_posture="Visible with caution. Expect rough edges and reconnects.",
        description="This connector is intentionally exposed as an early preview.",
        default_visibility="default",
        graduation_requirements=(
            "Install, configure, and reconnect flows are product-maintained.",
            "At least one maintained auth and sync path is exercised by tests.",
            "User-facing copy and operator policy details are no longer transitional.",
        ),
    ),
    "stub": ConnectorReleasePolicy(
        maturity="stub",
        label="Stub",
        support_posture="Not ready for normal end-user use.",
        description="This connector is incomplete or transitional and stays behind operator visibility.",
        default_visibility="operator_only",
        graduation_requirements=(
            "Core lifecycle state is implemented without manual dev-only steps.",
            "Auth/bootstrap and sync behavior are intentionally supported.",
            "The connector can be promoted to Preview without hidden operator knowledge.",
        ),
    ),
}


def connector_release_policy(
    *,
    source_id: str,
    manifest: ConnectorManifest | None,
) -> ConnectorReleasePolicy:
    raw_maturity = manifest.metadata.get("maturity") if manifest is not None else None
    if isinstance(raw_maturity, str):
        normalized = raw_maturity.strip().lower()
        if normalized in _RELEASE_POLICIES:
            return _RELEASE_POLICIES[normalized]  # type: ignore[index]
    return _RELEASE_POLICIES[_fallback_maturity(source_id)]


def release_policy_payload(
    *,
    source_id: str,
    manifest: ConnectorManifest | None,
) -> dict[str, object]:
    policy = connector_release_policy(source_id=source_id, manifest=manifest)
    return {
        "maturity": policy.maturity,
        "label": policy.label,
        "support_posture": policy.support_posture,
        "description": policy.description,
        "default_visibility": policy.default_visibility,
        "graduation_requirements": list(policy.graduation_requirements),
    }


def _fallback_maturity(source_id: str) -> ConnectorMaturity:
    fallback: dict[str, ConnectorMaturity] = {
        "lidl_plus_de": "working",
        "amazon_de": "preview",
        "amazon_fr": "preview",
        "amazon_gb": "preview",
        "rossmann_de": "preview",
        "rewe_de": "preview",
    }
    return fallback.get(source_id, "stub")
