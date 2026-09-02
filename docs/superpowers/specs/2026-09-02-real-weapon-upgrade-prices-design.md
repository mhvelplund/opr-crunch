# Real weapon and upgrade prices — Design

Status: approved 2026-09-02. Supersedes §4.3 ("Why weapon prices are not scraped") of
`2026-09-01-unit-costs-and-model-counts-design.md`. Extends `2026-08-31-opr-crunch-design.md`.

## 1. Goal

Weapon-swap and upgrade options currently all cost a flat placeholder (`10`), because
`pdftotext -layout` does not keep a card's `+Npts` price column aligned with the row it
prices. Scrape the real price instead, so `Cost/Wound` reflects an actual loadout rather
than a fiction where every option costs the same.

## 2. Non-goals

- **Replacing `pdftotext` for the existing line-based parsing.** Unit names, stats, rule
  text and weapon profiles keep coming from `pdftotext -layout` exactly as today. Only
  price-matching gets a second, coordinate-based extraction path.
- **Partial-unit weapon swaps, defender cost.** Still out of scope, per the prior spec.
- **A price for every option, unconditionally.** Some prices will not be confidently
  matchable; those are reported and left at a fallback value rather than guessed.

## 3. Tooling migration

This is a prerequisite: getting word coordinates needs a PDF library that isn't
`pdftotext`, and this is a natural point to also stop depending on ad-hoc venv/pip setup.

- Add `pyproject.toml` declaring the project and its runtime dependencies: `openpyxl`,
  `pytest`, `pdfplumber`. Transitive dependencies (`pdfminer.six`, `pypdfium2`, `Pillow`,
  `cryptography`) are resolved and locked by `uv`.
- `mise.toml`: add `[tools] uv = "latest"`. Drop the `python = "3"` tool and the
  `_.python.venv` auto-create env block — `uv sync` now owns `.venv`, sized from
  `pyproject.toml`'s `requires-python`. `tasks.build` becomes
  `run = "uv sync && uv run python -m opr_crunch.build"`.
- `CLAUDE.md`'s Commands section is rewritten around `uv`:

  ```shell
  mise install       # installs uv
  uv sync            # creates .venv, installs openpyxl/pytest/pdfplumber
  uv run pytest
  uv run python -m opr_crunch.build
  ```

  No more `./.venv/Scripts/python.exe` invocations anywhere in the docs.
- The existing `.venv` (created by the old `pip install` workflow) is replaced by uv's own;
  it is not preserved or migrated.
- `pdftotext` (any build — this machine has xpdf's, not poppler's) remains a separate,
  required system binary for the unchanged line-based parsing. This is unrelated to the
  `uv`-managed Python dependencies and is not something `uv sync` can install.

## 4. Price-matching design

### 4.1 Inputs

`import_army_book.import_book` currently takes only the `pdftotext`-extracted `text: str`.
It gains the source PDF `Path` too, so a new pass can open it directly with `pdfplumber`
for word coordinates. (A `.txt` source — used by tests and cached re-runs — has no PDF to
open; price-matching is skipped for those inputs and every option falls back, same as an
unmatched price today.)

### 4.2 Scoping a search to one card

Price-matching runs once per unit card, using the same x-band (`_band`) and line-range
that `armybook._partition` already computes for that card's span. A price token is only
ever considered for the options on the card whose region contains it — it can never drift
across cards, which is the failure mode the prior spec's §4.3 flagged as unacceptable.

For each card's region, `pdfplumber` gives `(text, x0, x1, top, bottom)` per word on the
corresponding page. Words are clustered into visual rows by `top`/`bottom` overlap (tested
against real pages during implementation to fix the tolerance — expect on the order of a
couple of points).

### 4.3 Two-layer matching

1. **Baseline match.** For each row in the card's region containing a price token
   (`+\d+pts` or the literal `Free`, which prices as `0`), check whether that same row's
   text also contains one of the card's already-parsed option names (from `find_weapons`
   or `parse_upgrades`, which already run against the `pdftotext` text). If so, that price
   belongs to that option.
2. **Sequential fallback.** For options in the card that still have no price after step 1,
   and price tokens in the card's region not yet claimed by step 1: if the two lists are
   the same length, zip them in top-to-bottom document order. Lengths that don't match are
   left alone rather than paired by guesswork — this is the scenario `_default_weapon_names`
   already flags as unreliable to guess through.

Anything still unpriced after both layers keeps the fallback (see 4.4).

### 4.4 Fallback and reporting

- Fallback price for an unmatched swap weapon or upgrade option becomes **`0`** (changed
  from today's flat `10` for these two cases — `0` reads unambiguously as "not filled in"
  rather than "this happens to cost 10").
- A starting weapon's cost is unaffected: it is never priced from a `+Npts` token (books
  don't print one for it), so it stays `0` unconditionally, exactly as today.
- Each unmatched option prints a warning line immediately (`  price not found: <unit> / <name>`)
  and is collected into an end-of-run summary block, so a run's output ends with a
  complete, copy-pasteable list of `(unit, faction, option)` needing a manual price in
  `csv/weapons.csv` or `csv/upgrades.csv`.

### 4.5 Code shape

- `armybook.py` gains a function, roughly `match_prices(pdf_path, page_index, card_region,
  options) -> Dict[str, Optional[int]]`, doing the row-clustering and two-layer match for
  one card; `linked_weapons`/`linked_upgrades` (or a thin wrapper in
  `import_army_book.py`) call it per card instead of hardcoding `SWAP_WEAPON_COST`/
  `UPGRADE_COST`.
- `STARTING_WEAPON_COST` stays as-is. `SWAP_WEAPON_COST`/`UPGRADE_COST` stop being flat
  constants and become the documented fallback value (`0`) used only on a match miss.
- `import_book` collects the misses returned across all cards and prints the summary once,
  at the end of the run — after the existing "reference-only rules in use" line.

## 5. CSV / data model impact

None structurally — `Cost` already exists as the last column on `weapons.csv` and
`upgrades.csv`. This changes how that column's *value* is produced during import, and
changes the unmatched fallback from `10` to `0`.

## 6. Re-import

Once implemented, all three books currently in `books/` (Battle Brothers, Havoc Brothers,
Robot Legions) are re-imported so their weapons/upgrades carry real prices. Same process
as the last import: isolated per-book runs, merge into `csv/`, review the diff (expect
`Cost` column changes and nothing else), full `pytest`, rebuild.

## 7. Docs

- `CLAUDE.md`: rewrite the Commands section per §3; rewrite "Editing data"'s placeholder
  explanation (currently describes the flat `10`/`0` scheme) to describe real prices plus
  the `0` + warning fallback.
- `.claude/skills/importing-army-books/SKILL.md`: add a "missing-price summary printed but
  not acted on" row to the silent-failures table, and a Verify step to check it.

## 8. Testing

- New unit tests for the row-clustering/two-layer matching logic, built on synthetic
  word-lists (plain dicts with `text`/`x0`/`top`/etc., matching `pdfplumber`'s word shape)
  rather than real PDF fixtures — mirroring how `test_armybook.py` already tests the
  line-based logic against plain-text `PAGE` fixtures rather than real PDFs.
- Cover: a clean baseline match; a price that drifted onto its own row (sequential
  fallback); a genuine count mismatch (left unmatched, both stay at fallback); a card
  boundary (a price physically near another card's rows must never attach to this one).
- After implementation, spot-check several real scraped prices from at least one book
  against the PDF by hand (same verification style as the unit-cost import), and confirm
  the end-of-run summary lists exactly the options that couldn't be checked that way.
