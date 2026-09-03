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

IGNORES_REGENERATION = frozenset({"Bane", "Rending", "Unstoppable", "Disintegrate"})

#: Rules this engine actually computes, and which side they act on. Anything
#: else an army book defines is carried as reference text only, because it
#: cannot change a single round's hits or wounds.
MODELLED_RULES = {
    "AP": "Attacker",
    "Aircraft": "Defender",
    "Artillery": "Both",
    "Bad Shot": "Attacker",
    "Bane": "Attacker",
    "Blast": "Attacker",
    "Counter": "Defender",
    "Crack": "Attacker",
    "Deadly": "Attacker",
    "Destructive": "Attacker",
    "Devout": "Attacker",
    "Devout Boost": "Attacker",
    "Disintegrate": "Attacker",
    "Evasive": "Defender",
    "Ferocious": "Attacker",
    "Ferocious Boost": "Attacker",
    "Fortified": "Defender",
    "Furious": "Attacker",
    "Good Shot": "Attacker",
    "Havocbound": "Attacker",
    "Impact": "Attacker",
    "Lacerate": "Attacker",
    "Melee Evasion": "Defender",
    "Melee Slayer": "Attacker",
    "Piercing Assault": "Attacker",
    "Precise": "Attacker",
    "Precision Charge Aura": "Attacker",
    "Predator": "Attacker",
    "Primal": "Attacker",
    "Primeborn": "Defender",
    "Protected": "Defender",
    "Ravage": "Attacker",
    "Regeneration": "Defender",
    "Relentless": "Attacker",
    "Reliable": "Attacker",
    "Rending": "Attacker",
    "Self-Repair": "Defender",
    "Self-Repair Boost": "Defender",
    "Shatter": "Attacker",
    "Shielded": "Defender",
    "Shred": "Attacker",
    "Stealth": "Defender",
    "Sturdy": "Defender",
    "Surge": "Attacker",
    "Targeting Visor": "Attacker",
    "Tear": "Attacker",
    "Thrust": "Attacker",
    "Tough": "Defender",
    "Unpredictable": "Attacker",
    "Unpredictable Fighter": "Attacker",
    "Unstoppable": "Attacker",
    "Versatile Attack": "Attacker",
}

#: Modelled rules that carry a value, and so get their own numeric column.
PARAMETERISED_RULES = frozenset({"AP", "Blast", "Deadly", "Impact", "Ravage", "Tough"})


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
    ravage: int = 0
    tough: int = 0
    att_rules: frozenset = field(default_factory=frozenset)
    def_rules: frozenset = field(default_factory=frozenset)
    combat: str = RANGED
    melee_state: str = "None"
    long_range: bool = True
    in_cover: bool = False
    variable_choice: str = "AP"

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


def has(rules, name: str) -> bool:
    """Whether ``rules`` grants ``name``.

    Matching is by substring, exactly as the sheet's SEARCH-based detection
    works, so the two cannot disagree. It is also what the army books mean:
    a model with "Relentless Aura" or "Unstoppable when Shooting" has that rule.
    """
    return any(name in rule for rule in rules)


def p_success(target: int) -> Fraction:
    """Chance a single d6 meets ``target``, honouring the natural 1 and 6 rules.

    "Regardless of modifiers, rolls of 6 always succeed, and rolls of 1 always
    fail." The inner clamp drops the 1 face; the outer clamp keeps the 6 face.
    """
    faces = min(5, max(1, 7 - max(2, target)))
    return Fraction(faces, 6)


def p_block_no6(target: int) -> Fraction:
    """Chance a d6 meets ``target`` on faces 2-5 only, ignoring the natural 6.

    Bane and Lacerate re-roll unmodified Defense results of 6, so the 6 face
    stops being an automatic block and is accounted for separately by the caller.
    """
    faces = min(4, max(0, 6 - max(2, target)))
    return Fraction(faces, 6)


