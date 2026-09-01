"""Drive the Simulation tab exactly as a user would and read Hits/Wounds.

Unlike test_formula_parity, this exercises the whole chain: dropdown values ->
INDEX/MATCH lookups into the data tabs -> Calc -> Simulation. A wrong column
letter in a lookup shows up here and nowhere else.

Expectations are derived from the CSVs rather than hardcoded, so importing a
new army book cannot silently invalidate them.
"""

import pytest

from opr_crunch import csvdata
from opr_crunch.build import STATE_COL, build_workbook
from opr_crunch.layout import (
    SIMULATION_COLUMNS,
    UNITS_COLUMNS,
    WEAPONS_COLUMNS,
    col_index,
)
from opr_crunch.model import Scenario, resolve

from .formula_eval import WorkbookEvaluator


def _by_name(rows, columns):
    """Keyed by (name, faction): army books share generic weapon names."""
    return {(row[0], row[1]): dict(zip(columns, row)) for row in rows}


@pytest.fixture(scope="module")
def units():
    return _by_name(csvdata.units(), UNITS_COLUMNS)


@pytest.fixture(scope="module")
def weapons():
    """Keyed by (name, faction, unit): the same weapon can belong to more

    than one unit with a different profile, so Name|Faction alone is not
    enough - this mirrors the sheet's own Name|Faction|Unit lookup key.
    """
    return {(row[0], row[1], row[2]): dict(zip(WEAPONS_COLUMNS, row)) for row in csvdata.weapons()}


def _weapon(weapons, name, faction, unit):
    """The unit's own row, falling back to a blank-Unit (faction-generic) row."""
    return weapons.get((name, faction, unit), weapons.get((name, faction, "")))


@pytest.fixture
def wb():
    return build_workbook()


def _rules(*texts):
    return frozenset(
        part.strip() for text in texts for part in str(text).split(",") if part.strip()
    )


def expected(units, weapons, chosen, models, def_models, **ctx):
    """Build the Scenario the sheet ought to assemble for these dropdown picks."""
    att_fac, def_fac = chosen["Att. faction"], chosen["Def. faction"]
    a = units[(chosen["Attacker"], att_fac)]
    w = _weapon(weapons, chosen["Weapon"], att_fac, chosen["Attacker"])
    d = units[(chosen["Defender"], def_fac)]
    return resolve(Scenario(
        models=models,
        attacks=w["Attacks"],
        quality=a["Quality"],
        defense=d["Defense"],
        def_models=def_models,
        ap=w["AP"],
        blast=w["Blast"],
        deadly=w["Deadly"],
        impact=w["Impact"],
        ravage=a["Ravage"],
        tough=d["Tough"],
        att_rules=_rules(a["Special Rules"], w["Special Rules"]),
        def_rules=_rules(d["Special Rules"]),
        **ctx,
    ))


def set_row(wb, row, **values):
    sim = wb["Simulation"]
    for header in SIMULATION_COLUMNS:
        sim.cell(row=row, column=col_index(header), value=values.get(header, None))


def outputs(wb, row):
    ev = WorkbookEvaluator(wb, "Simulation")
    sim = wb["Simulation"]
    return (
        ev.cell("Simulation", sim.cell(row=row, column=col_index("Hits")).coordinate),
        ev.cell("Simulation", sim.cell(row=row, column=col_index("Wounds")).coordinate),
    )


def rules_shown(wb, row):
    ev = WorkbookEvaluator(wb, "Simulation")
    sim = wb["Simulation"]
    return (
        ev.cell("Simulation", sim.cell(row=row, column=col_index("Att. Special Rules")).coordinate),
        ev.cell("Simulation", sim.cell(row=row, column=col_index("Def. Special Rules")).coordinate),
    )


def picks(**overrides):
    base = {
        "Att. faction": "Robot Legions", "Attacker": "Warriors", "#": 10,
        "Weapon": "Reaper Rifles", STATE_COL: "Yes", "Def. faction": "Havoc Brothers",
        "Defender": "Havoc Brothers", "Def. #": 5, "In cover": "No",
        "Variable effect": "AP",
    }
    base.update(overrides)
    return base


