"""Compile a local semantic overlay with networking denied; no authenticated inventory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import socket
from collections import Counter
from pathlib import Path

from studybr.importers.workbooks import CREATION_TABLES, PRODUCTION_TABLES, read_workbook
from studybr.reconciliation import reconcile_local
from studybr.security import Redactor, configure_logging


def deny_network(*args, **kwargs):
    raise RuntimeError("Networking disabled for local reconciliation")


def main() -> int:
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    redactor = Redactor.from_environment()
    configure_logging(redactor)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--creation", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--domain-config", type=Path, default=Path("config/domain.json"))
    parser.add_argument("--decisions", type=Path, default=Path("config/editorial-decisions.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        original = args.dataset.read_bytes()
        dataset = json.loads(original)
        manifest = {source["source_id"]: source["sha256"] for source in dataset["sources"]}
        rows = []
        for path, source_id, specs in (
            (args.creation, "creation", CREATION_TABLES),
            (args.production, "production", PRODUCTION_TABLES),
        ):
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get(source_id):
                raise ValueError("Source hash differs from the diagnostic manifest")
            source_rows, _, _ = read_workbook(path, source_id, specs)
            rows.extend(source_rows)
        if hashlib.sha256(args.domain_config.read_bytes()).hexdigest() != manifest.get(
            "domain_config"
        ):
            raise ValueError("Domain configuration differs from the diagnostic manifest")
        domain = json.loads(args.domain_config.read_text(encoding="utf-8"))
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        result = reconcile_local(dataset, rows, domain, decisions)
        result["input_dataset_sha256"] = hashlib.sha256(original).hexdigest()
        result["decision_registry_sha256"] = hashlib.sha256(args.decisions.read_bytes()).hexdigest()
        summary = {
            "scope": "local_evidence_only",
            "remote_verification": "not_performed",
            "diagnostic_only": True,
            "ready_for_write": False,
            "original_conflicts_preserved": result["original_conflicts_preserved"],
            "semantic_groups": len(result["semantic_conflicts"]),
            "classes": result["semantic_summary_by_class"],
            "evidence_by_class": dict(
                sorted(
                    Counter(
                        g["classification"]
                        for g in result["semantic_conflicts"]
                        for _ in g["evidence_ids"]
                    ).items()
                )
            ),
            "approved_name_resolutions": len(result["local_resolutions"]),
            "approved_name_conflicts": len(result["approved_name_conflicts"]),
            "input_dataset_sha256": result["input_dataset_sha256"],
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, payload in (
            ("conflicts-semantic.json", result),
            ("reconciliation-local-summary.json", summary),
        ):
            (args.output_dir / filename).write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        columns = [
            "institution",
            "language",
            "semantic_page",
            "field",
            "asset_id",
            "classification",
            "status",
            "scope",
            "stop_affected_page_or_institution",
            "evidence_count",
            "semantic_conflict_id",
        ]
        with (args.output_dir / "conflicts-human-review.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as output:
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for group in result["semantic_conflicts"]:
                if group["classification"] in {"C", "D"}:
                    writer.writerow(group)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 2  # This local overlay never fulfills or certifies the remote contract.
    except Exception as error:
        print(redactor.text(f"Local reconciliation failed: {type(error).__name__}: {error}"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
