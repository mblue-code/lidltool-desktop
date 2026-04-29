import { mkdtempSync, mkdirSync, rmSync, statSync, existsSync } from "node:fs";
import os from "node:os";
import { dirname, resolve, join } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const buildDir = resolve(desktopDir, "build");
const sourceSvg = resolve(desktopDir, "src", "renderer", "assets", "logo-mark.svg");

const pngOut = resolve(buildDir, "icon.png");
const icoOut = resolve(buildDir, "icon.ico");
const icnsOut = resolve(buildDir, "icon.icns");

mkdirSync(buildDir, { recursive: true });

if (process.platform !== "darwin") {
  const requiredIcons = [pngOut, icoOut, icnsOut];
  const missingIcons = requiredIcons.filter((iconPath) => !existsSync(iconPath));
  if (missingIcons.length > 0) {
    throw new Error(
      `Desktop icon artifacts are missing (${missingIcons.map((iconPath) => iconPath.replace(`${desktopDir}/`, "")).join(", ")}). ` +
        "Generate and commit them on macOS before packaging on this platform."
    );
  }
  console.log("Using committed desktop icon assets.");
  process.exit(0);
}

const iconSizes = [16, 32, 128, 256, 512];
const iconsetDir = `${mkdtempSync(join(os.tmpdir(), "outlays-desktop-iconset-"))}.iconset`;

mkdirSync(iconsetDir, { recursive: true });

function run(command, args) {
  execFileSync(command, args, { stdio: "inherit" });
}

function findPythonWithPillow() {
  const candidates = [
    process.env.PYTHON,
    "python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/opt/homebrew/opt/python@3.14/bin/python3.14",
    "/usr/bin/python3",
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      execFileSync(candidate, ["-c", "import PIL"], { stdio: "ignore" });
      return candidate;
    } catch {
      // Try the next interpreter until one can write .ico output via Pillow.
    }
  }

  throw new Error("Could not find a Python interpreter with Pillow installed to generate build/icon.ico.");
}

try {
  // Build the default icon builder PNG at a stable, high-resolution size.
  run("sips", ["-s", "format", "png", "-z", "1024", "1024", sourceSvg, "--out", pngOut]);

  for (const size of iconSizes) {
    const basePng = join(iconsetDir, `icon_${size}x${size}.png`);
    const retinaPng = join(iconsetDir, `icon_${size}x${size}@2x.png`);

    run("sips", ["-s", "format", "png", "-z", String(size), String(size), sourceSvg, "--out", basePng]);
    run("sips", ["-s", "format", "png", "-z", String(size * 2), String(size * 2), sourceSvg, "--out", retinaPng]);
  }

  run("iconutil", ["-c", "icns", iconsetDir, "-o", icnsOut]);
  if (!existsSync(icnsOut)) {
    throw new Error("iconutil did not produce build/icon.icns.");
  }

  run(findPythonWithPillow(), [
    "-c",
    [
      "from PIL import Image",
      `src = Image.open(${JSON.stringify(pngOut)}).convert('RGBA')`,
      "sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]",
      `src.save(${JSON.stringify(icoOut)}, format='ICO', sizes=sizes)`,
    ].join("; "),
  ]);

  const svgMtime = statSync(sourceSvg).mtimeMs;
  const generatedIcons = [pngOut, icoOut, icnsOut];
  const staleIcons = generatedIcons.filter((iconPath) => statSync(iconPath).mtimeMs < svgMtime);
  if (staleIcons.length > 0) {
    throw new Error(`Generated icons are stale: ${staleIcons.join(", ")}`);
  }

  console.log("Generated desktop app icons.");
} finally {
  rmSync(iconsetDir, { recursive: true, force: true });
}
