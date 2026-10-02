import importlib.util
from pathlib import Path


def guard():
    path = Path(__file__).resolve().parents[2] / "scripts/check_secrets.py"
    spec = importlib.util.spec_from_file_location("secret_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_secret_is_rejected_without_reporting_value(tmp_path):
    # Compose a synthetic signature rather than versioning an actual credential.
    secret = ".".join(["eyJ" + "a" * 25, "b" * 25, "c" * 25])
    (tmp_path / "new.txt").write_text(secret)
    failures, preserved = guard().scan(tmp_path, {}, ["new.txt"])
    assert failures == ["new.txt"]
    assert preserved == []
    assert secret not in str(failures)


def test_fingerprint_exception_rejects_changes(tmp_path):
    import hashlib

    path = tmp_path / "historical.txt"
    path.write_text("original")
    baseline = {"files": {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}
    assert guard().scan(tmp_path, baseline, [path.name]) == ([], [path.name])
    path.write_text("changed")
    assert guard().scan(tmp_path, baseline, [path.name]) == ([path.name], [])
