"""Deny networking before pytest imports/collection, not just inside test fixtures."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


def deny_network(*args, **kwargs):
    raise RuntimeError("Networking disabled by offline test runner")


def main() -> int:
    # Validation must not inherit real session credentials, even during collection.
    for key in list(os.environ):
        if any(word in key.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "API_USERNAME")):
            os.environ.pop(key, None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    import pytest

    arguments = sys.argv[1:]
    if "--legacy-baseline" not in arguments:
        return pytest.main(arguments)
    expected = {
        "legacy/tests/test_api_client.py::TestPloneRestClient::" + name
        for name in (
            "test_login_success",
            "test_resolve_url",
            "test_create_content_success",
            "test_update_content_success",
            "test_publish_content_success",
        )
    }

    class Baseline:
        def __init__(self):
            self.passed = set()
            self.failed = set()
            self.errors = []

        def pytest_runtest_logreport(self, report):
            if report.when == "call":
                if report.passed:
                    self.passed.add(report.nodeid)
                elif report.failed:
                    self.failed.add(report.nodeid)
            elif report.failed:
                self.errors.append(report.nodeid)

    baseline = Baseline()
    status = pytest.main(
        ["legacy/tests", "-p", "no:cacheprovider", "-q", "--tb=no"], plugins=[baseline]
    )
    valid = (
        status == 1
        and len(baseline.passed) == 8
        and baseline.failed == expected
        and not baseline.errors
    )
    print(
        json.dumps(
            {
                "legacy_baseline_matches": valid,
                "passed": len(baseline.passed),
                "known_failures": len(baseline.failed & expected),
            }
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
