"""Compile source evidence into a deterministic diagnostic dataset, without networking."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from studybr.api.errors import UnsafeURLError
from studybr.api.urls import safe_url
from studybr.models import (
    Conflict,
    DiagnosticDataset,
    EditorialPolicy,
    Institution,
    LocalizedInstitution,
    LocalizedPage,
    Location,
    MediaAsset,
    Observation,
    PageKind,
    Provenance,
    normalize_acronym,
)
from studybr.security import Redactor
from studybr.settings import validate_base_url

from .workbooks import (
    CREATION_TABLES,
    PRODUCTION_TABLES,
    SourceError,
    SourceRow,
    TableSpec,
    clean_value,
    read_workbook,
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def consensus(observations: list[Observation]) -> Any:
    values = {canonical(o.value): o.value for o in observations}
    return next(iter(values.values())) if len(values) == 1 else None


def normalized_path(value: Any, base_url: str) -> str | None:
    if value is None:
        return None
    target = safe_url(base_url, str(value))
    parts = urlsplit(target)
    if parts.query:
        raise UnsafeURLError()
    site = urlsplit(base_url).path.rstrip("/")
    return parts.path[len(site) :].rstrip("/") or "/"


def read_csv_source(path: Path, source_id: str, role: str) -> tuple:
    raw = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(raw[:10000], delimiters=",;")
        reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
        heads = [clean_value(h) for h in (reader.fieldnames or []) if clean_value(h)]
        if not heads or len(set(heads)) != len(heads):
            raise SourceError("Invalid CSV headers")
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = TableSpec("csv", "csv", (), role=role)
        rows = []
        for number, values in enumerate(reader, 2):
            observations = {}
            for key, value in values.items():
                if key is None:
                    continue
                header = clean_value(key)
                if not header:
                    continue
                observations[header] = Observation(
                    clean_value(value),
                    Provenance(
                        source_id,
                        path.name,
                        source_hash,
                        row=number,
                        field=header,
                    ),
                )
            rows.append(SourceRow(spec, observations))
    except (csv.Error, UnicodeError):
        raise SourceError("Unable to parse supplied CSV source") from None
    return rows, {"source_id": source_id, "filename": path.name, "sha256": source_hash}


class DiagnosticBuilder:
    def __init__(self, base_url: str, domain: dict[str, Any]) -> None:
        self.base_url = validate_base_url(base_url)
        self.domain = domain
        self.conflicts: list[Conflict] = []
        self.sources: list[dict[str, str]] = []
        self.fields: dict[str, dict[str, list[Observation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.local: dict[tuple, dict[str, list[Observation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.pages: dict[tuple, dict[str, list[Observation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.media: dict[tuple, dict[str, list[Observation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.unassigned: list[dict[str, Any]] = []
        self.targets: dict[tuple, list[Observation]] = defaultdict(list)

    def add(self, fields: dict, key: str, row: SourceRow, column: str, transform=None) -> None:
        observation = row.observations.get(column)
        if observation is None:
            return
        if transform is not None:
            try:
                observation = replace(observation, value=transform(observation.value))
            except UnsafeURLError:
                self.conflicts.append(
                    Conflict(
                        "paths",
                        row.value("Sigla") or "unknown",
                        column,
                        "Unsafe or external source path; no destination selected",
                        (observation,),
                    )
                )
                return
        fields[key].append(observation)

    def acronym(self, row: SourceRow, column: str = "Sigla") -> str | None:
        value = row.value(column)
        if not isinstance(value, str) or not value or value == "_Modelo":
            return None
        normalized = normalize_acronym(value)
        self.add(self.fields[normalized], "acronym_raw", row, column)
        return normalized

    def mapped(self, registry: str, value: Any, obs: Observation) -> Any:
        if value is None:
            return None
        result = self.domain[registry].get(value)
        if result is None:
            self.conflicts.append(
                Conflict(
                    "classification",
                    "source",
                    registry,
                    "Unregistered domain category",
                    (obs,),
                )
            )
        return result

    def import_creation(self, rows: list[SourceRow]) -> None:
        primary = [r for r in rows if r.spec.role in {"home", "subpage"}]
        for row in primary:
            acronym = self.acronym(row)
            if acronym is None:
                self.conflicts.append(
                    Conflict(
                        "identity",
                        "creation",
                        "Sigla",
                        "Missing institution identity",
                        tuple(row.observations.values()),
                    )
                )
                continue
            language = row.spec.language
            fields = self.fields[acronym]
            self.add(fields, "official_name", row, "Universidade")
            for key, column, registry in [
                ("institution_type", "Tipo", "institution_types"),
                ("administration", "Tipo2", "administration"),
                ("ownership", "Natureza", "ownership"),
                ("region_id", "Região", "regions"),
            ]:
                if column in row.observations:
                    obs = row.observations[column]
                    fields[key].append(replace(obs, value=self.mapped(registry, obs.value, obs)))
            self.add(fields, "state_code", row, "Estado")
            kind_key = row.value("tipo3") or row.value("Tipo3")
            kind = "home" if row.spec.role == "home" else self.domain["page_aliases"].get(kind_key)
            if kind is None:
                self.conflicts.append(
                    Conflict(
                        "editorial",
                        acronym,
                        "semantic_id",
                        "Unmapped page identity",
                        tuple(row.observations.values()),
                    )
                )
                continue
            self.add_page(acronym, language, kind, row)
            if kind == "home":
                local = self.local[acronym, language]
                self.add(local, "home_slug", row, "nome_curto")
                self.add(local, "container_path", row, "Onde criar", self.path)
                if language != self.domain["primary_language"]:
                    name_column = self.domain["language_fields"][language]["creation_name"]
                    self.add(local, "translated_name", row, name_column)
                    translated = row.value(name_column)
                    if translated and translated not in str(row.value("Título") or ""):
                        self.conflicts.append(
                            Conflict(
                                "names",
                                f"{acronym}:{language}",
                                "title",
                                "Home title differs from translated name; naming policy pending",
                                tuple(row.observations[k] for k in ("Título", name_column)),
                            )
                        )
        # Compiled sheets are additional evidence matched by declared destination, not authority.
        for row in rows:
            if not row.spec.role.startswith("compiled"):
                continue
            label = row.value("Tipo página") or row.value("tipo página")
            language = self.domain["compiled_languages"].get(label)
            try:
                path = self.path(row.value("Onde criar"))
            except UnsafeURLError:
                path = None
            matched = [
                key
                for key, fields in self.pages.items()
                if key[1] == language
                and any(o.value == path for o in fields.get("container_path", []))
                and any(o.value == row.value("nome_curto") for o in fields.get("slug", []))
            ]
            if len(matched) != 1:
                self.conflicts.append(
                    Conflict(
                        "paths",
                        "compiled",
                        "destination",
                        "Compiled row does not match one source page",
                        tuple(row.observations.values()),
                    )
                )
            else:
                self.add_page(*matched[0], row, register_target=False)

    def path(self, value: Any) -> str | None:
        return normalized_path(value, self.base_url)

    def add_page(self, acronym, language, kind, row, *, register_target=True) -> None:
        fields = self.pages[acronym, language, kind]
        for key, column in [
            ("slug", "nome_curto"),
            ("title", "Título"),
            ("title", "Título2"),
            ("title", "Título da página"),
            ("nav_title", "nav_title"),
            ("description", "Descrição"),
        ]:
            self.add(fields, key, row, column)
        self.add(fields, "container_path", row, "Onde criar", self.path)
        self.add(fields, "declared_path", row, "Onde criar")
        self.add(
            fields,
            "subjects",
            row,
            "TAGs",
            lambda x: sorted(set(p.strip() for p in str(x).split(";") if p.strip()))
            if x is not None
            else None,
        )
        if register_target and row.value("Onde criar") and row.value("nome_curto"):
            try:
                target = (
                    self.path(row.value("Onde criar")).rstrip("/") + "/" + row.value("nome_curto")
                )
                self.targets[row.observations["Onde criar"].provenance.source_id, target].append(
                    row.observations["nome_curto"]
                )
            except (UnsafeURLError, TypeError):
                pass

    def import_production(self, rows: list[SourceRow]) -> None:
        for row in rows:
            column = (
                "Siglas"
                if row.spec.role == "names"
                else "IES"
                if row.spec.role == "editorial"
                else "Sigla"
            )
            acronym = self.acronym(row, column)
            if acronym is None:
                continue
            if row.spec.role == "names":
                self.add(self.fields[acronym], "official_name", row, "Oficial")
                for language in self.domain["languages"]:
                    if language != self.domain["primary_language"]:
                        name_column = self.domain["language_fields"][language]["production_name"]
                        self.add(self.local[acronym, language], "translated_name", row, name_column)
            elif row.spec.role == "editorial":
                kind = self.domain["editorial_pages"].get(row.value("Página"))
                if kind is None:
                    self.conflicts.append(
                        Conflict(
                            "editorial",
                            acronym,
                            "semantic_id",
                            "Editorial page label has no approved semantic mapping",
                            (row.observations["Página"],),
                        )
                    )
                    self.unassigned.append(
                        {
                            "acronym": acronym,
                            "page_label": row.value("Página"),
                            "observations": row.observations,
                        }
                    )
                    continue
                for language in self.domain["languages"]:
                    fields = self.pages[acronym, language, kind]
                    for field in ["phase", "execution", "translation"]:
                        column = self.domain["language_fields"][language][field]
                        if column is not None:
                            self.add(fields, field, row, column)
            elif row.spec.role == "media":
                self.add_media(acronym, row)

    def add_media(self, acronym: str, row: SourceRow) -> None:
        filename = row.value("Nome do arquivo")
        if not isinstance(filename, str):
            self.conflicts.append(
                Conflict("metadata", acronym, "filename", "Missing media filename")
            )
            return
        fields = self.media[acronym, filename]
        for column in row.observations:
            self.add(fields, column, row, column)
        stem = Path(filename).stem
        prefix = stem.rsplit("_", 1)[0]
        if normalize_acronym(prefix) != acronym:
            self.conflicts.append(
                Conflict(
                    "aliases",
                    acronym,
                    "filename",
                    "Media filename does not match institution identity",
                    (row.observations["Nome do arquivo"],),
                )
            )

    def compare_csv(self, path: Path, role: str, xlsx_rows: list[SourceRow]) -> None:
        source_id = f"csv:{role}"
        csv_rows, manifest = read_csv_source(path, source_id, role)
        self.sources.append(manifest)

        def key(row):
            acronym = normalize_acronym(str(row.value("Sigla") or ""))
            if role == "media":
                return acronym, row.value("Nome do arquivo")
            if role == "home":
                return (acronym,)
            # Match semantic identity, not slug, so divergent slug remains a conflict.
            semantic = self.domain["page_aliases"].get(
                row.value("tipo3") or row.value("nome_curto")
            )
            return acronym, semantic

        xlsx_index = defaultdict(list)
        for row in xlsx_rows:
            if row.spec.role == role and (role == "media" or row.spec.language == "pt-br"):
                xlsx_index[key(row)].append(row)
        for row in csv_rows:
            matches = xlsx_index.get(key(row), [])
            if len(matches) != 1:
                self.conflicts.append(
                    Conflict(
                        "xlsx_csv",
                        ":".join(str(v) for v in key(row)),
                        "identity",
                        "CSV row has no unique XLSX counterpart",
                        tuple(row.observations.values()),
                    )
                )
                continue
            other = matches[0]
            for column in sorted(row.observations.keys() & other.observations.keys()):
                left, right = row.observations[column], other.observations[column]
                if canonical(left.value) != canonical(right.value):
                    self.conflicts.append(
                        Conflict(
                            "xlsx_csv",
                            ":".join(str(v) for v in key(row)),
                            column,
                            "XLSX and CSV disagree; no value selected",
                            (left, right),
                        )
                    )
            acronym = self.acronym(row)
            if acronym is None:
                continue
            if role == "media":
                self.add_media(acronym, row)
            else:
                kind = "home" if role == "home" else key(row)[1]
                if kind:
                    self.add_page(acronym, "pt-br", kind, row)
                if role == "home":
                    self.add(self.fields[acronym], "official_name", row, "Universidade")
                    self.add(self.fields[acronym], "city", row, "Cidade Sede")
                    self.add(self.local[acronym, "pt-br"], "home_slug", row, "nome_curto")
                    self.add(
                        self.local[acronym, "pt-br"], "container_path", row, "Onde criar", self.path
                    )
        csv_keys = {key(row) for row in csv_rows}
        for missing in sorted(set(xlsx_index) - csv_keys, key=str):
            self.conflicts.append(
                Conflict(
                    "xlsx_csv",
                    str(missing),
                    "identity",
                    "XLSX row is missing from CSV export",
                )
            )

    def compare_diagram(self, path: Path) -> None:
        """Optional historical JSON: slug and alias evidence only, never remote state."""
        records = json.loads(path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.sources.append({"source_id": "diagram", "filename": path.name, "sha256": digest})
        if not isinstance(records, list):
            raise SourceError("Expected a diagram JSON list")
        for number, record in enumerate(records, 1):
            acronym = normalize_acronym(record["sigla"])
            for column in ["sigla", "sigla_alt"]:
                if record.get(column):
                    self.fields[acronym]["acronym_raw"].append(
                        Observation(
                            record[column],
                            Provenance("diagram", path.name, digest, row=number, field=column),
                        )
                    )
            obs = Observation(
                record.get("slug"),
                Provenance(
                    "diagram",
                    path.name,
                    digest,
                    row=number,
                    field="slug",
                ),
            )
            self.local[acronym, "pt-br"]["home_slug"].append(obs)
            self.pages[acronym, "pt-br", "home"]["slug"].append(obs)

    def resolve_fields(self, entity: str, fields: dict) -> dict:
        resolved = {}
        for field, observations in sorted(fields.items()):
            observations.sort(
                key=lambda o: canonical(o.__dict__ | {"provenance": o.provenance.__dict__})
            )
            resolved[field] = consensus(observations)
            if field in {"acronym_raw", "declared_path"}:
                continue
            if len({canonical(o.value) for o in observations}) > 1:
                category = (
                    "names"
                    if "name" in field or field == "title"
                    else "slugs"
                    if "slug" in field
                    else "paths"
                    if "path" in field
                    else "metadata"
                )
                self.conflicts.append(
                    Conflict(
                        category,
                        entity,
                        field,
                        "Competing observations; diagnostic field left unset",
                        tuple(observations),
                    )
                )
        return resolved

    def finish(self) -> DiagnosticDataset:
        for (_, target), observations in sorted(self.targets.items()):
            if len(observations) > 1:
                self.conflicts.append(
                    Conflict(
                        "duplicate_destination",
                        target,
                        "destination",
                        "Duplicate destination within one source",
                        tuple(observations),
                    )
                )
        institutions = []
        for acronym, fields in sorted(self.fields.items()):
            values = self.resolve_fields(acronym, fields)
            aliases = tuple(
                sorted({o.value for o in fields.get("acronym_raw", []) if o.value != acronym})
            )
            if aliases:
                self.conflicts.append(
                    Conflict(
                        "aliases",
                        acronym,
                        "acronym",
                        "Spelling aliases grouped by explicit normalization; approval pending",
                        tuple(fields["acronym_raw"]),
                    )
                )
            localizations = []
            for (institution, language), local_fields in sorted(self.local.items()):
                if institution != acronym:
                    continue
                local_values = self.resolve_fields(f"{acronym}:{language}", local_fields)
                pages = []
                for (inst, lang, kind), page_fields in sorted(self.pages.items()):
                    if (inst, lang) != (acronym, language):
                        continue
                    page = self.resolve_fields(f"{inst}:{lang}:{kind}", page_fields)
                    for required in ["slug", "container_path", "title", "description"]:
                        if page.get(required) is None:
                            self.conflicts.append(
                                Conflict(
                                    "metadata",
                                    f"{inst}:{lang}:{kind}",
                                    required,
                                    "Required diagnostic page field is missing or unresolved",
                                    tuple(page_fields.get(required, [])),
                                )
                            )
                    pages.append(
                        LocalizedPage(
                            PageKind(kind),
                            lang,
                            page.get("slug"),
                            page.get("title"),
                            page.get("nav_title"),
                            page.get("description"),
                            tuple(page.get("subjects") or []),
                            page.get("container_path"),
                            EditorialPolicy(
                                phase=page.get("phase"),
                                execution=page.get("execution"),
                                translation=page.get("translation"),
                            ),
                            candidates=dict(page_fields),
                        )
                    )
                localizations.append(
                    LocalizedInstitution(
                        language,
                        local_values.get("translated_name"),
                        local_values.get("home_slug"),
                        local_values.get("container_path"),
                        tuple(pages),
                        dict(local_fields),
                    )
                )
            institutions.append(
                Institution(
                    f"br-{acronym.lower()}",
                    acronym,
                    aliases,
                    values.get("official_name"),
                    values.get("institution_type"),
                    values.get("administration"),
                    values.get("ownership"),
                    Location(values.get("region_id"), values.get("state_code"), values.get("city")),
                    tuple(localizations),
                    dict(fields),
                )
            )
        media_assets = []
        for (acronym, filename), fields in sorted(self.media.items()):
            values = self.resolve_fields(f"{acronym}:{filename}", fields)
            metadata = {}
            for lang in self.domain["languages"]:
                suffix = self.domain["language_fields"][lang]["media_suffix"]
                metadata[lang] = {
                    key: values.get(f"{label} {suffix}")
                    for key, label in [
                        ("title", "Título"),
                        ("description", "Descrição"),
                        ("caption", "Legenda"),
                        ("alt", "Texto alt"),
                    ]
                }
                if not all(metadata[lang].values()):
                    self.conflicts.append(
                        Conflict(
                            "metadata",
                            f"{acronym}:{filename}:{lang}",
                            "media_metadata",
                            "Media metadata missing or conflicting",
                        )
                    )
            match = re.search(r"_(\d\d)$", Path(filename).stem)
            role = self.domain["media_roles"].get(match[1]) if match else None
            if role is None:
                self.conflicts.append(Conflict("metadata", filename, "role", "Unknown media role"))
            media_assets.append(
                MediaAsset(
                    f"br-{acronym.lower()}:{filename}",
                    f"br-{acronym.lower()}",
                    filename,
                    role,
                    metadata,
                    dict(fields),
                )
            )
        self.conflicts.sort(
            key=lambda c: canonical(
                {
                    "category": c.category,
                    "entity": c.entity,
                    "field": c.field,
                    "message": c.message,
                    "candidates": [
                        o.__dict__ | {"provenance": o.provenance.__dict__} for o in c.candidates
                    ],
                }
            )
        )
        return DiagnosticDataset(
            1,
            True,
            tuple(institutions),
            tuple(media_assets),
            tuple(self.conflicts),
            tuple(sorted(self.sources, key=lambda s: s["source_id"])),
            tuple(sorted(self.unassigned, key=lambda r: (r["acronym"], r["page_label"]))),
        )


def build_diagnostic(
    creation: Path,
    production: Path,
    *,
    base_url: str,
    domain_path: Path,
    csv_sources: dict[str, Path] | None = None,
    diagram_json: Path | None = None,
) -> DiagnosticDataset:
    domain = json.loads(domain_path.read_text(encoding="utf-8"))
    builder = DiagnosticBuilder(base_url, domain)
    builder.sources.append(
        {
            "source_id": "domain_config",
            "filename": domain_path.name,
            "sha256": hashlib.sha256(domain_path.read_bytes()).hexdigest(),
        }
    )
    creation_rows, conflicts, manifest = read_workbook(creation, "creation", CREATION_TABLES)
    builder.sources.append(manifest)
    builder.conflicts.extend(conflicts)
    production_rows, conflicts, manifest = read_workbook(
        production, "production", PRODUCTION_TABLES
    )
    builder.sources.append(manifest)
    builder.conflicts.extend(conflicts)
    builder.import_creation(creation_rows)
    builder.import_production(production_rows)
    for role, path in sorted((csv_sources or {}).items()):
        if role not in {"home", "subpage", "media"}:
            raise SourceError("Unknown CSV source role")
        builder.compare_csv(path, role, production_rows if role == "media" else creation_rows)
    if diagram_json is not None:
        builder.compare_diagram(diagram_json)
    return builder.finish()


def serialize_dataset(dataset: DiagnosticDataset, redactor: Redactor | None = None) -> str:
    # Input content can itself contain a secret; redact all artifact values at the boundary.
    sanitized = (redactor or Redactor.from_environment()).data(dataset.to_dict())
    return json.dumps(sanitized, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
