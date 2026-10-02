"""Offline diagnosis and explicit bounded GET inventory share one installed package."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from studybr.importers import build_diagnostic, serialize_dataset
from studybr.security import Redactor, configure_logging


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "inventory":
        from studybr.inventory.cli import main as inventory_main

        return inventory_main(arguments[1:])
    redactor = Redactor.from_environment()
    configure_logging(redactor)
    parser = argparse.ArgumentParser(prog="studybr")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "inventory", help="Bounded local GET-only inventory; explicit environment required"
    )
    diagnostic = sub.add_parser("diagnose", help="Compile local XLSX/CSV evidence; no networking")
    diagnostic.add_argument("--creation", type=Path, required=True)
    diagnostic.add_argument("--production", type=Path, required=True)
    diagnostic.add_argument(
        "--base-url", required=True, help="Nonsecret URL used only to normalize paths"
    )
    diagnostic.add_argument("--domain-config", type=Path, default=Path("config/domain.json"))
    diagnostic.add_argument("--home-csv", type=Path)
    diagnostic.add_argument("--subpage-csv", type=Path)
    diagnostic.add_argument("--media-csv", type=Path)
    diagnostic.add_argument("--diagram-json", type=Path)
    diagnostic.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        csv_sources = {
            role: path
            for role, path in [
                ("home", args.home_csv),
                ("subpage", args.subpage_csv),
                ("media", args.media_csv),
            ]
            if path is not None
        }
        dataset = build_diagnostic(
            args.creation,
            args.production,
            base_url=args.base_url,
            domain_path=args.domain_config,
            csv_sources=csv_sources,
            diagram_json=args.diagram_json,
        )
        serialized = serialize_dataset(dataset, redactor)
        summary = {
            "diagnostic_only": True,
            "ready_for_write": False,
            "institutions": len(dataset.institutions),
            "localized_pages": sum(
                len(loc.pages) for inst in dataset.institutions for loc in inst.localizations
            ),
            "media_assets": len(dataset.media_assets),
            "unassigned_editorial_rows": len(dataset.unassigned_editorial_rows),
            "conflicts": len(dataset.conflicts),
            "conflicts_by_category": dict(
                sorted(Counter(c.category for c in dataset.conflicts).items())
            ),
            "dataset_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "dataset.json").write_text(serialized, encoding="utf-8")
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        # Unresolved evidence is not import success: code 2 signals diagnostic conflicts.
        return 2 if dataset.conflicts else 0
    except Exception as error:
        print(redactor.text(f"Diagnostic failed: {type(error).__name__}: {error}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
