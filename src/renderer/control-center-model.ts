import type {
  ConnectorCatalogEntry,
  DesktopReleaseMetadata,
  DesktopRuntimeDiagnostics,
  ReceiptPluginPackInfo
} from "../shared/contracts";
import type { DesktopLocale } from "../i18n";

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

export function formatTrustClassLabel(trustClass: string, locale: DesktopLocale): string {
  if (trustClass === "official") {
    return locale === "de" ? "Offiziell" : "Official";
  }
  if (trustClass === "community_verified") {
    return locale === "de" ? "Von der Community verifiziert" : "Community verified";
  }
  if (trustClass === "local_custom") {
    return locale === "de" ? "Lokale Eigenversion" : "Local custom";
  }
  return locale === "de" ? "Community ohne Signatur" : "Community unsigned";
}

export function trustClassMeaning(trustClass: string, locale: DesktopLocale): string {
  if (trustClass === "official") {
    return locale === "de"
      ? "Wird vom Projekt gepflegt und ausgeliefert."
      : "Maintained and shipped by the project.";
  }
  if (trustClass === "community_verified") {
    return locale === "de"
      ? "Signiertes Community-Paket, das von der vertrauenswürdigen Desktop-Distributionsrichtlinie zugelassen ist."
      : "Signed community pack allowed by desktop trusted distribution policy.";
  }
  if (trustClass === "local_custom") {
    return locale === "de"
      ? "Lokal bereitgestelltes Plugin ohne Support-Zusage von upstream."
      : "Operator-supplied local plugin with no upstream support promise.";
  }
  return locale === "de"
    ? "Manuelles oder unsigniertes Community-Plugin mit konservativer Vertrauensbehandlung."
    : "Manual or unsigned community plugin kept under conservative trust handling.";
}

export function formatPluginTrust(pack: ReceiptPluginPackInfo, locale: DesktopLocale): string {
  if (pack.trustStatus === "trusted") {
    if (pack.trustClass === "official") {
      return pack.signingKeyId
        ? locale === "de"
          ? `Vertrauenswürdig offiziell (${pack.signingKeyId})`
          : `Trusted official (${pack.signingKeyId})`
        : locale === "de"
          ? "Vertrauenswürdig offiziell"
          : "Trusted official";
    }
    return pack.signingKeyId
      ? locale === "de"
        ? `Vertrauenswürdig signiert (${pack.signingKeyId})`
        : `Trusted signed (${pack.signingKeyId})`
      : locale === "de"
        ? "Vertrauenswürdig signiert"
        : "Trusted signed";
  }
  if (pack.trustStatus === "revoked") {
    return locale === "de" ? "Widerrufen" : "Revoked";
  }
  if (pack.trustStatus === "signature_invalid") {
    return locale === "de" ? "Signatur ungültig" : "Signature invalid";
  }
  if (pack.trustStatus === "incompatible") {
    return locale === "de" ? "Inkompatibel" : "Incompatible";
  }
  if (pack.trustClass === "local_custom") {
    return locale === "de" ? "Lokale Eigenversion" : "Local custom";
  }
  return locale === "de" ? "Community ohne Signatur" : "Community unsigned";
}

