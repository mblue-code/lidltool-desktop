import type {
  ConnectorCatalogEntry,
  DesktopReleaseMetadata,
  DesktopRuntimeDiagnostics,
  ReceiptPluginPackInfo
} from "../shared/contracts";

export type StatusDescriptor = {
  label: string;
  detail: string;
  chipClass: string;
};

export type ControlCenterMode = {
  tone: "info" | "warning" | "success";
  label: string;
  title: string;
  detail: string;
};

export function compareVersions(left: string, right: string): number {
  const leftParts = left.split(/[\.-]/);
  const rightParts = right.split(/[\.-]/);
  const maxLength = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftParts[index] ?? "0";
    const rightPart = rightParts[index] ?? "0";
    const leftNumber = Number(leftPart);
    const rightNumber = Number(rightPart);
    const bothNumeric = Number.isFinite(leftNumber) && Number.isFinite(rightNumber);
    const comparison = bothNumeric
      ? leftNumber - rightNumber
      : leftPart.localeCompare(rightPart, undefined, { numeric: true, sensitivity: "base" });
    if (comparison !== 0) {
      return comparison < 0 ? -1 : 1;
    }
  }
  return 0;
}

export function formatTrustClassLabel(trustClass: string): string {
  if (trustClass === "official") {
    return "Official";
  }
  if (trustClass === "community_verified") {
    return "Community verified";
  }
  if (trustClass === "local_custom") {
    return "Local custom";
  }
  return "Community unsigned";
}

export function trustClassMeaning(trustClass: string): string {
  if (trustClass === "official") {
    return "Maintained and shipped by the project.";
  }
  if (trustClass === "community_verified") {
    return "Signed community pack allowed by desktop trusted distribution policy.";
  }
  if (trustClass === "local_custom") {
    return "Operator-supplied local plugin with no upstream support promise.";
  }
  return "Manual or unsigned community plugin kept under conservative trust handling.";
}

export function formatPluginTrust(pack: ReceiptPluginPackInfo): string {
  if (pack.trustStatus === "trusted") {
    if (pack.trustClass === "official") {
      return pack.signingKeyId ? `Trusted official (${pack.signingKeyId})` : "Trusted official";
    }
    return pack.signingKeyId ? `Trusted signed (${pack.signingKeyId})` : "Trusted signed";
  }
  if (pack.trustStatus === "revoked") {
    return "Revoked";
  }
  if (pack.trustStatus === "signature_invalid") {
    return "Signature invalid";
  }
  if (pack.trustStatus === "incompatible") {
    return "Incompatible";
  }
  if (pack.trustClass === "local_custom") {
    return "Local custom";
  }
  return "Community unsigned";
}

export function describeInstalledPack(pack: ReceiptPluginPackInfo): StatusDescriptor {
  if (pack.status === "enabled") {
    return {
      label: "Ready",
      detail: "Installed locally and loaded into the next backend run.",
      chipClass: "status-enabled"
    };
  }
  if (pack.status === "disabled") {
    return {
      label: "Installed",
      detail:
        pack.installedVia === "catalog_url"
          ? "Stored locally from the trusted catalog. You still decide when to enable it."
          : "Stored locally from a manual import. Desktop keeps activation explicit.",
      chipClass: "status-disabled"
    };
  }
  if (pack.status === "revoked") {
    return {
      label: "Blocked",
      detail: pack.trustReason ?? "This pack was revoked and cannot be enabled in desktop.",
      chipClass: "status-invalid"
    };
  }
  if (pack.status === "incompatible") {
    return {
      label: "Blocked",
      detail:
        pack.compatibilityReason ??
        "This pack does not match the current desktop build and stays disabled.",
      chipClass: "status-incompatible"
    };
  }
  return {
    label: "Needs attention",
    detail:
      pack.trustReason ??
      pack.compatibilityReason ??
      "Desktop found a validation problem and kept this pack disabled.",
    chipClass: "status-invalid"
  };
}

export function describeCatalogEntry(
  entry: DesktopReleaseMetadata["discovery_catalog"]["entries"][number],
  installedPack: ReceiptPluginPackInfo | null
): StatusDescriptor {
  if (entry.availability.blocked_by_policy) {
    return {
      label: "Blocked",
      detail: entry.availability.block_reason ?? "This catalog entry is blocked by desktop policy.",
      chipClass: "status-invalid"
    };
  }
  if (!installedPack) {
    return {
      label: "Available",
      detail: "Listed for this desktop build but not stored locally yet.",
      chipClass: "status-disabled"
    };
  }
  const installedState = describeInstalledPack(installedPack);
  if (
    entry.entry_type === "desktop_pack" &&
    entry.current_version &&
    compareVersions(installedPack.version, entry.current_version) < 0
  ) {
    return {
      label: "Update available",
      detail: `Installed version ${installedPack.version} is behind trusted version ${entry.current_version}.`,
      chipClass: "status-incompatible"
    };
  }
  return installedState;
}

export function findCatalogDesktopPackEntry(
  entries: DesktopReleaseMetadata["discovery_catalog"]["entries"],
  pluginId: string
): ConnectorCatalogEntry | null {
  return (
    entries
      .filter((entry): entry is ConnectorCatalogEntry => entry.entry_type === "desktop_pack" && entry.plugin_id === pluginId)
      .sort((left, right) => compareVersions(left.current_version ?? "0", right.current_version ?? "0"))
      .at(-1) ?? null
  );
}

