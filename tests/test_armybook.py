"""Parsing an OPR army-book PDF's extracted text.

Snippets below are copied verbatim from `pdftotext -layout` output of
GF - Robot Legions v3.5.3, including its column alignment.
"""

import pytest

from opr_crunch import armybook


class TestParseProfile:
    def test_a_ranged_weapon(self):
        got = armybook.parse_profile('18", A2, AP(1), Blast(3)')
        assert got == dict(range=18, attacks=2, ap=1, blast=3, deadly=0, impact=0, rules=[])

    def test_a_melee_weapon_has_no_range(self):
        got = armybook.parse_profile("A2, AP(1)")
        assert got["range"] == 0
        assert got["attacks"] == 2
        assert got["ap"] == 1

    def test_named_rules_are_collected(self):
        got = armybook.parse_profile('18", A1, AP(1), Shred')
        assert got["rules"] == ["Shred"]

    def test_several_named_rules_keep_their_order(self):
        got = armybook.parse_profile('24", A1, AP(1), Reliable, Takedown')
        assert got["rules"] == ["Reliable", "Takedown"]

    def test_deadly_and_impact_are_numeric(self):
        got = armybook.parse_profile("A2, AP(2), Deadly(3)")
        assert got["deadly"] == 3 and got["impact"] == 0

    def test_a_bare_attack_count(self):
        assert armybook.parse_profile("A6")["attacks"] == 6

    def test_table_debris_wrapped_into_a_rule_is_stripped(self):
        """A profile can wrap onto a line carrying the next row's stat cells."""
        got = armybook.parse_profile('12", A2, AP(1), Blast(3), 3+ 2+ Reliable')
        assert got["rules"] == ["Reliable"]

    def test_a_nested_weapon_profile_is_not_a_rule(self):
        got = armybook.parse_profile("A2, AP(4), Wraith Spear (A2, AP(4), Deadly(3))")
        assert got["rules"] == []


class TestWeaponNames:
    def test_a_clean_inline_profile(self):
        found = armybook.find_weapons('Lord Gauss Pistol (12", A2, Destructive)')
        assert "Lord Gauss Pistol" in found

    def test_a_count_prefix_is_stripped(self):
        found = armybook.find_weapons('5x Reaper Rifles (18", A1, AP(1), Shred)')
        assert "Reaper Rifles" in found

    def test_table_debris_before_the_name_is_discarded(self):
        """Scrambled table columns leave junk ahead of the real weapon name."""
        line = "A2       - Destructive             Gauss Blaster (18\", A4, Destructive)"
        assert list(armybook.find_weapons(line)) == ["Gauss Blaster"]

    def test_nested_parentheses_do_not_truncate_the_profile(self):
        found = armybook.find_weapons("Hyper Sword (A3, AP(1), Rending)")
        assert found["Hyper Sword"]["ap"] == 1
        assert found["Hyper Sword"]["rules"] == ["Rending"]

    def test_non_weapon_parentheses_are_ignored(self):
        assert armybook.find_weapons("Warden (Relentless Aura)") == {}

    def test_a_preceding_line_does_not_bleed_into_the_name(self):
        text = 'Equipment\n                 1x Annihilation Gun (18", A2, AP(1))'
        assert list(armybook.find_weapons(text)) == ["Annihilation Gun"]

    def test_a_count_split_across_columns_is_dropped(self):
        text = '5x    Reaper Rifles (18", A1, AP(1), Shred)'
        assert list(armybook.find_weapons(text)) == ["Reaper Rifles"]

    def test_a_unit_header_on_the_same_line_is_stripped(self):
        text = 'Support Platform [1] 3+ 2+ 1x Ray Caster (18", A2, AP(4), Unstoppable)'
        assert list(armybook.find_weapons(text)) == ["Ray Caster"]

    def test_an_earlier_profile_on_the_line_is_not_part_of_the_name(self):
        text = 'Rod-Shots (12", A2, AP(1)), Rod-Blade (A2, AP(1))'
        assert list(armybook.find_weapons(text)) == ["Rod-Shots", "Rod-Blade"]

    def test_a_name_with_an_unbalanced_bracket_is_rejected(self):
        """Scrambled cells can leave a stray open bracket glued to a name."""
        text = "Great Wraith (Wraith Spear (A2, AP(4), Deadly(3))"
        assert all("(" not in name for name in armybook.find_weapons(text))


