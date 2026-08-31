"""Structure of the generated workbook."""

import pytest
from openpyxl import load_workbook

from opr_crunch.build import build_workbook
from opr_crunch.layout import SIMULATION_COLUMNS, SIM_FIRST_ROW, SIM_ROWS


@pytest.fixture(scope="module")
def wb():
    return build_workbook()


def headers(sheet):
    return [c.value for c in sheet[1]]


class TestTabs:
    def test_simulation_is_the_leftmost_tab(self, wb):
        assert wb.sheetnames[0] == "Simulation"

    def test_all_tabs_are_present(self, wb):
        assert wb.sheetnames == [
            "Simulation",
            "Units",
            "Weapons",
            "Upgrades",
            "Special rules",
            "Factions",
            "Lists",
            "Calc",
            "Tests",
        ]

    @pytest.mark.parametrize("name", ["Lists", "Calc", "Tests"])
    def test_working_tabs_are_hidden(self, wb, name):
        assert wb[name].sheet_state == "hidden"

    @pytest.mark.parametrize(
        "name", ["Simulation", "Units", "Weapons", "Upgrades", "Special rules", "Factions"]
    )
    def test_content_tabs_are_visible(self, wb, name):
        assert wb[name].sheet_state == "visible"


class TestSimulationTab:
    def test_headers_match_the_spec(self, wb):
        assert headers(wb["Simulation"]) == SIMULATION_COLUMNS

    def test_hits_and_wounds_are_the_last_two_columns(self, wb):
        assert SIMULATION_COLUMNS[-2:] == ["Hits", "Wounds"]

    def test_every_row_has_a_hits_formula(self, wb):
        sim = wb["Simulation"]
        col = SIMULATION_COLUMNS.index("Hits") + 1
        for row in range(SIM_FIRST_ROW, SIM_FIRST_ROW + SIM_ROWS):
            assert str(sim.cell(row=row, column=col).value).startswith("=")

    def test_hits_delegates_to_the_calc_tab(self, wb):
        sim = wb["Simulation"]
        col = SIMULATION_COLUMNS.index("Hits") + 1
        assert "Calc!" in sim.cell(row=SIM_FIRST_ROW, column=col).value


class TestDataTabs:
    def test_units_headers(self, wb):
        assert headers(wb["Units"]) == ["Name", "Faction", "Quality", "Defense", "Special Rules"]

    def test_weapons_headers(self, wb):
        assert headers(wb["Weapons"]) == [
            "Name", "Faction", "Attacks", "AP", "Blast", "Deadly", "Impact", "Special Rules",
        ]

    def test_upgrades_headers(self, wb):
        assert headers(wb["Upgrades"]) == [
            "Name", "Faction", "AP", "Blast", "Deadly", "Impact", "Special Rules",
        ]

    def test_factions_are_seeded(self, wb):
        names = [r[0].value for r in wb["Factions"].iter_rows(min_row=2) if r[0].value]
        assert "Robot Legions" in names

    def test_all_fourteen_special_rules_are_listed(self, wb):
        names = {r[0].value for r in wb["Special rules"].iter_rows(min_row=2) if r[0].value}
        assert names == {
            "AP", "Bane", "Blast", "Counter", "Deadly", "Furious", "Impact",
            "Regeneration", "Relentless", "Reliable", "Rending", "Surge",
            "Thrust", "Unstoppable",
        }

    def test_seeded_unit_names_are_unique(self, wb):
        """Lookups match on name alone, so names must not collide."""
        names = [r[0].value for r in wb["Units"].iter_rows(min_row=2) if r[0].value]
        assert len(names) == len(set(names))

    def test_seeded_weapon_names_are_unique(self, wb):
        names = [r[0].value for r in wb["Weapons"].iter_rows(min_row=2) if r[0].value]
        assert len(names) == len(set(names))


class TestValidation:
    def test_dropdowns_are_attached_to_the_simulation_tab(self, wb):
        assert len(wb["Simulation"].data_validations.dataValidation) > 0

    def test_faction_dropdown_reads_from_the_factions_tab(self, wb):
        sources = [dv.formula1 for dv in wb["Simulation"].data_validations.dataValidation]
        assert any("Factions" in str(s) for s in sources)

    def test_unit_dropdowns_read_from_the_lists_tab(self, wb):
        sources = [dv.formula1 for dv in wb["Simulation"].data_validations.dataValidation]
        assert any("Lists" in str(s) for s in sources)


class TestTestsTab:
    def test_has_a_pass_fail_column(self, wb):
        assert "Result" in headers(wb["Tests"])

    def test_carries_scenarios(self, wb):
        rows = [r for r in wb["Tests"].iter_rows(min_row=2) if r[0].value]
        assert len(rows) >= 10

    def test_compares_expected_against_a_live_formula(self, wb):
        tests = wb["Tests"]
        cols = headers(tests)
        live = tests.cell(row=2, column=cols.index("Actual hits") + 1).value
        assert str(live).startswith("=")
