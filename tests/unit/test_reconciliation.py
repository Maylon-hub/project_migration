import copy
import json
from pathlib import Path

import pytest

from studybr.importers import build_diagnostic
from studybr.importers.workbooks import CREATION_TABLES, PRODUCTION_TABLES, read_workbook
from studybr.reconciliation import approved_names, canonical, reconcile_local
from tests.fixtures.factories import source_pair

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = json.loads((ROOT / "config/domain.json").read_text(encoding="utf-8"))
DECISIONS = json.loads((ROOT / "config/editorial-decisions.json").read_text(encoding="utf-8"))


def evidence(tmp_path):
    pair = source_pair(tmp_path)
    dataset = build_diagnostic(
        *pair,
        base_url="https://example.test/site",
        domain_path=ROOT / "config/domain.json",
    ).to_dict()
    # Use the same serialized data shape as the immutable diagnostic artifact.
    dataset = json.loads(canonical(dataset))
    creation, _, _ = read_workbook(pair[0], "creation", CREATION_TABLES)
    production, _, _ = read_workbook(pair[1], "production", PRODUCTION_TABLES)
    return dataset, creation + production


def test_overlay_preserves_original_and_accounts_for_every_evidence(tmp_path):
    dataset, rows = evidence(tmp_path)
    original = copy.deepcopy(dataset)
    result = reconcile_local(dataset, rows, DOMAIN, DECISIONS)
    assert dataset == original
    assert result["original_conflicts_preserved"] == len(dataset["conflicts"])
    ids = [number for group in result["semantic_conflicts"] for number in group["evidence_ids"]]
    assert sorted(ids) == list(range(len(dataset["conflicts"])))
    assert result["diagnostic_only"] is True
    assert result["ready_for_write"] is False
    assert result["remote_verification"] == "not_performed"
    assert canonical(result) == canonical(reconcile_local(dataset, rows, DOMAIN, DECISIONS))


def test_relations_resolved_as_home_component_only(tmp_path):
    dataset, rows = evidence(tmp_path)
    result = reconcile_local(dataset, rows, DOMAIN, DECISIONS)
    relations = [g for g in result["semantic_conflicts"] if "editorial" in g["categories"]]
    assert relations
    assert all(g["semantic_page"] == "home" for g in relations)
    assert all(g["field"] == "international_relations.semantic_id" for g in relations)
    assert all(g["classification"] == "B" for g in relations)
    for institution in dataset["institutions"]:
        for localization in institution["localizations"]:
            students = next(
                p for p in localization["pages"] if p["semantic_id"] == "international_students"
            )
            assert students["editorial_policy"]["phase"] is None


def test_approved_names_require_literal_unique_approved_source(tmp_path):
    dataset, _ = evidence(tmp_path)
    resolutions, pending = approved_names(dataset, DECISIONS)
    assert len(resolutions) == 2 and not pending
    en = next(loc for loc in dataset["institutions"][0]["localizations"] if loc["language"] == "en")
    approved = next(
        obs
        for obs in en["candidates"]["translated_name"]
        if obs["provenance"]["source_id"] == "production"
    )
    duplicate = copy.deepcopy(approved)
    duplicate["value"] = "Divergent approved name"
    en["candidates"]["translated_name"].append(duplicate)
    resolutions, pending = approved_names(dataset, DECISIONS)
    assert len(resolutions) == 1
    assert pending[0]["classification"] == "C"
    approved["provenance"]["cache_state"] = "unverified"
    _, pending = approved_names(dataset, DECISIONS)
    assert pending[0]["classification"] == "D"


def test_approved_missing_name_stays_human_conflict(tmp_path):
    dataset, _ = evidence(tmp_path)
    en = next(loc for loc in dataset["institutions"][0]["localizations"] if loc["language"] == "en")
    en["candidates"]["translated_name"] = [
        obs
        for obs in en["candidates"]["translated_name"]
        if obs["provenance"]["source_id"] != "production"
    ]
    _, pending = approved_names(dataset, DECISIONS)
    assert pending[0]["classification"] == "C"


def test_slug_never_resolved_and_source_values_not_dumped(tmp_path):
    dataset, rows = evidence(tmp_path)
    dataset["conflicts"].append(
        {
            "category": "slugs",
            "entity": "UFSCAR:en:about",
            "field": "slug",
            "message": "Divergence",
            "candidates": [],
        }
    )
    result = reconcile_local(dataset, rows, DOMAIN, DECISIONS)
    slug = next(
        g
        for g in result["semantic_conflicts"]
        if g["semantic_page"] == "about" and g["field"] == "slug"
    )
    assert slug["classification"] == "C"
    assert slug["stop_affected_page_or_institution"] is True
    assert "formula" not in canonical(result["semantic_conflicts"])
    assert "source_values" not in canonical(result)
    assert DECISIONS["decisions"]["legacy_protected_institutions"]["apply_to_new_flow"] is False


def test_write_ready_input_is_refused(tmp_path):
    dataset, rows = evidence(tmp_path)
    dataset["diagnostic_only"] = False
    with pytest.raises(ValueError):
        reconcile_local(dataset, rows, DOMAIN, DECISIONS)


def test_semantic_key_merges_causes_and_is_stable_when_severity_changes(tmp_path):
    dataset, rows = evidence(tmp_path)
    slug = {
        "category": "slugs",
        "entity": "UFSCAR:en:about",
        "field": "slug",
        "message": "Human slug decision",
        "candidates": [],
    }
    dataset["conflicts"].append(slug)
    first = reconcile_local(dataset, rows, DOMAIN, DECISIONS)
    before = next(
        g
        for g in first["semantic_conflicts"]
        if g["semantic_page"] == "about" and g["field"] == "slug"
    )
    dataset["conflicts"].append({**slug, "category": "formula_cache"})
    second = reconcile_local(dataset, rows, DOMAIN, DECISIONS)
    matches = [
        g
        for g in second["semantic_conflicts"]
        if g["semantic_page"] == "about" and g["field"] == "slug"
    ]
    assert len(matches) == 1
    assert matches[0]["classification"] == "D"
    assert {cause["classification"] for cause in matches[0]["causes"]} == {"C", "D"}
    assert matches[0]["semantic_conflict_id"] == before["semantic_conflict_id"]


def test_unknown_source_identity_is_not_guessed(tmp_path):
    dataset, rows = evidence(tmp_path)
    dataset["conflicts"].append(
        {
            "category": "metadata",
            "entity": "unknown-source-row",
            "field": "title",
            "message": "No identity binding",
            "candidates": [],
        }
    )
    result = reconcile_local(dataset, rows, DOMAIN, DECISIONS)
    unknown = next(g for g in result["semantic_conflicts"] if g["institution"] is None)
    assert unknown["classification"] == "D"
    assert unknown["semantic_page"] is None