export function describeInstalledPack(pack: ReceiptPluginPackInfo, locale: DesktopLocale): StatusDescriptor {
  if (pack.status === "enabled") {
    return {
      label: locale === "de" ? "Bereit" : "Ready",
      detail:
        locale === "de"
          ? "Lokal installiert und für den nächsten Backend-Start geladen."
          : "Installed locally and loaded into the next backend run.",
      chipClass: "status-enabled"
    };
  }
  if (pack.status === "disabled") {
    return {
      label: locale === "de" ? "Installiert" : "Installed",
      detail:
        pack.installedVia === "catalog_url"
          ? locale === "de"
            ? "Lokal aus dem vertrauenswürdigen Katalog gespeichert. Sie entscheiden weiterhin selbst, wann es aktiviert wird."
            : "Stored locally from the trusted catalog. You still decide when to enable it."
          : locale === "de"
            ? "Lokal aus einem manuellen Import gespeichert. Desktop hält die Aktivierung bewusst explizit."
            : "Stored locally from a manual import. Desktop keeps activation explicit.",
      chipClass: "status-disabled"
    };
  }
  if (pack.status === "revoked") {
    return {
      label: locale === "de" ? "Blockiert" : "Blocked",
      detail:
        pack.trustReason ??
        (locale === "de"
          ? "Dieses Paket wurde widerrufen und kann im Desktop nicht aktiviert werden."
          : "This pack was revoked and cannot be enabled in desktop."),
      chipClass: "status-invalid"
    };
  }
  if (pack.status === "incompatible") {
    return {
      label: locale === "de" ? "Blockiert" : "Blocked",
      detail:
        pack.compatibilityReason ??
        (locale === "de"
          ? "Dieses Paket passt nicht zur aktuellen Desktop-Build und bleibt deaktiviert."
          : "This pack does not match the current desktop build and stays disabled."),
      chipClass: "status-incompatible"
    };
  }
  return {
    label: locale === "de" ? "Benötigt Aufmerksamkeit" : "Needs attention",
    detail:
      pack.trustReason ??
      pack.compatibilityReason ??
      (locale === "de"
        ? "Desktop hat ein Validierungsproblem erkannt und dieses Paket deaktiviert gelassen."
        : "Desktop found a validation problem and kept this pack disabled."),
    chipClass: "status-invalid"
  };
}