def variable_effect(s: Scenario) -> tuple:
    """Rules granting "either AP(+1) or +1 to hit", as (active, weight on AP).

    Unpredictable rolls a die, so its two outcomes are averaged. Versatile
    Attack is a player's choice, so the pick is taken at face value. When no
    such rule applies the weight is 1, which collapses the mixture back onto
    the plain resolution.
    """
    att = set(s.att_rules)
    # "Unpredictable Fighter" contains "Unpredictable"; only the longer name
    # applies when it is the one printed on the profile.
    fighter = has(att, "Unpredictable Fighter")
    unpredictable = (fighter and s.is_melee) or (has(att, "Unpredictable") and not fighter)
    versatile = has(att, "Versatile Attack") and s.long_range

    if versatile:
        return True, Fraction(1) if s.variable_choice == "AP" else Fraction(0)
    if unpredictable:
        return True, Fraction(1, 2)  # 1-3 gives AP, 4-6 gives to-hit
    return False, Fraction(1)


def resolve(s: Scenario) -> Result:
    """Project hits and wounds, averaging over any either/or rule in play."""
    active, weight = variable_effect(s)
    if not active:
        return _resolve_branch(s, 0, 0)

    with_ap = _resolve_branch(s, 1, 0)
    with_hit = _resolve_branch(s, 0, 1)
    return Result(
        hits=weight * with_ap.hits + (1 - weight) * with_hit.hits,
        wounds=weight * with_ap.wounds + (1 - weight) * with_hit.wounds,
    )


