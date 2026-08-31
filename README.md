# UnitCrunch for OPR

Builds a Google Sheet that projects **hits** and **wounds** for one combat round in the
[One Page Rules](https://www.onepagerules.com/) system — the equivalent of what
[Unit Crunch](https://www.unitcrunch.com/) does for 40k.

## Build

```sh
python -m venv .venv
./.venv/Scripts/python.exe -m pip install openpyxl pytest   # Linux/macOS: .venv/bin/python
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m opr_crunch.build
```

That writes `dist/opr_crunch.xlsx`.

## Import

1. Upload `dist/opr_crunch.xlsx` to Google Drive.
2. Open it and choose **File -> Save as Google Sheets**.
3. Confirm the import worked: unhide the **Tests** tab and check the summary cell in the
   `Result` column reads `ALL PASS`. That verifies the formulas survived the conversion.

Then use the **Simulation** tab: pick a faction, and the attacker, upgrade and weapon
dropdowns filter to that faction. `Hits` and `Wounds` update as you go.

## Layout

| Tab | Purpose |
|---|---|
| `Simulation` | Entry tab — one attack per row |
| `Units` | Name, faction, Quality, Defense, special rules |
| `Weapons` | Attacks, AP/Blast/Deadly/Impact values, special rules |
| `Upgrades` | Rules and AP granted by an upgrade |
| `Special rules` | Reference text for the 14 modelled rules |
| `Factions` | Legal faction names |
| `Lists`, `Calc`, `Tests` | Hidden — dropdown sources, working, self-check |

Seed data is illustrative only; replace it with real army-list entries. **Names must be
unique** within `Units`, `Weapons` and `Upgrades`, because lookups match on name alone.

## How it works

`opr_crunch/model.py` is a pure-Python reference implementation of the rules;
`opr_crunch/formulas.py` emits the equivalent spreadsheet formulas. The test suite
evaluates the generated formulas and asserts they agree with the model, so the two
cannot drift. See `docs/superpowers/specs/2026-08-31-opr-crunch-design.md` for the
resolution model and the accepted deviations from the original requirements.