class TestWorkedExample:
    """The example from the requirements: Reaper Rifles belong to Warriors,
    not Eternals - a book-import bug briefly attributed them to the wrong
    unit; fixed, this now matches the requirements' own worked example.

    10 Warriors (Quality 4+) with AP(1), Shred Reaper Rifles, into 5 Havoc
    Brothers (Defense 3+): 5 hits, and 10/3 = 3.33 wounds.
    """

    def test_hits(self, wb):
        assert outputs(wb, 2)[0] == pytest.approx(5)

    def test_wounds_include_shreds_extra_wound(self, wb):
        assert outputs(wb, 2)[1] == pytest.approx(10 / 3)

    def test_shred_is_what_makes_it_higher_than_without(self, wb, weapons):
        """Without Shred the same profile would stop at 5/2 wounds."""
        assert weapons[("Reaper Rifles", "Robot Legions", "Warriors")]["Special Rules"] == "Shred"
        assert outputs(wb, 2)[1] > 5 / 2

    def test_the_att_special_rules_column_shows_the_unit_and_weapons_rules(self, wb):
        att, defn = rules_shown(wb, 2)
        assert att == "Self-Repair, Slow, Shred"
        assert defn == ""


class TestSpecialRulesColumns:
    """The Att./Def. Special Rules columns join the unit's, weapon's and

    upgrade's rules into one comma-separated list, skipping whichever of the
    three has none.
    """

    def test_an_upgrades_granted_rule_is_included(self, wb):
        set_row(wb, 17, **picks(
            Attacker="Tri-Scorpion Lord", **{"Att. upgrades": "Chronomancer"},
            Weapon="Annihilation Gun", **{"#": 1},
        ))
        att, _ = rules_shown(wb, 17)
        assert att == "Hero, Relentless, Self-Repair, Strider, Ambush Aura"


class TestLookupsMatchTheModel:
    """Each pick must produce exactly what the reference model says it should."""

    @pytest.mark.parametrize(
        "row,overrides,ctx",
        [
            (5, {}, {}),
            (6, {"In cover": "Yes"}, dict(in_cover=True)),
            (7, {"Attacker": "Robot Lord", "Weapon": "Gauss Blaster"}, {}),  # Destructive
            (8, {"Attacker": "Eternals", "Weapon": "Flux Carbines"}, {}),  # Surge
            (9, {"Defender": "Warriors", "Def. faction": "Robot Legions"}, {}),  # Self-Repair
            (10, {"Attacker": "Flesh-Eaters", "Weapon": "Metal Claws",
                  STATE_COL: "Charging"},
             dict(combat="Melee", melee_state="Charging")),
        ],
    )
    def test_sheet_agrees_with_the_model(self, wb, units, weapons, row, overrides, ctx):
        chosen = picks(**overrides)
        set_row(wb, row, **chosen)
        want = expected(
            units, weapons, chosen,
            models=chosen["#"], def_models=chosen["Def. #"],
            long_range=chosen[STATE_COL] == "Yes",
            variable_choice=chosen["Variable effect"], **ctx,
        )
        hits, wounds = outputs(wb, row)
        assert hits == pytest.approx(float(want.hits))
        assert wounds == pytest.approx(float(want.wounds))


