# Unit costs, model counts and Cost/Wound — Design

Status: approved 2026-09-01. Extends `2026-08-31-opr-crunch-design.md`.
Rules authority: One Page Rules, Grimdark Future Core Rules v3.5.1, and the
army books in `books/`.

## 1. Goal

Make the sheet answer "what does this damage cost me?" as well as "how much
damage is it?", and stop the user entering model counts the game does not allow.

Three changes, in dependency order:

1. Every unit, weapon and upgrade carries a **points cost**.
2. The attacker/defender model counts (`#`, `Def. #`) become **dropdowns of the
   legal values** for the chosen unit, flagged red when a value goes stale.
3. A derived **`Cost/Wound`** column divides the attacking unit's cost by its
   projected wounds.

## 2. Non-goals

- **Real weapon and upgrade prices from the PDF.** Unit costs scrape reliably;
  weapon and upgrade prices do not (see §4.3). They are seeded with a
  placeholder and corrected by a follow-up. This is deliberate, not an oversight.
- **Partial-unit weapon swaps.** A book's "Replace one Reaper Rifle" prices a
  swap for a single model; the sheet models a whole unit firing one profile, so
  the listed price is taken as-is. Out of scope.
- **Defender cost.** `Cost/Wound` measures the attacker's efficiency only.

## 3. Data model

A `Cost` column is **appended as the last CSV column** on three tabs. Appending
is the only safe edit: `build.py` compiles lookups against fixed column letters,
and the generated `Key` column is `layout.key_column(columns) = len(columns)+1`,
so it shifts right on its own.

| Tab | CSV column | Letter | Key moves to | Seeded with |
|---|---|---|---|---|
| `units.csv` | `Cost` | `I` | `J` | real cost, scraped from the book |
| `weapons.csv` | `Cost` | `K` | `L` | `0` for a starting weapon, `10` for a swap option |
| `upgrades.csv` | `Cost` | `I` | `J` | `10` |

`layout.py`'s `UNITS_COLUMNS`, `WEAPONS_COLUMNS` and `UPGRADES_COLUMNS` gain
`"Cost"` in last position. No existing letter moves, so no existing lookup
changes.

A unit's base cost already includes its starting weapon — `Warriors [5] -
100pts` is 5 Warriors *with* Reaper Rifles — so a starting weapon must cost `0`
or every unit reads high. `Lord Reaper Rifle` (the Robot Lord's own weapon) is
`0`; `Gauss Rifle`, which replaces Reaper Rifles for `+10pts`, is a swap.

`Units.Size` (column `E`) already holds the base model count `N`. The model-count
rule needs no new data.

## 4. Importer

### 4.1 Unit cost

`armybook.CARD` already captures the points value:

```python
CARD = re.compile(r"([A-Z][\w'\-]*(?:[ \-][A-Z]?[\w'\-]+)*) \[(\d+)\] - (\d+)pts")
```

`parse_units` discards `m.group(3)`. It starts keeping it as `cost`, and
`import_army_book.import_book` writes it as the unit row's last cell.

### 4.2 Weapon and upgrade cost

`linked_weapons` already builds its rows from two distinct paths, which is
exactly the distinction needed:

- `_default_weapon_names` → the card's own **starting** weapons → `cost = 0`.
- `find_weapons(span)` → inline **swap options** → `cost = 10`.

When the same `(unit, name)` arrives from both paths, the starting-weapon `0`
wins. The existing dedup in `linked_weapons` keys on `(unit, name, profile)`; it
gains cost-aware resolution so the surviving row is the cheaper (starting) one
rather than whichever was seen first.

`linked_upgrades` rows get a flat `cost = 10`.

### 4.3 Why weapon prices are not scraped

`pdftotext -layout` does not keep a card's price column aligned with the rows it
prices. On the Robot Legions Warriors card the four "Replace one Reaper Rifle"
prices interleave out of order; on the Guardians card all four prices
(`+10/+10/+20/+45`) appear *above* the weapons they belong to. Matching by
vertical order would silently mis-assign prices — numbers that look right and
are wrong, the failure mode this importer is already most prone to.

Doing it properly needs `pdftotext -bbox` word coordinates so a `+Npts` token
can be matched to the upgrade line sharing its baseline. That is a second
extraction path alongside the existing one, and is deferred to a follow-up.

### 4.4 Re-import

All three books in `books/` are re-imported so units carry true costs. Because
re-import regenerates rows wholesale, **the resulting `csv/` diff must be
reviewed: any change beyond the new `Cost` column is a regression**, not an
expected consequence.

## 5. Model counts

### 5.1 Rule

A unit whose book lists `N` models is fielded at `N` or `2N` models. A
single-model unit is fielded at 1 and cannot be doubled.

`model.py` owns this as the single source of truth:

```python
def valid_model_counts(size: int) -> list[int]:
    """A unit of ``size`` models is fielded at that size, or at double it."""
    if size < 1:
        return []
    return [size] if size == 1 else [size, size * 2]
