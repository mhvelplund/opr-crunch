# UnitCrunch for OPR — Design

Status: approved 2026-08-31. Source requirements: `gist/requirements.md`.
Rules authority: One Page Rules, Grimdark Future Core Rules v3.5.1 (pages 1–2).

## 1. Goal

A Google Sheet that estimates projected **hits** and **wounds** for one combat round
between an attacking unit and a defending unit in the One Page Rules system.

## 2. Delivery

The sheet is a **build artifact**, not a hand-edited file.

- `python -m opr_crunch.build` writes `dist/opr_crunch.xlsx`.
- The user uploads that file to Google Drive and converts it to a Google Sheet.
- No Google authentication, no Apps Script, no custom functions. Every calculation
  is a native spreadsheet formula that must survive the `.xlsx` → Sheets import.

Consequence: formulas are restricted to functions common to both Excel and Google
Sheets. No `REGEXEXTRACT`, no `FILTER`, no dynamic-array spill in data validation.

## 3. Tabs

Visible, left to right: `Simulation`, `Units`, `Weapons`, `Upgrades`,
`Special rules`, `Factions`. Hidden: `Lists`, `Calc`, `Tests`.

### 3.1 Simulation (entry tab)

| # | Column | Kind | Notes |
|---|---|---|---|
| 1 | `Att. faction` | dropdown | from `Factions!Name` |
| 2 | `Attacker` | dropdown | `Units!Name` filtered by `Att. faction` |
| 3 | `Att. upgrades` | dropdown | `Upgrades!Name` filtered by `Att. faction` |
| 4 | `#` | number | attacking models |
| 5 | `Weapon` | dropdown | `Weapons!Name` filtered by `Att. faction` |
| 6 | `Combat` | dropdown | `Ranged` / `Melee` |
| 7 | `Melee state` | dropdown | `Charging` / `Being charged` / `Fatigued` / `None` |
| 8 | `Range >9"` | dropdown | `Yes` / `No` — gates `Relentless` |
| 9 | `Def. faction` | dropdown | from `Factions!Name` |
| 10 | `Defender` | dropdown | `Units!Name` filtered by `Def. faction` |
| 11 | `Def. upgrades` | dropdown | `Upgrades!Name` filtered by `Def. faction` |
| 12 | `Def. #` | number | defending models — required by `Blast` |
| 13 | `In cover` | dropdown | `Yes` / `No` |
| 14 | `Hits` | formula | → `Calc` |
| 15 | `Wounds` | formula | → `Calc` |

`Def. #` and the four context columns (6, 7, 8, 13) are additions to the original
requirements. Rationale in §7.

### 3.2 Units

`Name`, `Faction` (dropdown), `Quality` (2–6), `Defense` (2–6), `Special Rules` (text).

`Special Rules` is an addition: without it, innate unit rules such as
`Regeneration` could only be expressed as a fictitious upgrade.

### 3.3 Weapons

`Name`, `Faction` (dropdown), `Attacks` (number),
`AP`, `Blast`, `Deadly`, `Impact` (numbers, blank = rule absent),
`Special Rules` (text — comma-separated names of the non-parameterised rules).

### 3.4 Upgrades

`Name`, `Faction` (dropdown), `AP`, `Blast`, `Deadly`, `Impact`, `Special Rules`.
Upgrade `AP` adds to weapon `AP`; other numeric rules take the upgrade value when
the weapon does not supply one.

### 3.5 Special rules

`Name`, `Parameterised` (Yes/No), `Applies to` (Attacker/Defender), `Text`.
Seeded with the 14 rules relevant to hit/wound projection, quoted from v3.5.1.

### 3.6 Factions

`Name`.

### 3.7 Lists (hidden)

Per-simulation-row filtered ranges backing the cascading dropdowns. One block per
row per dropdown, built with static `IF` columns rather than `FILTER`, so the
ranges are fixed ranges that data validation can point at after import.

### 3.8 Calc (hidden)

One row per Simulation row. Every intermediate of §5 in its own labelled column,
in resolution order. `Simulation!Hits` and `Simulation!Wounds` are thin references
into this tab.

### 3.9 Tests (hidden)

Scenario rows with a Python-computed expected value beside the live spreadsheet
formula result and a `PASS`/`FAIL` column. This is the only end-to-end check that
the formulas survived the import, because no Google Sheets or LibreOffice engine
is available in CI.

## 4. Probability primitives

The core rules state: *"Regardless of modifiers, rolls of 6 always succeed, and
rolls of 1 always fail."* This applies to Quality tests and Defense rolls alike,
and is why no naive `(7-target)/6` formula is correct.

Modifiers are folded into the **target**, not the roll. For a target `T`:

    p_success(T) = MIN(5, MAX(1, 7 - MAX(2, T))) / 6

The `MAX(2, ...)` encodes "1 always fails" (ceiling of 5/6); the outer `MAX(1, ...)`
encodes "6 always succeeds" (floor of 1/6).

Blocking with the natural 6 excluded — needed by `Bane`:

    p_block_no6(T) = MIN(4, MAX(0, 6 - MAX(2, T))) / 6

