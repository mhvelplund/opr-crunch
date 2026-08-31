"""Fixed geometry of the generated workbook."""

SIMULATION_COLUMNS = [
    "Att. faction",
    "Attacker",
    "Att. upgrades",
    "#",
    "Weapon",
    "Combat",
    "Melee state",
    'Range >9"',
    "Def. faction",
    "Defender",
    "Def. upgrades",
    "Def. #",
    "In cover",
    "Hits",
    "Wounds",
]

UNITS_COLUMNS = ["Name", "Faction", "Quality", "Defense", "Size", "Tough", "Ravage", "Special Rules"]
WEAPONS_COLUMNS = [
    "Name", "Faction", "Range", "Attacks", "AP", "Blast", "Deadly", "Impact", "Special Rules",
]
UPGRADES_COLUMNS = ["Name", "Faction", "AP", "Blast", "Deadly", "Impact", "Special Rules"]
SPECIAL_RULES_COLUMNS = ["Name", "Parameterised", "Applies to", "Modelled", "Text"]
FACTIONS_COLUMNS = ["Name"]

SIM_FIRST_ROW = 2
SIM_ROWS = 20

#: Rows of the Units/Weapons/Upgrades tabs that the cascading dropdowns scan.
#: Sized well past the imported data so rows can be added without a rebuild.
#: A tab that outgrows this loses its extra rows from the dropdowns silently,
#: so tests/test_build.py guards it.
SOURCE_CAPACITY = 160
SOURCE_FIRST_ROW = 2
SOURCE_LAST_ROW = SOURCE_FIRST_ROW + SOURCE_CAPACITY - 1

COMBAT_OPTIONS = ["Ranged", "Melee"]
MELEE_STATE_OPTIONS = ["None", "Charging", "Being charged", "Fatigued"]
YES_NO = ["Yes", "No"]


def col_index(header: str) -> int:
    """1-based column index of a Simulation header."""
    return SIMULATION_COLUMNS.index(header) + 1
