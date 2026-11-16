"""Export Wiki ItemSpawnLine coordinates without guessing runtime conditions or timer units.

Item infobox respawn values are ticks; per-coordinate respawn is free text in Module:Map.
Keep them separate. Consumers decide explicitly when an infobox default is applicable.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from scripts.wiki.wikitext_parser import extract_wikitext_template

ROOT = Path(__file__).resolve().parents[2]
KNOWN_ROW_PARAMETERS = {
    "name",
    "location",
    "members",
    "plane",
    "mapID",
    "zoom",
    "leagueRegion",
    "trailblazerRegion",
    "uk",
}


def _value(template, name, default=""):
    return str(template.get(name).value).strip() if template.has(name) else default


def _positive_integer(value):
    return int(value) if re.fullmatch(r"[1-9][0-9]*", value) else None


def _versions(text, title):
    versions = []
    for box in extract_wikitext_template(text, "infobox item"):
        selector_counts = Counter(str(p.name).strip() for p in box.params)
        duplicates = sorted(
            key
            for key, count in selector_counts.items()
            if count > 1 and re.fullmatch(r"(?:id|name|respawn)[0-9]*", key)
        )
        for param in box.params:
            key = str(param.name).strip()
            match = re.fullmatch(r"id([0-9]*)", key)
            if not match:
                continue
            suffix = match[1]
            raw_id = str(param.value).strip()
            versions.append(
                {
                    "id": int(raw_id) if re.fullmatch(r"[0-9]+", raw_id) else None,
                    "id_raw": raw_id,
                    "duplicate_selectors": duplicates,
                    "name": _value(box, "name" + suffix, _value(box, "name", title)),
                    "respawn_raw": _value(
                        box, "respawn" + suffix, _value(box, "respawn")
                    ),
                    "version": suffix,
                }
            )
    return versions


def _pickup_replacement(text, pages):
    """An Illegal Item page can explicitly name the real item awarded on Take."""
    if not re.search(r"\{\{\s*Illegal Item\s*\}\}", text, re.I):
        return None
    match = re.search(
        r"If the player picks it up, they will be given a regular \[\[([^\[\]|]+)\]\] instead\.",
        text,
    )
    if not match:
        return None
    title = match[1][0].upper() + match[1][1:]
    target_text = pages.get(title)
    if not isinstance(target_text, str):
        return None
    versions = _versions(target_text, title)
    if (
        len(versions) != 1
        or versions[0]["id"] is None
        or versions[0]["duplicate_selectors"]
    ):
        return None
    replacement = {"id": versions[0]["id"]}
    denial = re.search(
        r"""via \[\[telekinetic grab\]\] does not work, with a message stating "''([^"\n]+)''(?:")""",
        text,
        re.I,
    )
    if denial:
        replacement["telegrab_denial"] = denial[1]
    return replacement


