import json
import unittest

from scripts.items.item_spawns import build_export, parse_pages


def page(extra="", item_id="554", respawn="100"):
    return (
        "{{Infobox Item|name=Fire rune|id="
        + item_id
        + "|respawn="
        + respawn
        + "}}"
        + extra
    )


class ItemSpawnExportTests(unittest.TestCase):
    def test_case_alias_spawn_is_exported_once_with_both_source_identities(self):
        text = (
            "{{Infobox Item|name=Staff of Armadyl|id=84|respawn=100}}"
            "{{ItemSpawnLine|name=Staff of Armadyl|location=Temple|members=Yes|2638,9906}}"
        )
        pages = {"Staff of Armadyl": text, "Staff of armadyl": text.replace("Armadyl", "armadyl")}
        [spawn] = parse_pages(pages)
        self.assertEqual((spawn["id"], spawn["quantity"], spawn["infobox_respawn_ticks"]), (84, 1, 100))
        self.assertIsNone(spawn["tile_respawn_raw"])
        self.assertEqual(spawn["unresolved_reasons"], [])
        self.assertEqual([alias["page"] for alias in spawn["source_aliases"]], sorted(pages))
        self.assertEqual(len({alias["page_sha256"] for alias in spawn["source_aliases"]}), 2)
        raw = json.dumps(pages).encode()
        self.assertEqual(build_export(raw), build_export(raw))
        self.assertEqual(parse_pages(dict(reversed(list(pages.items())))), [spawn])

    def test_case_alias_conflicts_hold_every_alias_instead_of_picking_a_timer(self):
        text = "{{Infobox Item|name=Fire rune|id=554|respawn=100}}{{ItemSpawnLine|3026,3637}}"
        rows = parse_pages({"Fire rune": text, "Fire Rune": text.replace("respawn=100", "respawn=50")})
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["infobox_respawn_ticks"] for row in rows}, {50, 100})
        self.assertTrue(all("conflicting-source-alias-state" in row["unresolved_reasons"] for row in rows))
        self.assertTrue(all("source_aliases" not in row for row in rows))
        unresolved = parse_pages({"Fire rune": text, "Fire Rune": text.replace("3026,3637", "3026,3637,respawn:50")})
        self.assertTrue(all("conflicting-source-alias-state" in row["unresolved_reasons"] for row in unresolved))

    def test_case_alias_reconciliation_preserves_distinct_tiles_and_unrelated_pages(self):
        text = "{{Infobox Item|name=Fire rune|id=554|respawn=100}}{{ItemSpawnLine|3026,3637}}"
        unrelated = "{{Infobox Item|name=Earth rune|id=557|respawn=100}}{{ItemSpawnLine|3026,3637}}"
        expected = parse_pages({"Earth rune": unrelated})[0]
        rows = parse_pages({"Fire rune": text, "Fire Rune": text.replace("3026,3637", "3027,3637"), "Earth rune": unrelated})
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], expected)
        self.assertTrue(all("source_aliases" not in row for row in rows))

    def test_incomplete_case_alias_identity_holds_the_valid_sibling(self):
        text = "{{Infobox Item|name=Fire rune|id=554|respawn=100}}{{ItemSpawnLine|3026,3637}}"
        for uncertain in (
            text.replace("id=554", "id=554|id2=557"),
            text.replace("|3026,3637", "|plane=basement|3026,3637"),
            text.replace("3026,3637", "3026,unknown"),
        ):
            with self.subTest(uncertain=uncertain):
                rows = parse_pages({"Fire rune": text, "Fire Rune": uncertain})
                self.assertEqual(len(rows), 2)
                self.assertTrue(all("conflicting-source-alias-state" in row["unresolved_reasons"] for row in rows))
                self.assertTrue(all("source_aliases" not in row for row in rows))
        # Fully resolved different IDs and known-different tiles do not implicate each other.
        distinct = parse_pages({"Fire rune": text, "Fire Rune": text.replace("id=554", "id=557")})
        self.assertEqual({row["id"] for row in distinct}, {554, 557})
        self.assertTrue(all(row["unresolved_reasons"] == [] for row in distinct))
        unrelated = parse_pages({"Fire rune": text, "Fire Rune": text.replace("id=554", "id=554|id2=557").replace("3026,3637", "3027,3637")})
        valid = next(row for row in unrelated if row["id"] == 554)
        self.assertEqual(valid["unresolved_reasons"], [])

    def test_illegal_item_can_explicitly_award_a_different_item_on_pickup(self):
        display = (
            "{{Illegal Item}}"
            "{{Infobox Item|name=White apron|id=7957|respawn=10}}"
            "If the player picks it up, they will be given a regular [[white apron]] instead. "
            "Trying to obtain the white apron via [[telekinetic grab]] does not work, "
            "with a message stating \"''It seems to be firmly on the hook. I cannot get that this way.''\"."
            "{{ItemSpawnLine|name=White apron|3016,3229}}"
        )
        real = "{{Infobox Item|name=White apron|id=1005|respawn=100}}"
        [row] = parse_pages({"White apron": real, "White apron (hanging)": display})
        self.assertEqual((row["id"], row["infobox_respawn_ticks"]), (7957, 10))
        self.assertEqual(
            row["pickup_replacement"],
            {
                "id": 1005,
                "telegrab_denial": "It seems to be firmly on the hook. I cannot get that this way.",
            },
        )
        [ambiguous] = parse_pages(
            {
                "White apron": real.replace("|id=1005", "|id=1005|id2=123"),
                "White apron (hanging)": display,
            }
        )
        self.assertNotIn("pickup_replacement", ambiguous)

    def test_quantity_plane_members_and_separate_timer_sources(self):
        rows = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|location=Fortress|members=No|plane=1"
                    "|3026,3637,qty:5|3021,3640,qty:5,respawn:50}}"
                )
            }
        )
        self.assertEqual(
            (rows[0]["id"], rows[0]["quantity"], rows[0]["plane"], rows[0]["members"]),
            (554, 5, 1, False),
        )
        self.assertEqual(rows[0]["infobox_respawn_ticks"], 100)
        self.assertEqual(rows[0]["unresolved_reasons"], [])
        self.assertEqual(rows[1]["tile_respawn_raw"], "50")
        self.assertIn("untyped-tile-respawn", rows[1]["unresolved_reasons"])

    def test_defaults_and_zero_id_are_preserved(self):
        row = parse_pages(
            {"Fire rune": page("{{ItemSpawnLine|name=Fire rune|1,2}}", item_id="0")}
        )[0]
        self.assertEqual(
            (row["id"], row["quantity"], row["plane"], row["members"]), (0, 1, 0, False)
        )

    def test_no_guessed_duration_or_variable_quantity(self):
        row = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|1,2,qty:1-5}}", respawn=""
                )
            }
        )[0]
        self.assertIsNone(row["quantity"])
        self.assertIsNone(row["infobox_respawn_ticks"])
        self.assertIn("unresolved-quantity", row["unresolved_reasons"])
        self.assertIn("missing-positive-infobox-respawn", row["unresolved_reasons"])

    def test_version_ambiguity_notes_and_malformed_arguments_survive(self):
        text = (
            "{{Infobox Item|name=Fire rune|id1=1|id2=2|respawn=100}}"
            "{{ItemSpawnLine|name=Fire rune|group=historical|1,2,notes:after quest|not a tile}}"
        )
        rows = parse_pages({"Fire rune": text})
        self.assertEqual(len(rows), 2)
        self.assertIn("ambiguous-item-id", rows[0]["unresolved_reasons"])
        self.assertIn(
            "coordinate-condition-or-unknown-qualifier", rows[0]["unresolved_reasons"]
        )
        self.assertIn(
            "row-selection-or-unknown-parameter", rows[0]["unresolved_reasons"]
        )
        self.assertIn("unparsed-coordinate", rows[1]["unresolved_reasons"])
        self.assertEqual(rows[0]["coordinate_qualifiers"]["notes"], "after quest")

    def test_nested_templates_and_links_do_not_split_coordinates(self):
        rows = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|location=[[Al Kharid mine|mine]] {{Refn|a|b}}|3304,3311,qty:3}}"
                )
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["x"], rows[0]["quantity"]), (3304, 3))

    def test_named_item_version_selects_its_id_and_typed_default(self):
        text = (
            "{{Infobox Item|name1=Potion(4)|id1=2428|respawn1=100"
            "|name2=Potion(1)|id2=125|respawn2=200}}"
            "{{ItemSpawnLine|name=Potion(1)|1,2}}"
        )
        row = parse_pages({"Potion": text})[0]
        self.assertEqual((row["id"], row["infobox_respawn_ticks"]), (125, 200))
        self.assertEqual(row["unresolved_reasons"], [])

    def test_repeated_positional_keys_preserve_both_raw_arguments(self):
        rows = parse_pages(
            {"Fire rune": page("{{ItemSpawnLine|name=Fire rune|1=1,2|1=3,4}}")}
        )
        self.assertEqual([(r["x"], r["y"]) for r in rows], [(1, 2), (3, 4)])
        self.assertNotEqual(rows[0]["argument_index"], rows[1]["argument_index"])
        for row in rows:
            self.assertIn("duplicate-coordinate-argument", row["unresolved_reasons"])

    def test_same_name_unknown_version_never_becomes_single_valid_id(self):
        text = (
            "{{Infobox Item|name1=Fire rune|name2=Fire rune|id1=554|id2=unknown|respawn=100}}"
            "{{ItemSpawnLine|name=Fire rune|1,2}}"
        )
        row = parse_pages({"Fire rune": text})[0]
        self.assertIsNone(row["id"])
        self.assertIn("unresolved-item-version-selector", row["unresolved_reasons"])
        self.assertEqual(row["item_versions"][1]["id_raw"], "unknown")

    def test_duplicate_qualifier_cannot_hide_variable_quantity(self):
        row = parse_pages(
            {"Fire rune": page("{{ItemSpawnLine|name=Fire rune|1,2,qty:1-5,qty:2}}")}
        )[0]
        self.assertIsNone(row["quantity"])
        self.assertEqual(
            [q["value"] for q in row["coordinate_qualifier_arguments"]], ["1-5", "2"]
        )
        self.assertIn("duplicate-coordinate-qualifier", row["unresolved_reasons"])

    def test_contradictory_row_and_infobox_selectors_stay_unresolved(self):
        row = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|members=Yes|members=No|1,2}}"
                )
            }
        )[0]
        self.assertIsNone(row["members"])
        self.assertEqual(
            [p["value"] for p in row["row_parameters"] if p["name"] == "members"],
            ["Yes", "No"],
        )
        self.assertIn("duplicate-row-parameter", row["unresolved_reasons"])
        text = (
            "{{Infobox Item|name=Fire rune|id=554|id=555|respawn=100}}"
            "{{ItemSpawnLine|name=Fire rune|1,2}}"
        )
        row = parse_pages({"Fire rune": text})[0]
        self.assertIsNone(row["id"])
        self.assertIn("unresolved-item-version-selector", row["unresolved_reasons"])

    def test_deterministic_export_and_exact_raw_page_identity(self):
        raw = json.dumps(
            {"Fire rune": page("{{ItemSpawnLine|name=Fire rune|1,2}}")}
        ).encode()
        self.assertEqual(build_export(raw), build_export(raw))
        self.assertEqual(len(build_export(raw)["rows"][0]["page_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