class TestWeaponVariants:
    """Names must stay unique: the sheet's lookups match on name alone."""

    def test_one_profile_keeps_the_plain_name(self):
        assert list(armybook.find_weapons("CCW (A2)")) == ["CCW"]

    def test_conflicting_profiles_are_disambiguated_by_attacks(self):
        found = armybook.find_weapons("CCW (A2)\nCCW (A1)\nCCW (A3)")
        assert sorted(found) == ["CCW (A1)", "CCW (A2)", "CCW (A3)"]

    def test_a_repeated_identical_profile_is_not_duplicated(self):
        assert list(armybook.find_weapons("CCW (A2)\nCCW (A2)")) == ["CCW"]


class TestParseUnits:
    PAGE = "\n".join([
        "GF - ROBOT LEGIONS V3.5.3",
        "",
        "                     Tri-Scorpion Lord [1] - 205pts"
        "                                                       Robot Lord [1] - 45pts",
        "",
        "Quality 3+                          Defense 3+       Tough 6"
        "                                  Quality 3+       Defense 3+              Tough 3",
        "",
        "Hero, Ravage(4), Relentless, Self-Repair, Strider, Tough(6)"
        "                    Hero, Self-Repair, Shielded, Slow, Tough(3)",
    ])

    @pytest.fixture
    def units(self):
        return {u["name"]: u for u in armybook.parse_units([self.PAGE])}

    def test_both_columns_are_read(self, units):
        assert set(units) == {"Tri-Scorpion Lord", "Robot Lord"}

    def test_stats_attach_to_the_right_card(self, units):
        assert units["Robot Lord"]["quality"] == 3
        assert units["Robot Lord"]["defense"] == 3

    def test_size_comes_from_the_bracket(self, units):
        assert units["Tri-Scorpion Lord"]["size"] == 1

    def test_cost_comes_from_the_card(self, units):
        assert units["Tri-Scorpion Lord"]["cost"] == 205
        assert units["Robot Lord"]["cost"] == 45

    def test_rules_do_not_bleed_across_the_column_gutter(self, units):
        assert "Shielded" in units["Robot Lord"]["rules"]
        assert "Shielded" not in units["Tri-Scorpion Lord"]["rules"]

    def test_parameterised_rules_are_pulled_into_columns(self, units):
        assert units["Tri-Scorpion Lord"]["ravage"] == 4
        assert units["Tri-Scorpion Lord"]["tough"] == 6

    def test_parameterised_rules_leave_the_rules_text(self, units):
        """Ravage and Tough have numeric columns, so they aren't repeated."""
        assert "Ravage" not in units["Tri-Scorpion Lord"]["rules"]
        assert "Tough" not in units["Tri-Scorpion Lord"]["rules"]

    def test_plain_rules_are_kept(self, units):
        assert units["Tri-Scorpion Lord"]["rules"] == ["Hero", "Relentless", "Self-Repair", "Strider"]


class TestSingleRuleUnits:
    """A unit with only one rule prints it with no comma at all - taken verbatim
    from Havoc Brothers v3.5.3, where this used to leave Cultists' rules blank.
    """

    PAGE = "\n".join([
        "GF - HAVOC BROTHERS V3.5.3",
        "",
        "                               Cultists [10] - 140pts"
        "                                            Chosen Havoc Brothers [3] - 120pts",
        "",
        "                          Quality 5+       Defense 5+"
        "                                                    Quality 3+        Defense 3+",
        "",
        "Havocbound                                                                      "
        "Havocbound, Versatile Attack",
        "",
        "Weapon                         RNG         ATK             AP        SPE        "
        "Weapon                                RNG        ATK          AP    SPE",
    ])

    @pytest.fixture
    def units(self):
        return {u["name"]: u for u in armybook.parse_units([self.PAGE])}

    def test_a_lone_rule_with_no_comma_is_still_read(self, units):
        assert units["Cultists"]["rules"] == ["Havocbound"]

    def test_the_comma_separated_neighbour_is_unaffected(self, units):
        assert units["Chosen Havoc Brothers"]["rules"] == ["Havocbound", "Versatile Attack"]

    def test_the_weapon_table_header_is_never_mistaken_for_a_rule(self, units):
        assert "Weapon" not in units["Cultists"]["rules"]


