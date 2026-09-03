"""Spreadsheet translation of opr_crunch.model.

The calc block below is emitted twice: once on the Calc tab, reading from the
Simulation tab, and once on the Tests tab, reading from literal inputs. Both use
this one definition, so the Tests tab genuinely exercises the shipped formulas.

Only functions common to Excel and Google Sheets are used, because the workbook
is delivered as .xlsx and converted on import.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class Refs:
    """Cell references, or boolean expressions, for one row's inputs."""

    models: str
    attacks: str
    quality: str
    defense: str
    def_models: str
    ap: str
    blast: str
    deadly: str
    impact: str
    ravage: str
    tough: str
    att_rules: str
    def_rules: str
    extra_ap: str
    extra_hit: str
    is_melee: str
    is_charging: str
    is_fatigued: str
    long_range: str
    in_cover: str


def has(rules_ref: str, rule: str) -> str:
    """True when ``rule`` is named in a comma-separated Special Rules cell."""
    return f'ISNUMBER(SEARCH("{rule}",{rules_ref}))'


def p_success(target: str) -> str:
    """Chance a d6 meets ``target``; 1s always fail and 6s always succeed."""
    return f"MIN(5,MAX(1,7-MAX(2,{target})))/6"


def p_block_no6(target: str) -> str:
    """As p_success but without the natural 6, which Bane/Lacerate re-roll away."""
    return f"MIN(4,MAX(0,6-MAX(2,{target})))/6"


def _fortified(refs: Refs, ap_expr: str) -> str:
    """Fortified (always) or Primeborn (shot/charged past 9") reduce incoming AP by 1, never below 0."""
    primeborn = (
        f"AND({has(refs.def_rules, 'Primeborn')},"
        f"OR(NOT({refs.is_melee}),{refs.is_charging}),{refs.long_range})"
    )
    return (
        f"IF(OR({has(refs.def_rules, 'Fortified')},{primeborn}),"
        f"MAX(0,{ap_expr}-1),{ap_expr})"
    )


def _block(refs: Refs, target: str) -> str:
    return (
        f"IF(OR({has(refs.att_rules, 'Bane')},{has(refs.att_rules, 'Lacerate')}),"
        f"{p_block_no6(target)}+(1/6)*{p_success(target)},"
        f"{p_success(target)})"
    )


#: Wound-ignoring rules, as (rule, threshold). A unit with several does not get
#: several rolls, so the best threshold wins; 99 stands in for "absent".
IGNORE_RULES = [
    ("Self-Repair Boost", 5),
    ("Self-Repair", 6),
    ("Protected", 6),
]


Builder = Callable[[Refs, Dict[str, str]], str]

