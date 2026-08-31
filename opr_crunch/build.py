"""Assemble dist/opr_crunch.xlsx."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from opr_crunch import csvdata, layout
from opr_crunch.formulas import CALC_STEPS, Refs
from opr_crunch.model import Scenario, resolve
from opr_crunch.scenarios import TEST_SCENARIOS

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True)
OUTPUT_FILL = PatternFill("solid", fgColor="E2EFDA")

#: Inputs the calc block reads. On Calc these are lookups into the data tabs;
#: on Tests they are literals. Either way the step formulas are identical.
INPUT_HEADERS = [
    "models", "attacks", "quality", "defense", "def_models",
    "ap", "blast", "deadly", "impact", "ravage", "tough", "att_rules", "def_rules",
    "is_melee", "is_charging", "is_fatigued", "long_range", "in_cover",
]

LAST_SIM_ROW = layout.SIM_FIRST_ROW + layout.SIM_ROWS - 1
SRC_FIRST, SRC_LAST = layout.SOURCE_FIRST_ROW, layout.SOURCE_LAST_ROW


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def write_headers(ws: Worksheet, headers: List[str], width: int = 16) -> None:
    for i, name in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=i, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"


def lookup(sheet: str, value_col: str, key_ref: str, default: str = "0") -> str:
    """INDEX/MATCH on the Name column. Names are unique across a data tab."""
    return (
        f"IFERROR(INDEX('{sheet}'!${value_col}:${value_col},"
        f"MATCH({key_ref},'{sheet}'!$A:$A,0)),{default})"
    )


RANGE_COL = 'Range >9"'


def sim(col: str, row: int) -> str:
    """Absolute-column, relative-row reference into the Simulation tab."""
    return f"Simulation!${get_column_letter(layout.col_index(col))}{row}"


def list_validation(source: str) -> DataValidation:
    dv = DataValidation(type="list", formula1=source, allow_blank=True)
    dv.showDropDown = False  # openpyxl inverts this flag; False means "show it"
    return dv


def inline_validation(options: List[str]) -> DataValidation:
    return list_validation('"' + ",".join(options) + '"')


# --------------------------------------------------------------------------
# data tabs
# --------------------------------------------------------------------------

def _faction_dropdown(ws: Worksheet, column: int) -> None:
    dv = list_validation(f"Factions!$A${SRC_FIRST}:$A${SRC_LAST}")
    ws.add_data_validation(dv)
    letter = get_column_letter(column)
    dv.add(f"{letter}{SRC_FIRST}:{letter}{SRC_LAST}")


def build_data_tab(
    wb: Workbook,
    title: str,
    columns: List[str],
    rows: List[list],
    width: int = 16,
    widths: Dict[str, int] | None = None,
    faction_column: int | None = None,
    wrap_column: int | None = None,
) -> None:
    """Write one CSV-sourced tab: header, rows, widths and faction dropdown."""
    ws = wb.create_sheet(title)
    write_headers(ws, columns, width=width)
    for letter, size in (widths or {}).items():
        ws.column_dimensions[letter].width = size

    for i, row in enumerate(rows, start=2):
        for j, value in enumerate(row, start=1):
            cell = ws.cell(row=i, column=j, value=value)
            if j == wrap_column:
                cell.alignment = Alignment(wrap_text=True)

    if faction_column:
        _faction_dropdown(ws, faction_column)


#: (title, columns, loader, kwargs) for every tab sourced from csv/.
DATA_TABS = [
    ("Units", layout.UNITS_COLUMNS, csvdata.units,
     dict(widths={"A": 22, "H": 34}, faction_column=2)),
    ("Weapons", layout.WEAPONS_COLUMNS, csvdata.weapons,
     dict(width=11, widths={"A": 22, "I": 34}, faction_column=2)),
    ("Upgrades", layout.UPGRADES_COLUMNS, csvdata.upgrades,
     dict(width=11, widths={"A": 22, "G": 34}, faction_column=2)),
    ("Special rules", layout.SPECIAL_RULES_COLUMNS, csvdata.special_rules,
     dict(width=14, widths={"A": 16, "D": 90}, wrap_column=4)),
    ("Factions", layout.FACTIONS_COLUMNS, csvdata.factions, dict(width=22)),
]


# --------------------------------------------------------------------------
# cascading dropdown source lists
# --------------------------------------------------------------------------

#: (label, source tab, Simulation column holding the faction to filter by)
LIST_SPECS = [
    ("Attacker units", "Units", "Att. faction"),
    ("Attacker upgrades", "Upgrades", "Att. faction"),
    ("Weapons", "Weapons", "Att. faction"),
    ("Defender units", "Units", "Def. faction"),
    ("Defender upgrades", "Upgrades", "Def. faction"),
]


def build_lists(wb: Workbook) -> Dict[int, Dict[str, str]]:
    """One filtered name column per Simulation row per dropdown.

    Deliberately built from plain IF formulas rather than FILTER: the result is
    a fixed range that data validation can point at, and it survives the .xlsx
    round-trip into Google Sheets unchanged. Non-matching cells are left blank,
    which Sheets omits from the dropdown.
    """
    ws = wb.create_sheet("Lists")
    ranges: Dict[int, Dict[str, str]] = {}

    for i, row in enumerate(range(layout.SIM_FIRST_ROW, LAST_SIM_ROW + 1)):
        ranges[row] = {}
        for k, (label, source, faction_col) in enumerate(LIST_SPECS):
            column = i * len(LIST_SPECS) + k + 1
            letter = get_column_letter(column)
            ws.cell(row=1, column=column, value=f"{label} r{row}")
            key = sim(faction_col, row)
            for offset in range(layout.SOURCE_CAPACITY):
                src = SRC_FIRST + offset
                ws.cell(
                    row=SRC_FIRST + offset,
                    column=column,
                    value=f"=IF('{source}'!$B{src}={key},'{source}'!$A{src},\"\")",
                )
            ranges[row][label] = f"Lists!${letter}${SRC_FIRST}:${letter}${SRC_LAST}"
    return ranges


# --------------------------------------------------------------------------
# calc block
# --------------------------------------------------------------------------

def calc_inputs_for(row: int) -> List[str]:
    """Formulas pulling one Simulation row's inputs out of the data tabs."""
    weapon, att_up = sim("Weapon", row), sim("Att. upgrades", row)
    defender, def_up = sim("Defender", row), sim("Def. upgrades", row)
    combat, state = sim("Combat", row), sim("Melee state", row)

    def pair(weapon_col: str, upgrade_col: str) -> str:
        return (
            f"=MAX({lookup('Weapons', weapon_col, weapon)},"
            f"{lookup('Upgrades', upgrade_col, att_up)})"
        )

    attacker = sim("Attacker", row)
    return [
        f"={sim('#', row)}",
        f"={lookup('Weapons', 'D', weapon)}",
        f"={lookup('Units', 'C', attacker)}",
        f"={lookup('Units', 'D', defender)}",
        f"={sim('Def. #', row)}",
        f"={lookup('Weapons', 'E', weapon)}+{lookup('Upgrades', 'C', att_up)}",
        pair("F", "D"),
        pair("G", "E"),
        pair("H", "F"),
        f"={lookup('Units', 'G', attacker)}",
        f"={lookup('Units', 'F', defender)}",
        # The attacking unit's own profile grants rules too (Relentless,
        # Piercing Assault, ...), so it joins the weapon's and the upgrade's.
        f'={lookup("Units", "H", attacker, chr(34) * 2)}&", "'
        f'&{lookup("Weapons", "I", weapon, chr(34) * 2)}&", "'
        f'&{lookup("Upgrades", "G", att_up, chr(34) * 2)}',
        f'={lookup("Units", "H", defender, chr(34) * 2)}&", "'
        f'&{lookup("Upgrades", "G", def_up, chr(34) * 2)}',
        f'=({combat}="Melee")',
        f'=AND({combat}="Melee",{state}="Charging")',
        f'=AND({combat}="Melee",{state}="Fatigued")',
        f'=({sim(RANGE_COL, row)}="Yes")',
        f'=({sim("In cover", row)}="Yes")',
    ]


