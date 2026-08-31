"""Loading tab contents from the csv/ directory."""

import pytest

from opr_crunch import csvdata, layout


def field(row, columns, name):
    return row[columns.index(name)]


def find(rows, name):
    return next(r for r in rows if r[0] == name)


class TestLoading:
    def test_factions_are_read(self):
        assert ["Robot Legions"] in csvdata.factions()

    def test_units_are_read(self):
        names = [row[0] for row in csvdata.units()]
        assert "Warriors" in names

    def test_numeric_columns_become_integers(self):
        warriors = find(csvdata.units(), "Warriors")
        quality = field(warriors, layout.UNITS_COLUMNS, "Quality")
        assert quality == 4
        assert isinstance(quality, int)

    def test_text_columns_stay_text(self):
        warriors = find(csvdata.units(), "Warriors")
        assert field(warriors, layout.UNITS_COLUMNS, "Special Rules") == "Self-Repair, Slow"

    def test_blank_numeric_cells_become_zero(self):
        rifles = find(csvdata.weapons(), "Reaper Rifles")
        assert field(rifles, layout.WEAPONS_COLUMNS, "Blast") == 0

    def test_blank_text_cells_become_empty_string(self):
        plain = find(csvdata.units(), "Havoc Brothers")
        assert field(plain, layout.UNITS_COLUMNS, "Special Rules") == ""

    def test_commas_inside_rule_text_survive(self):
        bane = find(csvdata.special_rules(), "Bane")
        text = field(bane, layout.SPECIAL_RULES_COLUMNS, "Text")
        assert text.startswith("Ignores Regeneration, and when attacking")

    def test_quotes_inside_headers_survive(self):
        """The Simulation tab has a column literally named 'Range >9"'."""
        row = csvdata.simulation()[0]
        assert row[layout.SIMULATION_COLUMNS.index('Range >9"')] == "Yes"

    def test_simulation_carries_the_worked_example(self):
        row = csvdata.simulation()[0]
        assert row[layout.SIMULATION_COLUMNS.index("Attacker")] == "Warriors"
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

    @staticmethod
    def _write(path, *lines):
        """Write a units CSV whose header always matches the current layout."""
        header = ",".join(layout.UNITS_COLUMNS)
        path.write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")

    def test_a_matching_header_is_accepted(self, tmp_path):
        path = tmp_path / "units.csv"
        self._write(path, "Ork,Greenskins,4,4,5,3,0,")
        assert csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"}) == [
            ["Ork", "Greenskins", 4, "4", "5", "3", "0", ""]
        ]

    def test_short_rows_are_padded(self, tmp_path):
        path = tmp_path / "units.csv"
        self._write(path, "Ork,Greenskins")
        assert csvdata.load(path, layout.UNITS_COLUMNS, numeric={"Quality"}) == [
            ["Ork", "Greenskins", 0, "", "", "", "", ""]
        ]

    def test_blank_lines_are_skipped(self, tmp_path):
        path = tmp_path / "units.csv"
        self._write(path, "", "Ork,Greenskins,4,4,5,3,0,", "")
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