#: Ordered resolution steps. Each builder receives the input refs and a map of
#: already-emitted step names to their cell addresses.
CALC_STEPS: List[Tuple[str, Builder]] = [
    ("dice", lambda r, c: f"={r.models}*{r.attacks}"),
    ("quality_eff", lambda r, c: f"=IF({has(r.att_rules, 'Reliable')},2,{r.quality})"),
    (
        "thrusting",
        lambda r, c: f"=IF(AND({has(r.att_rules, 'Thrust')},{r.is_charging}),1,0)",
    ),
    (
        "fatigued",
        lambda r, c: (
            f"=IF(AND({r.is_fatigued},NOT({has(r.att_rules, 'Unstoppable')})),1,0)"
        ),
    ),
    (
        # Good Shot and Targeting Visor are +1-to-hit rules that only apply
        # when shooting; Targeting Visor is further gated past 9".
        "good_shot",
        lambda r, c: f"=IF(AND({has(r.att_rules, 'Good Shot')},NOT({r.is_melee})),1,0)",
    ),
    (
        "targeting_visor",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Targeting Visor')},"
            f"NOT({r.is_melee}),{r.long_range}),1,0)"
        ),
    ),
    (
        # Artillery gets +1 to hit shooting past 9", same gating as Targeting Visor.
        "artillery_bonus",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Artillery')},"
            f"NOT({r.is_melee}),{r.long_range}),1,0)"
        ),
    ),
    (
        # Stealth is the mirror image on the defender's side: enemies
        # shooting at this unit from over 9" away get -1 to hit.
        "stealth_malus",
        lambda r, c: (
            f"=IF(AND({has(r.def_rules, 'Stealth')},"
            f"NOT({r.is_melee}),{r.long_range}),1,0)"
        ),
    ),
    (
        # Aircraft: unconditional -1 to hit for anyone shooting at it (it
        # cannot be engaged in melee, so the malus never applies there).
        "aircraft_malus",
        lambda r, c: f"=IF(AND({has(r.def_rules, 'Aircraft')},NOT({r.is_melee})),1,0)",
    ),
    (
        # Melee Evasion is Stealth's melee counterpart: -1 to hit only in melee.
        "melee_evasion_malus",
        lambda r, c: f"=IF(AND({has(r.def_rules, 'Melee Evasion')},{r.is_melee}),1,0)",
    ),
    (
        # Evasive: unconditional -1 to hit for anyone attacking this unit,
        # shooting or melee.
        "evasive_malus",
        lambda r, c: f"=IF({has(r.def_rules, 'Evasive')},1,0)",
    ),
    (
        # Artillery: -2 to hit for anyone shooting it from past 9".
        "artillery_malus",
        lambda r, c: (
            f"=IF(AND({has(r.def_rules, 'Artillery')},"
            f"NOT({r.is_melee}),{r.long_range}),2,0)"
        ),
    ),
    (
        # Bad Shot: -1 to hit rolls when shooting (not in melee).
        "bad_shot_malus",
        lambda r, c: f"=IF(AND({has(r.att_rules, 'Bad Shot')},NOT({r.is_melee})),1,0)",
    ),
    (
        # Precision Charge Aura: +1 to hit rolls when charging.
        "precision_charge_bonus",
        lambda r, c: f"=IF(AND({has(r.att_rules, 'Precision Charge Aura')},{r.is_charging}),1,0)",
    ),
    (
        # Precise: unconditional +1 to hit, shooting or melee.
        "precise_bonus",
        lambda r, c: f"=IF({has(r.att_rules, 'Precise')},1,0)",
    ),
    (
        "hit_target",
        lambda r, c: (
            f"={c['quality_eff']}-{c['thrusting']}-{r.extra_hit}"
            f"-{c['good_shot']}-{c['targeting_visor']}-{c['artillery_bonus']}"
            f"-{c['precision_charge_bonus']}-{c['precise_bonus']}"
            f"+{c['stealth_malus']}+{c['aircraft_malus']}+{c['melee_evasion_malus']}"
            f"+{c['bad_shot_malus']}+{c['artillery_malus']}+{c['evasive_malus']}"
        ),
    ),
    (
        "p_hit",
        lambda r, c: (
            f"=IF({c['fatigued']}=1,1/6,{p_success(c['hit_target'])})"
        ),
    ),
    ("natural_6", lambda r, c: f"={c['dice']}/6"),
    (
        # "Point-Blank Surge" contains "Surge" but is a distinct, range-gated
        # rule this sheet does not model; it must not stand in for plain Surge.
        "extra_per_6",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Surge')},"
            f"NOT({has(r.att_rules, 'Point-Blank Surge')})),1,0)"
            f"+IF({has(r.att_rules, 'Devout')},1,0)"
            f"+IF({has(r.att_rules, 'Ferocious')},1,0)"
            f"+IF(AND({has(r.att_rules, 'Relentless')},NOT({r.is_melee}),{r.long_range}),1,0)"
            f"+IF(AND({has(r.att_rules, 'Furious')},{r.is_charging}),1,0)"
        ),
    ),
    (
        # Devout Boost widens Devout's natural-6-only bonus to naturals 5-6,
        # when shooting or charging enemies over 9" away.
        "devout_boost",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Devout Boost')},"
            f"OR(NOT({r.is_melee}),{r.is_charging}),{r.long_range},"
            f"{c['fatigued']}=0,{c['hit_target']}<=5),{c['dice']}/6,0)"
        ),
    ),
    (
        # Ferocious Boost: same widening, keyed on Ferocious instead of Devout.
        "ferocious_boost",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Ferocious Boost')},"
            f"OR(NOT({r.is_melee}),{r.is_charging}),{r.long_range},"
            f"{c['fatigued']}=0,{c['hit_target']}<=5),{c['dice']}/6,0)"
        ),
    ),
    (
        # Primal (and identically-worded Predator): for each unmodified 6 to
        # hit, this model rolls one extra attack with the same weapon,
        # resolved at the normal hit chance. "Primal Boost[ Buff]" is a
        # different rule that happens to contain "Primal" as a substring, so
        # it is excluded here.
        "primal_extra",
        lambda r, c: (
            f"=IF(OR(AND({has(r.att_rules, 'Primal')},"
            f"NOT({has(r.att_rules, 'Primal Boost')})),"
            f"{has(r.att_rules, 'Predator')}),{c['natural_6']}*{c['p_hit']},0)"
        ),
    ),
    (
        "normal",
        lambda r, c: (
            f"={c['dice']}*{c['p_hit']}-{c['natural_6']}"
            f"+{c['natural_6']}*{c['extra_per_6']}"
            f"+{c['devout_boost']}+{c['ferocious_boost']}+{c['primal_extra']}"
        ),
    ),
    (
        "blast_mult",
        lambda r, c: f"=IF({r.blast}>=1,MIN({r.blast},{r.def_models}),1)",
    ),
    ("hits_6", lambda r, c: f"={c['natural_6']}*{c['blast_mult']}"),
    ("hits_normal", lambda r, c: f"={c['normal']}*{c['blast_mult']}"),
    (
        "impact_dice",
        lambda r, c: (
            f"=IF(AND({r.is_charging},{c['fatigued']}=0,{r.impact}>=1),"
            f"MAX(0,{r.models}*{r.impact}"
            f"-IF({has(r.def_rules, 'Counter')},{r.def_models},0)),0)"
        ),
    ),
    ("hits_impact", lambda r, c: f"={c['impact_dice']}*5/6"),
    (
        "piercing",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Piercing Assault')},{r.is_charging}),1,0)"
        ),
    ),
    (
        # AP(+1) when shooting past 9" or when charging.
        "havocbound",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Havocbound')},"
            f"OR(AND(NOT({r.is_melee}),{r.long_range}),{r.is_charging})),1,0)"
        ),
    ),
    (
        "disintegrate_ap",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Disintegrate')},"
            f"OR({r.defense}=2,{r.defense}=3)),2,0)"
        ),
    ),
    (
        # Melee Slayer: AP(+2) on the charge against Tough(3)+ targets.
        "melee_slayer_ap",
        lambda r, c: (
            f"=IF(AND({has(r.att_rules, 'Melee Slayer')},{r.is_charging},"
            f"{r.tough}>=3),2,0)"
        ),
    ),
    (
        # Tear: AP(+4) against Tough(9)+ targets, any attack.
        "tear_ap",
        lambda r, c: f"=IF(AND({has(r.att_rules, 'Tear')},{r.tough}>=9),4,0)",
    ),
    (
        # Shatter: AP(+2) against Tough(3)+ targets, any attack.
        "shatter_ap",
        lambda r, c: f"=IF(AND({has(r.att_rules, 'Shatter')},{r.tough}>=3),2,0)",
    ),
    (
        "ap_base",
        lambda r, c: (
            f"={r.ap}+{c['thrusting']}+{c['piercing']}+{c['havocbound']}"
            f"+{c['disintegrate_ap']}+{c['melee_slayer_ap']}+{c['tear_ap']}"
            f"+{c['shatter_ap']}+{r.extra_ap}"
        ),
    ),
    (
        # Rending and Destructive both give unmodified 6s AP(+4); Crack is the
        # same mechanic at AP(+2).
        "ap_6",
        lambda r, c: (
            f"={c['ap_base']}+IF(OR({has(r.att_rules, 'Rending')},"
            f"{has(r.att_rules, 'Destructive')}),4,IF({has(r.att_rules, 'Crack')},2,0))"
        ),
    ),
    (
        "cover",
        lambda r, c: (
            f"=IF(AND(NOT({r.is_melee}),{r.in_cover},{r.blast}<1),1,0)"
        ),
    ),
    ("shielded", lambda r, c: f"=IF({has(r.def_rules, 'Shielded')},1,0)"),
    (
        # Sturdy: +1 to defense rolls when shot or charged from over 9",
        # gated the same way as Devout Boost (shooting, or charging, past 9").
        "sturdy",
        lambda r, c: (
            f"=IF(AND({has(r.def_rules, 'Sturdy')},"
            f"OR(NOT({r.is_melee}),{r.is_charging}),{r.long_range}),1,0)"
        ),
    ),
    (
        "block_normal",
        lambda r, c: "=" + _block(
            r,
            f"{r.defense}+{_fortified(r, c['ap_base'])}-{c['cover']}-{c['shielded']}-{c['sturdy']}",
        ),
    ),
    (
        "block_6",
        lambda r, c: "=" + _block(
            r,
            f"{r.defense}+{_fortified(r, c['ap_6'])}-{c['cover']}-{c['shielded']}-{c['sturdy']}",
        ),
    ),
    (
        "block_impact",
        lambda r, c: (
            f"={_block(r, f'{r.defense}-{c["cover"]}-{c["shielded"]}-{c["sturdy"]}')}"
        ),
    ),
    (
        # Deadly's wounds do not carry over, so the target absorbs at most as
        # many as it has: one, unless it has Tough.
        "deadly_mult",
        lambda r, c: f"=IF({r.deadly}>=1,MIN({r.deadly},MAX({r.tough},1)),1)",
    ),
    (
        # An unmodified 1 to block is unaffected by AP, so Shred is a flat 1/6.
        "shred_wounds",
        lambda r, c: (
            f"=IF({has(r.att_rules, 'Shred')},"
            f"({c['hits_6']}+{c['hits_normal']})/6,0)"
        ),
    ),
    (
        # Ravage inflicts wounds directly, bypassing the Defense roll.
        "ravage_wounds",
        lambda r, c: (
            f"=IF(AND({r.is_melee},{r.ravage}>=1),{r.models}*{r.ravage}/6,0)"
        ),
    ),
    (
        "ignore_best",
        lambda r, c: (
            "=MIN(IF(AND("
            f"{has(r.def_rules, 'Regeneration')},NOT(OR({has(r.att_rules, 'Bane')},"
            f"{has(r.att_rules, 'Rending')},{has(r.att_rules, 'Unstoppable')},"
            f"{has(r.att_rules, 'Disintegrate')}))),5,99)"
            + "".join(
                f",IF({has(r.def_rules, rule)},{threshold},99)"
                for rule, threshold in IGNORE_RULES
            )
            + ")"
        ),
    ),
    (
        "ignore_mult",
        lambda r, c: (
            f"=IF({c['ignore_best']}>6,1,1-{p_success(c['ignore_best'])})"
        ),
    ),
    (
        "hits",
        lambda r, c: f"={c['hits_6']}+{c['hits_normal']}+{c['hits_impact']}",
    ),
    (
        "wounds",
        lambda r, c: (
            f"=(({c['hits_6']}*(1-{c['block_6']})"
            f"+{c['hits_normal']}*(1-{c['block_normal']}))*{c['deadly_mult']}"
            f"+{c['shred_wounds']}"
            f"+{c['hits_impact']}*(1-{c['block_impact']})"
            f"+{c['ravage_wounds']})*{c['ignore_mult']}"
        ),
    ),
]

CALC_HEADERS = [name for name, _ in CALC_STEPS]