def _resolve_branch(s: Scenario, extra_ap: int, extra_hit: int) -> Result:
    """One resolution at a fixed set of modifiers.

    Dice are split into three pools because several rules key off *unmodified*
    6s to hit, and Rending resolves exactly those hits at a different AP.
    """
    att, dfn = set(s.att_rules), set(s.def_rules)
    unstoppable = has(att, "Unstoppable")
    thrusting = has(att, "Thrust") and s.is_charging

    # --- to hit -----------------------------------------------------------
    quality = 2 if has(att, "Reliable") else s.quality
    fatigued = s.is_melee and s.melee_state == FATIGUED and not unstoppable
    dice = s.models * s.attacks
    # Good Shot and Targeting Visor are +1-to-hit rules that only apply when
    # shooting (not in melee); Targeting Visor is further gated past 9".
    good_shot = has(att, "Good Shot") and not s.is_melee
    targeting_visor = has(att, "Targeting Visor") and not s.is_melee and s.long_range
    # Artillery gets +1 to hit shooting past 9", same gating as Targeting Visor.
    artillery_bonus = has(att, "Artillery") and not s.is_melee and s.long_range
    # Stealth is the mirror image on the defender's side: enemies shooting at
    # this unit from over 9" away get -1 to hit.
    stealth_malus = has(dfn, "Stealth") and not s.is_melee and s.long_range
    # Aircraft: unconditional -1 to hit for anyone shooting at it (it cannot
    # be engaged in melee, so the malus never applies there).
    aircraft_malus = has(dfn, "Aircraft") and not s.is_melee
    # Melee Evasion is Stealth's melee counterpart: -1 to hit only in melee.
    melee_evasion_malus = has(dfn, "Melee Evasion") and s.is_melee
    # Evasive: unconditional -1 to hit for anyone attacking this unit, shooting or melee.
    evasive_malus = has(dfn, "Evasive")
    # Artillery: -2 to hit for anyone shooting it from past 9".
    artillery_malus = 2 if (has(dfn, "Artillery") and not s.is_melee and s.long_range) else 0
    # Bad Shot: -1 to hit rolls when shooting (not in melee).
    bad_shot_malus = has(att, "Bad Shot") and not s.is_melee
    # Precision Charge Aura: +1 to hit rolls when charging.
    precision_charge_bonus = has(att, "Precision Charge Aura") and s.is_charging
    # Precise: unconditional +1 to hit, shooting or melee.
    precise_bonus = has(att, "Precise")
    hit_target = (
        quality
        - (1 if thrusting else 0)
        - extra_hit
        - (1 if good_shot else 0)
        - (1 if targeting_visor else 0)
        - (1 if artillery_bonus else 0)
        - (1 if precision_charge_bonus else 0)
        - (1 if precise_bonus else 0)
        + (1 if stealth_malus else 0)
        + (1 if aircraft_malus else 0)
        + (1 if melee_evasion_malus else 0)
        + (1 if bad_shot_malus else 0)
        + (1 if evasive_malus else 0)
        + artillery_malus
    )
    p_hit = SIX if fatigued else p_success(hit_target)

    natural_6 = Fraction(dice, 6)
    normal = dice * p_hit - natural_6

    # "Point-Blank Surge" contains "Surge" but is a distinct, range-gated rule
    # this engine does not model; it must not stand in for plain Surge.
    surge = has(att, "Surge") and not has(att, "Point-Blank Surge")
    extra_per_6 = sum(
        (
            surge,
            has(att, "Devout"),
            has(att, "Ferocious"),
            has(att, "Relentless") and not s.is_melee and s.long_range,
            has(att, "Furious") and s.is_charging,
        )
    )
    normal += natural_6 * extra_per_6

    # Devout Boost widens Devout's natural-6-only bonus to naturals 5-6, when
    # shooting or charging enemies over 9" away.
    devout_boost = (
        has(att, "Devout Boost")
        and (not s.is_melee or s.is_charging)
        and s.long_range
        and not fatigued
        and hit_target <= 5
    )
    if devout_boost:
        normal += Fraction(dice, 6)

    # Ferocious Boost: same widening, keyed on Ferocious instead of Devout.
    ferocious_boost = (
        has(att, "Ferocious Boost")
        and (not s.is_melee or s.is_charging)
        and s.long_range
        and not fatigued
        and hit_target <= 5
    )
    if ferocious_boost:
        normal += Fraction(dice, 6)

    # Primal (and identically-worded Predator): for each unmodified 6 to hit,
    # this model rolls one extra attack with the same weapon, resolved at the
    # normal hit chance. "Primal Boost[ Buff]" is a different rule that
    # happens to contain "Primal" as a substring, so it is excluded here.
    primal = has(att, "Primal") and not has(att, "Primal Boost")
    if primal or has(att, "Predator"):
        normal += natural_6 * p_hit

    # --- Blast ------------------------------------------------------------
    blast_mult = min(s.blast, s.def_models) if s.blast >= 1 else 1
    natural_6 *= blast_mult
    normal *= blast_mult

    # --- Impact -----------------------------------------------------------
    impact_hits = Fraction(0)
    if s.is_charging and not fatigued and s.impact >= 1:
        counter = s.def_models if has(dfn, "Counter") else 0
        impact_dice = max(0, s.models * s.impact - counter)
        impact_hits = impact_dice * Fraction(5, 6)

    # --- to block ---------------------------------------------------------
    piercing = has(att, "Piercing Assault") and s.is_charging
    havocbound = has(att, "Havocbound") and (
        (not s.is_melee and s.long_range) or s.is_charging
    )
    disintegrate_ap = 2 if has(att, "Disintegrate") and s.defense in (2, 3) else 0
    # Melee Slayer: AP(+2) on the charge against targets with Tough(3) or higher.
    melee_slayer_ap = 2 if has(att, "Melee Slayer") and s.is_charging and s.tough >= 3 else 0
    # Tear: AP(+4) against targets with Tough(9) or higher, any attack.
    tear_ap = 4 if has(att, "Tear") and s.tough >= 9 else 0
    # Shatter: AP(+2) against targets with Tough(3) or higher, any attack.
    shatter_ap = 2 if has(att, "Shatter") and s.tough >= 3 else 0
    ap_base = (
        s.ap
        + (1 if thrusting else 0)
        + (1 if piercing else 0)
        + (1 if havocbound else 0)
        + disintegrate_ap
        + melee_slayer_ap
        + tear_ap
        + shatter_ap
        + extra_ap
    )
    cover = 1 if (not s.is_melee and s.in_cover and s.blast < 1) else 0
    shielded = 1 if has(dfn, "Shielded") else 0
    # Sturdy: +1 to defense rolls when shot or charged from over 9" away;
    # gated the same way as Devout Boost (shooting, or charging, past 9").
    sturdy = 1 if (
        has(dfn, "Sturdy") and (not s.is_melee or s.is_charging) and s.long_range
    ) else 0
    # Primeborn: same gating as Sturdy, but reduces AP by 1 (min AP(0))
    # instead of boosting defense.
    primeborn_reduce = (
        has(dfn, "Primeborn") and (not s.is_melee or s.is_charging) and s.long_range
    )

    def wounds_from(hits: Fraction, ap: int) -> Fraction:
        if has(dfn, "Fortified") or primeborn_reduce:
            ap = max(0, ap - 1)
        target = s.defense + ap - cover - shielded - sturdy
        if has(att, "Bane") or has(att, "Lacerate"):
            block = p_block_no6(target) + SIX * p_success(target)
        else:
            block = p_success(target)
        return hits * (1 - block)

    # Rending and Destructive both give unmodified 6s to hit AP(+4); only
    # Rending also ignores Regeneration. Crack is the same mechanic at AP(+2).
    ap_6 = ap_base + (
        4 if has(att, "Rending") or has(att, "Destructive") else 2 if has(att, "Crack") else 0
    )

    # Deadly's wounds do not carry over, so a target can only absorb as many as
    # it has wounds to give: one, unless it has Tough.
    deadly_mult = min(s.deadly, max(s.tough, 1)) if s.deadly >= 1 else 1

    weapon_hits = natural_6 + normal
    wounds = (wounds_from(natural_6, ap_6) + wounds_from(normal, ap_base)) * deadly_mult
    if has(att, "Shred"):
        # An unmodified 1 to block is unaffected by AP, so this is a flat 1/6.
        wounds += weapon_hits * SIX
    wounds += wounds_from(impact_hits, 0)

    # Ravage inflicts wounds directly, bypassing the Defense roll entirely.
    if s.is_melee and s.ravage >= 1:
        wounds += s.models * s.ravage * SIX

    wounds *= _ignore_multiplier(att, dfn)

    return Result(hits=natural_6 + normal + impact_hits, wounds=wounds)