## 5. Resolution model

Attacker rules are the union of the weapon's and the attacker upgrade's.
Defender rules are the union of the defending unit's and the defender upgrade's.
Only `Regeneration` and `Counter` are defender-side.

### 5.1 To-hit

    Q       = Reliable ? 2 : unit Quality
    hit_mod = +1 if (Thrust and Melee and Charging) else 0
    T_hit   = Q - hit_mod
    p_hit   = p_success(T_hit)

Fatigued (Melee, `Melee state = Fatigued`) forces `p_hit = 1/6` — only unmodified
6s hit — unless the attacker has `Unstoppable`, which ignores negative modifiers.

### 5.2 Three hit pools

Rules keyed on unmodified 6s require the natural-6 dice to be resolved separately,
because `Rending` gives exactly those hits `AP(+4)`.

    D        = models * weapon Attacks
    h6       = D / 6                        natural-6 hits
    h_norm   = D * p_hit - h6               other successful hits
    extra    = h6 * extra_per_6             extra hits, join the normal pool
    extra_per_6 = Surge
                + Relentless (Ranged and Range >9")
                + Furious    (Melee and Charging)

Extra hits are not themselves natural 6s — *"only the original hit counts as a 6
for special rules."*

Impact pool, only when Melee and Charging and not Fatigued:

    imp_dice = MAX(0, models * Impact - counter_models)
    imp_hits = imp_dice * 5/6               each 2+ is a hit
    counter_models = Def. # if defender has Counter else 0

### 5.3 Blast

    blast_mult = Blast >= 1 ? MIN(Blast, Def. #) : 1

Multiplies the two weapon pools. Not applied to the Impact pool. `Blast` also
suppresses the cover bonus.

### 5.4 AP per pool

    ap_base   = weapon AP + upgrade AP + (1 if Thrust and Melee and Charging)
    ap_pool6  = ap_base + (4 if Rending)
    ap_norm   = ap_base
    ap_impact = 0

### 5.5 To-block

    cover = 1 if (Ranged and In cover and not Blast) else 0
    T_blk = Defense + ap_pool - cover
    p_blk = Bane ? p_block_no6(T_blk) + (1/6) * p_success(T_blk)
                 : p_success(T_blk)

`Bane` re-rolls unmodified Defense results of 6: the natural 6 no longer
auto-blocks, it is re-rolled once at the normal odds.

    wounds_pool = hits_pool * (1 - p_blk)

### 5.6 Post-block

    Regeneration applies unless the attacker has Bane, Rending or Unstoppable.
    regen_mult = regen_applies ? 2/3 : 1        ignored on a 5+

    deadly_mult = Deadly >= 1 ? Deadly : 1      weapon pools only, not Impact

### 5.7 Outputs

    Hits   = (h_norm + extra + h6) * blast_mult + imp_hits
    Wounds = sum of pool wounds, after regen_mult and deadly_mult

## 6. Worked example (corrected)

10 Warriors, Quality 4, one Attack each, Reaper rifle `AP(1)`, shooting 5 Battle
Brothers with Defense 3, no cover.

    D      = 10,  p_hit = p_success(4) = 3/6      -> Hits = 5
    T_blk  = 3 + 1 - 0 = 4,  p_blk = 3/6          -> Wounds = 5 * 1/2 = 2.5

The 3.33 figure in the original requirements came from `Shred`, an army-list rule
that is out of scope here. `Rending` is AP(+4) on unmodified 6s to hit, per v3.5.1.

## 7. Accepted deviations from the original requirements

1. **`Deadly(X)` is modelled as *X wounds.** Strictly, Deadly's wounds do not
   carry over, so against models without `Tough` it is entirely wasted and a
   literal implementation would make it a no-op. It is treated as a damage-output
   metric. Adding `Tough(X)` would make it exact.
2. **`Counter`'s "strikes first" is not modelled**, only its Impact reduction.
   Sequencing cannot affect expected values without model-removal simulation.
3. **`Units` gains a `Special Rules` column** — see §3.2.
4. **`Def. #` added to Simulation** — `Blast(X)` caps X at the target's model
   count and is otherwise uncomputable.
5. **Four context columns added to Simulation** — `Counter`, `Furious`, `Impact`
   and `Thrust` are inert at range, and `Relentless` and `Blast` are conditional.
   Without this context those six rules are unreachable.
6. **`Special Rules` is comma-separated text, not a multi-select.** Neither
   `.xlsx` nor Google Sheets supports multi-select data validation. Parameterised
   rules get dedicated numeric columns instead.
7. **Cover and Fatigue are modelled** though absent from the original rule list;
   both are core rules that directly gate rules that *are* on the list.

## 8. Testing

- `opr_crunch/model.py` — pure-Python reference implementation of §4–§5.
- `tests/` — pytest, hand-verified cases per rule plus the §6 example.
- The `Tests` tab carries the same scenarios into the delivered sheet so the
  formula translation can be verified in Google Sheets after import.