export function describeCatalogEntry(
  entry: DesktopReleaseMetadata["discovery_catalog"]["entries"][number],
  installedPack: ReceiptPluginPackInfo | null,
  locale: DesktopLocale
): StatusDescriptor {
  if (entry.availability.blocked_by_policy) {
    return {
      label: locale === "de" ? "Blockiert" : "Blocked",
      detail:
        entry.availability.block_reason ??
        (locale === "de"
          ? "Dieser Katalogeintrag wird durch die Desktop-Richtlinie blockiert."
          : "This catalog entry is blocked by desktop policy."),
      chipClass: "status-invalid"
    };
  }
  if (!installedPack) {
    return {
      label: locale === "de" ? "Verfügbar" : "Available",
      detail:
        locale === "de"
          ? "Für diese Desktop-Build gelistet, aber noch nicht lokal gespeichert."
          : "Listed for this desktop build but not stored locally yet.",
      chipClass: "status-disabled"
    };
  }
  const installedState = describeInstalledPack(installedPack, locale);
  if (
    entry.entry_type === "desktop_pack" &&
    entry.current_version &&
    compareVersions(installedPack.version, entry.current_version) < 0
  ) {
    return {
      label: locale === "de" ? "Update verfügbar" : "Update available",
      detail:
        locale === "de"
          ? `Installierte Version ${installedPack.version} liegt hinter der vertrauenswürdigen Version ${entry.current_version}.`
          : `Installed version ${installedPack.version} is behind trusted version ${entry.current_version}.`,
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

export function packInstallSource(pack: ReceiptPluginPackInfo, locale: DesktopLocale): string {
  return pack.installedVia === "catalog_url"
    ? locale === "de"
      ? "Vertrauenswürdiger Katalog-Download"
      : "Trusted catalog download"
    : locale === "de"
      ? "Manueller Dateiimport"
      : "Manual file import";
}

export function packOriginSummary(pack: ReceiptPluginPackInfo, locale: DesktopLocale): string {
  if (pack.installedVia === "catalog_url") {
    return locale === "de"
      ? "Aus einem vertrauenswürdigen Katalog-Download installiert und lokal auf diesem Computer gespeichert."
      : "Installed from a trusted catalog download and stored locally on this computer.";
  }
  return locale === "de"
    ? "Aus einer lokalen Datei installiert. Desktop hält Support- und Vertrauenskennzeichnungen bewusst konservativ."
    : "Installed from a local file. Desktop keeps support and trust labels conservative.";
}

export function packSupportSummary(
  pack: ReceiptPluginPackInfo,
  catalogEntry: ConnectorCatalogEntry | null,
  locale: DesktopLocale
): string {
  if (catalogEntry?.support_policy) {
    return `${catalogEntry.support_policy.maintainer_support} ${catalogEntry.support_policy.update_expectations}`;
  }
  return trustClassMeaning(pack.trustClass, locale);
}

export function catalogSupportSummary(
  entry: DesktopReleaseMetadata["discovery_catalog"]["entries"][number],
  locale: DesktopLocale
): string {
  if (entry.support_policy) {
    return `${entry.support_policy.maintainer_support} ${entry.support_policy.update_expectations}`;
  }
  return trustClassMeaning(entry.trust_class, locale);
}

export function catalogProfileSummary(
  entry: DesktopReleaseMetadata["discovery_catalog"]["entries"][number],
  releaseMetadata: DesktopReleaseMetadata | null,
  locale: DesktopLocale
): string {
  if (!releaseMetadata) {
    return locale === "de" ? "Editionsmetadaten werden noch geladen." : "Edition metadata is still loading.";
  }
  const selectedProfileId = releaseMetadata.selected_market_profile_id;
  if (entry.market_profile_ids.includes(selectedProfileId)) {
    return locale === "de"
      ? `Für das aktuelle Marktprofil angezeigt (${releaseMetadata.selected_market_profile.display_name}).`
      : `Shown for the current market profile (${releaseMetadata.selected_market_profile.display_name}).`;
  }
  if (entry.official_bundle_ids.length > 0) {
    return locale === "de"
      ? `Von Bundle(s) referenziert: ${entry.official_bundle_ids.join(", ")}.`
      : `Referenced by bundle(s): ${entry.official_bundle_ids.join(", ")}.`;
  }
  return locale === "de"
    ? "Optional für diese Build, aber nicht Teil des Standardprofils."
    : "Optional for this build, but not part of the default profile.";
}

export function formatCatalogVerification(
  catalog: DesktopReleaseMetadata["discovery_catalog"] | null,
  locale: DesktopLocale
): string {
  if (!catalog) {
    return locale === "de" ? "Lädt" : "Loading";
  }
  if (catalog.verification_status === "trusted") {
    return catalog.signed_by_key_id
      ? locale === "de"
        ? `Vertrauenswürdig (${catalog.signed_by_key_id})`
        : `Trusted (${catalog.signed_by_key_id})`
      : locale === "de"
        ? "Vertrauenswürdig"
        : "Trusted";
  }
  if (catalog.verification_status === "revoked") {
    return locale === "de" ? "Widerrufen" : "Revoked";
  }
  if (catalog.verification_status === "signature_invalid") {
    return locale === "de" ? "Signatur ungültig" : "Signature invalid";
  }
  if (catalog.verification_status === "incompatible") {
    return locale === "de" ? "Inkompatibel" : "Incompatible";
  }
  return locale === "de" ? "Nicht verfügbar" : "Unavailable";
}

export function formatCatalogEntryType(
  entryType: DesktopReleaseMetadata["discovery_catalog"]["entries"][number]["entry_type"],
  locale: DesktopLocale
): string {
  if (entryType === "bundle") {
    return locale === "de" ? "Bundle" : "Bundle";
  }
  if (entryType === "desktop_pack") {
    return locale === "de" ? "Belegpaket" : "Receipt pack";
  }
  return locale === "de" ? "Anbindung" : "Connector";
}

export function formatInstallMethods(
  methods: DesktopReleaseMetadata["discovery_catalog"]["entries"][number]["install_methods"],
  locale: DesktopLocale
): string {
  return methods
    .map((method) => {
      if (method === "built_in") {
        return locale === "de" ? "Integriert" : "Built in";
      }
      if (method === "manual_import") {
        return locale === "de" ? "Manueller Import" : "Manual import";
      }
      if (method === "manual_mount") {
        return locale === "de" ? "Manuelles Mounten" : "Manual mount";
      }
      return locale === "de" ? "Vertrauenswürdiger Download" : "Trusted download";
    })
    .join(", ");
}

export function describeControlCenterMode(
  bootError: string | null,
  diagnostics: DesktopRuntimeDiagnostics | null,
  locale: DesktopLocale
): ControlCenterMode {
  if (bootError) {
    return {
      tone: "warning",
      label: locale === "de" ? "Reduzierter Modus" : "Reduced mode",
      title: locale === "de" ? "Die Haupt-App wurde nicht automatisch geöffnet." : "The main app did not open automatically.",
      detail:
        locale === "de"
          ? "Nutzen Sie das Kontrollzentrum für lokale Synchronisierung, Plugin-Pakete, Export- und Backup-Aufgaben, während Sie das Startproblem prüfen."
          : "Use the control center for local sync, plugin packs, export, and backup tasks while you review the startup issue."
    };
  }
  if (diagnostics && !diagnostics.fullAppReady) {
    return {
      tone: "warning",
      label: locale === "de" ? "Nur Kontrollzentrum" : "Control center only",
      title: locale === "de" ? "Dieser Build fehlen die gebündelten Haupt-App-Seiten." : "This build is missing the bundled main app pages.",
      detail:
        locale === "de"
          ? "Desktop kann aus dieser Shell weiterhin gelegentliche lokale Synchronisierung, Prüfung, Export, Backup und manuelle Belegpaket-Aufgaben ausführen."
          : "Desktop can still handle occasional local sync, review, export, backup, and manual receipt pack tasks from this shell."
    };
  }
  return {
    tone: "success",
    label: locale === "de" ? "Voll-App verfügbar" : "Full app available",
    title: locale === "de" ? "Das lokale Kontrollzentrum ist bereit." : "The local control center is ready.",
    detail:
      locale === "de"
        ? "Nutzen Sie es für schnelle lokale Aufgaben oder öffnen Sie die Haupt-App, wenn Sie den vollständigen Browser-Workflow auf diesem Computer möchten."
        : "Use it for quick local tasks, or open the main app when you want the full in-browser workflow on this computer."
  };
}

export function describeBackendCommand(
  diagnostics: DesktopRuntimeDiagnostics | null,
  locale: DesktopLocale
): string {
  if (!diagnostics) {
    return locale === "de" ? "Lokale Laufzeitdetails werden geladen." : "Loading local runtime details.";
  }
  if (diagnostics.backendCommandSource === "bundled") {
    return locale === "de" ? "Mit dieser Desktop-Build gebündelt." : "Bundled with this desktop build.";
  }
  if (diagnostics.backendCommandSource === "managed_dev") {
    return locale === "de"
      ? "Die von Desktop verwaltete Entwicklungs-Laufzeit wird verwendet."
      : "Using the desktop-managed development runtime.";
  }
  if (diagnostics.backendCommandSource === "env_override") {
    return diagnostics.backendCommandStatus === "missing"
      ? locale === "de"
        ? "Ein benutzerdefinierter Laufzeitpfad ist konfiguriert, aber die Datei fehlt."
        : "A custom runtime path is configured, but the file is missing."
      : locale === "de"
        ? "Eine über LIDLTOOL_EXECUTABLE konfigurierte benutzerdefinierte Laufzeit wird verwendet."
        : "Using a custom runtime configured through LIDLTOOL_EXECUTABLE.";
  }
  return locale === "de"
    ? "Desktop sucht die lokale Laufzeit in Ihrem System-PATH."
    : "Desktop will look for the local runtime in your system PATH.";
}

export function formatEditionKind(
  kind: DesktopReleaseMetadata["active_release_variant"]["edition_kind"],
  locale: DesktopLocale
): string {
  return kind === "regional_edition"
    ? locale === "de"
      ? "Regionale Edition"
      : "Regional edition"
    : locale === "de"
      ? "Universelle Desktop-Shell"
      : "Universal desktop shell";
}
