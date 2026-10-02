"""Domain records. Conflicting values remain as observations, never last-row-wins."""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


def normalize_acronym(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip().upper().replace("_", "-")
    return "-".join(value.split())


class PageKind(str, Enum):
    HOME = "home"
    ABOUT = "about"
    CAMPUS_LIFE = "campus_life"
    INTERNATIONAL_STUDENTS = "international_students"


@dataclass(frozen=True)
class Provenance:
    source_id: str
    filename: str
    sha256: str
    sheet: str | None = None
    table: str | None = None
    row: int | None = None
    cell: str | None = None
    field: str | None = None
    formula: str | None = None
    cache_state: str = "not_applicable"


@dataclass(frozen=True)
class Observation:
    value: Any
    provenance: Provenance


@dataclass(frozen=True)
class Location:
    region_id: str | None = None
    state_code: str | None = None
    city: str | None = None


@dataclass(frozen=True)
class RemoteBinding:
    uid: str
    url: str
    language: str
    parent_url: str | None = None
    observed_modified: str | None = None
    content_hash: str | None = None


@dataclass(frozen=True)
class EditorialPolicy:
    ownership: str = "unconfirmed"
    managed_fields: tuple[str, ...] = ()
    managed_block_ids: tuple[str, ...] = ()
    approved_by: str | None = None
    phase: str | None = None
    execution: str | None = None
    translation: str | None = None

    def __post_init__(self) -> None:
        if self.ownership not in {"unconfirmed", "manual", "managed", "mixed"}:
            raise ValueError("Invalid editorial ownership")


@dataclass(frozen=True)
class LocalizedPage:
    semantic_id: PageKind
    language: str
    slug: str | None = None
    title: str | None = None
    nav_title: str | None = None
    description: str | None = None
    subjects: tuple[str, ...] = ()
    container_path: str | None = None
    editorial_policy: EditorialPolicy = field(default_factory=EditorialPolicy)
    remote_binding: RemoteBinding | None = None
    candidates: dict[str, list[Observation]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_id", PageKind(self.semantic_id))


@dataclass(frozen=True)
class LocalizedInstitution:
    language: str
    translated_name: str | None = None
    home_slug: str | None = None
    container_path: str | None = None
    pages: tuple[LocalizedPage, ...] = ()
    candidates: dict[str, list[Observation]] = field(default_factory=dict)


@dataclass(frozen=True)
class Institution:
    institution_id: str
    acronym: str
    aliases: tuple[str, ...] = ()
    official_name: str | None = None
    institution_type: str | None = None
    administration: str | None = None
    ownership: str | None = None
    location: Location = field(default_factory=Location)
    localizations: tuple[LocalizedInstitution, ...] = ()
    candidates: dict[str, list[Observation]] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaAsset:
    asset_id: str
    institution_id: str
    filename: str
    role: str | None = None
    localized_metadata: dict[str, dict[str, str | None]] = field(default_factory=dict)
    candidates: dict[str, list[Observation]] = field(default_factory=dict)


@dataclass(frozen=True)
class Conflict:
    category: str
    entity: str
    field: str
    message: str
    candidates: tuple[Observation, ...] = ()
    blocking: bool = True


@dataclass(frozen=True)
class DiagnosticDataset:
    schema_version: int
    diagnostic_only: bool
    institutions: tuple[Institution, ...]
    media_assets: tuple[MediaAsset, ...]
    conflicts: tuple[Conflict, ...]
    sources: tuple[dict[str, str], ...]
    unassigned_editorial_rows: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
