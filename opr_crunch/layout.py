"""Fixed geometry of the generated workbook."""

SIMULATION_COLUMNS = [
    "Att. faction",
    "Attacker",
    "Att. upgrades",
    "#",
    "Weapon",
    "Weapon stats",
    "Combat",
    'Melee state / Range >9"',
    "Def. faction",
    "Defender",
    "Def. upgrades",
    "Def. #",
    "In cover",
    "Variable effect",
    "Hits",
    "Wounds",
    "Att. Special Rules",
    "Def. Special Rules",
]

UNITS_COLUMNS = ["Name", "Faction", "Quality", "Defense", "Size", "Tough", "Ravage", "Special Rules"]
WEAPONS_COLUMNS = [
    "Name", "Faction", "Unit", "Range", "Attacks", "AP", "Blast", "Deadly", "Impact", "Special Rules",
]
UPGRADES_COLUMNS = ["Name", "Faction", "Unit", "AP", "Blast", "Deadly", "Impact", "Special Rules"]

#: Tabs whose lookup key includes the owning Unit, not just Name|Faction.
#: A weapon or upgrade option can belong to more than one unit; those are
#: written as separate rows rather than merged, so Unit must join the key.
KEY_PARTS = {
    "Units": ["Name", "Faction"],
    "Weapons": ["Name", "Faction", "Unit"],
    "Upgrades": ["Name", "Faction", "Unit"],
}
SPECIAL_RULES_COLUMNS = ["Name", "Parameterised", "Applies to", "Modelled", "Text"]
FACTIONS_COLUMNS = ["Name"]

SIM_FIRST_ROW = 2
SIM_ROWS = 20

#: Rows of each data tab that the cascading dropdowns scan, sized per tab so a
#: large Weapons tab does not inflate every other dropdown's helper range.
#: A tab that outgrows its capacity loses the extra rows from the dropdowns
#: silently, so tests/test_build.py guards it.
CAPACITY = {
    "Units": 120,
    "Weapons": 650,
    "Upgrades": 170,
    "Factions": 40,
}
SOURCE_FIRST_ROW = 2


def last_row(tab: str) -> int:
    """Last row of ``tab`` that dropdowns and lookups reach."""
    return SOURCE_FIRST_ROW + CAPACITY[tab] - 1


def key_column(columns) -> int:
    """Index of the generated Name|Faction column, one past the CSV's own."""
    return len(columns) + 1

VARIABLE_EFFECT_OPTIONS = ["AP", "To-hit"]
MELEE_STATE_OPTIONS = ["None", "Charging", "Being charged", "Fatigued"]
YES_NO = ["Yes", "No"]


def col_index(header: str) -> int:
    """1-based column index of a Simulation header."""
    return SIMULATION_COLUMNS.index(header) + 1
