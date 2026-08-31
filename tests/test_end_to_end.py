"""Drive the Simulation tab exactly as a user would and read Hits/Wounds.

Unlike test_formula_parity, this exercises the whole chain: dropdown values ->
INDEX/MATCH lookups into the data tabs -> Calc -> Simulation. A wrong column
letter in a lookup shows up here and nowhere else.
"""

import pytest

from opr_crunch.build import build_workbook
from opr_crunch.layout import col_index

from .formula_eval import WorkbookEvaluator


def set_row(wb, row, **values):
    sim = wb["Simulation"]
    for header, value in values.items():
        sim.cell(row=row, column=col_index(header), value=value)


def outputs(wb, row):
    ev = WorkbookEvaluator(wb, "Simulation")
    sim = wb["Simulation"]
    hits = sim.cell(row=row, column=col_index("Hits")).coordinate
    wounds = sim.cell(row=row, column=col_index("Wounds")).coordinate
    return ev.cell("Simulation", hits), ev.cell("Simulation", wounds)


@pytest.fixture
def wb():
    return build_workbook()


WARRIORS_VS_BROTHERS = dict(
    **{
        "Att. faction": "Robot Legions",
        "Attacker": "Warrior",
        "#": 10,
        "Weapon": "Reaper rifle",
        "Combat": "Ranged",
        "Melee state": "None",
        'Range >9"': "Yes",
        "Def. faction": "Havoc Brothers",
        "Defender": "Battle Brother",
        "Def. #": 5,
        "In cover": "No",
    }
)


class TestWorkedExample:
    """10 Warriors (Q4) with AP(1) Reaper rifles vs 5 Battle Brothers (D3)."""

    def test_seeded_example_row_is_the_worked_example(self, wb):
        hits, wounds = outputs(wb, 2)
        assert hits == pytest.approx(5.0)
        assert wounds == pytest.approx(2.5)

    def test_cover_pulls_the_defence_back_to_a_three_up(self, wb):
        set_row(wb, 3, **{**WARRIORS_VS_BROTHERS, "In cover": "Yes"})
        hits, wounds = outputs(wb, 3)
        assert hits == pytest.approx(5.0)
        assert wounds == pytest.approx(5 * 2 / 6)


class TestLookups:
    def test_weapon_attacks_are_read_from_the_weapons_tab(self, wb):
        # Assault rifle has 2 attacks; 10 Battle Brothers at Quality 3.
        set_row(wb, 4, **{
            **WARRIORS_VS_BROTHERS,
            "Att. faction": "Havoc Brothers",
            "Attacker": "Battle Brother",
            "Weapon": "Assault rifle",
        })
        hits, _ = outputs(wb, 4)
        assert hits == pytest.approx(20 * 4 / 6)

    def test_upgrade_special_rules_reach_the_calculation(self, wb):
        # Targeting matrix grants Relentless: +1 hit per natural 6 over 9".
        set_row(wb, 5, **{**WARRIORS_VS_BROTHERS, "Att. upgrades": "Targeting matrix"})
        hits, _ = outputs(wb, 5)
        assert hits == pytest.approx(5.0 + 10 / 6)

    def test_defender_unit_special_rules_reach_the_calculation(self, wb):
        # Immortals (D3) have innate Regeneration.
        set_row(wb, 6, **{
            **WARRIORS_VS_BROTHERS,
            "Def. faction": "Robot Legions",
            "Defender": "Immortal",
        })
        _, wounds = outputs(wb, 6)
        assert wounds == pytest.approx(2.5 * 2 / 3)

    def test_weapon_rules_column_is_read(self, wb):
        # Gauss blaster: 2 attacks, AP(1), Rending.
        set_row(wb, 7, **{**WARRIORS_VS_BROTHERS, "Weapon": "Gauss blaster"})
        hits, wounds = outputs(wb, 7)
        assert hits == pytest.approx(10.0)
        # 20 dice: 20/6 natural 6s at AP5 (blocked only by a 6), rest at AP1.
        assert wounds == pytest.approx(20 / 6 * 5 / 6 + (10 - 20 / 6) * 3 / 6)


class TestBlankRows:
    def test_an_empty_row_shows_nothing(self, wb):
        hits, wounds = outputs(wb, 12)
        assert hits == ""
        assert wounds == ""


class TestMelee:
    def test_impact_hits_are_added_on_a_charge(self, wb):
        # Smashing fists: 2 attacks, AP(1), Impact(1). 10 models charging.
        set_row(wb, 8, **{
            **WARRIORS_VS_BROTHERS,
            "Weapon": "Smashing fists",
            "Combat": "Melee",
            "Melee state": "Charging",
        })
        hits, _ = outputs(wb, 8)
        assert hits == pytest.approx(20 * 3 / 6 + 10 * 5 / 6)

    def test_fatigued_attackers_only_land_sixes(self, wb):
        set_row(wb, 9, **{
            **WARRIORS_VS_BROTHERS,
            "Weapon": "Smashing fists",
            "Combat": "Melee",
            "Melee state": "Fatigued",
        })
        hits, _ = outputs(wb, 9)
        assert hits == pytest.approx(20 / 6)