def _reconcile_case_aliases(rows):
    """Keep one source-complete spawn for case-only page aliases, with provenance.

    A disagreement never picks a winning alias: every row stays visible and held.
    Repeated coordinates on the same page are outside this alias correction.
    """
    identity = ("id", "x", "y", "plane")

    def could_share_identity(first, second):
        for key in identity:
            left, right = first[key], second[key]
            if type(left) is int and type(right) is int and left != right:
                return False
            if key == "id":
                for resolved, uncertain in ((first, second), (second, first)):
                    candidates = uncertain.get("candidate_ids", [])
                    if type(resolved["id"]) is int and candidates and resolved["id"] not in candidates:
                        return False
        return True

    by_title = {}
    for row in rows:
        by_title.setdefault(row["page"].casefold(), []).append(row)
    # An incomplete sibling cannot disappear merely because it lacks a group key.
    for aliases in by_title.values():
        for index, first in enumerate(aliases):
            for second in aliases[index + 1:]:
                if first["page"] == second["page"]:
                    continue
                if all(type(row[key]) is int for row in (first, second) for key in identity):
                    continue
                if could_share_identity(first, second):
                    for row in (first, second):
                        row["unresolved_reasons"] = sorted(
                            set(row["unresolved_reasons"]) | {"conflicting-source-alias-state"}
                        )
    groups = {}
    for index, row in enumerate(rows):
        if all(type(row[key]) is int for key in identity):
            key = (row["page"].casefold(), row["id"], row["x"], row["y"], row["plane"])
            groups.setdefault(key, []).append(index)
    removed = set()
    for indices in groups.values():
        titles = {rows[index]["page"] for index in indices}
        if len(titles) < 2 or len(titles) != len(indices):
            continue
        aliases = [rows[index] for index in indices]
        fields = (
            "id", "x", "y", "plane", "members", "quantity", "location",
            "infobox_respawn_ticks", "infobox_respawn_raw", "tile_respawn_raw",
            "coordinate_qualifiers", "coordinate_qualifier_arguments", "pickup_replacement",
        )
        states = {
            json.dumps({key: row.get(key) for key in fields}, sort_keys=True)
            for row in aliases
        }
        if len(states) != 1 or any(row["unresolved_reasons"] for row in aliases):
            for row in aliases:
                row["unresolved_reasons"] = sorted(
                    set(row["unresolved_reasons"]) | {"conflicting-source-alias-state"}
                )
            continue
        canonical = aliases[0]  # parse_pages visits sorted source titles.
        canonical["source_aliases"] = [
            {key: row[key] for key in ("page", "page_sha256", "row_index", "argument", "argument_index")}
            for row in aliases
        ]
        removed.update(indices[1:])
    return [row for index, row in enumerate(rows) if index not in removed]