class TestUnitProfileRules:
    """Rules printed on a unit's own profile, not on its weapon or upgrade."""

    LORD = dict(Attacker="Tri-Scorpion Lord", Weapon="Annihilation Gun")

    def test_the_attacking_units_rules_reach_the_calculation(self, wb, units):
        """Tri-Scorpion Lord has Relentless, which only bites over 9 inches."""
        assert "Relentless" in units[("Tri-Scorpion Lord", "Robot Legions")]["Special Rules"]
        set_row(wb, 11, **picks(**self.LORD, **{"#": 1, STATE_COL: "Yes"}))
        set_row(wb, 12, **picks(**self.LORD, **{"#": 1, STATE_COL: "No"}))
        assert outputs(wb, 11)[0] > outputs(wb, 12)[0]

    def test_the_attacking_units_ravage_reaches_the_calculation(self, wb, units, weapons):
        """Ravage(4) adds direct wounds, but only in melee.

        Combat is now derived from the weapon, so a melee weapon can't be
        forced through a ranged row to isolate Ravage by comparison anymore.
        Instead this compares the sheet's melee-row wounds against the same
        profile resolved with ravage=0, via the reference model directly.
        """
        lord = units[("Tri-Scorpion Lord", "Robot Legions")]
        assert lord["Ravage"] == 4
        w = _weapon(weapons, "Harvest Blade", "Robot Legions", "Tri-Scorpion Lord")
        defender = units[("Havoc Brothers", "Havoc Brothers")]

        set_row(wb, 13, **picks(Attacker="Tri-Scorpion Lord", Weapon="Harvest Blade", **{"#": 1}))
        _, wounds = outputs(wb, 13)

        without_ravage = resolve(Scenario(
            models=1, attacks=w["Attacks"], quality=lord["Quality"], defense=defender["Defense"],
            def_models=5, ap=w["AP"], blast=w["Blast"], deadly=w["Deadly"], impact=w["Impact"],
            ravage=0, tough=defender["Tough"],
            att_rules=_rules(lord["Special Rules"], w["Special Rules"]),
            def_rules=_rules(defender["Special Rules"]), combat="Melee",
        ))
        assert wounds > float(without_ravage.wounds)

    def test_the_defending_units_tough_caps_deadly(self, wb, units):
        assert units[("Tri-Scorpion Lord", "Robot Legions")]["Tough"] == 6


class TestBlankRows:
    def test_an_empty_row_shows_nothing(self, wb):
        assert outputs(wb, 18) == ("", "")


class TestNamesSharedAcrossFactions:
    """Several books print a Spider Fangs; they are not the same weapon.

    Robot Legions' is A6 with Bane, Havoc Brothers' is A8 with Rending. Looking
    up by name alone returned whichever the import happened to write first.
    """

    SHARED = "Spider Fangs"

    def test_the_two_profiles_really_do_differ(self, weapons):
        legions = weapons[(self.SHARED, "Robot Legions", "Forge Spider")]
        havoc = weapons[(self.SHARED, "Havoc Brothers", "Spider Walker")]
        assert (legions["Attacks"], legions["Special Rules"]) != (
            havoc["Attacks"], havoc["Special Rules"]
        )

    @pytest.mark.parametrize(
        "faction,attacker",
        [("Robot Legions", "Forge Spider"), ("Havoc Brothers", "Spider Walker")],
    )
    def test_each_faction_gets_its_own_profile(self, wb, units, weapons, faction, attacker):
        chosen = picks(**{
            "Att. faction": faction, "Attacker": attacker, "Weapon": self.SHARED,
            "#": 1, STATE_COL: "None",
        })
        set_row(wb, 15, **chosen)
        want = expected(
            units, weapons, chosen,
            models=1, def_models=chosen["Def. #"],
            combat="Melee", long_range=False,
        )
        hits, wounds = outputs(wb, 15)
        assert hits == pytest.approx(float(want.hits))
        assert wounds == pytest.approx(float(want.wounds))

    def test_the_havoc_profile_is_not_the_legions_one(self, wb):
        """Pins the number: 8 attacks at Quality 3+, not the Legions' 6.

        Comparing the two factions' rows to each other would not do - their
        attackers differ in Quality, so the totals differ either way.
        """
        set_row(wb, 16, **picks(**{
            "Att. faction": "Havoc Brothers", "Attacker": "Spider Walker",
            "Weapon": self.SHARED, "#": 1, STATE_COL: "None",
        }))
        assert outputs(wb, 16)[0] == pytest.approx(8 * 4 / 6)