def write_calc_block(ws: Worksheet, row: int, first_col: int) -> Dict[str, str]:
    """Emit the resolution steps and return each step's cell address."""
    letters = {}
    for offset, name in enumerate(INPUT_HEADERS):
        letters[name] = f"${get_column_letter(first_col + offset)}{row}"

    refs = Refs(**{name: letters[name] for name in INPUT_HEADERS})

    step_col = first_col + len(INPUT_HEADERS)
    cells: Dict[str, str] = {}
    for offset, (name, builder) in enumerate(CALC_STEPS):
        column = step_col + offset
        address = f"${get_column_letter(column)}{row}"
        ws.cell(row=row, column=column, value=builder(refs, cells))
        cells[name] = address
    return cells


def build_calc(wb: Workbook) -> Dict[str, str]:
    ws = wb.create_sheet("Calc")
    headers = INPUT_HEADERS + [name for name, _ in CALC_STEPS]
    write_headers(ws, headers, width=13)

    for row in range(layout.SIM_FIRST_ROW, LAST_SIM_ROW + 1):
        for offset, formula in enumerate(calc_inputs_for(row)):
            ws.cell(row=row, column=offset + 1, value=formula)
        write_calc_block(ws, row, first_col=1)

    step_start = len(INPUT_HEADERS) + 1
    names = [name for name, _ in CALC_STEPS]
    return {
        "hits": get_column_letter(step_start + names.index("hits")),
        "wounds": get_column_letter(step_start + names.index("wounds")),
    }


