---
name: importing-army-books
description: Use when adding or refreshing a faction in this repo from a One Page Rules army-book PDF or army-forge URL, or when a faction's units, weapons, upgrades or special rules are missing, stale or wrong.
---

# Importing Army Books

## Overview

`tools/import_army_book.py` reads an OPR army book and rewrites that faction's rows across `csv/`. Other factions are
untouched; special rules are merged, not replaced, because the core rules share that tab.

**The import is the easy part. The failures are silent** — nothing errors, the sheet just quietly computes with data it
cannot see or rules it does not model. Work the Verify section, don't skip to "it printed some counts".

## Import

```shell
./.venv/Scripts/python.exe tools/import_army_book.py <url-or-pdf>
```

The faction comes from the book's page header (`GF - ROBOT LEGIONS V3.5.3` → `Robot Legions`). Pass `--faction` only to
override it. Downloads cache in `books/` (gitignored); `--refresh` re-fetches. Needs `pdftotext` (poppler) on PATH.

## Verify

Run every step. Each catches a different silent failure.

1. **Read the `reference-only rules in use` line the importer prints.** These are rules the book uses that the engine
   does not model. Decide for each whether it can change a single round's hits or wounds. If one can, see below —
   importing it as text makes it look supported while doing nothing.
2. **`./.venv/Scripts/python.exe -m pytest -q`** — guards duplicate Name|Faction keys, dropdown
   capacity, and seeded Simulation rows left pointing at data a later import deleted.
3. **Check `csv/simulation.csv` still references rows that exist.** Replacing a faction deletes its old units and
   weapons; a seeded row pointing at a deleted name silently evaluates to zero.
4. **Rebuild and spot-check one unit against the PDF**: `./.venv/Scripts/python.exe -m opr_crunch.build`. Compare
   Quality, Defense and rules for one unit you can see on a card.
5. **Check the importer's "price not found" summary, if it printed one.** Each listed
   `(unit, option)` needs its real price entered by hand in `csv/weapons.csv` or
   `csv/upgrades.csv` - the importer already set it to `0` rather than guess.

## Silent failures

| Symptom                                                    | Cause                                                                          |
|------------------------------------------------------------|--------------------------------------------------------------------------------|
| Faction appears twice, half the units unselectable         | `--faction` spelling differs from the existing rows. Prefer the detected name. |
| A weapon is missing from the dropdown                      | Its tab outgrew `layout.CAPACITY[tab]`; the range stops mid-tab. Raise it.   |
| A unit's stats belong to a different unit                  | Parsed from page 2's roster table instead of the page 4+ cards. See below.     |
| Wounds unchanged by a rule the book clearly gives the unit | The rule is imported as text but is not in `model.MODELLED_RULES`.             |
| Hits/Wounds blank on a seeded row                          | `csv/simulation.csv` names a unit or weapon this import removed.               |
| A weapon's stats look like another faction's | Two books print that name; lookups key on Name-plus-Faction, so check the tab has its generated `Key` column. |
| A weapon/upgrade option's Cost is 0 when it shouldn't be | Its price couldn't be matched from the PDF - check the importer's end-of-run "price not found" summary and fill it in by hand. |

## Units come from the unit cards, not the roster

Page 2's roster is a grid whose cells do not survive text extraction in reading order — stats land on the wrong rows.
`parse_units` reads the per-unit cards from page 4 onwards and keeps each column band separate. If you extend the
parser, validate against a card you have actually looked at, not against page 2.

## When the book adds a rule that changes the maths

Data alone is not enough. A rule needs four changes, or it is inert:

1. `opr_crunch/model.py` — the maths, plus an entry in `MODELLED_RULES`
2. `opr_crunch/formulas.py` — the spreadsheet translation
3. `opr_crunch/scenarios.py` — a scenario, so the parity tests cover the formula
4. tests in `tests/test_army_rules.py`

Rules are matched by **substring** in both the model and the sheet, so `Relentless Aura` grants `Relentless`. Keep those
two in step: `model.has()` exists to mirror the sheet's `SEARCH`. Watch for a rule whose name contains another's:
`Unpredictable Fighter` contains `Unpredictable`, and had to be excluded explicitly.

A rule granting *"either AP(+1) or +1 to hit"* does not fit a single pass. The engine resolves both branches and
takes a weighted sum: `var_active` switches the mixture on and `w_ap` weights it — 1/2 for a die roll like
`Unpredictable`, or 0/1 for a player's choice like `Versatile Attack`, which reads the Simulation tab's
`Variable effect` column.