class TestLinkedWeaponsAndUpgrades:
    """Weapons and upgrades are tagged with the unit card they're printed under."""

    PAGE = "\n".join([
        "GF - ROBOT LEGIONS V3.5.3",
        "",
        "Warriors [5] - 65pts",
        "Quality 4+ Defense 3+",
        'CCW (A1), Reaper Rifles (18", A1, AP(1), Shred), Sergeant (Relentless Aura)',
        "",
        "Eternals [5] - 90pts",
        "Quality 3+ Defense 3+",
        'CCW (A1), Flux Carbines (18", A1, AP(1), Surge)',
    ])

    @pytest.fixture
    def weapons(self):
        return armybook.linked_weapons(["", "", "", self.PAGE])

    @pytest.fixture
    def upgrades(self):
        return armybook.linked_upgrades(["", "", "", self.PAGE])

    def test_a_weapon_only_one_unit_has_is_tagged_to_that_unit(self, weapons):
        owners = {unit for unit, name, _ in weapons if name == "Reaper Rifles"}
        assert owners == {"Warriors"}

    def test_a_name_shared_by_two_units_becomes_two_rows(self, weapons):
        rows = [(unit, name) for unit, name, _ in weapons if name == "CCW"]
        assert sorted(rows) == [("Eternals", "CCW"), ("Warriors", "CCW")]

    def test_a_units_own_profile_does_not_bleed_into_its_neighbour(self, weapons):
        eternals_weapons = {name for unit, name, _ in weapons if unit == "Eternals"}
        assert "Reaper Rifles" not in eternals_weapons

    def test_an_upgrade_is_tagged_to_its_unit(self, upgrades):
        rows = [(unit, name) for unit, name, _ in upgrades]
        assert ("Warriors", "Sergeant") in rows
        assert not any(unit == "Eternals" and name == "Sergeant" for unit, name in rows)


class TestWeaponCosts:
    """A unit's listed price already includes its starting weapons.

    Only a swap costs extra, so the two must be priced differently even though
    both end up as rows on the Weapons tab.
    """

    ROSTER = 'Reaper Rifles (18", A1, AP(1), Shred)'
    CARD = "\n".join([
        "GF - ROBOT LEGIONS V3.5.3",
        "",
        "Warriors [5] - 100pts",
        "Quality 4+ Defense 4+",
        "Weapon                              RNG     ATK           AP SPE",
        "5x Reaper Rifles",
        "Replace all Reaper Rifles",
        'Gauss Rifle (24", A1, Destructive)                                  +10pts',
    ])

    def costs_for(self, card):
        rows = armybook.linked_weapons([self.ROSTER, "", "", card])
        return {(unit, name): w["cost"] for unit, name, w in rows}

    def test_a_starting_weapon_is_already_paid_for(self):
        assert self.costs_for(self.CARD)[("Warriors", "Reaper Rifles")] == 0

    def test_a_swap_option_costs_extra(self):
        assert self.costs_for(self.CARD)[("Warriors", "Gauss Rifle")] == 10

    def test_a_starting_weapon_printed_inline_too_stays_free(self):
        """Both paths can find the same weapon; being a starting weapon wins."""
        card = "\n".join([
            "Warriors [5] - 100pts",
            "Quality 4+ Defense 4+",
            'Reaper Rifles (18", A1, AP(1), Shred)',
            "Weapon                              RNG     ATK           AP SPE",
            "5x Reaper Rifles",
        ])
        rows = armybook.linked_weapons([self.ROSTER, "", "", card])
        assert [w["cost"] for _, name, w in rows if name == "Reaper Rifles"] == [0]