# --------------------------------------------------------------------------
# simulation tab
# --------------------------------------------------------------------------

def build_simulation(wb: Workbook, ranges, calc_cols) -> None:
    ws = wb["Simulation"]
    write_headers(ws, layout.SIMULATION_COLUMNS, width=15)
    ws.column_dimensions[get_column_letter(layout.col_index("Attacker"))].width = 20
    ws.column_dimensions[get_column_letter(layout.col_index("Defender"))].width = 20

    for offset, seeded in enumerate(csvdata.simulation()):
        row = layout.SIM_FIRST_ROW + offset
        if row > LAST_SIM_ROW:
            break
        for column, value in enumerate(seeded, start=1):
            if value != "":
                ws.cell(row=row, column=column, value=value)

    hits_col = layout.col_index("Hits")
    wounds_col = layout.col_index("Wounds")
    attacker = get_column_letter(layout.col_index("Attacker"))

    for row in range(layout.SIM_FIRST_ROW, LAST_SIM_ROW + 1):
        guard = f'IF(${attacker}{row}="","",'
        for column, letter in ((hits_col, calc_cols["hits"]), (wounds_col, calc_cols["wounds"])):
            cell = ws.cell(row=row, column=column, value=f"={guard}Calc!${letter}{row})")
            cell.number_format = "0.00"
            cell.fill = OUTPUT_FILL

    # faction dropdowns
    for header in ("Att. faction", "Def. faction"):
        dv = list_validation(f"Factions!$A${SRC_FIRST}:$A${SRC_LAST}")
        ws.add_data_validation(dv)
        letter = get_column_letter(layout.col_index(header))
        dv.add(f"{letter}{layout.SIM_FIRST_ROW}:{letter}{LAST_SIM_ROW}")

    # per-row cascading dropdowns
    column_for_label = {
        "Attacker units": "Attacker",
        "Attacker upgrades": "Att. upgrades",
        "Weapons": "Weapon",
        "Defender units": "Defender",
        "Defender upgrades": "Def. upgrades",
    }
    for row, per_label in ranges.items():
        for label, source in per_label.items():
            dv = list_validation(source)
            ws.add_data_validation(dv)
            letter = get_column_letter(layout.col_index(column_for_label[label]))
            dv.add(f"{letter}{row}")

    # fixed-option dropdowns
    for header, options in (
        ("Combat", layout.COMBAT_OPTIONS),
        ("Melee state", layout.MELEE_STATE_OPTIONS),
        ('Range >9"', layout.YES_NO),
        ("In cover", layout.YES_NO),
    ):
        dv = inline_validation(options)
        ws.add_data_validation(dv)
        letter = get_column_letter(layout.col_index(header))
        dv.add(f"{letter}{layout.SIM_FIRST_ROW}:{letter}{LAST_SIM_ROW}")