def _ignore_multiplier(att: set, dfn: set) -> Fraction:
    """Chance a wound survives the defender's best wound-ignoring rule.

    Regeneration, Self-Repair and friends all roll one die per wound, so a unit
    with several does not get several rolls — the best threshold applies once.
    Only Regeneration can be switched off by Bane, Rending or Unstoppable; the
    army-book rules keep working.
    """
    thresholds = []
    if has(dfn, "Regeneration") and not any(has(att, r) for r in IGNORES_REGENERATION):
        thresholds.append(5)
    if has(dfn, "Self-Repair Boost"):
        thresholds.append(5)
    elif has(dfn, "Self-Repair"):
        thresholds.append(6)
    if has(dfn, "Protected"):
        thresholds.append(6)

    if not thresholds:
        return Fraction(1)
    return 1 - p_success(min(thresholds))


# --------------------------------------------------------------------------
# points cost
# --------------------------------------------------------------------------

def valid_model_counts(size: int) -> list:
    """The model counts a unit of ``size`` may be fielded at.

    A unit is taken as the book lists it, or as the doubled version of it. A
    single-model unit has no doubled form. Size 0 means the unit lookup found
    nothing, which offers no counts rather than defaulting to one model.
    """
    if size < 1:
        return []
    return [size] if size == 1 else [size, size * 2]


def unit_cost(base: int, weapon: int, upgrade: int, size: int, models: int) -> Fraction:
    """Points for ``models`` models, from the book's price for ``size`` of them.

    A book prices the unit with its starting weapons already included, so a
    starting weapon costs nothing here and only a swap or an upgrade adds to
    the bill. Both are priced for one unit, so the doubled unit pays twice:
    5 Warriors with Gauss Rifles cost 110, and 10 of them cost 220.
    """
    if size < 1:
        return Fraction(0)
    return Fraction((base + weapon + upgrade) * models, size)


def cost_per_wound(cost: Fraction, wounds: Fraction):
    """Points spent per projected wound, or None when none are projected.

    None is the "cannot hurt it at all" case, which the sheet shows as an
    infinity marker rather than a division error.
    """
    return None if wounds == 0 else cost / wounds