class TestStartingWeapons:
    """A starting weapon's name lives on the unit's own card; its profile only
    ever appears, unattributed, as inline ``Name (...)`` text on the roster
    page. ``pdftotext -layout`` does not reliably keep the roster's rows in
    step with the unit each is meant to be under - see the fixture below,
    copied verbatim from Robot Legions v3.5.3: "Warriors" visually carries
    "Lord Gauss Pistol", which actually belongs to a different unit's row
    that wrapped. Cross-referencing the card's name against the roster's
    profiles by name, rather than trusting row position, recovers the real
    pairing (Warriors -> Reaper Rifles) instead of the wrong one.
    """

    ROSTER_PAGE = "\n".join([
        "GF - ROBOT LEGIONS V3.5.3",
        "",
        'Warriors [5]            3+ 3+ 1x Lord Gauss Pistol (12", A2, Destructive)   Self-Repair, Slow   100pts',
        "                                    2x CCWs (A2)",
        'Eternals [5]            4+ 4+ 5x Reaper Rifles (18", A1, AP(1), Shred)      Self-Repair, Slow   150pts',
    ])

    CARD_PAGE = "\n".join([
        "GF - ROBOT LEGIONS V3.5.3",
        "",
        "                               Warriors [5] - 100pts",
        "                   Quality 4+               Defense 4+",
        "Self-Repair, Slow",
        "Weapon                              RNG     ATK           AP SPE",
        "5x Reaper Rifles",
        '5x CCWs                             18"     A1            1      Shred',
        "",
        '                                    -       A1            -      -',
    ])

    def weapons(self):
        return armybook.linked_weapons(["", "", self.ROSTER_PAGE, self.CARD_PAGE])

    def test_the_roster_row_shift_does_not_misattribute_the_weapon(self):
        owners = {(unit, name) for unit, name, _ in self.weapons()}
        assert ("Warriors", "Reaper Rifles") in owners
        assert ("Warriors", "Lord Gauss Pistol") not in owners

    def test_the_profile_still_comes_from_the_roster_despite_the_shift(self):
        profiles = {(unit, name): p for unit, name, p in self.weapons()}
        reaper = profiles["Warriors", "Reaper Rifles"]
        assert (reaper["range"], reaper["attacks"], reaper["ap"]) == (18, 1, 1)
        assert reaper["rules"] == ["Shred"]

    def test_a_second_weapon_named_on_the_cards_own_line_is_also_found(self):
        owners = {(unit, name) for unit, name, _ in self.weapons()}
        assert ("Warriors", "CCWs") in owners


class TestParseSpecialRules:
    PAGE = "\n".join([
        "GF - ROBOT LEGIONS V3.5.3",
        "",
        "Self-Repair: When a unit where all models have this      ignored."
        "                                                 Swift: This model may ignore the Slow rule.",
        "rule takes wounds, roll one die for each. On a 6+ it is",
        "ignored.                                                 Protection Feat: Once per game, when this unit",
    ])

    def test_a_definition_is_captured(self):
        rules = dict(armybook.parse_special_rules(self.PAGE))
        assert rules["Self-Repair"].startswith("When a unit where all models have this rule takes wounds")

    def test_wrapped_lines_are_rejoined(self):
        rules = dict(armybook.parse_special_rules(self.PAGE))
        assert rules["Self-Repair"].endswith("On a 6+ it is ignored.")

    def test_other_columns_are_found_too(self):
        rules = dict(armybook.parse_special_rules(self.PAGE))
        assert rules["Swift"] == "This model may ignore the Slow rule."


class TestDetectFaction:
    """Every army book names itself on the first line of every page."""

    def test_reads_the_faction_from_the_header(self):
        assert armybook.detect_faction("GF - ROBOT LEGIONS V3.5.3\nName [Size]") == "Robot Legions"

    def test_other_game_systems_use_the_same_shape(self):
        assert armybook.detect_faction("AoF - DWARF GUILDS V3.4.0") == "Dwarf Guilds"

    def test_hyphenated_names_keep_both_capitals(self):
        assert armybook.detect_faction("GF - WRAITH-SHARD HOST V1.0") == "Wraith-Shard Host"

    def test_a_book_without_a_header_returns_nothing(self):
        assert armybook.detect_faction("just some text") is None