# --------------------------------------------------------------------------
# tests tab
# --------------------------------------------------------------------------

def scenario_inputs(s: Scenario) -> List:
    return [
        s.models, s.attacks, s.quality, s.defense, s.def_models,
        s.ap, s.blast, s.deadly, s.impact, s.ravage, s.tough,
        ", ".join(sorted(s.att_rules)), ", ".join(sorted(s.def_rules)),
        s.is_melee, s.is_charging,
        s.is_melee and s.melee_state == "Fatigued",
        s.long_range, s.in_cover,
    ]


def build_tests(wb: Workbook) -> None:
    """Carry the pytest scenarios into the sheet so the formulas self-check."""
    ws = wb.create_sheet("Tests")
    step_names = [name for name, _ in CALC_STEPS]
    headers = (
        ["Scenario"]
        + INPUT_HEADERS
        + step_names
        + ["Expected hits", "Actual hits", "Expected wounds", "Actual wounds", "Result"]
    )
    write_headers(ws, headers, width=13)
    ws.column_dimensions["A"].width = 34

    for i, (name, scenario) in enumerate(TEST_SCENARIOS):
        row = 2 + i
        ws.cell(row=row, column=1, value=name)
        for offset, value in enumerate(scenario_inputs(scenario)):
            ws.cell(row=row, column=2 + offset, value=value)

        cells = write_calc_block(ws, row, first_col=2)
        expected = resolve(scenario)

        base = 2 + len(INPUT_HEADERS) + len(step_names)
        ws.cell(row=row, column=base, value=float(expected.hits))
        ws.cell(row=row, column=base + 1, value=f"={cells['hits']}")
        ws.cell(row=row, column=base + 2, value=float(expected.wounds))
        ws.cell(row=row, column=base + 3, value=f"={cells['wounds']}")

        eh, ah = get_column_letter(base), get_column_letter(base + 1)
        ew, aw = get_column_letter(base + 2), get_column_letter(base + 3)
        ws.cell(
            row=row,
            column=base + 4,
            value=(
                f"=IF(AND(ABS({ah}{row}-{eh}{row})<0.000001,"
                f"ABS({aw}{row}-{ew}{row})<0.000001),\"PASS\",\"FAIL\")"
            ),
        )

    summary = 2 + len(TEST_SCENARIOS)
    result_col = get_column_letter(len(headers))
    ws.cell(row=summary + 1, column=1, value="All scenarios")
    ws.cell(
        row=summary + 1,
        column=len(headers),
        value=(
            f'=IF(COUNTIF({result_col}2:{result_col}{summary - 1},"FAIL")=0,'
            f'"ALL PASS","FAILURES")'
        ),
    )


# --------------------------------------------------------------------------

def build_workbook() -> Workbook:
    wb = Workbook()
    wb.active.title = "Simulation"

    for title, columns, loader, options in DATA_TABS:
        build_data_tab(wb, title, columns, loader(), **options)
    ranges = build_lists(wb)
    calc_cols = build_calc(wb)
    build_tests(wb)
    build_simulation(wb, ranges, calc_cols)

    for name in ("Lists", "Calc", "Tests"):
        wb[name].sheet_state = "hidden"
    return wb


def main() -> Path:
    out = Path("dist") / "opr_crunch.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_workbook().save(out)
    return out


if __name__ == "__main__":
    print(f"wrote {main()}")
