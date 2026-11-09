"""Refresh one saved dialogue source from a verified immutable Wiki revision.

This updates the source cache only; run the dialogue exporter separately.
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://oldschool.runescape.wiki/api.php"


def refresh(cache_path, title, revision, expected_sha256, response):
    pages = response["query"]["pages"]
    if len(pages) != 1 or pages[0].get("title") != title:
        raise ValueError("Unexpected Wiki page")
    revisions = pages[0].get("revisions", [])
    if len(revisions) != 1 or revisions[0].get("revid") != revision:
        raise ValueError("Unexpected Wiki revision")
    text = revisions[0]["slots"]["main"]["content"]
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_sha256:
        raise ValueError("Wiki source hash mismatch")
    path = Path(cache_path)
    cached = json.loads(path.read_text(encoding="utf-8"))
    if title not in cached:
        raise ValueError("Page is not already in this source cache")
    if set(cached[title]) != {"revision", "wikitext"}:
        raise ValueError("Source cache page has unsupported metadata")
    cached[title] = {"revision": revision, "wikitext": text}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cached, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    query = urlencode({"action": "query", "format": "json", "formatversion": 2,
                       "prop": "revisions", "rvprop": "ids|content", "rvslots": "main",
                       "revids": args.revision})
    request = Request(f"{API}?{query}", headers={"User-Agent": "osrsreboxed-db dialogue source refresh"})
    with urlopen(request, timeout=60) as response:
        data = json.load(response)
    refresh(args.cache, args.title, args.revision, args.sha256, data)


if __name__ == "__main__":
    main()