class TestSources:
    @pytest.mark.parametrize("url", [
        "https://army-forge.opr-cdn.com/a/b.pdf",
        "http://example.com/book.pdf",
    ])
    def test_a_url_is_recognised(self, url):
        assert armybook.is_url(url)

    @pytest.mark.parametrize("path", [
        r"C:\Users\me\book.pdf", "books/book.pdf", "./book.txt",
    ])
    def test_a_local_path_is_not_a_url(self, path):
        assert not armybook.is_url(path)

    def test_cache_name_uses_the_final_path_segment(self):
        assert armybook.cache_name("https://host/army-books/pdfs/x/abc123.pdf") == "abc123.pdf"

    def test_cache_name_adds_a_pdf_suffix(self):
        assert armybook.cache_name("https://host/download/9f8e7d").endswith(".pdf")

    def test_cache_name_ignores_a_query_string(self):
        assert armybook.cache_name("https://host/book.pdf?token=abc") == "book.pdf"

    def test_cache_name_cannot_escape_its_directory(self):
        """A crafted URL must not write outside books/."""
        name = armybook.cache_name("https://host/../../etc/passwd")
        assert "/" not in name and "\\" not in name and ".." not in name


class TestParseUpgrades:
    def test_a_rule_granting_upgrade(self):
        got = dict(armybook.parse_upgrades("Warden (Relentless Aura)"))
        assert got["Warden"] == ["Relentless Aura"]

    def test_several_granted_rules(self):
        got = dict(armybook.parse_upgrades("Jetpack (Ambush, Flying, Swift)"))
        assert got["Jetpack"] == ["Ambush", "Flying", "Swift"]

    def test_weapon_options_are_not_upgrades(self):
        assert dict(armybook.parse_upgrades('Wrist-Plasma (24", A1, AP(4))')) == {}

    def test_parameterised_grants_are_kept_whole(self):
        got = dict(armybook.parse_upgrades("Technomancer (Caster(2))"))
        assert got["Technomancer"] == ["Caster(2)"]

    def test_the_previous_line_is_not_part_of_the_name(self):
        got = dict(armybook.parse_upgrades("Doom Ray\nWarp Gate (Ambush)"))
        assert list(got) == ["Warp Gate"]


class TestRowsInBand:
    WORDS = [
        {"text": "Plasma", "x0": 10, "top": 100},
        {"text": "Caster", "x0": 45, "top": 100},
        {"text": "+10pts", "x0": 200, "top": 100},
        {"text": "Flame", "x0": 10, "top": 120},
        {"text": "Caster", "x0": 40, "top": 120},
        {"text": "+15pts", "x0": 200, "top": 120},
        {"text": "Other", "x0": 300, "top": 100},  # outside the x-range
    ]

    def test_words_join_into_one_row_by_rounded_top(self):
        rows = armybook._rows_in_band(self.WORDS, x_min=0, x_max=250, top_min=0, top_max=1000)
        assert rows == [
            (100, "Plasma Caster +10pts"),
            (120, "Flame Caster +15pts"),
        ]

    def test_words_outside_the_x_range_are_excluded(self):
        rows = armybook._rows_in_band(self.WORDS, x_min=0, x_max=250, top_min=0, top_max=1000)
        assert "Other" not in " ".join(text for _, text in rows)

    def test_words_outside_the_top_range_are_excluded(self):
        rows = armybook._rows_in_band(self.WORDS, x_min=0, x_max=250, top_min=0, top_max=110)
        assert rows == [(100, "Plasma Caster +10pts")]

    def test_a_row_close_but_not_identical_top_still_groups(self):
        """pdfplumber tops within the same visual row can differ by a fraction
        of a point between words; rounding to the nearest point groups them."""
        words = [
            {"text": "A", "x0": 0, "top": 100.2},
            {"text": "B", "x0": 10, "top": 99.8},
        ]
        rows = armybook._rows_in_band(words, x_min=0, x_max=100, top_min=0, top_max=1000)
        assert rows == [(100, "A B")]


class TestBandBounds:
    def test_two_well_separated_anchors_split_at_the_midpoint(self):
        bounds = armybook._band_bounds([126.0, 402.0])
        assert bounds[0] == (-1, pytest.approx(264.0))
        assert bounds[1] == (pytest.approx(264.0), float("inf"))

    def test_a_single_anchor_covers_everything(self):
        assert armybook._band_bounds([126.0]) == [(-1, float("inf"))]

    def test_anchors_closer_than_the_gap_merge_into_one_band(self):
        """Two words of the same card's name (e.g. a two-word unit name) must
        not be mistaken for two separate cards."""
        bounds = armybook._band_bounds([126.0, 140.0, 402.0])
        assert len(bounds) == 2
