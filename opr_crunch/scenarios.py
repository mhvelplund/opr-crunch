"""Scenarios written onto the hidden Tests tab.

These mirror the pytest suite. Because the sheet cannot be recalculated in CI,
they are the only check that the generated formulas still agree with the
reference model once Google Sheets has imported the file.
"""

from opr_crunch.model import Scenario

BASE = dict(models=10, attacks=1, quality=4, defense=3, def_models=5)


def _s(**overrides) -> Scenario:
    return Scenario(**{**BASE, **overrides})


TEST_SCENARIOS = [
    ("Baseline: 10 models, Quality 4 vs Defense 3", _s()),
    ("AP(1) worsens the Defense roll", _s(ap=1)),
    ("AP(5) cannot beat the natural-6 block", _s(ap=5)),
    ("Cover improves the Defense roll", _s(ap=1, in_cover=True)),
    ("Reliable attacks at Quality 2+", _s(att_rules={"Reliable"})),
    ("Surge adds a hit per natural 6", _s(att_rules={"Surge"})),
    ("Relentless over 9 inches", _s(att_rules={"Relentless"}, long_range=True)),
    ("Relentless inside 9 inches", _s(att_rules={"Relentless"}, long_range=False)),
    ("Rending gives natural 6s AP(+4)", _s(att_rules={"Rending"})),
    ("Bane re-rolls the defender's 6s", _s(att_rules={"Bane"})),
    ("Lacerate re-rolls the defender's 6s", _s(att_rules={"Lacerate"})),
    ("Lacerate does not bypass Regeneration", _s(att_rules={"Lacerate"}, def_rules={"Regeneration"})),
    ("Blast(3) multiplies hits", _s(blast=3)),
    ("Blast(7) capped at 5 defenders", _s(blast=7)),
    ("Deadly(2) doubles wounds", _s(deadly=2)),
    ("Regeneration ignores wounds on 5+", _s(def_rules={"Regeneration"})),
    ("Rending bypasses Regeneration", _s(att_rules={"Rending"}, def_rules={"Regeneration"})),
    ("Melee, no charge", _s(combat="Melee")),
    ("Furious while charging", _s(combat="Melee", melee_state="Charging", att_rules={"Furious"})),
    ("Thrust while charging", _s(combat="Melee", melee_state="Charging", att_rules={"Thrust"})),
    ("Impact(2) on the charge", _s(combat="Melee", melee_state="Charging", impact=2)),
    (
        "Counter cuts Impact dice",
        _s(combat="Melee", melee_state="Charging", impact=2, def_rules={"Counter"}),
    ),
    ("Fatigued: only 6s hit", _s(combat="Melee", melee_state="Fatigued")),
    (
        "Unstoppable ignores fatigue",
        _s(combat="Melee", melee_state="Fatigued", att_rules={"Unstoppable"}),
    ),
    # --- Robot Legions army book -----------------------------------------
    ("Shred: extra wound on a Defense roll of 1", _s(att_rules={"Shred"})),
    ("Shred with AP(1): the original 3.33", _s(ap=1, att_rules={"Shred"})),
    ("Destructive gives natural 6s AP(+4)", _s(att_rules={"Destructive"})),
    (
        "Destructive does not bypass Regeneration",
        _s(att_rules={"Destructive"}, def_rules={"Regeneration"}),
    ),
    ("Self-Repair ignores wounds on 6+", _s(def_rules={"Self-Repair"})),
    (
        "Self-Repair survives Rending",
        _s(att_rules={"Rending"}, def_rules={"Self-Repair"}),
    ),
    (
        "Self-Repair Boost ignores on 5+",
        _s(def_rules={"Self-Repair", "Self-Repair Boost"}),
    ),
    ("Protected ignores wounds on 6+", _s(def_rules={"Protected"})),
    (
        "Stacked ignore rules take the best once",
        _s(def_rules={"Protected", "Regeneration"}),
    ),
    ("Shielded gives +1 to Defense", _s(def_rules={"Shielded"})),
    ("Ravage(2) in melee", _s(combat="Melee", ravage=2)),
    ("Ravage does nothing at range", _s(ravage=2)),
    (
        "Piercing Assault adds AP on a charge",
        _s(combat="Melee", melee_state="Charging", att_rules={"Piercing Assault"}),
    ),
    ("Deadly(3) capped by Tough(2)", _s(deadly=3, tough=2)),
    ("Deadly(3) against Tough(6)", _s(deadly=3, tough=6)),
    ("Deadly(3) wasted on a 1-wound model", _s(deadly=3)),
    # --- Havoc Brothers army book ----------------------------------------
    ("Havocbound past 9 inches", _s(att_rules={"Havocbound"}, long_range=True)),
    ("Havocbound inside 9 inches", _s(att_rules={"Havocbound"}, long_range=False)),
    (
        "Havocbound on the charge",
        _s(combat="Melee", melee_state="Charging", att_rules={"Havocbound"}),
    ),
    ("Unpredictable averages both branches", _s(att_rules={"Unpredictable"})),
    (
        "Unpredictable Fighter in melee",
        _s(combat="Melee", att_rules={"Unpredictable Fighter"}),
    ),
    (
        "Unpredictable Fighter is inert at range",
        _s(att_rules={"Unpredictable Fighter"}),
    ),
    (
        "Versatile Attack, AP chosen",
        _s(att_rules={"Versatile Attack"}, variable_choice="AP"),
    ),
    (
        "Versatile Attack, to-hit chosen",
        _s(att_rules={"Versatile Attack"}, variable_choice="To-hit"),
    ),
    (
        "Versatile Attack is inert inside 9 inches",
        _s(att_rules={"Versatile Attack"}, long_range=False),
    ),
    # --- Blessed Sisters army book -----------------------------------------
    ("Devout adds a hit per natural 6", _s(att_rules={"Devout"})),
    ("Devout applies in melee without a charge", _s(combat="Melee", att_rules={"Devout"})),
    (
        "Devout Boost widens the bonus to naturals 5-6 past 9 inches",
        _s(att_rules={"Devout Boost"}, long_range=True),
    ),
    (
        "Devout Boost is inert inside 9 inches",
        _s(att_rules={"Devout Boost"}, long_range=False),
    ),
    (
        "Devout Boost applies on a charge from over 9 inches",
        _s(combat="Melee", melee_state="Charging", att_rules={"Devout Boost"}, long_range=True),
    ),
    ("Disintegrate bypasses Regeneration", _s(att_rules={"Disintegrate"}, def_rules={"Regeneration"})),
    ("Disintegrate adds AP(+2) against Defense 3", _s(att_rules={"Disintegrate"})),
    ("Disintegrate adds nothing against Defense 4", _s(att_rules={"Disintegrate"}, defense=4)),
    ("Fortified reduces incoming AP by 1", _s(ap=2, def_rules={"Fortified"})),
    ("Fortified never pushes AP below 0", _s(def_rules={"Fortified"})),
    (
        "Point-Blank Surge does not stand in for plain Surge",
        _s(att_rules={"Point-Blank Surge"}),
    ),
    # --- Dao Union army book ------------------------------------------------
    ("Good Shot adds +1 to hit when shooting", _s(att_rules={"Good Shot"})),
    (
        "Good Shot does not apply in melee",
        _s(combat="Melee", att_rules={"Good Shot"}),
    ),
    (
        "Targeting Visor adds +1 to hit past 9 inches",
        _s(att_rules={"Targeting Visor"}, long_range=True),
    ),
    (
        "Targeting Visor is inert inside 9 inches",
        _s(att_rules={"Targeting Visor"}, long_range=False),
    ),
    (
        "Targeting Visor does not apply in melee",
        _s(combat="Melee", att_rules={"Targeting Visor"}, long_range=True),
    ),
    (
        "Stealth gives -1 to hit when shot from over 9 inches",
        _s(def_rules={"Stealth"}, long_range=True),
    ),
    (
        "Stealth is inert inside 9 inches",
        _s(def_rules={"Stealth"}, long_range=False),
    ),
    (
        "Stealth does not apply in melee",
        _s(combat="Melee", def_rules={"Stealth"}, long_range=True),
    ),
    # --- Dark Elf Raiders army book ------------------------------------------
    ("Aircraft gives -1 to hit when shot at", _s(def_rules={"Aircraft"})),
    (
        "Aircraft is inert in melee",
        _s(combat="Melee", def_rules={"Aircraft"}),
    ),
    (
        "Melee Evasion gives -1 to hit in melee",
        _s(combat="Melee", def_rules={"Melee Evasion"}),
    ),
    (
        "Melee Evasion does not apply when shooting",
        _s(def_rules={"Melee Evasion"}),
    ),
    # --- Dwarf Guilds army book -----------------------------------------
    (
        "Sturdy gives +1 to defense past 9 inches when shot",
        _s(def_rules={"Sturdy"}, long_range=True),
    ),
    (
        "Sturdy is inert inside 9 inches",
        _s(def_rules={"Sturdy"}, long_range=False),
    ),
    (
        "Sturdy applies on a charge from over 9 inches",
        _s(combat="Melee", melee_state="Charging", def_rules={"Sturdy"}, long_range=True),
    ),
    (
        "Sturdy does not apply in melee without a charge",
        _s(combat="Melee", def_rules={"Sturdy"}, long_range=True),
    ),
    (
        "Melee Slayer adds AP(+2) on the charge against Tough(3)+",
        _s(combat="Melee", melee_state="Charging", att_rules={"Melee Slayer"}, tough=3),
    ),
    (
        "Melee Slayer adds nothing against Tough(2)",
        _s(combat="Melee", melee_state="Charging", att_rules={"Melee Slayer"}, tough=2),
    ),
    (
        "Melee Slayer does not apply without a charge",
        _s(combat="Melee", att_rules={"Melee Slayer"}, tough=3),
    ),
    # --- High Elf Fleets army book -----------------------------------------
    ("Crack gives natural 6s AP(+2)", _s(att_rules={"Crack"})),
    (
        "Crack does not bypass Regeneration",
        _s(att_rules={"Crack"}, def_rules={"Regeneration"}),
    ),
    (
        "Artillery gives +1 to hit shooting past 9 inches",
        _s(att_rules={"Artillery"}, long_range=True),
    ),
    (
        "Artillery's hit bonus is inert inside 9 inches",
        _s(att_rules={"Artillery"}, long_range=False),
    ),
    (
        "Artillery gives -2 to enemy hit rolls past 9 inches",
        _s(def_rules={"Artillery"}, long_range=True),
    ),
    (
        "Artillery's defensive malus is inert inside 9 inches",
        _s(def_rules={"Artillery"}, long_range=False),
    ),
    (
        "Artillery's defensive malus does not apply in melee",
        _s(combat="Melee", def_rules={"Artillery"}, long_range=True),
    ),
    # --- Orc Marauders army book ---------------------------------------------
    ("Ferocious adds a hit per natural 6", _s(att_rules={"Ferocious"})),
    ("Ferocious applies in melee without a charge", _s(combat="Melee", att_rules={"Ferocious"})),
    (
        "Ferocious Boost widens the bonus to naturals 5-6 past 9 inches",
        _s(att_rules={"Ferocious", "Ferocious Boost"}, long_range=True),
    ),
    (
        "Ferocious Boost is inert inside 9 inches",
        _s(att_rules={"Ferocious", "Ferocious Boost"}, long_range=False),
    ),
    (
        "Ferocious Boost applies on a charge from over 9 inches",
        _s(
            combat="Melee",
            melee_state="Charging",
            att_rules={"Ferocious", "Ferocious Boost"},
            long_range=True,
        ),
    ),
    ("Bad Shot gives -1 to hit when shooting", _s(att_rules={"Bad Shot"})),
    ("Bad Shot does not apply in melee", _s(combat="Melee", att_rules={"Bad Shot"})),
    (
        "Precision Charge Aura gives +1 to hit when charging",
        _s(combat="Melee", melee_state="Charging", att_rules={"Precision Charge Aura"}),
    ),
    (
        "Precision Charge Aura does not apply without a charge",
        _s(combat="Melee", att_rules={"Precision Charge Aura"}),
    ),
    (
        "Tear gives AP(+4) against Tough(9)+",
        _s(att_rules={"Tear"}, tough=9),
    ),
    ("Tear adds nothing against Tough(8)", _s(att_rules={"Tear"}, tough=8)),
    # --- Prime Brothers army book ------------------------------------------
    ("Precise gives +1 to hit when shooting", _s(att_rules={"Precise"})),
    (
        "Precise gives +1 to hit in melee too",
        _s(combat="Melee", att_rules={"Precise"}),
    ),
    (
        "Shatter gives AP(+2) against Tough(3)+",
        _s(att_rules={"Shatter"}, tough=3),
    ),
    ("Shatter adds nothing against Tough(2)", _s(att_rules={"Shatter"}, tough=2)),
    (
        "Primeborn reduces AP by 1 past 9 inches when shot",
        _s(ap=2, def_rules={"Primeborn"}, long_range=True),
    ),
    (
        "Primeborn is inert inside 9 inches",
        _s(ap=2, def_rules={"Primeborn"}, long_range=False),
    ),
    (
        "Primeborn never pushes AP below 0",
        _s(def_rules={"Primeborn"}, long_range=True),
    ),
    (
        "Primeborn applies on a charge from over 9 inches",
        _s(
            combat="Melee",
            melee_state="Charging",
            ap=2,
            def_rules={"Primeborn"},
            long_range=True,
        ),
    ),
    (
        "Primeborn does not apply in melee without a charge",
        _s(combat="Melee", ap=2, def_rules={"Primeborn"}, long_range=True),
    ),
    # --- Saurian Starhost army book -----------------------------------------
    ("Evasive gives -1 to hit when shot", _s(def_rules={"Evasive"})),
    ("Evasive gives -1 to hit in melee too", _s(combat="Melee", def_rules={"Evasive"})),
    ("Primal rolls an extra attack per unmodified 6", _s(att_rules={"Primal"})),
    ("Predator behaves exactly like Primal", _s(att_rules={"Predator"})),
    (
        "Primal Boost Buff does not stand in for plain Primal",
        _s(att_rules={"Primal Boost Buff"}),
    ),
]
