"""Observational comparisons only; editorial authority remains studybr.reconciliation."""


def compare_page(observed, expected):
    conflicts = []

    def add(category, field, wanted, actual):
        conflicts.append(
            {"category": category, "field": field, "expected": wanted, "observed": actual}
        )

    fields = {
        "slug": "slug conflict",
        "@type": "structure mismatch",
        "language": "language mismatch",
        "title": "title/name mismatch",
        "review_state": "workflow mismatch",
        "blocks_layout": "block mismatch",
        "parent": "structure mismatch",
        "is_folderish": "structure mismatch",
    }
    for field, wanted in expected.get("fields", {}).items():
        if field not in observed:
            add("metadata mismatch", field, wanted, {"status": "not_observed"})
        elif observed[field] != wanted:
            add(fields.get(field, "metadata mismatch"), field, wanted, observed[field])
    if "block_types" in expected:
        actual = sorted(set(observed.get("block_types", {}).values()), key=str)
        wanted = sorted(set(expected["block_types"]), key=str)
        if actual != wanted:
            add("block mismatch", "block_types", wanted, actual)
    if "children" in expected:
        actual = {
            item.get("id") or item.get("@id", "").rstrip("/").rsplit("/", 1)[-1]
            for item in observed.get("children", [])
        }
        wanted = set(expected["children"])
        for child in sorted(wanted - actual):
            add("missing page", "children", child, None)
        for child in sorted(actual - wanted, key=str):
            add("unexpected page", "children", None, child)
    return conflicts


def compare_models(english, spanish):
    """Report structural differences without assuming equal UUIDs or translated slugs."""
    left = sorted(english.get("block_types", {}).values(), key=str)
    right = sorted(spanish.get("block_types", {}).values(), key=str)
    conflicts = []
    for field in ("@type", "is_folderish", "review_state"):
        if field in english and field in spanish and english[field] != spanish[field]:
            category = "workflow mismatch" if field == "review_state" else "structure mismatch"
            conflicts.append(
                {"category": category, "field": field, "en": english[field], "es": spanish[field]}
            )
    if left != right:
        conflicts.append(
            {"category": "block mismatch", "field": "block_types", "en": left, "es": right}
        )
    if english.get("block_order") != spanish.get("block_order"):
        conflicts.append(
            {
                "category": "block mismatch",
                "field": "block_order",
                "en": english.get("block_order"),
                "es": spanish.get("block_order"),
            }
        )
    return conflicts
