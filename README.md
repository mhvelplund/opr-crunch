# UnitCrunch for OPR

Builds a Google Sheet that projects **hits** and **wounds** for one combat round in the
[One Page Rules](https://www.onepagerules.com/) system — the equivalent of what
[Unit Crunch](https://www.unitcrunch.com/) does for 40k.

## Build

```shell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install openpyxl pytest   # Linux/macOS: .venv/bin/python
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m opr_crunch.build
```

That writes `dist/opr_crunch.xlsx`.

## Import

1. Upload `dist/opr_crunch.xlsx` to Google Drive.
2. Open it and choose **File -> Save as Google Sheets**.
3. Confirm the import worked: unhide the **Tests** tab and check the summary cell in the `Result` column reads
   `ALL PASS`. That verifies the formulas survived the conversion.

Then use the **Simulation** tab: pick a faction and a unit, and the weapon and upgrade dropdowns filter to what that
unit can actually take. `Hits` and `Wounds` update as you go.

## Layout

| Tab                      | Purpose                                                             |
|--------------------------|----------------------------------------------------------------------|
| `Simulation`             | Entry tab — one attack per row                                     |
| `Units`                  | Name, faction, Quality, Defense, special rules                     |
| `Weapons`                | Unit it belongs to, Attacks, AP/Blast/Deadly/Impact, special rules  |
| `Upgrades`               | Unit it belongs to, rules and AP granted by an upgrade             |
| `Special rules`          | Reference text for the 14 modelled rules                            |
| `Factions`               | Legal faction names                                                 |
| `Lists`, `Calc`, `Tests` | Hidden — dropdown sources, working, self-check                     |

## Editing the data

Every tab's contents come from `csv/`, one file per tab:

```text
csv/simulation.csv     csv/units.csv     csv/weapons.csv
csv/upgrades.csv       csv/special_rules.csv                csv/factions.csv
```

Edit a CSV and re-run the build. `csv/simulation.csv` seeds starting rows on the entry tab; its `Hits` and `Wounds`
columns stay blank, since the build writes formulas there.

Add and remove *rows* freely. Do not reorder or rename *columns* — the lookups compile against fixed column positions,
so the build validates each header against `layout.py` and fails with a diff rather than producing wrong numbers.

Names may repeat **across** factions — several books print a `CCW` or a `Stomp` — because lookups match on `Name` plus
`Faction` via a generated `Key` column. On `Weapons` and `Upgrades`, that key also includes `Unit`: the same weapon
name can belong to more than one unit with a different profile, so it's written as one row per unit rather than
merged. A blank `Unit` means the row is generic to the whole faction. Within one faction, `Name`+`Unit` must still be
unique for `Weapons`/`Upgrades`, and `Name` alone for `Units`.

## Importing an army book

```shell
./.venv/Scripts/python.exe tools/import_army_book.py <url-or-book.pdf>
```

Takes an army-forge URL or a local file. The faction is read from the book's page header (`GF - ROBOT LEGIONS V3.5.3` ->
`Robot Legions`); `--faction` overrides it. Downloads cache in `books/` (gitignored), `--refresh` re-fetches. Needs
`pdftotext` (poppler) on PATH.

Replaces every row for that faction across the CSVs and leaves other factions alone; special rules are merged, since the
core rules share that tab. Re-run the build afterwards.

The `importing-army-books` skill in `.claude/skills/` walks the whole job, including the checks for the failures that
happen silently.

Rules the engine computes are flagged `Modelled = Yes` on the `Special rules` tab. Everything else a book defines —
deployment, movement, morale, spells — is imported as reference text, because it cannot change a single round's hits or
wounds.

## How it works

`opr_crunch/model.py` is a pure-Python reference implementation of the rules; `opr_crunch/formulas.py` emits the
equivalent spreadsheet formulas. The test suite evaluates the generated formulas and asserts they agree with the model,
so the two cannot drift. See `docs/superpowers/specs/2026-08-31-opr-crunch-design.md` for the resolution model and the
accepted deviations from the original requirements.
