"""Generate the diagnostic JSON contract from the domain dataclasses, offline."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from studybr.models import DiagnosticDataset


def schema() -> dict:
    definitions = {}

    def describe(kind):
        if kind is Any:
            return {}
        if kind is type(None):
            return {"type": "null"}
        if kind in (str, int, bool, float):
            return {"type": {str: "string", int: "integer", bool: "boolean", float: "number"}[kind]}
        origin, args = get_origin(kind), get_args(kind)
        if origin in (Union, types.UnionType):
            return {"anyOf": [describe(arg) for arg in args]}
        if origin in (list, tuple):
            return {"type": "array", "items": describe(args[0])}
        if origin is dict:
            return {"type": "object", "additionalProperties": describe(args[1])}
        if isinstance(kind, type) and issubclass(kind, Enum):
            return {"enum": [entry.value for entry in kind]}
        if is_dataclass(kind):
            name = kind.__name__
            if name not in definitions:
                definitions[name] = {}
                hints = get_type_hints(kind)
                definitions[name] = {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {f.name: describe(hints[f.name]) for f in fields(kind)},
                    "required": [f.name for f in fields(kind)],
                }
            return {"$ref": f"#/$defs/{name}"}
        raise TypeError("Unsupported schema field type")

    root = describe(DiagnosticDataset)
    definitions["DiagnosticDataset"]["properties"]["schema_version"] = {"const": 1}
    definitions["DiagnosticDataset"]["properties"]["diagnostic_only"] = {"const": True}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "StudyBR diagnostic evidence, never a write plan",
        **root,
        "$defs": definitions,
    }


if __name__ == "__main__":
    Path("schemas/diagnostic.schema.json").write_text(
        json.dumps(schema(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
