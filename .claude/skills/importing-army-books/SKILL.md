---
name: importing-army-books
description: Use when adding or refreshing a faction in this repo from a One Page Rules army-book PDF or army-forge URL, or when a faction's units, weapons, upgrades or special rules are missing, stale or wrong.
---

# Importing Army Books

## Overview

`tools/import_army_book.py` reads an OPR army book and rewrites that faction's rows
across `csv/`. Other factions are untouched; special rules are merged, not replaced,
because the core rules share that tab.

**The import is the easy part. The failures are silent** — nothing errors, the sheet
just quietly computes with data it cannot see or rules it does not model. Work the
Verify section, don't skip to "it printed some counts".

## Import

```sh
./.venv/Scripts/python.exe tools/import_army_book.py <url-or-pdf>
```

The faction comes from the book's page header (`GF - ROBOT LEGIONS V3.5.3` →
`Robot Legions`). Pass `--faction` only to override it. Downloads cache in `books/`
(gitignored); `--refresh` re-fetches. Needs `pdftotext` (poppler) on PATH.

## Verify

Run every step. Each catches a different silent failure.

1. **Read the `reference-only rules in use` line the importer prints.** These are rules
   the book uses that the engine does not model. Decide for each whether it can change
   a single round's hits or wounds. If one can, see below — importing it as text makes
   it look supported while doing nothing.
2. **`./.venv/Scripts/python.exe -m pytest -q`** — guards name collisions (lookups match
   on name alone, across all factions) and dropdown capacity.
3. **Check `csv/simulation.csv` still references rows that exist.** Replacing a faction
   deletes its old units and weapons; a seeded row pointing at a deleted name silently
   evaluates to zero.
4. **Rebuild and spot-check one unit against the PDF**:
   `./.venv/Scripts/python.exe -m opr_crunch.build`. Compare Quality, Defense and rules
   for one unit you can see on a card.

## Silent failures

| Symptom | Cause |
|---|---|
| Faction appears twice, half the units unselectable | `--faction` spelling differs from the existing rows. Prefer the detected name. |
| A weapon is missing from the dropdown | Its tab outgrew `layout.SOURCE_CAPACITY`; the range stops mid-tab. Raise it. |
| A unit's stats belong to a different unit | Parsed from page 2's roster table instead of the page 4+ cards. See below. |
| Wounds unchanged by a rule the book clearly gives the unit | The rule is imported as text but is not in `model.MODELLED_RULES`. |
| Hits/Wounds blank on a seeded row | `csv/simulation.csv` names a unit or weapon this import removed. |

## Units come from the unit cards, not the roster

Page 2's roster is a grid whose cells do not survive text extraction in reading order —
stats land on the wrong rows. `parse_units` reads the per-unit cards from page 4 onwards
and keeps each column band separate. If you extend the parser, validate against a card
you have actually looked at, not against page 2.

## When the book adds a rule that changes the maths

Data alone is not enough. A rule needs four changes, or it is inert:

1. `opr_crunch/model.py` — the maths, plus an entry in `MODELLED_RULES`
2. `opr_crunch/formulas.py` — the spreadsheet translation
3. `opr_crunch/scenarios.py` — a scenario, so the parity tests cover the formula
4. tests in `tests/test_army_rules.py`

Rules are matched by **substring** in both the model and the sheet, so `Relentless Aura`
grants `Relentless`. Keep those two in step: `model.has()` exists to mirror the sheet's
`SEARCH`.
