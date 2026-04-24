from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a Netto Plus session bundle before importing it into the desktop plugin."
    )
    parser.add_argument("bundle_path", help="Absolute or relative path to netto-session-bundle.json")
    parser.add_argument(
        "--store-name",
        default="Netto Plus",
        help="Optional store-name prefix used for the dry-run normalized records.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the validation report as JSON instead of a short text summary.",
    )
    return parser


def _print_human_report(report: dict[str, object]) -> None:
    print(f"Bundle OK: {report['bundle_path']}")
    print(f"Schema version: {report['schema_version']}")
    print(f"Account email: {report.get('account_email') or '-'}")
    print(f"Receipt count: {report['receipt_count']}")
    receipts = report.get("receipts")
    if not isinstance(receipts, list):
        return
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        print(
            " - "
            f"{receipt.get('record_ref')} | "
            f"{receipt.get('store_name')} | "
            f"total={receipt.get('total_gross_cents')} | "
            f"discounts={receipt.get('discount_total_cents')} | "
            f"items={receipt.get('item_count')} | "
            f"pdf_payload={receipt.get('has_pdf_payload')}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        from plugin import NettoPlusPluginError, validate_session_bundle_file
    except ModuleNotFoundError as exc:
        missing_name = getattr(exc, "name", None) or "required dependency"
        print(
            "Bundle validation could not start because a plugin dependency is missing "
            f"({missing_name}). Run this from the project environment, for example:\n"
            "uv run python plugins/netto_plus_de/validate_session_bundle.py /path/to/netto-session-bundle.json",
            file=sys.stderr,
        )
        return 1

    try:
        report = validate_session_bundle_file(
            Path(args.bundle_path),
            store_name=args.store_name,
        )
    except (NettoPlusPluginError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "bundle_path": str(Path(args.bundle_path).expanduser()),
                        "error": str(exc),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
        else:
            print(f"Bundle validation failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