def parse_pages(pages):
    """Preserve spawn arguments; reconcile agreeing case aliases with provenance."""
    rows = []
    for title, text in sorted(pages.items()):
        if not isinstance(text, str):
            continue
        versions = (
            _versions(text, title) if re.search("ItemSpawnLine", text, re.I) else []
        )
        replacement = _pickup_replacement(text, pages) if versions else None
        for index, template in enumerate(
            extract_wikitext_template(text, "itemspawnline")
        ):
            raw_parameters = [
                (str(p.name).strip(), str(p.value).strip()) for p in template.params
            ]
            counts = Counter(key for key, _ in raw_parameters)
            duplicate_named = sorted(
                key for key, count in counts.items() if count > 1 and not key.isdigit()
            )
            row_name = _value(template, "name", title)
            matching = [v for v in versions if v["name"] == row_name]
            candidates = matching or (versions if row_name == title else [])
            ids = sorted({v["id"] for v in candidates if v["id"] is not None})
            unresolved_version = any(
                v["id"] is None or v["duplicate_selectors"] for v in candidates
            )
            item_id = (
                ids[0]
                if len(ids) == 1
                and not unresolved_version
                and "name" not in duplicate_named
                else None
            )
            defaults = (
                sorted({v["respawn_raw"] for v in candidates if v["id"] == item_id})
                if item_id is not None
                else []
            )
            default_raw = defaults[0] if len(defaults) == 1 else ""
            page_ticks = _positive_integer(default_raw)
            member_raw = _value(template, "members", "No")
            members = (
                {"yes": True, "no": False}.get(member_raw.lower())
                if "members" not in duplicate_named
                else None
            )
            plane_raw = _value(template, "plane", "0")
            unknown_parameters = sorted(
                key
                for key, _ in raw_parameters
                if not key.isdigit() and key not in KNOWN_ROW_PARAMETERS
            )
            for argument_index, (argument, raw) in enumerate(raw_parameters):
                if not argument.isdigit():
                    continue
                reasons = []
                if counts[argument] > 1:
                    reasons.append("duplicate-coordinate-argument")
                if duplicate_named:
                    reasons.append("duplicate-row-parameter")
                if unresolved_version:
                    reasons.append("unresolved-item-version-selector")
                coordinate = re.fullmatch(r"([0-9]+)\s*,\s*([0-9]+)(.*)", raw)
                qualifier_arguments = []
                if coordinate:
                    for part in coordinate[3].strip(",").split(","):
                        if part.strip():
                            key, separator, value = part.partition(":")
                            qualifier_arguments.append(
                                {
                                    "name": key.strip(),
                                    "value": value.strip() if separator else None,
                                }
                            )
                else:
                    reasons.append("unparsed-coordinate")
                qualifier_counts = Counter(q["name"] for q in qualifier_arguments)
                qualifiers = {q["name"]: q["value"] for q in qualifier_arguments}
                duplicate_qualifiers = sorted(
                    key for key, count in qualifier_counts.items() if count > 1
                )
                if duplicate_qualifiers:
                    reasons.append("duplicate-coordinate-qualifier")
                actual_plane = qualifiers.get("plane", plane_raw)
                plane = (
                    int(actual_plane)
                    if isinstance(actual_plane, str)
                    and actual_plane in {"0", "1", "2", "3"}
                    and "plane" not in duplicate_named
                    and "plane" not in duplicate_qualifiers
                    else None
                )
                quantity_raw = qualifiers.get("qty", "1")
                quantity = (
                    _positive_integer(quantity_raw)
                    if isinstance(quantity_raw, str)
                    and "qty" not in duplicate_qualifiers
                    else None
                )
                if item_id is None:
                    reasons.append("ambiguous-item-id")
                if page_ticks is None:
                    reasons.append("missing-positive-infobox-respawn")
                if members is None:
                    reasons.append("unresolved-members")
                if plane is None:
                    reasons.append("unresolved-plane")
                if quantity is None:
                    reasons.append("unresolved-quantity")
                if "respawn" in qualifiers:
                    reasons.append("untyped-tile-respawn")
                if set(qualifiers) - {"qty", "plane", "respawn"}:
                    reasons.append("coordinate-condition-or-unknown-qualifier")
                if unknown_parameters:
                    reasons.append("row-selection-or-unknown-parameter")
                rows.append(
                    {
                        "page": title,
                        "page_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "row_index": index,
                        "argument": argument,
                        "argument_index": argument_index,
                        "name": row_name,
                        "id": item_id,
                        "candidate_ids": ids,
                        "item_versions": candidates,
                        "location": _value(template, "location"),
                        "x": int(coordinate[1]) if coordinate else None,
                        "y": int(coordinate[2]) if coordinate else None,
                        "plane": plane,
                        "members": members,
                        "quantity": quantity,
                        "infobox_respawn_ticks": page_ticks,
                        "infobox_respawn_raw": default_raw,
                        "tile_respawn_raw": qualifiers.get("respawn"),
                        "coordinate_raw": raw,
                        "coordinate_qualifiers": qualifiers,
                        "coordinate_qualifier_arguments": qualifier_arguments,
                        "row_parameters": [
                            {"name": key, "value": value}
                            for key, value in raw_parameters
                            if not key.isdigit()
                        ],
                        "unresolved_reasons": sorted(reasons),
                        **(
                            {"pickup_replacement": replacement}
                            if replacement
                            and item_id is not None
                            and item_id != replacement["id"]
                            else {}
                        ),
                    }
                )
    return _reconcile_case_aliases(rows)


def build_export(raw_bytes):
    pages = json.loads(raw_bytes)
    return {
        "schema": 1,
        "input_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "timer_policy": "Infobox respawn is ticks; tile overrides remain untyped raw text. No automatic inheritance is asserted.",
        "rows": parse_pages(pages),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "data/items/items-wiki-page-text.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/ground-item-spawns.json"
    )
    args = parser.parse_args()
    result = build_export(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    print(
        f"Exported {len(result['rows'])} spawn arguments from {result['input_sha256']}"
    )


if __name__ == "__main__":
    main()