export function packInstallSource(pack: ReceiptPluginPackInfo): string {
  return pack.installedVia === "catalog_url" ? "Trusted catalog download" : "Manual file import";
}

export function packOriginSummary(pack: ReceiptPluginPackInfo): string {
  if (pack.installedVia === "catalog_url") {
    return "Installed from a trusted catalog download and stored locally on this computer.";
  }
  return "Installed from a local file. Desktop keeps support and trust labels conservative.";
}

export function packSupportSummary(
  pack: ReceiptPluginPackInfo,
  catalogEntry: ConnectorCatalogEntry | null
): string {
  if (catalogEntry?.support_policy) {
    return `${catalogEntry.support_policy.maintainer_support} ${catalogEntry.support_policy.update_expectations}`;
  }
  return trustClassMeaning(pack.trustClass);
}

export function catalogSupportSummary(
  entry: DesktopReleaseMetadata["discovery_catalog"]["entries"][number]
): string {
  if (entry.support_policy) {
    return `${entry.support_policy.maintainer_support} ${entry.support_policy.update_expectations}`;
  }
  return trustClassMeaning(entry.trust_class);
}

export function catalogProfileSummary(
  entry: DesktopReleaseMetadata["discovery_catalog"]["entries"][number],
  releaseMetadata: DesktopReleaseMetadata | null
): string {
  if (!releaseMetadata) {
    return "Edition metadata is still loading.";
  }
  const selectedProfileId = releaseMetadata.selected_market_profile_id;
  if (entry.market_profile_ids.includes(selectedProfileId)) {
    return `Shown for the current market profile (${releaseMetadata.selected_market_profile.display_name}).`;
  }
  if (entry.official_bundle_ids.length > 0) {
    return `Referenced by bundle(s): ${entry.official_bundle_ids.join(", ")}.`;
  }
  return "Optional for this build, but not part of the default profile.";
}

export function formatCatalogVerification(
  catalog: DesktopReleaseMetadata["discovery_catalog"] | null
): string {
  if (!catalog) {
    return "Loading";
  }
  if (catalog.verification_status === "trusted") {
    return catalog.signed_by_key_id ? `Trusted (${catalog.signed_by_key_id})` : "Trusted";
  }
  if (catalog.verification_status === "revoked") {
    return "Revoked";
  }
  if (catalog.verification_status === "signature_invalid") {
    return "Signature invalid";
  }
  if (catalog.verification_status === "incompatible") {
    return "Incompatible";
  }
  return "Unavailable";
}

export function formatCatalogEntryType(
  entryType: DesktopReleaseMetadata["discovery_catalog"]["entries"][number]["entry_type"]
): string {
  if (entryType === "bundle") {
    return "Bundle";
  }
  if (entryType === "desktop_pack") {
    return "Receipt pack";
  }
  return "Connector";
}

export function formatInstallMethods(
  methods: DesktopReleaseMetadata["discovery_catalog"]["entries"][number]["install_methods"]
): string {
  return methods
    .map((method) => {
      if (method === "built_in") {
        return "Built in";
      }
      if (method === "manual_import") {
        return "Manual import";
      }
      if (method === "manual_mount") {
        return "Manual mount";
      }
      return "Trusted download";
    })
    .join(", ");
}

export function describeControlCenterMode(
  bootError: string | null,
  diagnostics: DesktopRuntimeDiagnostics | null
): ControlCenterMode {
  if (bootError) {
    return {
      tone: "warning",
      label: "Reduced mode",
      title: "The main app did not open automatically.",
      detail:
        "Use the control center for local sync, plugin packs, export, and backup tasks while you review the startup issue."
    };
  }
  if (diagnostics && !diagnostics.fullAppReady) {
    return {
      tone: "warning",
      label: "Control center only",
      title: "This build is missing the bundled main app pages.",
      detail:
        "Desktop can still handle occasional local sync, review, export, backup, and manual receipt pack tasks from this shell."
    };
  }
  return {
    tone: "success",
    label: "Full app available",
    title: "The local control center is ready.",
    detail:
      "Use it for quick local tasks, or open the main app when you want the full in-browser workflow on this computer."
  };
}

export function describeBackendCommand(diagnostics: DesktopRuntimeDiagnostics | null): string {
  if (!diagnostics) {
    return "Loading local runtime details.";
  }
  if (diagnostics.backendCommandSource === "bundled") {
    return "Bundled with this desktop build.";
  }
  if (diagnostics.backendCommandSource === "managed_dev") {
    return "Using the desktop-managed development runtime.";
  }
  if (diagnostics.backendCommandSource === "env_override") {
    return diagnostics.backendCommandStatus === "missing"
      ? "A custom runtime path is configured, but the file is missing."
      : "Using a custom runtime configured through LIDLTOOL_EXECUTABLE.";
  }
  return "Desktop will look for the local runtime in your system PATH.";
}

export function formatEditionKind(
  kind: DesktopReleaseMetadata["active_release_variant"]["edition_kind"]
): string {
  return kind === "regional_edition" ? "Regional edition" : "Universal desktop shell";
}
