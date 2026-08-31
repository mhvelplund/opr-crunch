"""Structure of the generated workbook."""

import pytest
from openpyxl import load_workbook

from opr_crunch import csvdata
from opr_crunch.build import build_workbook
from opr_crunch.layout import SIMULATION_COLUMNS, SIM_FIRST_ROW, SIM_ROWS, last_row
from opr_crunch.model import MODELLED_RULES


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
        assert headers(wb["Units"]) == [
            "Name", "Faction", "Quality", "Defense", "Size", "Tough", "Ravage",
            "Special Rules", "Key",
        ]

    def test_weapons_headers(self, wb):
        assert headers(wb["Weapons"]) == [
            "Name", "Faction", "Range", "Attacks", "AP", "Blast", "Deadly", "Impact",
            "Special Rules", "Key",
        ]

    def test_upgrades_headers(self, wb):
        assert headers(wb["Upgrades"]) == [
            "Name", "Faction", "AP", "Blast", "Deadly", "Impact", "Special Rules", "Key",
        ]

    def test_factions_are_seeded(self, wb):
        names = [r[0].value for r in wb["Factions"].iter_rows(min_row=2) if r[0].value]
        assert "Robot Legions" in names

    def test_every_modelled_rule_is_documented(self, wb):
        """The tab is the user's reference for what the sheet actually computes."""
        rows = [r for r in wb["Special rules"].iter_rows(min_row=2) if r[0].value]
        listed = {r[0].value for r in rows}
        assert set(MODELLED_RULES) <= listed

    def test_modelled_rules_are_flagged_as_such(self, wb):
        cols = headers(wb["Special rules"])
        name_i, flag_i = cols.index("Name"), cols.index("Modelled")
        for row in wb["Special rules"].iter_rows(min_row=2):
            if not row[name_i].value:
                continue
            expected = "Yes" if row[name_i].value in MODELLED_RULES else "No"
            assert row[flag_i].value == expected, row[name_i].value

    def test_reference_only_rules_are_listed_too(self, wb):
        """Scraped army-book rules the engine ignores still belong in the tab."""
        listed = {r[0].value for r in wb["Special rules"].iter_rows(min_row=2) if r[0].value}
        assert "Infiltrate" in listed and "Infiltrate" not in MODELLED_RULES

    @pytest.mark.parametrize("tab", ["Units", "Weapons", "Upgrades"])
    def test_lookup_keys_are_unique(self, wb, tab):
        """Names repeat across army books; Name|Faction is what must not.

        Several books print a CCW or a Stomp, so lookups match on the pair.
        """
        keys = [
            (r[0].value, r[1].value)
            for r in wb[tab].iter_rows(min_row=2)
            if r[0].value
        ]
        assert len(keys) == len(set(keys)), tab

    def test_a_name_shared_by_two_factions_is_kept_distinct(self, wb):
        rows = [
            (r[0].value, r[1].value)
            for r in wb["Weapons"].iter_rows(min_row=2)
            if r[0].value
        ]
        shared = {n for n, f in rows if sum(1 for m, _ in rows if m == n) > 1}
        assert shared, "expected at least one name shared across factions"


class TestDropdownCapacity:
    """The cascading dropdowns scan a fixed range; the data must fit inside it.

    Importing an army book grows these tabs, and a row past the end of the
    range simply never appears in the dropdown - silently.
    """

    @pytest.mark.parametrize(
        "tab,loader",
        [
            ("Units", csvdata.units),
            ("Weapons", csvdata.weapons),
            ("Upgrades", csvdata.upgrades),
            ("Factions", csvdata.factions),
        ],
    )
    def test_every_row_is_reachable_from_a_dropdown(self, tab, loader):
        last_used = len(loader()) + 1  # +1 for the header row
        assert last_used <= last_row(tab), (
            f"{tab} reaches row {last_used} but dropdowns only scan to "
            f"{last_row(tab)}; raise layout.CAPACITY[{tab!r}]"
        )


class TestSeededRowsResolve:
    """Importing a faction deletes its old rows, which can orphan a seeded pick.

    A Simulation row naming a unit or weapon that no longer exists still looks
    fine - the lookups just return nothing and the row quietly reads zero.
    """

    @pytest.mark.parametrize(
        "column,loader",
        [
            ("Attacker", csvdata.units),
            ("Defender", csvdata.units),
            ("Weapon", csvdata.weapons),
            ("Att. upgrades", csvdata.upgrades),
            ("Def. upgrades", csvdata.upgrades),
        ],
    )
    def test_every_seeded_pick_exists(self, column, loader):
        known = {row[0] for row in loader()}
        index = SIMULATION_COLUMNS.index(column)
        for number, row in enumerate(csvdata.simulation(), start=2):
            picked = row[index]
            assert not picked or picked in known, (
                f"csv/simulation.csv row {number}: {column}={picked!r} "
                f"is not in the data"
            )


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
