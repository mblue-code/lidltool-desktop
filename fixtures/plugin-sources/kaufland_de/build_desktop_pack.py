from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
PAYLOAD_FILES = (
    ROOT / "plugin.py",
    ROOT / "README.md",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_pack(output_dir: Path) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    packaged_manifest = dict(manifest)
    packaged_manifest["entrypoint"] = "payload/plugin.py:KauflandReceiptPlugin"
    plugin_id = str(packaged_manifest["plugin_id"])
    plugin_version = str(packaged_manifest["plugin_version"])

    output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = output_dir / f"{plugin_id}-{plugin_version}-electron.zip"

    files: dict[str, bytes] = {
        "manifest.json": json.dumps(packaged_manifest, indent=2).encode("utf-8"),
    }
    for source_path in PAYLOAD_FILES:
        archive_path = Path("payload") / source_path.relative_to(ROOT)
        files[str(archive_path)] = source_path.read_bytes()

    metadata = {
        "pack_version": "1",
        "plugin_id": plugin_id,
        "plugin_version": plugin_version,
        "plugin_family": "receipt",
        "manifest_path": "manifest.json",
        "runtime_root": "payload",
    }
    files["plugin-pack.json"] = json.dumps(metadata, indent=2).encode("utf-8")

    integrity = {
        "algorithm": "sha256",
        "files": {name: _sha256_bytes(content) for name, content in files.items()},
    }
    files["integrity.json"] = json.dumps(integrity, indent=2).encode("utf-8")

    with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as archive:
        for archive_path, contents in files.items():
            archive.writestr(archive_path, contents)
    return pack_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a desktop receipt-pack ZIP for the Kaufland plugin.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="Directory where the ZIP archive should be written.",
    )
    args = parser.parse_args()
    pack_path = build_pack(args.output_dir.resolve())
    print(pack_path)


if __name__ == "__main__":
    main()
