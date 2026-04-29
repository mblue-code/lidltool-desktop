const SECRET_PATTERNS = [
  /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/,
  /\b(?:ghp|github_pat|glpat|sk-[A-Za-z0-9]|xox[baprs])_[A-Za-z0-9_=-]{16,}/,
  /\b(?:password|passwd|secret|token|dsn|auth_token|api_key)\s*[:=]\s*['"]?[A-Za-z0-9_./:+=-]{12,}/i
];

const RUNTIME_BUILD_FILE_PATTERN =
  /^(?:package\.json|electron\.vite\.config\.ts|electron-builder\..*|src\/main\/.*|src\/preload\/.*|scripts\/.*)$/;

export function findStagedEnvFiles(paths) {
  return paths.filter((path) => /(^|\/)\.env(?:\.|$)/.test(path));
}

export function findDiagnosticsArchives(paths) {
  return paths.filter((path) => /diagnostics.*\.zip$/i.test(path) || /\.diagnostics\.zip$/i.test(path));
}

export function findPrivateKeyMaterial(files) {
  return files.filter((file) => SECRET_PATTERNS.some((pattern) => pattern.test(file.content)));
}

export function findRuntimeBoundaryReferences(files) {
  return files.filter(
    (file) =>
      RUNTIME_BUILD_FILE_PATTERN.test(file.path) &&
      /(?:['"`]\.\.\/\.\.\/|path\.join\([^)]*["']\.\.["'][^)]*["']\.\.["'])/.test(file.content)
  );
}

export function validateReleaseChannelVersion(channel, version) {
  const normalizedChannel = String(channel ?? "").trim().toLowerCase();
  const normalizedVersion = String(version ?? "").trim();
  if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(normalizedVersion)) {
    return {
      ok: false,
      reason: "Package version must be valid semver."
    };
  }
  if (normalizedChannel === "beta") {
    return normalizedVersion.includes("-beta.")
      ? { ok: true, reason: null }
      : { ok: false, reason: "Beta releases must use a -beta.N version suffix." };
  }
  if (normalizedChannel === "stable") {
    return normalizedVersion.includes("-")
      ? { ok: false, reason: "Stable releases must not use a prerelease version suffix." }
      : { ok: true, reason: null };
  }
  return {
    ok: false,
    reason: "LIDLTOOL_DESKTOP_RELEASE_CHANNEL must be beta or stable."
  };
}

export function summarizePreflightFindings({ stagedPaths, stagedFiles, channel, version }) {
  const findings = [];
  const envFiles = findStagedEnvFiles(stagedPaths);
  const diagnosticsArchives = findDiagnosticsArchives(stagedPaths);
  const privateKeyMaterial = findPrivateKeyMaterial(stagedFiles);
  const boundaryReferences = findRuntimeBoundaryReferences(stagedFiles);
  const versionValidation = validateReleaseChannelVersion(channel, version);

  if (envFiles.length > 0) {
    findings.push(`Staged .env files are not allowed: ${envFiles.join(", ")}`);
  }
  if (diagnosticsArchives.length > 0) {
    findings.push(`Diagnostics archives must not be committed: ${diagnosticsArchives.join(", ")}`);
  }
  if (privateKeyMaterial.length > 0) {
    findings.push(`Possible secret or private key material found in: ${privateKeyMaterial.map((file) => file.path).join(", ")}`);
  }
  if (boundaryReferences.length > 0) {
    findings.push(`Runtime/build files reference ../../ paths: ${boundaryReferences.map((file) => file.path).join(", ")}`);
  }
  if (!versionValidation.ok) {
    findings.push(versionValidation.reason);
  }

  return findings;
}
