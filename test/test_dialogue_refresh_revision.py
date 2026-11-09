"""A pinned source refresh must not accept a different page or revision."""

import hashlib
import json
import copy

import pytest

from scripts.dialogues.refresh_revision import refresh


def test_refresh_checks_identity_before_changing_cache(tmp_path):
    path = tmp_path / "quest-pages.json"
    original = {"Transcript:Example": {"revision": 1, "wikitext": "old"}}
    path.write_text(json.dumps(original), encoding="utf-8")
    source = "==New==\n* '''Player:''' Hello.\n"
    result = {"query": {"pages": [{"title": "Transcript:Example", "revisions": [
        {"revid": 2, "slots": {"main": {"content": source}}}
    ]}]}}
    digest = hashlib.sha256(source.encode()).hexdigest()
    with pytest.raises(ValueError, match="hash mismatch"):
        refresh(path, "Transcript:Example", 2, "0" * 64, result)
    assert json.loads(path.read_text(encoding="utf-8")) == original
    with pytest.raises(ValueError, match="revision"):
        refresh(path, "Transcript:Example", 3, digest, result)
    assert json.loads(path.read_text(encoding="utf-8")) == original
    wrong_title = copy.deepcopy(result)
    wrong_title["query"]["pages"][0]["title"] = "Transcript:Other"
    with pytest.raises(ValueError, match="page"):
        refresh(path, "Transcript:Example", 2, digest, wrong_title)
    missing = {"query": {"pages": []}}
    with pytest.raises(ValueError, match="page"):
        refresh(path, "Transcript:Example", 2, digest, missing)
    multiple = {"query": {"pages": result["query"]["pages"] * 2}}
    with pytest.raises(ValueError, match="page"):
        refresh(path, "Transcript:Example", 2, digest, multiple)
    assert json.loads(path.read_text(encoding="utf-8")) == original
    refresh(path, "Transcript:Example", 2, digest, result)
    assert json.loads(path.read_text(encoding="utf-8"))["Transcript:Example"] == {
        "revision": 2, "wikitext": source,
    }


def test_refreshed_slug_source_retains_refusal_and_positive_variants():
    from scripts.dialogues import update
    from scripts.dialogues.fetch import QUEST_CACHE, read_cache

    source = read_cache(QUEST_CACHE)["Transcript:The Slug Menace"]
    assert source["revision"] == 15395854
    assert hashlib.sha256(source["wikitext"].encode("utf-8")).hexdigest() == (
        "df1d3a498eccc175f17a3a3aa0080c4123320cd21a4e4c8998911856d75238b8"
    )
    record = update.gameplay_npc("The Slug Menace", update.parse_npc("The Slug Menace", source["wikitext"]))
    variants = record["variants"]
    assert variants["the-pages-using-swamp-paste-on-the-pages-without-the-commorb"] == [
        {"player": "I really should get my commorb before trying that.", "presentation": "overhead"}
    ]
    assert variants["the-pages-using-swamp-paste-on-the-pages"][0]["text"] == "[player name], stop!"
    assert "the-shrine-pushing-the-wall" in variants
    assert "the-pages-talking-to-col-o-niall-after-learning-about-mother-mallum" in variants


def test_speaker_colon_outside_bold_keeps_overhead_presentation():
    from scripts.dialogues import update

    node = update.parse_step("'''Player''': {{overhead|Hello.}}", [], 1)
    assert update.gameplay_step(node, "Example") == {
        "player": "Hello.", "presentation": "overhead",
    }


@pytest.mark.parametrize("raw", [
    "'''Player:''' Hello.",
    "'''Player''': Hello.",
    "'''Player''' : Hello.",
])
def test_speaker_colon_placements_keep_player_text(raw):
    from scripts.dialogues import update

    assert update.gameplay_step(update.parse_step(raw, [], 1), "Example") == {"player": "Hello."}


@pytest.mark.parametrize("raw", ["'''''' : Not a speaker", "'''...''': Not a speaker"])
def test_empty_or_punctuation_bold_is_not_a_speaker(raw):
    from scripts.dialogues import update

    assert update.parse_step(raw, [], 1).get("speaker") is None


def test_outside_colon_does_not_change_children_or_anchors():
    from scripts.dialogues import update

    def parse(line):
        record = update.gameplay_npc("Example", update.parse_npc("Example", line, []))
        return record["variants"]["start"][0]

    inside = parse("==Start==\n* {{anchor|x}} '''Player:''' Hello.\n** {{tact|receives=a lamp}}")
    outside = parse("==Start==\n* {{anchor|x}} '''Player''': Hello.\n** {{tact|receives=a lamp}}")
    assert inside == outside


def test_quoted_speaker_matches_existing_colon_form():
    from scripts.dialogues import update

    inside = update.parse_step("'''\"Guard\":''' Halt.", [], 1)
    outside = update.parse_step("'''\"Guard\"''': Halt.", [], 1)
    assert inside == outside
