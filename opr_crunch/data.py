"""Seed content for the workbook.

Example data only — enough to exercise every modelled rule out of the box.
Replace it with real army-list entries; the sheet does not depend on it.

Rule text is quoted from One Page Rules, Grimdark Future Core Rules v3.5.1.
"""

FACTIONS = ["Robot Legions", "Havoc Brothers"]

# Name, Faction, Quality, Defense, Special Rules
UNITS = [
    ("Warrior", "Robot Legions", 4, 4, ""),
    ("Immortal", "Robot Legions", 3, 3, "Regeneration"),
    ("Wraith", "Robot Legions", 3, 3, ""),
    ("Battle Brother", "Havoc Brothers", 3, 3, ""),
    ("Havoc Champion", "Havoc Brothers", 3, 2, ""),
    ("Cultist", "Havoc Brothers", 5, 5, ""),
]

# Name, Faction, Attacks, AP, Blast, Deadly, Impact, Special Rules
WEAPONS = [
    ("Reaper rifle", "Robot Legions", 1, 1, 0, 0, 0, ""),
    ("Gauss blaster", "Robot Legions", 2, 1, 0, 0, 0, "Rending"),
    ("Tesla carbine", "Robot Legions", 1, 0, 0, 0, 0, "Surge"),
    ("Smashing fists", "Robot Legions", 2, 1, 0, 0, 1, ""),
    ("Assault rifle", "Havoc Brothers", 2, 0, 0, 0, 0, ""),
    ("Plasma gun", "Havoc Brothers", 1, 2, 0, 3, 0, ""),
    ("Frag grenade", "Havoc Brothers", 1, 0, 3, 0, 0, ""),
    ("Heavy flamer", "Havoc Brothers", 1, 0, 6, 0, 0, "Reliable"),
    ("Energy sword", "Havoc Brothers", 3, 1, 0, 0, 0, "Thrust"),
    ("Chain fist", "Havoc Brothers", 2, 2, 0, 0, 0, "Bane"),
]

# Name, Faction, AP, Blast, Deadly, Impact, Special Rules
UPGRADES = [
    ("Living metal", "Robot Legions", 0, 0, 0, 0, "Regeneration"),
    ("Phase shift", "Robot Legions", 0, 0, 0, 0, "Unstoppable"),
    ("Targeting matrix", "Robot Legions", 0, 0, 0, 0, "Relentless"),
    ("Captain", "Havoc Brothers", 0, 0, 0, 0, "Furious"),
    ("Veteran", "Havoc Brothers", 0, 0, 0, 0, "Reliable"),
    ("Shield wall", "Havoc Brothers", 0, 0, 0, 0, "Counter"),
]

#: The rules that affect hit/wound projection. ``parameterised`` rules take a
#: value and live in their own numeric column; the rest are named in the
#: free-text "Special Rules" column.
SPECIAL_RULES = [
    ("AP", True, "Attacker", "Targets get -X to Defense rolls when blocking hits from this weapon."),
    ("Bane", False, "Attacker", "Ignores Regeneration, and when attacking the target must re-roll unmodified Defense results of 6."),
    ("Blast", True, "Attacker", "Ignores cover, and after resolving other special rules, each hit is multiplied by X, where X is up to as many hits as models in the target unit."),
    ("Counter", False, "Defender", "Strikes first with this weapon when charged, and the charging unit gets -1 total Impact rolls per model with Counter."),
    ("Deadly", True, "Attacker", "Assign each wound to one model, and multiply it by X. Hits from Deadly must be resolved first, and these wounds don't carry over to other models if the original target is killed."),
    ("Furious", False, "Attacker", "When charging, unmodified results of 6 to hit in melee deal 1 extra hit (only the original hit counts as a 6 for special rules)."),
    ("Impact", True, "Attacker", "Roll X dice when attacking after charging, unless fatigued. For each 2+ the target takes one hit."),
    ("Regeneration", False, "Defender", "When a unit where all models have this rule takes wounds, roll one die for each. On a 5+ it is ignored."),
    ("Relentless", False, "Attacker", "When this model shoots at enemies over 9\" away, unmodified results of 6 to hit deal 1 extra hit (only the original hit counts as a 6 for special rules)."),
    ("Reliable", False, "Attacker", "Attacks at Quality 2+."),
    ("Rending", False, "Attacker", "Ignores Regeneration, and on unmodified results of 6 to hit, those hits get AP(+4)."),
    ("Surge", False, "Attacker", "On unmodified results of 6 to hit, this weapon deals 1 extra hit (only the original hit counts as a 6 for special rules)."),
    ("Thrust", False, "Attacker", "When charging, gets +1 to hit rolls and AP(+1) in melee."),
    ("Unstoppable", False, "Attacker", "Ignores Regeneration, and ignores all negative modifiers to this weapon."),
]

#: Rules named in the free-text column rather than given a numeric column.
BOOLEAN_RULES = [name for name, param, _, _ in SPECIAL_RULES if not param]

#: A starting row for the Simulation tab, matching the spec's worked example.
EXAMPLE_ROW = {
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
