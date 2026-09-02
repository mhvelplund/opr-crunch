# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Generates `dist/opr_crunch.xlsx`, a spreadsheet that projects **hits** and **wounds** for one combat round in the
[One Page Rules](https://www.onepagerules.com/) system (the "Unit Crunch" equivalent for OPR). The workbook is meant
to be imported into Google Sheets: upload it to Drive, **File -> Save as Google Sheets**, then unhide the `Tests` tab
and confirm the summary cell reads `ALL PASS` — that's the check that the formulas survived the `.xlsx` round-trip.

## Commands

```shell
mise install                                    # installs uv
uv sync                                         # creates .venv, installs openpyxl/pdfplumber/pytest
uv run pytest                                    # full suite
uv run pytest tests/test_army_rules.py           # single file
uv run pytest -k unpredictable                   # single test by name
uv run python -m opr_crunch.build                # writes dist/opr_crunch.xlsx
```

`mise run build` does the same build (`uv sync && uv run python -m opr_crunch.build`).

Importing an army book:

```shell
uv run python tools/import_army_book.py <url-or-book.pdf>
```

Requires `pdftotext` (poppler) on PATH for the line-based parsing; word-coordinate price
matching uses `pdfplumber` directly and needs no separate binary. See "Importing an army
book" below — the `importing-army-books` skill covers the full workflow including the
checks for its silent failure modes.

## Architecture

**The model is defined twice, deliberately, and a test suite keeps the two in lockstep:**

- `opr_crunch/model.py` — pure-Python reference implementation of the resolution maths (`resolve(Scenario) -> Result`).
- `opr_crunch/formulas.py` — the same resolution steps (`CALC_STEPS`) emitted as Excel/Google-Sheets formula strings.
- `tests/formula_eval.py` — a minimal formula interpreter (IF/AND/OR/INDEX/MATCH/TEXTJOIN/etc.) that lets pytest
  execute the *generated formula strings* and assert they agree with `model.py`, without needing Excel or Sheets
  installed. `tests/test_formula_parity.py` and `tests/test_army_rules.py` drive this.
- `opr_crunch/scenarios.py` mirrors the pytest scenarios onto the workbook's hidden `Tests` tab (via
  `opr_crunch/build.py::build_tests`), so the check for formula-vs-model agreement travels with the shipped file and
  still runs after Google Sheets has re-parsed it (see "ALL PASS" above).

**When a rule affects the maths, it needs four matching changes** (see the `importing-army-books` skill for the full
checklist): an entry in `model.MODELLED_RULES` plus the maths in `model.py`, the equivalent step in `formulas.py`, a
scenario in `scenarios.py`, and a test in `tests/test_army_rules.py`. Rule names are matched by **substring** in both
places (`model.has()` mirrors the sheet's `SEARCH`), so watch for a rule name that's a substring of another (e.g.
`Unpredictable` inside `Unpredictable Fighter` — the longer name has to be excluded explicitly wherever the shorter
one is checked).

**Data flow, CSV to workbook:**

- `csv/*.csv` (`units`, `weapons`, `upgrades`, `special_rules`, `factions`, `simulation`) are the source of truth for
  everything except formulas. `opr_crunch/csvdata.py` loads them.
- `opr_crunch/layout.py` is the fixed geometry: column order for every tab, capacity per data tab for the cascading
  dropdowns, and the Simulation tab's column layout. **Column order in a CSV must match `layout.py` exactly** —
  `csvdata.load` validates the header and raises rather than silently producing wrong numbers, because
  `opr_crunch/build.py` compiles lookups against fixed column letters (e.g. `Weapons!$C:$C` is always Attacks).
- `opr_crunch/build.py` assembles the workbook: writes each data tab, builds the cascading-dropdown source lists
  (`Lists` tab), emits the `Calc` tab (both resolution branches per Simulation row, for rules that are "either AP(+1)
  or +1 to hit" and need a weighted average — see `var_active`/`w_ap`), and wires the `Simulation` tab's dropdowns and
  output formulas. `Lists`, `Calc`, `Tests` ship hidden.
- Lookups key on a generated `Name|Faction` column (`Name|Faction|Unit` for `Weapons`/`Upgrades`, since the same
  weapon name can have a different profile per unit) rather than on `Name` alone, because army books reuse generic
  names (`CCW`, `Stomp`) across factions and units.

**Importing an army book** (`opr_crunch/armybook.py`, driven by `tools/import_army_book.py`): parses `pdftotext
-layout` output, which preserves horizontal position — army books are laid out in multi-column grids, and reading
top-to-bottom without that would interleave unrelated cells. Unit cards are read from page 4 onward, not from page
2's roster grid (that table's cells don't survive extraction in reading order). Replaces every row for the imported
faction in `csv/`; other factions are untouched. Special rules are merged, not replaced, since core rules share that
tab with faction-specific ones. The import step itself fails silently in several ways (missing rule detection, stale
`csv/simulation.csv` references, dropdown capacity overflow) — the `importing-army-books` skill's Verify section is
the actual procedure, not just running the script.

## Editing data

Edit a CSV and re-run the build; add/remove *rows* freely but never reorder or rename *columns*. A genuinely new
column goes on the *end* of a data tab, never in the middle — `build.py` compiles lookups against fixed column
letters, so an inserted column silently repoints every lookup after it.

`csv/simulation.csv` seeds starting rows on the `Simulation` tab — its `Hits`, `Wounds` and `Cost/Wound` columns stay
blank since the build writes formulas there. A seeded `#`/`Def. #` must be one of the counts the unit's `Size`
allows (`Size`, or double it; a single-model unit only ever 1), or the shipped workbook opens with the row already
flagged red — `tests/test_build.py::TestSeededModelCounts` guards that.

Points costs live in the `Cost` column of `units`, `weapons` and `upgrades`. Unit costs are
scraped from the book. Weapon-swap and upgrade prices are also scraped, by reading the PDF a
second time with `pdfplumber` for word coordinates and matching each option's `+Npts` token to
the option it prices, scoped to one unit's card at a time. A price that can't be confidently
matched falls back to `0` (same as a starting weapon, which is never priced from a `+Npts`
token at all - the unit's own cost already covers it) and is listed in the importer's
end-of-run "price not found" summary, so it can be filled in by hand in `csv/weapons.csv` or
`csv/upgrades.csv`. A `.txt` source carries no word coordinates, so that run prices nothing and
says so. See `docs/superpowers/specs/2026-09-02-real-weapon-upgrade-prices-design.md`.
