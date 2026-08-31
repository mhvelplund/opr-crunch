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
]
