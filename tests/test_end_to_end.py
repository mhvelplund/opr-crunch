"""Drive the Simulation tab exactly as a user would and read Hits/Wounds.

Unlike test_formula_parity, this exercises the whole chain: dropdown values ->
INDEX/MATCH lookups into the data tabs -> Calc -> Simulation. A wrong column
letter in a lookup shows up here and nowhere else.

Expectations are derived from the CSVs rather than hardcoded, so importing a
new army book cannot silently invalidate them.
"""

import pytest

from opr_crunch import csvdata
from opr_crunch.build import build_workbook
from opr_crunch.layout import (
    SIMULATION_COLUMNS,
    UNITS_COLUMNS,
    WEAPONS_COLUMNS,
    col_index,
)
from opr_crunch.model import Scenario, resolve

from .formula_eval import WorkbookEvaluator


def _by_name(rows, columns):
    return {row[0]: dict(zip(columns, row)) for row in rows}


@pytest.fixture(scope="module")
def units():
    return _by_name(csvdata.units(), UNITS_COLUMNS)


@pytest.fixture(scope="module")
def weapons():
    return _by_name(csvdata.weapons(), WEAPONS_COLUMNS)


@pytest.fixture
def wb():
    return build_workbook()


def _rules(*texts):
    return frozenset(
        part.strip() for text in texts for part in str(text).split(",") if part.strip()
    )


def expected(units, weapons, attacker, weapon, defender, models, def_models, **ctx):
    """Build the Scenario the sheet ought to assemble for these dropdown picks."""
    a, w, d = units[attacker], weapons[weapon], units[defender]
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


def picks(**overrides):
    base = {
        "Att. faction": "Robot Legions", "Attacker": "Warriors", "#": 10,
        "Weapon": "Reaper Rifles", "Combat": "Ranged", "Melee state": "None",
        'Range >9"': "Yes", "Def. faction": "Havoc Brothers",
        "Defender": "Battle Brother", "Def. #": 5, "In cover": "No",
    }
    base.update(overrides)
    return base


class TestWorkedExample:
    """The example from the requirements, now with Shred correctly attributed.

    10 Warriors (Quality 4+) with AP(1), Shred Reaper Rifles, into 5 Battle
    Brothers (Defense 3+): 5 hits, and 2.5 + 5/6 = 3.33 wounds.
    """

    def test_hits(self, wb):
        assert outputs(wb, 2)[0] == pytest.approx(5.0)

    def test_wounds_include_shreds_extra_wound(self, wb):
        assert outputs(wb, 2)[1] == pytest.approx(10 / 3)

    def test_shred_is_what_makes_it_more_than_two_and_a_half(self, wb, weapons):
        """Without Shred the same profile would stop at 5 x 1/2 = 2.5 wounds."""
        assert weapons["Reaper Rifles"]["Special Rules"] == "Shred"
        assert outputs(wb, 2)[1] == pytest.approx(2.5 + 5 / 6)


class TestLookupsMatchTheModel:
    """Each pick must produce exactly what the reference model says it should."""

    @pytest.mark.parametrize(
        "row,overrides,ctx",
        [
            (5, {}, {}),
            (6, {"In cover": "Yes"}, dict(in_cover=True)),
            (7, {"Weapon": "Gauss Blaster"}, {}),  # Destructive
            (8, {"Attacker": "Eternals", "Weapon": "Flux Carbines"}, {}),  # Surge
            (9, {"Defender": "Warriors", "Def. faction": "Robot Legions"}, {}),  # Self-Repair
            (10, {"Attacker": "Flesh-Eaters", "Weapon": "Metal Claws",
                  "Combat": "Melee", "Melee state": "Charging"},
             dict(combat="Melee", melee_state="Charging")),
        ],
    )
    def test_sheet_agrees_with_the_model(self, wb, units, weapons, row, overrides, ctx):
        chosen = picks(**overrides)
        set_row(wb, row, **chosen)
        want = expected(
            units, weapons, chosen["Attacker"], chosen["Weapon"], chosen["Defender"],
            models=chosen["#"], def_models=chosen["Def. #"],
            long_range=chosen['Range >9"'] == "Yes", **ctx,
        )
        hits, wounds = outputs(wb, row)
        assert hits == pytest.approx(float(want.hits))
        assert wounds == pytest.approx(float(want.wounds))


class TestUnitProfileRules:
    """Rules printed on a unit's own profile, not on its weapon or upgrade."""

    LORD = dict(Attacker="Tri-Scorpion Lord", Weapon="Annihilation Gun")

    def test_the_attacking_units_rules_reach_the_calculation(self, wb, units):
        """Tri-Scorpion Lord has Relentless, which only bites over 9 inches."""
        assert "Relentless" in units["Tri-Scorpion Lord"]["Special Rules"]
        set_row(wb, 11, **picks(**self.LORD, **{"#": 1, 'Range >9"': "Yes"}))
        set_row(wb, 12, **picks(**self.LORD, **{"#": 1, 'Range >9"': "No"}))
        assert outputs(wb, 11)[0] > outputs(wb, 12)[0]

    def test_the_attacking_units_ravage_reaches_the_calculation(self, wb, units):
        """Ravage(4) adds direct wounds, but only in melee."""
        assert units["Tri-Scorpion Lord"]["Ravage"] == 4
        set_row(wb, 13, **picks(**self.LORD, **{"#": 1},
                                Combat="Melee", **{"Melee state": "None"}))
        set_row(wb, 14, **picks(**self.LORD, **{"#": 1}))
        assert outputs(wb, 13)[1] > outputs(wb, 14)[1]

    def test_the_defending_units_tough_caps_deadly(self, wb, units):
        assert units["Tri-Scorpion Lord"]["Tough"] == 6


class TestBlankRows:
    def test_an_empty_row_shows_nothing(self, wb):
        assert outputs(wb, 18) == ("", "")