```

### 5.2 Dropdowns

A new `build_count_lists(wb, start_column)` mirrors `build_state_lists`: two
`Lists` columns per Simulation row (attacker, then defender), starting at
`layout.SIM_ROWS * (len(LIST_SPECS) + 1) + 1` so it sits clear of the cascading
block (columns 1–100) and the state block (101–120).

Each pair holds, for a row `r` whose size expression is `S` (an
`INDEX`/`MATCH` on `Units!$E:$E`, keyed as every other lookup is):

```
row 2:  =IF(S<1,"",S)
row 3:  =IF(OR(S<1,S=1),"",S*2)
```

`lookup()` already returns `0` when the match fails, so a blank or unrecognised
unit yields two blank cells and an empty dropdown — no separate `unit=""` test
is needed. Blank cells drop out of a list-validation dropdown, which is the same
property `build_state_lists` already relies on.

`#` and `Def. #` get `list_validation` against their row's 2-cell range.

### 5.3 Stale-value flagging

Changing the unit cannot clear an already-entered count (no Apps Script), so an
invalid count is flagged with the **same** `FormulaRule` + `STALE_FILL` /
`STALE_FONT` treatment the cascading dropdowns already use:

```
AND($D3<>"",COUNTIF(Lists!$DS$2:$DS$3,$D3)=0)
```

This is the case from the request: Warriors at 10 models, switched to Robot
Snakes (size 3, so 3 or 6), turns red.

## 6. `Cost/Wound`

### 6.1 Column

Inserted into `layout.SIMULATION_COLUMNS` between `Wounds` and
`Att. Special Rules`, making the Simulation tab 19 columns wide:

```
... Hits (O), Wounds (P), Cost/Wound (Q), Att. Special Rules (R), Def. Special Rules (S)
```

`csv/simulation.csv` gains the column in the same position, left blank like
`Hits` and `Wounds`, because the build writes formulas there.

### 6.2 Cost

```
total cost = (unit cost + weapon cost + upgrade cost) × (# ÷ Size)
```

`# ÷ Size` is exactly `1` or `2` for a legal count, which is the doubling rule
("10 Warriors with Gauss Rifles cost 220"). For an illegal count it degrades to
a proportional number rather than an error — acceptable, because that cell is
flagged red by §5.3.

`model.py` owns the arithmetic:

```python
def unit_cost(base: int, weapon: int, upgrade: int, size: int, models: int) -> Fraction:
    """Points for ``models`` models, given the base unit's cost at ``size``."""
    if size < 1:
        return Fraction(0)
    return Fraction((base + weapon + upgrade) * models, size)
```

### 6.3 Where it is computed, and why not in `CALC_STEPS`

`resolve()` averages two resolution branches for rules that grant "either AP(+1)
or +1 to hit". Cost per wound must divide by the **averaged** wounds:

```
cost ÷ avg(wounds)  ≠  avg(cost ÷ wounds)
```

So `Cost/Wound` cannot be a `CALC_STEPS` entry — every step there is evaluated
once per branch and then averaged, which would compute the wrong quantity.

Instead a `build_cost_calc(wb, start_col)` helper block on the `Calc` tab
(mirroring the existing `build_weapon_stat_calc`) emits per-row `size`,
`unit_cost`, `weapon_cost`, `upgrade_cost` and `total_cost` columns and returns
their addresses. The Simulation cell divides that by the already-averaged wounds
column produced by `write_both_branches`:

```
=IF(<attacker>="","",IF(<wounds>=0,"∞",<total cost>/<wounds>))
```

An empty row is blank, matching `Hits`/`Wounds`. A matchup projecting no wounds
shows `∞`, so "cannot hurt it" is visibly distinct from "not filled in". The
cell carries the `0.00` number format; the `∞` string passes through it as text.

Its `model.py` counterpart returns `None` for the infinite case:

```python
def cost_per_wound(cost: Fraction, wounds: Fraction):
    """Points per projected wound; None when no wounds are projected."""
    return None if wounds == 0 else cost / wounds
```

## 7. Testing

| Area | Test |
|---|---|
| `model.py` helpers | new `tests/test_costs.py`: doubling, single-model units, `size < 1`, zero wounds, `valid_model_counts` |
| Formula parity | the emitted `total_cost` and `Cost/Wound` strings evaluated through `tests/formula_eval.py` and compared to the `model.py` helpers — the interpreter already supports `IF`, `IFERROR`, `INDEX`, `MATCH` and division, which is all these formulas use |
| Workbook structure | `tests/test_build.py`: new column order, `Cost` on the three data tabs, count-list ranges, validation on `#`/`Def. #`, the stale-count conditional-formatting rule |
| Importer | `tests/test_armybook.py`: cost parsed off a card line, starting weapon `0` vs swap `10` |

The hidden `Tests` tab is unchanged. It exists to prove `CALC_STEPS` survives the
Google Sheets round-trip, and `Cost/Wound` is deliberately not one of those steps
(§6.3); adding it would mean restructuring `build_tests` around a second kind of
row for no gain in what is being guarded.

## 8. Verification

Beyond `pytest`, after re-importing:

1. **Review the `csv/` diff** — anything but the new `Cost` column is a regression (§4.4).
2. **Check the seeded `csv/simulation.csv` counts** against each unit's `Size`, or
   the shipped workbook opens with rows already flagged red.
3. **Confirm dropdown capacity** still holds after re-import (`layout.CAPACITY`,
   already guarded by `tests/test_build.py`).
4. **Build and open the workbook**, confirm the `Tests` tab still reads `ALL PASS`.

## 9. Follow-up

Real weapon and upgrade prices via `pdftotext -bbox` coordinate matching (§4.3).
Until then every weapon swap and upgrade is priced at a flat 10 points, so
`Cost/Wound` is exact for a unit with its starting weapon and approximate
otherwise.
