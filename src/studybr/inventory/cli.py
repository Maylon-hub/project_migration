"""Inventory entry point; never imports the operational legacy configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from studybr.api.client import ReadOnlyClient
from studybr.api.errors import InventoryError, PloneError
from studybr.reconciliation import legacy_expectations, read_approved_overlay
from studybr.settings import ConfigurationError, Settings

from .runner import STAGES, InventoryRunner
from .snapshots import SnapshotStore


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="studybr inventory", description="Bounded Plone GET-only inventory."
    )
    parser.add_argument("--stage", choices=STAGES, default="roots")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--max-requests", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-children", type=int, default=30)
    parser.add_argument("--expectations", type=Path)
    parser.add_argument("--approved-resolutions", type=Path)
    parser.add_argument("--approved-workbook", type=Path)
    parser.add_argument("--home-csv", type=Path, default=Path("studyinbr/lista_ies_completa.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path(".local/inventory"))
    parser.add_argument(
        "--resume", help="Explicitly resume a local run; protected roots are requested again."
    )
    args = parser.parse_args(argv)
    client = None
    try:
        settings = Settings.from_env(
            rest_path="", timeout=(args.timeout, args.timeout), max_requests=args.max_requests
        )
        if args.max_pages <= 0 or args.max_children <= 0:
            raise InventoryError("configuration", "Pagination and child limits must be positive.")
        project = Path(__file__).resolve().parents[3]
        output = args.output_dir.resolve()
        if output.is_relative_to(project) and not output.is_relative_to(project / ".local"):
            raise InventoryError(
                "unsafe_output", "Inside this checkout, snapshots must remain under .local/."
            )
        expectations = (
            json.loads(args.expectations.read_text(encoding="utf-8-sig"))
            if args.expectations
            else {}
        )
        if not isinstance(expectations, dict):
            raise InventoryError("configuration", "Expectations must be an object indexed by path.")
        if args.approved_workbook and not args.approved_resolutions:
            raise InventoryError(
                "configuration", "--approved-workbook requires --approved-resolutions."
            )
        names = (
            read_approved_overlay(args.approved_resolutions, args.approved_workbook)
            if args.approved_resolutions
            else {}
        )
        legacy = legacy_expectations(args.home_csv) if args.home_csv.exists() else {}
        run_id = args.resume or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        )
        store = SnapshotStore(args.output_dir, run_id)
        client = ReadOnlyClient(settings)
        runner = InventoryRunner(
            client, store, args.max_pages, args.max_children, expectations, legacy, names
        )
        runner.report["source_hashes"] = {
            label: hashlib.sha256(path.read_bytes()).hexdigest()
            for label, path in (
                ("legacy_csv", args.home_csv),
                ("approved_resolutions", args.approved_resolutions),
                ("approved_workbook", args.approved_workbook),
                ("expectations", args.expectations),
            )
            if path is not None and path.exists()
        }
        runner.report["approved_workbook_verified"] = bool(args.approved_workbook)
        if args.resume:
            runner.resume()
        report = runner.execute(args.stage)
        output = {
            "stage": args.stage,
            "complete": report["complete"],
            "requests_made": report["requests_made"],
            "conflicts": len(report["conflicts"]),
            "pending": len(report["pending"]),
            "ready_for_write": False,
            "sanitized_dir": str(store.sanitized),
        }
        if report.get("error"):
            output["error"] = report["error"]
        print(json.dumps(client.redact(output), ensure_ascii=False))
        return (
            1
            if report.get("error")
            else (
                0 if report["complete"] and not report["conflicts"] and not report["pending"] else 2
            )
        )
    except ConfigurationError:
        print(
            json.dumps(
                {
                    "type": "configuration",
                    "message": "Invalid or missing PLONE_BASE_URL/PLONE_TOKEN or limits.",
                }
            )
        )
        return 1
    except PloneError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        return 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print(
            json.dumps(
                {
                    "type": "local_input_error",
                    "message": "Local source absent or invalid; private details omitted.",
                }
            )
        )
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
