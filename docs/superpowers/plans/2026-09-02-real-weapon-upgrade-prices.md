# Real Weapon/Upgrade Prices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape real `+Npts` prices for weapon-swap and upgrade options out of the army-book PDFs (instead of the flat `10` placeholder), and migrate the project's Python dependency management to `pyproject.toml` + `uv` (installed via `mise`) so `pdfplumber` can be added cleanly.

**Architecture:** A new, self-contained pass in `opr_crunch/armybook.py` reads each PDF a second time with `pdfplumber` to get word coordinates, clusters words into visual rows scoped to one unit card at a time (mirroring the existing `_partition` card-scoping, but in point-space), and attaches a price to each already-parsed option name by row-text containment, falling back to a single-leftover pairing when exactly one option and one price remain unclaimed on a card. Anything still unmatched keeps the existing `0`-cost path used for starting weapons, plus a warning and an end-of-run summary. The existing `pdftotext -layout` based parsing (names, stats, rules, weapon profiles) is untouched.

**Tech Stack:** Python 3.11+, `uv` for dependency management, `pdfplumber` (new dependency) for word-coordinate PDF extraction, `pdftotext` (external binary, unchanged) for the existing text extraction, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-02-real-weapon-upgrade-prices-design.md`

## Global Constraints

- `pdftotext` stays a required external binary on PATH for the unchanged line-based parsing — this plan does not remove that dependency.
- Starting-weapon rows are never priced from a `+Npts` token and stay at cost `0` unconditionally (unchanged behavior).
- A price is only ever matched within the card region it was found in — never across two different units' cards, even when their rows visually share the same PDF baseline (two-up layout).
- An unmatched swap/upgrade option's fallback cost is `0` (not `10`), and must produce both an immediate warning line and an entry in the end-of-run summary.
- Re-importing a book must not change anything in `csv/*.csv` other than the `Cost` column on `weapons.csv`/`upgrades.csv` — any other diff is a regression, not an expected consequence (mirrors the constraint from the Sept 1 costs spec).

---

### Task 1: Migrate dependency management to `pyproject.toml` + `uv`

**Files:**
- Create: `pyproject.toml`
- Modify: `mise.toml`
- Modify: `CLAUDE.md:9-31` (Commands section)
- Modify: `README.md:8-15` (Build section)
- Test: none (tooling change; verified by running the existing suite through the new workflow)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a working `uv run pytest` / `uv run python -m opr_crunch.build` workflow that every later task's Verify steps use instead of `./.venv/Scripts/python.exe`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "opr-crunch"
version = "0.1.0"
description = "Generates a hits/wounds projection workbook for One Page Rules armies."
requires-python = ">=3.11"
dependencies = [
    "openpyxl>=3.1",
    "pdfplumber>=0.11",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]
```

- [ ] **Step 2: Update `mise.toml`**

Replace the whole file with:

```toml
[tools]
uv = "latest"

[tasks.build]
description = "Build dist/opr_crunch.xlsx from the CSVs"
run = "uv sync && uv run python -m opr_crunch.build"
```

This drops the `python = "3"` tool and the `_.python.venv` auto-create `[env]` block — `uv sync` now owns `.venv`, sized from `pyproject.toml`'s `requires-python`.

- [ ] **Step 3: Remove the old venv and sync with uv**

```bash
rm -rf .venv
mise install
uv sync
```

Expected: `uv sync` creates a new `.venv` and reports installing `openpyxl`, `pdfplumber` (and its transitive deps: `pdfminer.six`, `pypdfium2`, `Pillow`, `cryptography`, `charset-normalizer`, `cffi`, `pycparser`), and `pytest`. A `uv.lock` file appears in the project root — this should be committed alongside `pyproject.toml`.

- [ ] **Step 4: Verify the existing suite passes under the new workflow**

Run: `uv run pytest -q`
Expected: `406 passed` (the same count as before this plan — this step only changes *how* the interpreter is invoked, not any test).

- [ ] **Step 5: Verify the build task works**

Run: `mise run build`
Expected: `wrote dist\opr_crunch.xlsx` (via the new `uv sync && uv run python -m opr_crunch.build` task).

- [ ] **Step 6: Rewrite `CLAUDE.md`'s Commands section**

Replace lines 9-31 (from `## Commands` through the `Requires pdftotext...` line) with:

````markdown
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
````

- [ ] **Step 7: Rewrite `README.md`'s Build section**

Replace lines 8-15 (the ` ```shell ... ``` ` block plus its trailing sentence) with:

````markdown
```shell
mise install
uv sync
uv run pytest
uv run python -m opr_crunch.build
```

That writes `dist/opr_crunch.xlsx`. Once `uv sync` has run once, `mise run build` does the same thing.
````

- [ ] **Step 8: Update `.gitignore` if needed**

Check `.gitignore` for a `.venv` entry (it should already be there from the old workflow — confirm, don't duplicate). `uv.lock` should NOT be ignored (it's meant to be committed).

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock mise.toml CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
Migrate dependency management to pyproject.toml + uv

Replaces the ad-hoc pip-into-.venv workflow with uv, installed via
mise, so pdfplumber (needed for the next commit's word-coordinate
price matching) can be added as a normal declared dependency instead
of a manual pip install.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 2: Row-clustering and band-boundary primitives

**Files:**
- Modify: `opr_crunch/armybook.py` (new section, after the existing "sources" section at the end of the file)
- Test: `tests/test_armybook.py` (new test class)

**Interfaces:**
- Consumes: nothing from earlier tasks (pure functions operating on plain dicts shaped like `pdfplumber`'s `extract_words()` output: `{"text": str, "x0": float, "top": float}`).
- Produces:
  - `PRICE: re.Pattern` — matches `+Npts` (group 1 = N) or the literal `Free`.
  - `_rows_in_band(words: List[dict], x_min: float, x_max: float, top_min: float, top_max: float) -> List[Tuple[float, str]]` — `(top, row_text)` pairs, sorted top-to-bottom, for words inside the given box.
  - `_band_bounds(xs: List[float], gap: float = 40) -> List[Tuple[float, float]]` — one `(low, high)` per clustered anchor, covering `-inf`..`inf` between neighbours.

These are used by Task 3's region/matching code.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_armybook.py`:

```python
class TestRowsInBand:
    WORDS = [
        {"text": "Plasma", "x0": 10, "top": 100},
        {"text": "Caster", "x0": 45, "top": 100},
        {"text": "+10pts", "x0": 200, "top": 100},
        {"text": "Flame", "x0": 10, "top": 120},
        {"text": "Caster", "x0": 40, "top": 120},
        {"text": "+15pts", "x0": 200, "top": 120},
        {"text": "Other", "x0": 300, "top": 100},  # outside the x-range
    ]

    def test_words_join_into_one_row_by_rounded_top(self):
        rows = armybook._rows_in_band(self.WORDS, x_min=0, x_max=250, top_min=0, top_max=1000)
        assert rows == [
            (100, "Plasma Caster +10pts"),
            (120, "Flame Caster +15pts"),
        ]

    def test_words_outside_the_x_range_are_excluded(self):
        rows = armybook._rows_in_band(self.WORDS, x_min=0, x_max=250, top_min=0, top_max=1000)
        assert "Other" not in " ".join(text for _, text in rows)

    def test_words_outside_the_top_range_are_excluded(self):
        rows = armybook._rows_in_band(self.WORDS, x_min=0, x_max=250, top_min=0, top_max=110)
        assert rows == [(100, "Plasma Caster +10pts")]

    def test_a_row_close_but_not_identical_top_still_groups(self):
        """pdfplumber tops within the same visual row can differ by a fraction
        of a point between words; rounding to the nearest point groups them."""
        words = [
            {"text": "A", "x0": 0, "top": 100.2},
            {"text": "B", "x0": 10, "top": 99.8},
        ]
        rows = armybook._rows_in_band(words, x_min=0, x_max=100, top_min=0, top_max=1000)
        assert rows == [(100, "A B")]


class TestBandBounds:
    def test_two_well_separated_anchors_split_at_the_midpoint(self):
        bounds = armybook._band_bounds([126.0, 402.0])
        assert bounds[0] == (-1, pytest.approx(264.0))
        assert bounds[1] == (pytest.approx(264.0), float("inf"))

    def test_a_single_anchor_covers_everything(self):
        assert armybook._band_bounds([126.0]) == [(-1, float("inf"))]

    def test_anchors_closer_than_the_gap_merge_into_one_band(self):
        """Two words of the same card's name (e.g. a two-word unit name) must
        not be mistaken for two separate cards."""
        bounds = armybook._band_bounds([126.0, 140.0, 402.0])
        assert len(bounds) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_armybook.py::TestRowsInBand tests/test_armybook.py::TestBandBounds -v`
Expected: FAIL with `AttributeError: module 'opr_crunch.armybook' has no attribute '_rows_in_band'`

- [ ] **Step 3: Implement**

Add to the end of `opr_crunch/armybook.py`:

```python
# --------------------------------------------------------------------------
# real prices (word coordinates)
# --------------------------------------------------------------------------

#: A card's ``+Npts`` price, or the literal ``Free`` some first upgrade slots use.
PRICE = re.compile(r"\+(\d+)pts|\bFree\b")


def _rows_in_band(
    words: List[dict], x_min: float, x_max: float, top_min: float, top_max: float
) -> List[Tuple[float, str]]:
    """Visual rows built only from words inside one card's box.

    Filtering by position *before* joining words into a row is what keeps two
    side-by-side cards' options from being concatenated into one row's text
    when they happen to share a baseline - a real occurrence in these books'
    two-up upgrade tables.
    """
    banded = [w for w in words if x_min <= w["x0"] < x_max and top_min <= w["top"] < top_max]
    rows: Dict[int, List[dict]] = {}
    for w in banded:
        rows.setdefault(round(w["top"]), []).append(w)
    return [
        (top, " ".join(w["text"] for w in sorted(rows[top], key=lambda w: w["x0"])))
        for top in sorted(rows)
    ]


def _band_bounds(xs: List[float], gap: float = 40) -> List[Tuple[float, float]]:
    """One (low, high) span per clustered x-anchor, covering -inf..inf overall.

    Mirrors the character-column clustering ``_columns_of`` already does for
    the special-rules page, but in PDF point-space rather than text columns -
    the two are not on the same scale, so this is a separate small helper
    rather than a shared one.
    """
    anchors: List[float] = []
    for x in sorted(xs):
        if not anchors or x - anchors[-1] > gap:
            anchors.append(x)
    bounds = []
    for i, a in enumerate(anchors):
        lo = -1.0 if i == 0 else (anchors[i - 1] + a) / 2
        hi = float("inf") if i == len(anchors) - 1 else (a + anchors[i + 1]) / 2
        bounds.append((lo, hi))
    return bounds
```

Add `Tuple` to the existing `from typing import Dict, List, Optional, Tuple` import if not already present (it already is, per the current file).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_armybook.py::TestRowsInBand tests/test_armybook.py::TestBandBounds -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add opr_crunch/armybook.py tests/test_armybook.py
git commit -m "$(cat <<'EOF'
Add row-clustering and band-boundary primitives for price matching

First piece of the word-coordinate price-matching pass: group
pdfplumber words into visual rows scoped to a box (so two side-by-side
cards' options never get concatenated), and cluster x-anchors into
band boundaries. Pure functions, tested against synthetic word lists.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 3: Two-layer price matching for one card

**Files:**
- Modify: `opr_crunch/armybook.py`
- Test: `tests/test_armybook.py` (new test class)

**Interfaces:**
- Consumes: `PRICE` from Task 2.
- Produces: `_match_prices(card_rows: List[Tuple[float, str]], option_names: List[str]) -> Dict[str, int]` — `{option_name: price}` for whichever options in `option_names` could be confidently matched against a price token in `card_rows`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_armybook.py`:

```python
class TestMatchPrices:
    def test_a_price_on_the_same_row_as_its_option_is_matched(self):
        rows = [(191.0, 'Plasma Caster (24", A1, AP(4)) +10pts')]
        assert armybook._match_prices(rows, ["Plasma Caster"]) == {"Plasma Caster": 10}

    def test_free_prices_as_zero(self):
        rows = [(410.0, "Twin Atom-Caster (12\", A2, AP(1)) Free")]
        assert armybook._match_prices(rows, ["Twin Atom-Caster"]) == {"Twin Atom-Caster": 0}

    def test_the_longer_of_two_overlapping_names_wins(self):
        """'Storm Rifle' is a substring of 'Champion Storm Rifle' - the row
        naming the longer, more specific option must not be stolen by the
        shorter one."""
        rows = [(1.0, 'Champion Storm Rifle (24", A4, AP(1)) +75pts')]
        matched = armybook._match_prices(rows, ["Storm Rifle", "Champion Storm Rifle"])
        assert matched == {"Champion Storm Rifle": 75}

    def test_a_single_leftover_name_and_price_are_paired(self):
        """A price that drifted onto its own row (the pdftotext-layout
        wrapping artifact this whole feature exists to work around) - but
        here recovered straight from pdfplumber's own row grouping, so this
        covers the case where a name and its price still end up on separate
        rows even in true coordinates (e.g. a very long option name)."""
        rows = [
            (1.0, "Some Very Long Option Name (A2, AP(1), Rending)"),
            (2.0, "+35pts"),
        ]
        assert armybook._match_prices(rows, ["Some Very Long Option Name"]) == {
            "Some Very Long Option Name": 35
        }

    def test_two_leftover_names_and_prices_are_not_guessed(self):
        rows = [(1.0, "First Option"), (2.0, "+10pts"), (3.0, "Second Option"), (4.0, "+20pts")]
        assert armybook._match_prices(rows, ["First Option", "Second Option"]) == {}

    def test_an_option_with_no_price_row_at_all_is_left_unmatched(self):
        rows = [(1.0, 'Plasma Caster (24", A1, AP(4)) +10pts')]
        matched = armybook._match_prices(rows, ["Plasma Caster", "Ray Caster"])
        assert matched == {"Plasma Caster": 10}
        assert "Ray Caster" not in matched
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_armybook.py::TestMatchPrices -v`
Expected: FAIL with `AttributeError: module 'opr_crunch.armybook' has no attribute '_match_prices'`

- [ ] **Step 3: Implement**

Add to `opr_crunch/armybook.py`, after `_band_bounds`:

```python
def _match_prices(card_rows: List[Tuple[float, str]], option_names: List[str]) -> Dict[str, int]:
    """Attach a scraped price to as many of ``option_names`` as can be done
    with confidence, out of one card's rows.

    Layer 1: a row naming both a price and one of the options is a direct
    match - the longer of two overlapping names wins, so 'Champion Storm
    Rifle' isn't stolen by a shorter 'Storm Rifle' option on the same card.
    Layer 2: if that leaves exactly one option and one price unclaimed, they
    are paired - the common case is a name too long for its own row, wrapping
    the price onto the next one. Anything else (zero, or more than one, of
    either) is left unmatched rather than guessed; the caller reports these.
    """
    unclaimed_names = list(option_names)
    unclaimed_prices: List[int] = []
    matches: Dict[str, int] = {}

    for _, text in card_rows:
        found = PRICE.search(text)
        if not found:
            continue
        price = 0 if found.group(0) == "Free" else int(found.group(1))
        candidates = [n for n in unclaimed_names if n in text]
        if candidates:
            name = max(candidates, key=len)
            matches[name] = price
            unclaimed_names.remove(name)
        else:
            unclaimed_prices.append(price)

    if len(unclaimed_names) == 1 and len(unclaimed_prices) == 1:
        matches[unclaimed_names[0]] = unclaimed_prices[0]
    return matches
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_armybook.py::TestMatchPrices -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add opr_crunch/armybook.py tests/test_armybook.py
git commit -m "$(cat <<'EOF'
Add two-layer price matching for one unit card

Layer 1 matches a price to an option printed on the same visual row;
layer 2 pairs a single leftover name with a single leftover price (the
long-name-wraps-the-price case). Anything else is left unmatched so
the caller can fall back and report it, rather than guessing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 4: Locate each unit's card region in `pdfplumber` coordinates

**Files:**
- Modify: `opr_crunch/armybook.py`
- Test: `tests/test_armybook.py` (new test class)

**Interfaces:**
- Consumes: `_band_bounds` from Task 2.
- Produces: `_card_regions(units: List[dict], pages_words: List[List[dict]], page_heights: List[float]) -> Dict[str, Tuple[int, float, float, float, float]]` — `unit name -> (page_index, x_min, x_max, top_min, top_max)` for every unit whose card header could be found verbatim in `pages_words`; a unit not found is simply absent from the returned dict (the caller treats that as "no region", falling back for all of that unit's options).

`units` is `parse_units`'s output (each dict has `name`, `size`, `cost`). `pages_words` is one `page.extract_words(...)` list per PDF page, in the same order as `pdf.pages`. `page_heights` is `[page.height for page in pdf.pages]`, used as the bottom bound for the last card in a band on a page.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_armybook.py`:

```python
class TestCardRegions:
    UNITS = [
        {"name": "Warriors", "size": 5, "cost": 100},
        {"name": "Snipers", "size": 3, "cost": 110},
    ]

    #: One page, two cards side by side - Warriors left, Snipers right -
    #: each with one option row below its header, mirroring a real card page.
    PAGE_WORDS = [
        {"text": "Warriors", "x0": 126, "top": 57},
        {"text": "[5]", "x0": 156, "top": 57},
        {"text": "-", "x0": 169, "top": 57},
        {"text": "100pts", "x0": 173, "top": 57},
        {"text": "Snipers", "x0": 402, "top": 57},
        {"text": "[3]", "x0": 427, "top": 57},
        {"text": "-", "x0": 445, "top": 57},
        {"text": "110pts", "x0": 449, "top": 57},
        {"text": "Gauss", "x0": 126, "top": 163},
        {"text": "Rifle", "x0": 155, "top": 163},
        {"text": "+10pts", "x0": 300, "top": 163},
        {"text": "D-Marks", "x0": 402, "top": 163},
        {"text": "+15pts", "x0": 550, "top": 163},
    ]

    def test_both_cards_are_found(self):
        regions = armybook._card_regions(self.UNITS, [self.PAGE_WORDS], [800.0])
        assert set(regions) == {"Warriors", "Snipers"}

    def test_each_card_is_scoped_to_its_own_band(self):
        regions = armybook._card_regions(self.UNITS, [self.PAGE_WORDS], [800.0])
        page_index, x_min, x_max, top_min, top_max = regions["Warriors"]
        assert page_index == 0
        assert x_min < 200 <= x_max  # Warriors' own price row (x0=300) is out of range...
        # ...specifically, the band boundary falls between the two cards' anchors:
        assert x_min < 126 and x_max <= 402

    def test_a_card_not_found_verbatim_is_absent(self):
        units = self.UNITS + [{"name": "Ghost Unit", "size": 1, "cost": 999}]
        regions = armybook._card_regions(units, [self.PAGE_WORDS], [800.0])
        assert "Ghost Unit" not in regions

    def test_rows_in_each_region_only_see_that_cards_own_words(self):
        regions = armybook._card_regions(self.UNITS, [self.PAGE_WORDS], [800.0])
        page_index, x_min, x_max, top_min, top_max = regions["Warriors"]
        rows = armybook._rows_in_band(self.PAGE_WORDS, x_min, x_max, top_min, top_max)
        joined = " ".join(text for _, text in rows)
        assert "Gauss Rifle +10pts" in joined
        assert "D-Marks" not in joined
        assert "+15pts" not in joined
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_armybook.py::TestCardRegions -v`
Expected: FAIL with `AttributeError: module 'opr_crunch.armybook' has no attribute '_card_regions'`

- [ ] **Step 3: Implement**

Add to `opr_crunch/armybook.py`, after `_match_prices`:

```python
def _find_card_anchor(name: str, size: int, cost: int, words: List[dict]) -> Optional[Tuple[float, float]]:
    """(x0, top) of this unit's card header on one page, or None.

    Looks for the exact printed header - "Name [size] - costpts" - built the
    same way CARD's own text is: a plain unit name never contains the
    characters CARD's regex itself excludes, so this string is unambiguous.
    """
    needle = f"{name} [{size}] - {cost}pts"
    first_word = name.split()[0]
    rows: Dict[int, List[dict]] = {}
    for w in words:
        rows.setdefault(round(w["top"]), []).append(w)
    for top, row_words in rows.items():
        row_words = sorted(row_words, key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in row_words)
        if needle in text:
            anchor = next(w for w in row_words if w["text"] == first_word)
            return anchor["x0"], top
    return None


def _card_regions(
    units: List[dict], pages_words: List[List[dict]], page_heights: List[float]
) -> Dict[str, Tuple[int, float, float, float, float]]:
    """(page_index, x_min, x_max, top_min, top_max) per unit whose card header
    could be found verbatim in ``pages_words``.

    Mirrors ``_partition``'s card-to-card spanning (a card runs from its own
    header to the next one in the same band, or the page's end) but in
    ``pdfplumber`` point-space rather than text-line/character-column space,
    since the two extractions don't share a coordinate system.
    """
    anchors: Dict[str, Tuple[int, float, float]] = {}
    for u in units:
        for page_index, words in enumerate(pages_words):
            found = _find_card_anchor(u["name"], u["size"], u["cost"], words)
            if found:
                anchors[u["name"]] = (page_index, found[0], found[1])
                break

    by_page: Dict[int, List[Tuple[str, float, float]]] = {}
    for name, (page_index, x0, top) in anchors.items():
        by_page.setdefault(page_index, []).append((name, x0, top))

    regions: Dict[str, Tuple[int, float, float, float, float]] = {}
    for page_index, entries in by_page.items():
        bounds = _band_bounds([x0 for _, x0, _ in entries])
        for name, x0, top in entries:
            x_min, x_max = next((lo, hi) for lo, hi in bounds if lo <= x0 < hi)
            same_band_tops = sorted(t for n2, x2, t in entries if x_min <= x2 < x_max)
            next_top = next((t for t in same_band_tops if t > top), page_heights[page_index])
            regions[name] = (page_index, x_min, x_max, top, next_top)
    return regions
```

`Optional` is already imported. Add `_find_card_anchor` as a module-private helper (leading underscore, consistent with the file's existing convention for internal helpers like `_partition`/`_band`).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_armybook.py::TestCardRegions -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add opr_crunch/armybook.py tests/test_armybook.py
git commit -m "$(cat <<'EOF'
Locate each unit's card region in pdfplumber coordinates

Finds a unit's card header verbatim in the word-coordinate extraction
and spans it to the next card in the same band (or the page bottom),
mirroring _partition's existing card-to-card spanning but in point-
space. This is the scoping that keeps price matching from ever
crossing between two different units' cards.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 5: `apply_real_prices` entry point

**Files:**
- Modify: `opr_crunch/armybook.py`
- Test: `tests/test_armybook.py` (new test class)

**Interfaces:**
- Consumes: `_card_regions`, `_rows_in_band`, `_match_prices` from Tasks 2-4. `SWAP_WEAPON_COST`, `STARTING_WEAPON_COST`, `UPGRADE_COST` (existing module constants).
- Produces: `apply_real_prices(pdf_path: Path, units: List[dict], weapon_rows: List[Tuple[str, str, dict]], upgrade_names: List[Tuple[str, str]]) -> Tuple[List[Tuple[str, str, dict]], Dict[Tuple[str, str], int], List[Tuple[str, str]]]` — patched `weapon_rows` (same shape as the input, only `cost` fields changed on rows that needed pricing), a `{(unit, name): price}` dict for every upgrade that matched (upgrades have no `cost` field on their own tuple, so this is returned separately rather than patched in place), and a list of `(unit, option name)` pairs that could not be matched (the caller applies the `UNMATCHED_PRICE_FALLBACK` fallback and reports these - `apply_real_prices` itself never writes that fallback into a weapon row, so a miss is always visible). This is what `tools/import_army_book.py` calls in Task 6. Also introduces the module constant `UNMATCHED_PRICE_FALLBACK = 0`, added next to the existing `STARTING_WEAPON_COST`/`SWAP_WEAPON_COST`/`UPGRADE_COST` block without changing those three values (see the note on that distinction below, before the implementation).

This task takes a real PDF `Path` and calls `pdfplumber.open(...)`, so its own tests use a tiny real PDF fixture rather than synthetic dicts (unlike Tasks 2-4, which test pure functions). Build the fixture with `pdfplumber`'s own writer is not available, so instead this task's tests exercise `apply_real_prices`'s *routing* logic (which rows get touched, which don't, how misses are collected) by monkeypatching `pdfplumber.open` to return a small fake `Page`-like object exposing `.extract_words()` and `.height` — this keeps the test fast and avoids needing a real PDF fixture file in the repo.

- [ ] **Step 1: Write the failing tests**

Add `from pathlib import Path` to `tests/test_armybook.py`'s existing imports (currently just `import pytest` and `from opr_crunch import armybook`) - these tests construct a `Path("fake.pdf")` to pass in.

Add to `tests/test_armybook.py`:

```python
class _FakePage:
    def __init__(self, words, height=800.0):
        self._words = words
        self.height = height

    def extract_words(self, **kwargs):
        return self._words


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestApplyRealPrices:
    UNITS = [{"name": "Warriors", "size": 5, "cost": 100}]

    PAGE_WORDS = [
        {"text": "Warriors", "x0": 126, "top": 57},
        {"text": "[5]", "x0": 156, "top": 57},
        {"text": "-", "x0": 169, "top": 57},
        {"text": "100pts", "x0": 173, "top": 57},
        {"text": "Gauss", "x0": 126, "top": 163},
        {"text": "Rifle", "x0": 155, "top": 163},
        {"text": "+10pts", "x0": 300, "top": 163},
    ]

    def _apply(self, monkeypatch, weapon_rows, upgrade_rows=()):
        monkeypatch.setattr(
            armybook.pdfplumber, "open", lambda path: _FakePdf([_FakePage(self.PAGE_WORDS)])
        )
        return armybook.apply_real_prices(
            Path("fake.pdf"), self.UNITS, list(weapon_rows), list(upgrade_rows)
        )

    def test_a_matched_swap_weapon_gets_its_real_price(self, monkeypatch):
        rows = [("Warriors", "Gauss Rifle", dict(cost=armybook.SWAP_WEAPON_COST, attacks=1))]
        new_weapons, _, misses = self._apply(monkeypatch, rows)
        assert new_weapons == [("Warriors", "Gauss Rifle", dict(cost=10, attacks=1))]
        assert misses == []

    def test_a_starting_weapon_is_never_touched(self, monkeypatch):
        rows = [("Warriors", "Reaper Rifles", dict(cost=armybook.STARTING_WEAPON_COST, attacks=1))]
        new_weapons, _, misses = self._apply(monkeypatch, rows)
        assert new_weapons == rows
        assert misses == []

    def test_an_unmatchable_option_falls_back_to_zero_and_is_reported(self, monkeypatch):
        rows = [("Warriors", "Nonexistent Weapon", dict(cost=armybook.SWAP_WEAPON_COST, attacks=1))]
        new_weapons, _, misses = self._apply(monkeypatch, rows)
        assert new_weapons == [("Warriors", "Nonexistent Weapon", dict(cost=0, attacks=1))]
        assert misses == [("Warriors", "Nonexistent Weapon")]

    def test_upgrades_are_priced_the_same_way(self, monkeypatch):
        rows = [("Warriors", "Gauss Rifle", ["Destructive"])]
        _, new_upgrades, misses = self._apply(monkeypatch, [], rows)
        assert new_upgrades == [("Warriors", "Gauss Rifle", ["Destructive"])]
        # Gauss Rifle here has no matching weapon row, but the price row still
        # exists on the card, so it resolves the same way an upgrade would:
        assert misses == [] or misses == [("Warriors", "Gauss Rifle")]
```

Note on the last test: whether an upgrade named the same as a priced weapon row resolves depends only on whether `_match_prices` finds `"Gauss Rifle"` in the card's rows for that unit's upgrade pass too - it will, since upgrade option names are matched against the same card region independently of weapon rows. Confirm this once Step 3 is implemented and tighten the assertion to a single expected value (drop the `or`) before committing.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_armybook.py::TestApplyRealPrices -v`
Expected: FAIL with `AttributeError: module 'opr_crunch.armybook' has no attribute 'apply_real_prices'`

- [ ] **Step 3: Implement**

Add `import pdfplumber` to the top of `opr_crunch/armybook.py`'s import block (alongside the existing `import re` etc). Also add `Path` to its existing `from pathlib import PurePosixPath` line, making it `from pathlib import Path, PurePosixPath` - the module only imports `PurePosixPath` today (used by `cache_name`), and `apply_real_prices`'s signature below needs `Path`.

**Note on `upgrade_rows`'s shape:** `linked_upgrades` (existing code) returns `(unit, name, granted_rules)` tuples with **no cost field at all** - `import_army_book.py` applies `UPGRADE_COST` as a separate literal when building the CSV row. So `apply_real_prices` takes just the `(unit, name)` pairs for upgrades (`upgrade_names`, extracted by the caller from `linked_upgrades`'s output) and returns their prices as a separate `Dict[Tuple[str, str], int]` rather than trying to rewrite a cost field that doesn't exist on the upgrade tuple.

**Note on the `SWAP_WEAPON_COST`/`STARTING_WEAPON_COST` distinction:** `linked_weapons`'s existing dedup logic (in `opr_crunch/armybook.py`, already shipped, not touched by this plan) prefers a starting-weapon row over a swap row for the same `(unit, name, profile)` by comparing `profile["cost"] < best[key][2]["cost"]` - relying on `STARTING_WEAPON_COST (0) < SWAP_WEAPON_COST (10)`. `apply_real_prices` below also uses `profile["cost"] == SWAP_WEAPON_COST` to detect "this row needs a real price". Both of these break if `SWAP_WEAPON_COST` and `STARTING_WEAPON_COST` are ever made equal - so `SWAP_WEAPON_COST`/`UPGRADE_COST` **stay at their current value of `10`, unchanged**, used purely as an internal "not yet priced" marker that never reaches the CSV once this function runs. Add a new, distinct constant for the value actually written to CSV on a miss:

```python
#: Written to the CSV when apply_real_prices can't confidently match a
#: price - distinct from SWAP_WEAPON_COST/UPGRADE_COST (which stay internal
#: "needs pricing" markers so linked_weapons's existing dedup, and the
#: check below, can still tell a swap/upgrade option apart from a starting
#: weapon even after this constant makes both read as 0 on the sheet).
UNMATCHED_PRICE_FALLBACK = 0
```

Add this constant directly below the existing `STARTING_WEAPON_COST`/`SWAP_WEAPON_COST`/`UPGRADE_COST` block (do not change those three constants' values).

Add to `opr_crunch/armybook.py`, after `_card_regions`:

```python
def apply_real_prices(
    pdf_path: Path,
    units: List[dict],
    weapon_rows: List[Tuple[str, str, dict]],
    upgrade_names: List[Tuple[str, str]],
) -> Tuple[List[Tuple[str, str, dict]], Dict[Tuple[str, str], int], List[Tuple[str, str]]]:
    """Replace the internal "needs pricing" marker cost with a real price
    scraped from the PDF's word coordinates, where one can be matched.

    A starting weapon (cost == STARTING_WEAPON_COST) is never touched - the
    book prints no +Npts for it at all. A weapon row whose cost is
    SWAP_WEAPON_COST needs a price; ``upgrade_names`` (every upgrade option
    always needs one) is a separate (unit, name) list because linked_upgrades
    carries no cost field to mark in the first place. Anything that can't be
    confidently matched is returned in the third element (misses) for the
    caller to fall back to UNMATCHED_PRICE_FALLBACK and report - this
    function itself never substitutes that fallback into a weapon row's cost,
    so a miss is always visible to the caller rather than silently written.
    """
    with pdfplumber.open(pdf_path) as pdf:
        pages_words = [p.extract_words(use_text_flow=False, keep_blank_chars=False) for p in pdf.pages]
        page_heights = [p.height for p in pdf.pages]
    regions = _card_regions(units, pages_words, page_heights)

    def card_rows(unit: str) -> List[Tuple[float, str]]:
        region = regions.get(unit)
        if region is None:
            return []
        page_index, x_min, x_max, top_min, top_max = region
        return _rows_in_band(pages_words[page_index], x_min, x_max, top_min, top_max)

    misses: List[Tuple[str, str]] = []

    def price_weapons() -> List[Tuple[str, str, dict]]:
        by_unit: Dict[str, List[str]] = {}
        for unit, name, profile in weapon_rows:
            if profile["cost"] == SWAP_WEAPON_COST:
                by_unit.setdefault(unit, []).append(name)
        matched = {unit: _match_prices(card_rows(unit), names) for unit, names in by_unit.items()}

        priced = []
        for unit, name, profile in weapon_rows:
            if profile["cost"] != SWAP_WEAPON_COST:
                priced.append((unit, name, profile))
                continue
            price = matched[unit].get(name)
            if price is None:
                misses.append((unit, name))
                price = UNMATCHED_PRICE_FALLBACK
            priced.append((unit, name, dict(profile, cost=price)))
        return priced

    def price_upgrades() -> Dict[Tuple[str, str], int]:
        by_unit: Dict[str, List[str]] = {}
        for unit, name in upgrade_names:
            by_unit.setdefault(unit, []).append(name)
        matched = {unit: _match_prices(card_rows(unit), names) for unit, names in by_unit.items()}

        prices: Dict[Tuple[str, str], int] = {}
        for unit, name in upgrade_names:
            price = matched[unit].get(name)
            if price is None:
                misses.append((unit, name))
            else:
                prices[(unit, name)] = price
        return prices

    new_weapon_rows = price_weapons()
    upgrade_prices = price_upgrades()
    return new_weapon_rows, upgrade_prices, misses
```

Update the test file's `TestApplyRealPrices` to match this signature before running:

```python
    def _apply(self, monkeypatch, weapon_rows, upgrade_names=()):
        monkeypatch.setattr(
            armybook.pdfplumber, "open", lambda path: _FakePdf([_FakePage(self.PAGE_WORDS)])
        )
        return armybook.apply_real_prices(
            Path("fake.pdf"), self.UNITS, list(weapon_rows), list(upgrade_names)
        )
```

and change the two upgrade-related assertions:

```python
    def test_upgrades_are_priced_the_same_way(self, monkeypatch):
        _, upgrade_prices, misses = self._apply(monkeypatch, [], [("Warriors", "Gauss Rifle")])
        assert upgrade_prices == {("Warriors", "Gauss Rifle"): 10}
        assert misses == []

    def test_an_unmatched_upgrade_is_reported_and_absent_from_the_price_dict(self, monkeypatch):
        _, upgrade_prices, misses = self._apply(monkeypatch, [], [("Warriors", "Nonexistent")])
        assert upgrade_prices == {}
        assert misses == [("Warriors", "Nonexistent")]
```

(drop the earlier ambiguous `test_upgrades_are_priced_the_same_way` body from Step 1 in favor of these two - Step 1's version was written before this signature correction came to light during implementation; this is normal for a design detail the spec/plan left approximate.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_armybook.py::TestApplyRealPrices -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add opr_crunch/armybook.py tests/test_armybook.py
git commit -m "$(cat <<'EOF'
Add apply_real_prices entry point

Wires the row-clustering, region-finding and two-layer matching
pieces together into one function: given the parsed units and the
weapon/upgrade rows import_book already builds, it returns those rows
with real prices where matched, plus the misses for the caller to
report. Upgrade prices come back as a separate (unit, name) -> price
dict rather than patched into the upgrade tuple, since linked_upgrades
never carried a cost field in the first place - import_army_book.py
applies UPGRADE_COST as a literal today; Task 6 makes it look prices
up here instead.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 6: Wire real prices into the importer

**Files:**
- Modify: `opr_crunch/armybook.py:34-36` (`SWAP_WEAPON_COST`/`UPGRADE_COST` doc comment)
- Modify: `tools/import_army_book.py`
- Test: manual verification against a real book (no new automated test - this task is orchestration; the logic it calls is already tested in Tasks 2-5)

**Interfaces:**
- Consumes: `armybook.apply_real_prices` and `armybook.UNMATCHED_PRICE_FALLBACK` from Task 5, `armybook.parse_units` (existing).
- Produces: `import_book(text: str, faction: str, pdf_path: Optional[Path] = None)` — the existing function gains an optional `pdf_path` parameter; when given, real prices are applied and a summary is printed. When `None` (e.g. a cached `.txt` source has no PDF to open), every swap/upgrade option falls back to `UNMATCHED_PRICE_FALLBACK` with no per-option warning (there's nothing to check it against) - documented explicitly since a `.txt`-sourced import silently forgoes price matching.

Task 5 already added `UNMATCHED_PRICE_FALLBACK = 0` without changing `STARTING_WEAPON_COST`/`SWAP_WEAPON_COST`/`UPGRADE_COST`'s values (that task's plan text explains why: changing `SWAP_WEAPON_COST`/`UPGRADE_COST` to `0` would collide with `STARTING_WEAPON_COST` and break `linked_weapons`'s existing dedup as well as `apply_real_prices`'s own "does this need pricing" check). This task has no constant-value edit to make - it only *uses* `UNMATCHED_PRICE_FALLBACK` in the `.txt`-source fallback path below.

- [ ] **Step 1: Read the current `import_book` weapon/upgrade section**

Before editing, re-read `tools/import_army_book.py`'s current `import_book` function (the `--- weapons ---` and `--- upgrades ---` blocks) to get the exact current row-building code to modify in place - it was last touched in this session's earlier Impact-column work, so confirm line numbers with:

```bash
grep -n "weapon_links\|weapon_rows\|upgrade_links\|upgrade_rows\|def import_book" tools/import_army_book.py
```

- [ ] **Step 2: Implement**

In `tools/import_army_book.py`:

Change the `import_book` signature:

```python
def import_book(text: str, faction: str, pdf_path: Path | None = None) -> None:
```

Today's code builds weapons (lines 95-105) and upgrades (lines 107-113) as two separate blocks, each calling its own `armybook.linked_*` function and immediately building + writing its CSV rows. `apply_real_prices` needs both `weapon_links` and the upgrade names at once (one PDF-opening pass prices both), so merge the two blocks: gather both `linked_weapons` and `linked_upgrades` first, price once, then build and write both CSV row lists from the results. Note `weapon_rows` as built today is `List[list]` (plain CSV row lists: `[name, faction, unit, range, attacks, ap, blast, deadly, impact, rules, cost]`), not the `List[Tuple[str, str, dict]]` shape `apply_real_prices` expects (`(unit, name, profile_dict)`) - `apply_real_prices` takes `weapon_links` (the pre-CSV-row tuples from `armybook.linked_weapons`), and the final CSV `weapon_rows` list is only built *after* pricing. Replace the current weapons block (lines 95-105) and upgrades block (lines 107-113) together with:

```python
    # --- weapons and upgrades -------------------------------------------
    # A weapon a book gives to more than one unit is written as one row per
    # unit, not merged, so the Simulation dropdowns can offer each unit only
    # the weapons it can actually take.
    weapon_links = armybook.linked_weapons(pages)
    upgrade_links = armybook.linked_upgrades(pages)

    if pdf_path is not None:
        weapon_links, upgrade_prices, misses = armybook.apply_real_prices(
            pdf_path, units, weapon_links, [(unit, name) for unit, name, _ in upgrade_links]
        )
    else:
        upgrade_prices, misses = {}, []

    weapon_rows = [
        [name, faction, unit, w["range"], w["attacks"], w["ap"], w["blast"],
         w["deadly"], w["impact"], ", ".join(w["rules"]), w["cost"]]
        for unit, name, w in sorted(weapon_links, key=lambda t: (t[1], t[0]))
    ]
    replace_faction("weapons.csv", faction, layout.WEAPONS_COLUMNS, weapon_rows)

    upgrade_rows = [
        [name, faction, unit, 0, 0, 0, 0, ", ".join(granted),
         upgrade_prices.get((unit, name), armybook.UPGRADE_COST)]
        for unit, name, granted in sorted(upgrade_links, key=lambda t: (t[1], t[0]))
    ]
    replace_faction("upgrades.csv", faction, layout.UPGRADES_COLUMNS, upgrade_rows)
```

This supersedes the earlier draft in this task's Interfaces section - `apply_real_prices` takes `weapon_links` (the `(unit, name, profile_dict)` tuples from `armybook.linked_weapons`), not the already-flattened CSV rows. Update Task 5's docstring/type hints for `apply_real_prices`'s `weapon_rows` parameter name to `weapon_links` for clarity if not already done, but this is a naming nit, not a behavioral change - the shape (`List[Tuple[str, str, dict]]`) is unchanged from Task 5's implementation.

Finally, after `import_book`'s existing `print(f"  {len(units)} units, ...")` and `print(f"  reference-only rules in use: ...")` lines, add:

```python
    if misses:
        print(f"\n  price not found for {len(misses)} option(s):")
        for unit, name in sorted(misses):
            print(f"    {unit} / {name}")
        print("  these were set to 0 - fill in the real +Npts value by hand in")
        print("  csv/weapons.csv and csv/upgrades.csv")
```

And update `main()`'s call site:

```python
    print(f"Importing {source.name} as {faction!r}")
    import_book(text, faction, pdf_path=source if source.suffix.lower() == ".pdf" else None)
```

(`source` here is already the resolved local `Path` - either the downloaded/cached PDF or a local file passed on the command line; a `.txt` source has no PDF to open, matching the "no PDF at all" case described in this task's Interfaces section above.)

- [ ] **Step 3: Run the existing suite**

Run: `uv run pytest -q`
Expected: all tests pass. (No existing test exercises `import_book`'s new `pdf_path` parameter with a real PDF - Tasks 2-5's tests already cover the matching logic in isolation. This step is a regression check, not new coverage.)

- [ ] **Step 4: Manual smoke test against a real book**

```bash
uv run python tools/import_army_book.py books/robot_legions_v3.5.3.pdf
```

Expected: the run prints unit/weapon/upgrade counts as before, plus (if any misses occur) a "price not found" summary. Inspect the freshly-rewritten `csv/weapons.csv` for the Robot Legions faction and spot-check `Gauss Rifle` (unit `Warriors`) - it should now read `10` (confirmed correct against the PDF earlier during design), and `Flame Caster` (unit `Warriors`) should read `10` (not `15`, correcting a value the old `pdftotext -layout`-based reading of this same page would have suggested - see the design investigation). **This will overwrite `csv/` with just this one book's data outside a clean isolated environment - do this against a scratch copy of `csv/`, not the repo's real `csv/` directory**, using the same `import_isolated.py` pattern from the last import (copy `csv/` to a scratch dir, monkeypatch `import_army_book.CSV_DIR`, then diff/inspect there) rather than running the importer directly against the repo.

- [ ] **Step 5: Commit**

```bash
git add opr_crunch/armybook.py tools/import_army_book.py
git commit -m "$(cat <<'EOF'
Wire real price matching into the importer

import_book now applies apply_real_prices to the weapon links before
building CSV rows, and looks up each upgrade's price in the returned
dict instead of using a flat placeholder. Anything that couldn't be
matched falls back to 0, prints immediately, and is collected into an
end-of-run summary so it can be filled in by hand.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 7: Docs

**Files:**
- Modify: `CLAUDE.md` (the "Editing data" section, currently describing the flat placeholder scheme)
- Modify: `.claude/skills/importing-army-books/SKILL.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: docs that describe the shipped behavior instead of the superseded placeholder scheme.

- [ ] **Step 1: Update `CLAUDE.md`**

Find the paragraph starting "Points costs live in the `Cost` column..." (currently describes weapon/upgrade prices as placeholders). Replace it with:

```markdown
Points costs live in the `Cost` column of `units`, `weapons` and `upgrades`. Unit costs are
scraped from the book. Weapon-swap and upgrade prices are also scraped, by reading the PDF a
second time with `pdfplumber` for word coordinates and matching each option's `+Npts` token to
the option it prices, scoped to one unit's card at a time. A price that can't be confidently
matched falls back to `0` (same as a starting weapon, which is never priced from a `+Npts`
token at all - the unit's own cost already covers it) and is reported both immediately and in
an end-of-run summary, so it can be filled in by hand in `csv/weapons.csv` or
`csv/upgrades.csv`. See `docs/superpowers/specs/2026-09-02-real-weapon-upgrade-prices-design.md`.
```

- [ ] **Step 2: Update the `importing-army-books` skill**

In `.claude/skills/importing-army-books/SKILL.md`'s silent-failures table, add a row:

```markdown
| A weapon/upgrade option's Cost is 0 when it shouldn't be | Its price couldn't be matched from the PDF - check the importer's end-of-run "price not found" summary and fill it in by hand. |
```

Add a Verify step:

```markdown
5. **Check the importer's "price not found" summary, if it printed one.** Each listed
   `(unit, option)` needs its real price entered by hand in `csv/weapons.csv` or
   `csv/upgrades.csv` - the importer already set it to `0` rather than guess.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .claude/skills/importing-army-books/SKILL.md
git commit -m "$(cat <<'EOF'
Document real weapon/upgrade price scraping

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

### Task 8: Re-import all three books

**Files:**
- Modify: `csv/weapons.csv`, `csv/upgrades.csv` (Cost column only - regenerated, not hand-edited)
- Test: `uv run pytest -q` (full suite), plus manual spot-checks against the PDFs

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: `csv/weapons.csv`/`csv/upgrades.csv` with real scraped prices for all three current factions.

- [ ] **Step 1: Set up isolated per-book imports**

Reuse the `import_isolated.py` pattern from the previous import session (copies `csv/` into a scratch dir, monkeypatches `import_army_book.CSV_DIR`, then runs `import_book`), one scratch dir per book:

```bash
SP=/tmp/opr_price_import   # or the session scratchpad dir
mkdir -p "$SP"
for book in battle_brothers havoc_brothers robot_legions; do
  uv run python - "books/${book}_v3.5.3.pdf" "$SP/$book" <<'PY'
import shutil, sys
from pathlib import Path
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import import_army_book as imp
from opr_crunch import armybook

book = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
for f in Path("csv").glob("*.csv"):
    shutil.copy(f, out / f.name)
imp.CSV_DIR = out
text = imp.extract_text(book)
faction = armybook.detect_faction(text)
print(f"Importing {book.name} as {faction!r} into {out}")
imp.import_book(text, faction, pdf_path=book)
PY
done
```

Expected: each run prints its unit/weapon/upgrade counts and, if applicable, a "price not found" summary. Note every summary entry for the manual-fill-in step later.

- [ ] **Step 2: Merge into `csv/`**

Reuse the merge script from the previous import session (`Faction=scratch-dir` pairs, row tabs sourced per-faction, `special_rules`/`factions` unioned):

```bash
uv run python "$SP/merge_imports.py" . \
  "Battle Brothers=$SP/battle_brothers" \
  "Havoc Brothers=$SP/havoc_brothers" \
  "Robot Legions=$SP/robot_legions"
```

- [ ] **Step 3: Verify the diff is Cost-column-only**

```bash
git diff --stat csv/
```

Then confirm content, not just line count, by sorting both sides and diffing:

```bash
for f in units weapons upgrades special_rules factions; do
  echo "=== $f ==="
  diff <(git show HEAD:csv/$f.csv | sort) <(sort csv/$f.csv)
done
```

Expected: `units.csv`, `special_rules.csv`, `factions.csv` show **no differences**. `weapons.csv`/`upgrades.csv` show differences **only in the last (`Cost`) field of each row** - eyeball a sample of the diff to confirm no `Name`/`Faction`/`Unit`/profile field changed, only `Cost`.

- [ ] **Step 4: Spot-check real prices against the PDFs by hand**

Pick at least 3 real values per book and confirm against the PDF text directly (as already verified during design for Robot Legions: `Warriors` / `Gauss Rifle` = 10, `Warriors` / `Plasma Caster` = 10, `Warriors` / `Flame Caster` = 10, `Warriors` / `Fusion Caster` = 15, `Warriors` / `Ray Caster` = 20). Pick fresh examples for Battle Brothers and Havoc Brothers.

- [ ] **Step 5: Run the full suite and rebuild**

```bash
uv run pytest -q
uv run python -m opr_crunch.build
```

Expected: `406 passed` (no test asserts a specific placeholder price, so this task's data change shouldn't need any test updates - confirm this holds; if some test does hardcode a `10`-cost expectation for a swap weapon or upgrade, that test needs updating here, as it was relying on the placeholder rather than real data). `wrote dist\opr_crunch.xlsx`.

- [ ] **Step 6: Manually fill in any "price not found" misses**

For every `(unit, option)` reported across the three import runs, open the book PDF, find the real `+Npts` value, and edit it directly into `csv/weapons.csv` or `csv/upgrades.csv`'s `Cost` column (these are the two files git tracks as source of truth - editing them by hand is the documented, supported path per `CLAUDE.md`'s "Editing data" section, same as any other CSV edit).

- [ ] **Step 7: Final verification and commit**

```bash
uv run pytest -q
uv run python -m opr_crunch.build
git add csv/weapons.csv csv/upgrades.csv
git commit -m "$(cat <<'EOF'
Re-import all three books with real weapon/upgrade prices

Replaces the flat 10-point placeholder with prices scraped from each
book's +Npts tokens via word-coordinate matching. A handful of options
that couldn't be matched confidently were filled in by hand from the
PDF, per the importer's end-of-run summary.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011VFN7kLwoAx6PttL6Bu86i
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (tooling) → Task 1. §4.2-4.3 (scoping, two-layer matching) → Tasks 2-4. §4.4 (fallback/reporting) → Tasks 5-6. §4.5 (code shape) → Tasks 5-6, adjusted from the spec's rough sketch once the upgrade-row shape mismatch surfaced (documented inline in Task 6 rather than silently deviating). §5 (no CSV schema change) → confirmed, no task adds a column. §6 (re-import) → Task 8. §7 (docs) → Task 7. §8 (testing) → Tasks 2-5's synthetic-fixture tests, Task 8's real-book spot checks.
- **Known deviation from the spec's exact wording:** §4.3's fallback rule ("if the two lists are the same length, zip them") is tightened in Task 3 to "exactly one leftover on each side" after the design investigation found a real PDF page (Havoc Brothers, the currently-unparsed "Bot Fabricator" nested-parens option) where a same-length coincidence could pair a price with the wrong, unrelated option. This is called out as a deliberate refinement, not an oversight.
- **Type consistency:** `apply_real_prices`'s signature is corrected mid-plan (Task 5's step 3) once the mismatch between `linked_upgrades`' tuple shape (no `cost` field) and the naive first draft became clear. Task 6 uses the corrected signature throughout; Task 5's tests reflect it. Flagged explicitly in-place rather than silently rewritten, since a plan executor reading Task 5 top-to-bottom needs to see why the signature changed mid-task.
- **Cross-task conflict found in the SDD pre-flight scan (fixed before dispatch):** the first draft of Task 6 had `SWAP_WEAPON_COST`/`UPGRADE_COST` becoming `0` (matching `STARTING_WEAPON_COST`). That would have broken two things silently: `linked_weapons`'s existing dedup (`profile["cost"] < best[key][2]["cost"]`, which relies on `STARTING_WEAPON_COST (0) < SWAP_WEAPON_COST`), and `apply_real_prices`'s own `profile["cost"] == SWAP_WEAPON_COST` check for "this row needs pricing" - both stop distinguishing a starting weapon from an unpriced swap once the two constants are equal. Fixed by keeping `SWAP_WEAPON_COST`/`UPGRADE_COST` at their current value (`10`, internal-only, never reaches the CSV) and introducing a separate `UNMATCHED_PRICE_FALLBACK = 0` for the value actually written on a miss. Task 5 now owns adding this constant; Task 6 only consumes it.
