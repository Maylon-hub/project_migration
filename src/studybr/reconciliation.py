"""Semantic local evidence overlay; never modify sources or imply remote verification."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from studybr.api.errors import InventoryError
from studybr.importers.diagnostic import read_csv_source
from studybr.importers.workbooks import SourceRow
from studybr.models import normalize_acronym
from studybr.security import Redactor

CLASSES = {
    "A": "informative",
    "B": "approved_rule",
    "C": "human_decision",
    "D": "technical_blocker",
}
FIELD_ALIASES = {
    "Título": "title",
    "Título2": "title",
    "nome_curto": "slug",
    "home_slug": "slug",
    "Onde criar": "container_path",
    "TAGs": "subjects",
    "Descrição": "description",
    "Universidade": "official_name",
    "Oficial": "official_name",
    "Nome Inglês": "translated_name",
    "Nome Espanhol": "translated_name",
    "Inglês": "translated_name",
    "Espanhol": "translated_name",
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def row_key(provenance: dict) -> tuple:
    return tuple(provenance.get(k) for k in ("source_id", "sheet", "table", "row"))


def source_reference(observation: dict) -> dict:
    # No formulas, source values, staff names or free-text authenticated data.
    provenance = observation.get("provenance", {})
    return {
        k: provenance.get(k)
        for k in ("source_id", "sha256", "sheet", "table", "row", "cell", "field", "cache_state")
    }


def language_for_column(column: str, domain: dict) -> str | None:
    for language, fields in domain["language_fields"].items():
        if column in {
            fields.get("creation_name"),
            fields.get("production_name"),
            fields.get("phase"),
            fields.get("execution"),
            fields.get("translation"),
        }:
            return language
        if column.endswith(" " + fields["media_suffix"]):
            return language
    return None


def semantic_field(column: str, domain: dict) -> str:
    for fields in domain["language_fields"].values():
        suffix = " " + fields["media_suffix"]
        if column.endswith(suffix):
            label = column[: -len(suffix)]
            return {
                "Título": "title",
                "Descrição": "description",
                "Legenda": "caption",
                "Texto alt": "alt_text",
            }.get(label, column)
    return FIELD_ALIASES.get(column, column)


def row_context(row: SourceRow, column: str, domain: dict, decisions: dict) -> tuple | None:
    identity = row.value("Siglas") or row.value("IES") or row.value("Sigla")
    if not isinstance(identity, str) or identity.startswith("_Modelo"):
        return None
    institution = normalize_acronym(identity)
    language = row.spec.language or language_for_column(column, domain)
    page = None
    field = semantic_field(column, domain)
    asset = None
    if row.spec.role == "home":
        page = "home"
    elif row.spec.role == "subpage":
        page = domain["page_aliases"].get(row.value("tipo3") or row.value("Tipo3"))
    elif row.spec.role == "editorial":
        if language:
            for policy_field in ("phase", "execution", "translation"):
                if column == domain["language_fields"][language].get(policy_field):
                    field = policy_field
        label = row.value("Página")
        policy = decisions["decisions"]["international_relations"]
        if label == policy["source_label"]:
            page = policy["semantic_page"]
            field = policy["component"] + "." + ("semantic_id" if column == "Página" else field)
        else:
            page = domain["editorial_pages"].get(label)
    elif row.spec.role == "media":
        page = "media"
        asset = row.value("Nome do arquivo")
    return institution, language, page, field, asset


def build_context_index(
    dataset: dict, rows: list[SourceRow], domain: dict, decisions: dict
) -> dict:
    contexts = defaultdict(set)
    for row in rows:
        for column, observation in row.observations.items():
            context = row_context(row, column, domain, decisions)
            if context:
                key = row_key(observation.provenance.__dict__) + (column,)
                contexts[key].add(context)
    # Compiled tables have no acronym. Use bindings established by the importer,
    # not path guessing or a new slug-based identity rule.
    for institution in dataset["institutions"]:
        for localization in institution["localizations"]:
            for page in localization["pages"]:
                for field, observations in page["candidates"].items():
                    for observation in observations:
                        provenance = observation["provenance"]
                        key = row_key(provenance) + (provenance.get("field"),)
                        if key not in contexts:
                            contexts[key].add(
                                (
                                    institution["acronym"],
                                    localization["language"],
                                    page["semantic_id"],
                                    field,
                                    None,
                                )
                            )
    return contexts


def conflict_context(conflict: dict, contexts: dict, dataset: dict, domain: dict) -> tuple:
    matches = set()
    for candidate in conflict.get("candidates", []):
        provenance = candidate["provenance"]
        matches.update(contexts.get(row_key(provenance) + (provenance.get("field"),), ()))
    normalized_field = semantic_field(conflict["field"], domain)
    field_matches = {context for context in matches if context[3] == normalized_field}
    if field_matches:
        matches = field_matches
    if len(matches) == 1:
        return next(iter(matches))
    # Only explicit diagnostic identities can disambiguate a conflict.
    parts = conflict["entity"].split(":")
    institutions = {i["acronym"] for i in dataset["institutions"]}
    if parts[0] in institutions:
        language = next((p for p in parts[1:] if p in {"pt-br", "en", "es"}), None)
        language = language or language_for_column(conflict["field"], domain)
        page = next(
            (
                p
                for p in parts[1:]
                if p in {"home", "about", "campus_life", "international_students"}
            ),
            None,
        )
        if page is None and normalized_field in {"title", "slug", "container_path"}:
            page = "home"
        asset = parts[1] if len(parts) > 1 and "_" in parts[1] else None
        if asset:
            page = "media"
        if conflict["category"] == "editorial":
            component_matches = {
                c for c in matches if c[3] == "international_relations.semantic_id"
            }
            if len(component_matches) == 1:
                return next(iter(component_matches))
        return parts[0], language, page, normalized_field, asset
    # Ambiguous/unknown source identity stays a technical blocker, never a guessed IES.
    return None, None, None, normalized_field, None


def approved_names(dataset: dict, decisions: dict) -> tuple[list, list]:
    policy = decisions["decisions"]["approved_institutional_translations"]
    resolutions, pending = [], []
    for institution in dataset["institutions"]:
        for localization in institution["localizations"]:
            language = localization["language"]
            if language not in policy["languages"]:
                continue
            observations = [
                obs
                for obs in localization["candidates"].get("translated_name", [])
                if all(
                    obs["provenance"].get(k) == policy[k] for k in ("source_id", "sheet", "table")
                )
                and obs["provenance"].get("field") == policy["columns"][language]
            ]
            context = {
                "institution": institution["acronym"],
                "language": language,
                "semantic_page": None,
                "field": "translated_name",
            }
            values = {
                obs["value"]
                for obs in observations
                if isinstance(obs["value"], str) and obs["value"]
            }
            uncertain = any(
                obs["provenance"].get("cache_state") != "not_applicable" for obs in observations
            )
            if (
                observations
                and len(values) == 1
                and all(obs["value"] for obs in observations)
                and not uncertain
            ):
                resolutions.append(
                    {
                        **context,
                        "classification": "B",
                        "status": "resolved_in_overlay",
                        "rule": "approved_institutional_translations",
                        "value": next(iter(values)),
                        "source_references": [source_reference(obs) for obs in observations],
                    }
                )
            else:
                pending.append(
                    {
                        **context,
                        "classification": "D" if uncertain else "C",
                        "status": "open",
                        "reason": "approved_name_missing_divergent_or_uncertified",
                        "source_references": [source_reference(obs) for obs in observations],
                    }
                )
    return resolutions, pending


def reconcile_local(dataset: dict, rows: list[SourceRow], domain: dict, decisions: dict) -> dict:
    """Group all original evidence; applying rules does not make a write-ready dataset."""
    if dataset.get("diagnostic_only") is not True:
        raise ValueError("A diagnostic-only dataset is required")
    contexts = build_context_index(dataset, rows, domain, decisions)
    resolutions, pending_names = approved_names(dataset, decisions)
    approved_contexts = {
        (resolution["institution"], resolution["language"]) for resolution in resolutions
    }
    groups = {}
    for number, conflict in enumerate(dataset["conflicts"]):
        context = conflict_context(conflict, contexts, dataset, domain)
        institution, language, page, field, asset = context
        category = conflict["category"]
        classification = "C"
        if category == "formula_cache" or institution is None or category in {"paths", "identity"}:
            classification = "D"
        if field == "international_relations.semantic_id" and category == "editorial":
            classification = "B"
        if field == "translated_name" and (institution, language) in approved_contexts:
            classification = "B" if category != "formula_cache" else "D"
        if field in {"Tratar", "Metadados", "Baixar", "phase", "execution", "translation"}:
            classification = "D" if category == "formula_cache" else "A"
        # One group per semantic field; keep every cause and take its highest severity.
        key = context
        group = groups.setdefault(
            key,
            {
                "institution": institution,
                "language": language,
                "semantic_page": page,
                "field": field,
                "asset_id": asset,
                "classification": classification,
                "status": "resolved_in_overlay" if classification == "B" else "open",
                "scope": "local_evidence_only",
                "stop_affected_page_or_institution": classification in {"C", "D"},
                "categories": set(),
                "causes": [],
                "evidence_ids": [],
                "source_references": {},
            },
        )
        if "ABCD".index(classification) > "ABCD".index(group["classification"]):
            group["classification"] = classification
        group["status"] = "resolved_in_overlay" if group["classification"] == "B" else "open"
        group["stop_affected_page_or_institution"] = group["classification"] in {"C", "D"}
        group["causes"].append(
            {"category": category, "classification": classification, "evidence_id": number}
        )
        group["categories"].add(category)
        group["evidence_ids"].append(number)
        for observation in conflict.get("candidates", []):
            reference = source_reference(observation)
            group["source_references"][canonical(reference)] = reference
    semantic = []
    for group in groups.values():
        group["categories"] = sorted(group["categories"])
        group["source_references"] = [
            value for _, value in sorted(group["source_references"].items())
        ]
        group["evidence_count"] = len(group["evidence_ids"])
        group["semantic_conflict_id"] = hashlib.sha256(
            canonical(
                {
                    k: group[k]
                    for k in (
                        "institution",
                        "language",
                        "semantic_page",
                        "field",
                        "asset_id",
                    )
                }
            ).encode()
        ).hexdigest()[:20]
        semantic.append(group)
    return Redactor.from_environment().data(
        {
            "schema_version": 1,
            "diagnostic_only": True,
            "ready_for_write": False,
            "remote_verification": "not_performed",
            "original_conflicts_preserved": len(dataset["conflicts"]),
            "semantic_conflicts": sorted(semantic, key=canonical),
            "semantic_summary_by_class": dict(
                sorted(Counter(g["classification"] for g in semantic).items())
            ),
            "local_resolutions": resolutions,
            "approved_name_conflicts": pending_names,
            "editorial_decisions": copy.deepcopy(decisions),
        }
    )


def legacy_expectations(path):
    """CSV paths are evidence for comparison, never discovery/request targets."""
    rows, _ = read_csv_source(Path(path), "legacy_csv", "home")
    result = {}
    for row in rows:
        institution = row.value("Sigla")
        key = institution.casefold()
        expected = {
            "institution": institution,
            "expected_url": row.value("Onde criar").rstrip("/") + "/" + row.value("nome_curto"),
            "expected_slug": row.value("nome_curto"),
            "expected_title": row.value("Título"),
        }
        if key in result and result[key] != expected:
            raise InventoryError(
                "source_conflict", "Conflicting CSV institution evidence; no value selected."
            )
        result[key] = expected
    return result


def read_approved_overlay(path, workbook=None):
    """Use only the literal approved resolution overlay exported from the cloud."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if workbook:
        digest = hashlib.sha256(Path(workbook).read_bytes()).hexdigest()
        references = {
            reference.get("sha256")
            for item in data.get("local_resolutions", [])
            if item.get("rule") == "approved_institutional_translations"
            for reference in item.get("source_references", [])
            if reference.get("source_id") == "production"
        }
        if references != {digest}:
            raise InventoryError(
                "source_conflict",
                "Planilha atual diverge da origem do overlay aprovado; comparação interrompida.",
            )
    result = {}
    for item in data.get("local_resolutions", []):
        if (
            item.get("rule") != "approved_institutional_translations"
            or item.get("field") != "translated_name"
            or item.get("status") != "resolved_in_overlay"
        ):
            continue
        key = (item["institution"].casefold(), item["language"])
        if key in result and result[key]["value"] != item["value"]:
            raise InventoryError(
                "source_conflict", "Traduções aprovadas divergentes; nenhuma escolha automática."
            )
        result[key] = {
            "value": item["value"],
            "source_references": item.get("source_references", []),
        }
    return result
