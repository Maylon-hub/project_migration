"""Offline secret guard. Emit paths/counts only; never secret values or matching lines."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = (
    re.compile(rb"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(rb"(?i)(?:plone_token|api_token|api_password)\s*[:=]\s*[\"'][^\"'\r\n]{20,}[\"']"),
)

# Exact documented placeholders are not credentials. No arbitrary file/line exclusion.
PLACEHOLDERS = {b'API_TOKEN = "Bearer SEU_TOKEN_AQUI"'}


def scan(root: Path, baseline: dict, files: list[str]) -> tuple[list[str], list[str]]:
    failures, preserved = [], []
    for name in sorted(set(files)):
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        entry = baseline.get("files", {}).get(name)
        if entry:
            # Entire-file fingerprint: any change to an excepted capture blocks the scan.
            if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                failures.append(name)
            else:
                preserved.append(name)
        elif any(
            match.group() not in PLACEHOLDERS
            for pattern in PATTERNS
            for match in pattern.finditer(data)
        ):
            failures.append(name)
    return failures, preserved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=Path(".secrets-baseline.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    baseline_path = args.baseline if args.baseline.is_absolute() else root / args.baseline
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    )
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    files = [name.decode() for name in result.stdout.split(b"\0") if name]
    failures, preserved = scan(root, baseline, files)
    # Paths themselves might contain credentials: counts only at the output boundary.
    print(
        json.dumps(
            {
                "new_or_changed_sensitive_files": len(failures),
                "unchanged_historical_exceptions": len(preserved),
            },
            sort_keys=True,
        )
    )
    if failures:
        print(
            "Secret guard failed; inspect affected files locally without printing values.",
            file=sys.stderr,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
