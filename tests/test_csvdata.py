"""Loading tab contents from the csv/ directory."""

import pytest

from opr_crunch import csvdata, layout


class TestLoading:
    def test_factions_are_read(self):
        assert ["Robot Legions"] in csvdata.factions()

    def test_units_are_read(self):
        names = [row[0] for row in csvdata.units()]
        assert "Warrior" in names

    def test_numeric_columns_become_integers(self):
        warrior = next(r for r in csvdata.units() if r[0] == "Warrior")
        quality = warrior[layout.UNITS_COLUMNS.index("Quality")]
        assert quality == 4
        assert isinstance(quality, int)

    def test_text_columns_stay_text(self):
        immortal = next(r for r in csvdata.units() if r[0] == "Immortal")
        assert immortal[layout.UNITS_COLUMNS.index("Special Rules")] == "Regeneration"

    def test_blank_numeric_cells_become_zero(self):
        rifle = next(r for r in csvdata.weapons() if r[0] == "Reaper rifle")
        assert rifle[layout.WEAPONS_COLUMNS.index("Blast")] == 0

    def test_blank_text_cells_become_empty_string(self):
        warrior = next(r for r in csvdata.units() if r[0] == "Warrior")
        assert warrior[layout.UNITS_COLUMNS.index("Special Rules")] == ""

    def test_commas_inside_rule_text_survive(self):
        bane = next(r for r in csvdata.special_rules() if r[0] == "Bane")
        assert bane[3].startswith("Ignores Regeneration, and when attacking")

    def test_quotes_inside_headers_survive(self):
        """The Simulation tab has a column literally named 'Range >9"'."""
        row = csvdata.simulation()[0]
        assert row[layout.SIMULATION_COLUMNS.index('Range >9"')] == "Yes"

    def test_simulation_carries_the_worked_example(self):
        row = csvdata.simulation()[0]
        assert row[layout.SIMULATION_COLUMNS.index("Attacker")] == "Warrior"
        assert row[layout.SIMULATION_COLUMNS.index("#")] == 10

    def test_generated_output_columns_are_left_blank(self):
        row = csvdata.simulation()[0]
        assert row[layout.SIMULATION_COLUMNS.index("Hits")] == ""


class TestHeaderValidation:
    """Column order is fixed by layout.py because the lookups hardcode letters."""

    def test_a_mismatched_header_is_rejected(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_text("Name,Faction,Defense,Quality,Special Rules\n", encoding="utf-8")
        with pytest.raises(ValueError, match="units.csv"):
            csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"})

    def test_a_missing_column_is_rejected(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_text("Name,Faction,Quality\n", encoding="utf-8")
        with pytest.raises(ValueError):
            csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"})

    def test_the_error_names_both_headers(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_text("Name,Faction,Defence,Quality,Special Rules\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Defence"):
            csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"})

    def test_a_matching_header_is_accepted(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_text(
            "Name,Faction,Quality,Defense,Special Rules\nOrk,Greenskins,4,4,\n",
            encoding="utf-8",
        )
        assert csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"}) == [
            ["Ork", "Greenskins", 4, "4", ""]
        ]

    def test_short_rows_are_padded(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_text(
            "Name,Faction,Quality,Defense,Special Rules\nOrk,Greenskins\n",
            encoding="utf-8",
        )
        assert csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"}) == [
            ["Ork", "Greenskins", 0, "", ""]
        ]

    def test_blank_lines_are_skipped(self, tmp_path):
        path = tmp_path / "units.csv"
        path.write_text(
            "Name,Faction,Quality,Defense,Special Rules\n\nOrk,Greenskins,4,4,\n\n",
            encoding="utf-8",
        )
        assert len(csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"})) == 1


class TestEveryTabIsCovered:
    @pytest.mark.parametrize(
        "loader,columns",
        [
            (csvdata.simulation, layout.SIMULATION_COLUMNS),
            (csvdata.units, layout.UNITS_COLUMNS),
            (csvdata.weapons, layout.WEAPONS_COLUMNS),
            (csvdata.upgrades, layout.UPGRADES_COLUMNS),
            (csvdata.special_rules, layout.SPECIAL_RULES_COLUMNS),
            (csvdata.factions, layout.FACTIONS_COLUMNS),
        ],
    )
    def test_rows_are_the_right_width(self, loader, columns):
        for row in loader():
            assert len(row) == len(columns)
