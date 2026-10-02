"""Non-destructive structured snapshots and credential-redacted local bodies."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from studybr.api.errors import InventoryError
from studybr.security import Redactor

clean = Redactor().public_data

FIELDS = (
    "@id",
    "@type",
    "id",
    "UID",
    "title",
    "description",
    "language",
    "review_state",
    "parent",
    "is_folderish",
    "subjects",
    "modified",
    "nav_title",
)
STRUCTURAL = {
    "@type",
    "@id",
    "@layout",
    "id",
    "block",
    "align",
    "field",
    "href",
    "url",
    "target",
    "mode",
    "variation",
    "image_field",
    "heading",
    "title",
    "level",
    "styles",
    "className",
    "linkTo",
    "columns",
    "blocks_layout",
    "type",
    "name",
    "fields",
    "required",
    "review_state",
    "state",
    "language",
    "factory",
    "format",
    "enum",
    "choices",
    "default",
    "vocabulary",
    "addable",
    "immediately_addable",
}


def shape(value, key=""):
    if isinstance(value, dict):
        return {name: shape(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [shape(item, key) for item in value]
    if isinstance(value, str):
        if key in STRUCTURAL and len(value) <= 180:
            return value
        return {"kind": "string", "length": len(value), "empty": not bool(value)}
    return value


def child_snapshot(item):
    return {key: item[key] for key in FIELDS if key in item}


def snapshot(data, url, kind="page", model=False):
    data = clean(data)
    if kind != "page":
        return {"schema_version": 1, "url": url, "kind": kind, "structure": shape(data)}
    if not isinstance(data, dict):
        raise InventoryError("invalid_shape", "Página deve ser um objeto JSON.")
    if not isinstance(data.get("items", []), list) or not all(
        isinstance(item, dict) for item in data.get("items", [])
    ):
        raise InventoryError("invalid_shape", "items deve ser uma lista de objetos.")
    if "@id" in data and not isinstance(data["@id"], str):
        raise InventoryError("invalid_shape", "@id deve ser texto.")
    blocks = data.get("blocks") or {}
    if not isinstance(blocks, dict):
        raise InventoryError("invalid_shape", "blocks deve ser um objeto.")
    layout = data.get("blocks_layout") or {}
    if not isinstance(layout, dict) or not isinstance(layout.get("items", []), list):
        raise InventoryError("invalid_shape", "blocks_layout deve conter uma lista de IDs.")
    result = {"schema_version": 1, "url": url, "path": urlsplit(url).path, "kind": kind}
    result.update({key: data[key] for key in FIELDS if key in data})
    result["slug"] = data.get(
        "id", urlsplit(data.get("@id", url)).path.rstrip("/").rsplit("/", 1)[-1]
    )
    result["children"] = [
        child_snapshot(item) for item in data.get("items", []) if isinstance(item, dict)
    ]
    result["items_total"] = data.get("items_total")
    result["blocks_layout"] = data.get("blocks_layout")
    result["block_types"] = {
        block_id: block.get("@type")
        for block_id, block in blocks.items()
        if isinstance(block, dict)
    }
    result["block_order"] = (
        [result["block_types"].get(block_id) for block_id in layout.get("items", [])]
        if isinstance(layout, dict)
        else None
    )
    if model:
        result["blocks_structure"] = shape(blocks)
    ignored = set(FIELDS) | {
        "items",
        "items_total",
        "blocks",
        "blocks_layout",
        "@components",
        "batching",
    }
    result["custom_fields"] = {
        key: shape(value, key) for key, value in data.items() if key not in ignored
    }
    result["sanitization"] = "credentials_removed; long/custom text represented by structure"
    return result


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class SnapshotStore:
    def __init__(self, root, run_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise InventoryError("unsafe_run_id", "Run identifier must not contain paths.")
        self.raw = Path(root) / "raw" / run_id
        self.sanitized = Path(root) / "sanitized" / run_id

    def save(self, url, data, kind="page", model=False, aggregate=False, api_path=None):
        data = clean(data)
        name = (
            hashlib.sha256(url.encode()).hexdigest()[:24]
            + ("-aggregate" if aggregate else "")
            + ".json"
        )
        if not aggregate:
            original = name
            sequence = 1
            while (self.raw / name).exists():
                sequence += 1
                name = original.removesuffix(".json") + f"-{sequence:04d}.json"
            write_json(self.raw / name, data)
        result = snapshot(data, url, kind, model)
        if aggregate:
            result["pagination_complete"] = True
            result["api_path"] = api_path
        write_json(self.sanitized / name, result)
        return result

    def previous(self):
        summary = json.loads((self.sanitized / "summary.json").read_text(encoding="utf-8"))
        pages = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self.sanitized.glob("*-aggregate.json")
        ]
        return summary, pages
