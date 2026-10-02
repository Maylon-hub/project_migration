import json
from pathlib import Path

import jsonschema

from studybr.importers import build_diagnostic, serialize_dataset
from tests.fixtures.factories import source_pair

ROOT = Path(__file__).resolve().parents[2]


def test_diagnostic_matches_versioned_schema(tmp_path):
    dataset = build_diagnostic(
        *source_pair(tmp_path),
        base_url="https://example.test/site",
        domain_path=ROOT / "config/domain.json",
    )
    contract = json.loads((ROOT / "schemas/diagnostic.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(contract)
    jsonschema.validate(json.loads(serialize_dataset(dataset)), contract)


def test_fixture_contains_only_minimal_historical_content():
    path = ROOT / "tests/fixtures/historical_ufscar.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["language"] == "pt-br"
    assert data["@type"] == "Document"
    assert data["review_state"] == "private"
    assert set(data["blocks"]) == set(data["blocks_layout"]["items"])
    assert {p["id"] for p in data["subpages"]} == {
        "sobre-nos",
        "vida_na_ies",
        "estudantes-internacionais",
    }
    for key in ["Authorization", "Bearer", "window.__data", "cookies", "token"]:
        assert key not in path.read_text(encoding="utf-8")
