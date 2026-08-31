"""Reference implementation of the OPR hit/wound projection model.

Mirrors sections 4 and 5 of docs/superpowers/specs/2026-08-31-opr-crunch-design.md.
Every function here has a formula counterpart in opr_crunch.formulas; the two are
kept in step by the scenarios written onto the sheet's hidden Tests tab.
"""

from dataclasses import dataclass, field
from fractions import Fraction

SIX = Fraction(1, 6)

RANGED = "Ranged"
MELEE = "Melee"
CHARGING = "Charging"
BEING_CHARGED = "Being charged"
FATIGUED = "Fatigued"

IGNORES_REGENERATION = frozenset({"Bane", "Rending", "Unstoppable"})


@dataclass(frozen=True)
class Scenario:
    """One Simulation row, flattened to the values the Calc tab works from."""

    models: int
    attacks: int
    quality: int
    defense: int
    def_models: int
    ap: int = 0
    blast: int = 0
    deadly: int = 0
    impact: int = 0
    att_rules: frozenset = field(default_factory=frozenset)
    def_rules: frozenset = field(default_factory=frozenset)
    combat: str = RANGED
    melee_state: str = "None"
    long_range: bool = True
    in_cover: bool = False

    @property
    def is_melee(self) -> bool:
        return self.combat == MELEE

    @property
    def is_charging(self) -> bool:
        return self.is_melee and self.melee_state == CHARGING


@dataclass(frozen=True)
class Result:
    hits: Fraction
    wounds: Fraction


def p_success(target: int) -> Fraction:
    """Chance a single d6 meets ``target``, honouring the natural 1 and 6 rules.

    "Regardless of modifiers, rolls of 6 always succeed, and rolls of 1 always
    fail." The inner clamp drops the 1 face; the outer clamp keeps the 6 face.
    """
    faces = min(5, max(1, 7 - max(2, target)))
    return Fraction(faces, 6)


def p_block_no6(target: int) -> Fraction:
    """Chance a d6 meets ``target`` on faces 2-5 only, ignoring the natural 6.

    Bane re-rolls unmodified Defense results of 6, so the 6 face stops being an
    automatic block and is accounted for separately by the caller.
    """
    faces = min(4, max(0, 6 - max(2, target)))
    return Fraction(faces, 6)


def resolve(s: Scenario) -> Result:
    """Project hits and wounds for a single round of one unit attacking another.

    Dice are split into three pools because several rules key off *unmodified*
    6s to hit, and Rending resolves exactly those hits at a different AP.
    """
    att, dfn = set(s.att_rules), set(s.def_rules)
    unstoppable = "Unstoppable" in att
    thrusting = "Thrust" in att and s.is_charging

    # --- to hit -----------------------------------------------------------
    quality = 2 if "Reliable" in att else s.quality
    fatigued = s.is_melee and s.melee_state == FATIGUED and not unstoppable
    dice = s.models * s.attacks
    p_hit = SIX if fatigued else p_success(quality - (1 if thrusting else 0))

    natural_6 = Fraction(dice, 6)
    normal = dice * p_hit - natural_6

    extra_per_6 = sum(
        (
            "Surge" in att,
            "Relentless" in att and not s.is_melee and s.long_range,
            "Furious" in att and s.is_charging,
        )
    )
    normal += natural_6 * extra_per_6

    # --- Blast ------------------------------------------------------------
    blast_mult = min(s.blast, s.def_models) if s.blast >= 1 else 1
    natural_6 *= blast_mult
    normal *= blast_mult

    # --- Impact -----------------------------------------------------------
    impact_hits = Fraction(0)
    if s.is_charging and not fatigued and s.impact >= 1:
        counter = s.def_models if "Counter" in dfn else 0
        impact_dice = max(0, s.models * s.impact - counter)
        impact_hits = impact_dice * Fraction(5, 6)

    # --- to block ---------------------------------------------------------
    ap_base = s.ap + (1 if thrusting else 0)
    cover = 1 if (not s.is_melee and s.in_cover and s.blast < 1) else 0

    def wounds_from(hits: Fraction, ap: int) -> Fraction:
        target = s.defense + ap - cover
        if "Bane" in att:
            block = p_block_no6(target) + SIX * p_success(target)
        else:
            block = p_success(target)
        return hits * (1 - block)

    ap_6 = ap_base + (4 if "Rending" in att else 0)
    deadly_mult = s.deadly if s.deadly >= 1 else 1

    wounds = (wounds_from(natural_6, ap_6) + wounds_from(normal, ap_base)) * deadly_mult
    wounds += wounds_from(impact_hits, 0)

    if "Regeneration" in dfn and not att & IGNORES_REGENERATION:
        wounds *= Fraction(2, 3)

    return Result(hits=natural_6 + normal + impact_hits, wounds=wounds)
