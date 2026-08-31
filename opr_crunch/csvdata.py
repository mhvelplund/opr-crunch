"""Tab contents, loaded from the csv/ directory.

Editing a CSV and re-running the build is the supported way to change what the
sheet ships with. Column *order* is not taken from the CSV, though: build.py
compiles lookups against fixed column letters (Weapons!$C:$C is Attacks), so a
reordered file would silently produce wrong numbers. The header is validated
against layout.py instead, turning that into a build failure.
"""

import csv
from pathlib import Path
from typing import Iterable, List, Sequence, Set

from opr_crunch import layout

CSV_DIR = Path(__file__).resolve().parent.parent / "csv"

#: Columns parsed as integers. Everything else is kept as text.
NUMERIC = {
    "simulation": {"#", "Def. #"},
    "units": {"Quality", "Defense", "Size", "Tough", "Ravage"},
    "weapons": {"Range", "Attacks", "AP", "Blast", "Deadly", "Impact"},
    "upgrades": {"AP", "Blast", "Deadly", "Impact"},
    "special_rules": set(),
    "factions": set(),
}

#: Columns the build fills with formulas, so the CSV leaves them blank.
GENERATED = {"Hits", "Wounds"}


def _coerce(value: str, header: str, numeric: Set[str]):
    if header in GENERATED:
        return ""
    text = (value or "").strip()
    if header not in numeric:
        return text
    try:
        return int(text)
    except ValueError:
        return 0


def load(path: Path, columns: Sequence[str], numeric: Iterable[str]) -> List[list]:
    """Read a CSV, checking its header matches ``columns`` exactly."""
    numeric = set(numeric)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))

    if not rows:
        raise ValueError(f"{path.name} is empty; expected a header row")

    header = [cell.strip() for cell in rows[0]]
    if header != list(columns):
        raise ValueError(
            f"{path.name} header does not match layout.py.\n"
            f"  expected: {list(columns)}\n"
            f"  found:    {header}"
        )

    loaded = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        padded = list(row) + [""] * (len(columns) - len(row))
        loaded.append(
            [_coerce(padded[i], name, numeric) for i, name in enumerate(columns)]
        )
    return loaded


def _tab(name: str, columns: Sequence[str]) -> List[list]:
    return load(CSV_DIR / f"{name}.csv", columns, NUMERIC[name])


def simulation() -> List[list]:
    return _tab("simulation", layout.SIMULATION_COLUMNS)


def units() -> List[list]:
    return _tab("units", layout.UNITS_COLUMNS)


def weapons() -> List[list]:
    return _tab("weapons", layout.WEAPONS_COLUMNS)


def upgrades() -> List[list]:
    return _tab("upgrades", layout.UPGRADES_COLUMNS)


def special_rules() -> List[list]:
    return _tab("special_rules", layout.SPECIAL_RULES_COLUMNS)


def factions() -> List[list]:
    return _tab("factions", layout.FACTIONS_COLUMNS)
