import { mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync, existsSync } from "node:fs";
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

function writeIcoFromPngs(outputPath, entries) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entries.length, 4);

  const directory = Buffer.alloc(entries.length * 16);
  let offset = header.length + directory.length;

  entries.forEach((entry, index) => {
    const png = readFileSync(entry.path);
    const widthByte = entry.size >= 256 ? 0 : entry.size;
    const heightByte = entry.size >= 256 ? 0 : entry.size;
    const directoryOffset = index * 16;

    directory.writeUInt8(widthByte, directoryOffset);
    directory.writeUInt8(heightByte, directoryOffset + 1);
    directory.writeUInt8(0, directoryOffset + 2);
    directory.writeUInt8(0, directoryOffset + 3);
    directory.writeUInt16LE(1, directoryOffset + 4);
    directory.writeUInt16LE(32, directoryOffset + 6);
    directory.writeUInt32LE(png.length, directoryOffset + 8);
    directory.writeUInt32LE(offset, directoryOffset + 12);

    entry.png = png;
    offset += png.length;
  });

  writeFileSync(outputPath, Buffer.concat([header, directory, ...entries.map((entry) => entry.png)]));
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

  const icoSizes = [16, 24, 32, 48, 64, 128, 256];
  const icoEntries = icoSizes.map((size) => {
    const pngPath = join(iconsetDir, `ico_${size}.png`);
    run("sips", ["-s", "format", "png", "-z", String(size), String(size), sourceSvg, "--out", pngPath]);
    return { size, path: pngPath, png: null };
  });
  writeIcoFromPngs(icoOut, icoEntries);

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
