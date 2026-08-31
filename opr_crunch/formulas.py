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
    att_rules: str
    def_rules: str
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
    """As p_success but without the natural 6, which Bane re-rolls away."""
    return f"MIN(4,MAX(0,6-MAX(2,{target})))/6"


def _block(refs: Refs, target: str) -> str:
    return (
        f"IF({has(refs.att_rules, 'Bane')},"
        f"{p_block_no6(target)}+(1/6)*{p_success(target)},"
        f"{p_success(target)})"
    )


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
        "p_hit",
        lambda r, c: (
            f"=IF({c['fatigued']}=1,1/6,"
            f"{p_success(f'{c['quality_eff']}-{c['thrusting']}')})"
        ),
    ),
    ("natural_6", lambda r, c: f"={c['dice']}/6"),
    (
        "extra_per_6",
        lambda r, c: (
            f"=IF({has(r.att_rules, 'Surge')},1,0)"
            f"+IF(AND({has(r.att_rules, 'Relentless')},NOT({r.is_melee}),{r.long_range}),1,0)"
            f"+IF(AND({has(r.att_rules, 'Furious')},{r.is_charging}),1,0)"
        ),
    ),
    (
        "normal",
        lambda r, c: (
            f"={c['dice']}*{c['p_hit']}-{c['natural_6']}"
            f"+{c['natural_6']}*{c['extra_per_6']}"
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
    ("ap_base", lambda r, c: f"={r.ap}+{c['thrusting']}"),
    (
        "ap_6",
        lambda r, c: f"={c['ap_base']}+IF({has(r.att_rules, 'Rending')},4,0)",
    ),
    (
        "cover",
        lambda r, c: (
            f"=IF(AND(NOT({r.is_melee}),{r.in_cover},{r.blast}<1),1,0)"
        ),
    ),
    (
        "block_normal",
        lambda r, c: f"={_block(r, f'{r.defense}+{c["ap_base"]}-{c["cover"]}')}",
    ),
    (
        "block_6",
        lambda r, c: f"={_block(r, f'{r.defense}+{c["ap_6"]}-{c["cover"]}')}",
    ),
    (
        "block_impact",
        lambda r, c: f"={_block(r, f'{r.defense}-{c["cover"]}')}",
    ),
    ("deadly_mult", lambda r, c: f"=IF({r.deadly}>=1,{r.deadly},1)"),
    (
        "regen_mult",
        lambda r, c: (
            f"=IF(AND({has(r.def_rules, 'Regeneration')},"
            f"NOT(OR({has(r.att_rules, 'Bane')},{has(r.att_rules, 'Rending')},"
            f"{has(r.att_rules, 'Unstoppable')}))),2/3,1)"
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
            f"+{c['hits_impact']}*(1-{c['block_impact']}))*{c['regen_mult']}"
        ),
    ),
]

CALC_HEADERS = [name for name, _ in CALC_STEPS]
