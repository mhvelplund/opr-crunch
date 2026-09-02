"""Parse an OPR army-book PDF into rows for the csv/ tabs.

Input is `pdftotext -layout` output. That preserves horizontal position, which
matters: army books are laid out in two- and three-column grids, and naive
top-to-bottom reading interleaves unrelated cells. Unit stats in particular end
up attached to the wrong unit unless columns are separated first.

Two patterns carry almost all the information and survive the layout intact:

* per-unit cards, ``Name [size] - Npts`` followed by ``Quality X+ Defense Y+``
  and a comma-separated rules line, all within one column band;
* inline weapon profiles, ``Name (12", A2, AP(1), Blast(3))``, which are
  self-contained and can be scanned for anywhere in the document.
"""

import re
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pdfplumber

#: Every page of an army book carries "<system> - <FACTION> V<version>".
BOOK_HEADER = re.compile(r"^\s*[A-Za-z]{2,4}\s*-\s*(.+?)\s+V[\d.]+\s*$", re.M)

#: Rules that get their own numeric column rather than a name in the text.
PARAMETERISED = {"AP", "Blast", "Deadly", "Impact", "Ravage", "Tough"}

#: Seed prices, written by linked_weapons before any price matching happens.
#: A weapon the unit starts with is already covered by the unit's own cost, so
#: STARTING_WEAPON_COST is its final price. SWAP_WEAPON_COST is an internal
#: "needs pricing" marker, never a real cost: apply_real_prices replaces every
#: row still carrying it with either the ``+Npts`` value scraped from the
#: card's price column or UNMATCHED_PRICE_FALLBACK. Its value is deliberately
#: not 0 so a swap option stays distinguishable from a starting weapon. Given
#: a text source rather than a PDF there are no word coordinates to match
#: against, so the importer has no prices to scrape and converts the marker
#: straight to UNMATCHED_PRICE_FALLBACK.
STARTING_WEAPON_COST = 0
SWAP_WEAPON_COST = 10

#: Written to the CSV when apply_real_prices can't confidently match a
#: price - distinct from SWAP_WEAPON_COST (which stays an internal "needs
#: pricing" marker so linked_weapons's existing dedup, and the check below,
#: can still tell a swap option apart from a starting weapon even after this
#: constant makes both read as 0 on the sheet). Never reuse SWAP_WEAPON_COST
#: as a fallback: a marker written to the CSV is indistinguishable from a
#: real 10-point price, so a miss stops being reportable.
UNMATCHED_PRICE_FALLBACK = 0

#: Column bands. Unit cards are laid out two-up, rules three-up.
CARD_GUTTER = 60
RULE_COLUMNS = [(0, 57), (57, 115), (115, 999)]

CARD = re.compile(r"([A-Z][\w'\-]*(?:[ \-][A-Z]?[\w'\-]+)*) \[(\d+)\] - (\d+)pts")
STATS = re.compile(r"Quality (\d)\+")
DEFENSE = re.compile(r"Defense (\d)\+")
COUNT_PREFIX = re.compile(r"^\d+x\s+")
RULE_TOKEN = re.compile(r"^[A-Z][\w'\-]*(?:[ \-][\w'\-]+)*(?:\(\d+\))?$")
DEFINITION = re.compile(r"^([A-Z][\w \-]*?): (.*)$")


# --------------------------------------------------------------------------
# weapon profiles
# --------------------------------------------------------------------------

def _split_top_level(text: str) -> List[str]:
    """Split on commas that are not inside parentheses."""
    parts, depth, current = [], 0, ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def parse_profile(text: str) -> dict:
    """Turn ``18", A2, AP(1), Blast(3)`` into columns plus leftover rule names."""
    profile = dict(range=0, attacks=0, ap=0, blast=0, deadly=0, impact=0, rules=[])

    for token in _split_top_level(text):
        if match := re.fullmatch(r'(\d+)"', token):
            profile["range"] = int(match.group(1))
        elif match := re.fullmatch(r"A(\d+)", token):
            profile["attacks"] = int(match.group(1))
        elif match := re.fullmatch(r"(\w[\w \-]*)\((\d+)\)", token):
            name, value = match.group(1), int(match.group(2))
            if name in PARAMETERISED:
                profile[name.lower()] = value
            else:
                profile["rules"].append(token)
        elif token:
            # A wrapped profile can pick up the next table row's stat cells, so
            # only keep tokens that actually read as a rule name.
            cleaned = re.sub(r"^[\d+\s]+", "", token).strip()
            if RULE_TOKEN.fullmatch(cleaned):
                profile["rules"].append(cleaned)
    return profile


def _balanced(text: str, start: int) -> int:
    """Index just past the parenthesis group opening at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _clean_name(before: str) -> str:
    """Recover a name from whatever the table layout left in front of it.

    Only the final line counts — a name never wraps onto the line with its
    profile — and only the last cell of that line, since scrambled table columns
    leave unrelated debris to the left.
    """
    tail = before.split("\n")[-1]
    # A unit's roster header can share a line with its first weapon.
    tail = re.sub(r"^.*\[\d+\][\s\d+]*", "", tail)
    # As can an earlier weapon's own profile.
    tail = re.split(r"[),]", tail)[-1]

    chunk = re.split(r"\s{2,}", tail.strip())[-1].strip()
    chunk = COUNT_PREFIX.sub("", chunk)
    chunk = re.sub(r"^[^A-Za-z]+", "", chunk)
    return re.sub(r"^x\s+", "", chunk).strip()


def find_weapons(text: str) -> Dict[str, dict]:
    """Every inline weapon profile in ``text``, keyed by weapon name.

    The same name can carry different profiles on different units — a CCW is
    A1 here and A3 there. Names have to stay unique because the sheet's lookups
    match on name alone, so genuine variants are suffixed with their attacks.
    """
    variants: Dict[str, List[dict]] = {}
    for match in re.finditer(r"\(", text):
        close = _balanced(text, match.start())
        if close < 0:
            continue
        body = text[match.start() + 1:close]
        if not re.search(r"\bA\d+\b", body):
            continue  # not a weapon profile

        name = _clean_name(text[:match.start()])
        if not name or len(name) > 40 or "(" in name or ")" in name:
            continue
        profile = parse_profile(body)
        if profile not in variants.setdefault(name, []):
            variants[name].append(profile)

    found: Dict[str, dict] = {}
    for name, profiles in variants.items():
        if len(profiles) == 1:
            found[name] = profiles[0]
        else:
            for profile in profiles:
                found[f"{name} (A{profile['attacks']})"] = profile
    return found


# --------------------------------------------------------------------------
# units
# --------------------------------------------------------------------------

def _band(column: int) -> int:
    return 0 if column < CARD_GUTTER else 1


def _chunks(line: str) -> List[Tuple[int, str]]:
    """Split a laid-out line into (start column, text) cells."""
    return [(m.start(), m.group().strip()) for m in re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|$)", line)]


#: Single cells that can land alone in a card's rules band but are never a
#: rule - the weapon table header splits into several single-word cells, and
#: on some layouts only one of them falls in this band.
_NOT_A_RULE = {"Weapon", "Upgrade", "Replace"}


def _rules_near(lines: List[str], first: int, column: int) -> List[str]:
    """Find the rules cell below a unit's stats line.

    A unit with only one rule prints it with no comma at all (``Havocbound``),
    so a lone cell is accepted the same as a comma-separated list - but only
    when it is the *only* cell in this band on its line, since a table header
    row splits into several single-word cells across the same band and would
    otherwise be misread as a one-rule unit.
    """
    for line in lines[first:first + 5]:
        in_band = [text for start, text in _chunks(line) if _band(start) == _band(column)]
        if len(in_band) != 1 or in_band[0] in _NOT_A_RULE:
            continue
        tokens = [t.strip() for t in in_band[0].split(",")]
        if all(RULE_TOKEN.fullmatch(t) for t in tokens if t):
            return [t for t in tokens if t]
    return []


def parse_units(pages: List[str]) -> List[dict]:
    """Read every unit card, keeping each column band separate."""
    units = []
    for page in pages:
        lines = page.split("\n")
        cards, stats = [], []
        for i, line in enumerate(lines):
            cards += [
                (i, m.start(), m.group(1), int(m.group(2)), int(m.group(3)))
                for m in CARD.finditer(line)
            ]
            for m in STATS.finditer(line):
                if d := DEFENSE.search(line[m.end():]):
                    stats.append((i, m.start(), int(m.group(1)), int(d.group(1))))

        for line_no, column, name, size, cost in cards:
            match = next(
                (s for s in stats if s[0] > line_no and _band(s[1]) == _band(column)), None
            )
            if match is None:
                continue
            stat_line, stat_col, quality, defense = match
            raw = _rules_near(lines, stat_line + 1, stat_col)

            unit = dict(
                name=name, size=size, cost=cost, quality=quality, defense=defense,
                tough=0, ravage=0, impact=0, rules=[],
            )
            for token in raw:
                if param := re.fullmatch(r"(\w[\w \-]*)\((\d+)\)", token):
                    key, value = param.group(1), int(param.group(2))
                    if key in PARAMETERISED:
                        unit[key.lower()] = value
                        continue
                unit["rules"].append(token)
            units.append(unit)
    return units


# --------------------------------------------------------------------------
# linking weapons and upgrades to the unit card they're printed under
# --------------------------------------------------------------------------

def _blank_other_band(line: str, band: int) -> str:
    """Replace ``line``'s cells outside ``band`` with spaces.

    Keeps every surviving character in its original column, so multi-space
    cell gaps the profile parsers key on stay intact - unlike joining cell
    text back together, which would collapse them.
    """
    chars = list(line)
    for start, text in _chunks(line):
        if _band(start) != band:
            chars[start:start + len(text)] = " " * len(text)
    return "".join(chars)


def _partition(pages: List[str]) -> Tuple[List[Tuple[str, str]], str]:
    """Split unit-card pages into per-card spans plus one leftover block.

    A card's span runs from its own line to the next card's line in the same
    column band, or to the end of the page - the same band-keeping rule
    ``parse_units`` follows. A neighbouring unit's text on a shared line is
    blanked rather than included, so its weapons and upgrades aren't credited
    to this card too. Lines no card reaches (a shared armoury page, say)
    become the leftover, returned separately so callers can treat what's
    found there as generic rather than tied to whichever card is nearby.
    """
    spans: List[Tuple[str, str]] = []
    leftovers: List[str] = []
    for page in pages:
        lines = page.split("\n")
        cards = sorted(
            {(i, _band(m.start()), m.group(1)) for i, line in enumerate(lines) for m in CARD.finditer(line)},
            key=lambda c: (c[1], c[0]),
        )
        blanked = {band: [_blank_other_band(line, band) for line in lines] for band in (0, 1)}
        covered = set()
        for idx, (line_no, band, name) in enumerate(cards):
            end = next((c[0] for c in cards[idx + 1:] if c[1] == band), len(lines))
            covered.update(range(line_no, end))
            spans.append((name, "\n".join(blanked[band][line_no:end])))
        leftovers.append("\n".join(line for i, line in enumerate(lines) if i not in covered))
    return spans, "\n".join(leftovers)


WEAPON_TABLE_HEADER = re.compile(r"\bWeapon\b.*\bATK\b")


def _default_weapon_names(card_text: str) -> List[str]:
    """A card's own starting weapons, name only, no profile.

    A unit's starting weapon(s) only ever appear in the card's Weapon table as
    a plain grid - no parentheses at all - so ``find_weapons`` can't read a
    profile from it. Worse, ``pdftotext -layout`` frequently lands a row's RNG
    /ATK/AP/SPE cells one line away from its own name (the same column-flow
    quirk that makes the roster unreliable for weapon *profiles*), so this
    reads only the leftmost cell of each row and ignores the numbers - the
    profile comes from cross-referencing this name against
    ``find_weapons(roster_text)`` instead, which doesn't depend on row
    position at all. Stops at the first ``Replace``/``Upgrade`` line, since
    those are optional swaps handled by the normal inline-profile path.
    """
    lines = card_text.split("\n")
    header = next((i for i, line in enumerate(lines) if WEAPON_TABLE_HEADER.search(line)), None)
    if header is None:
        return []

    names = []
    for line in lines[header + 1:]:
        if re.match(r"^\s*(Replace|Upgrade)\b", line):
            break
        cells = _chunks(line)
        if not cells:
            continue
        cell = COUNT_PREFIX.sub("", cells[0][1])
        if re.fullmatch(r"[A-Z][\w'\-]*(?:[ \-][\w'\-]+)*", cell):
            names.append(cell)
    return names


def _pick_variant(name: str, pool: Dict[str, dict], hint_text: str) -> Optional[dict]:
    """The right profile for ``name`` out of a pool that may hold variants.

    ``find_weapons`` suffixes a name with its attacks, e.g. ``CCW (A2)``, when
    the pool's source text (the whole roster) carries more than one profile
    under that name - different units' CCWs have different Attacks. This
    prefers whichever variant's attack count is actually written somewhere in
    the card's own text, falling back to a deterministic pick so the same
    input always produces the same (if unverified) output.
    """
    if name in pool:
        return pool[name]
    variants = {n: p for n, p in pool.items() if n.startswith(f"{name} (A")}
    if not variants:
        return None
    for profile in variants.values():
        if re.search(rf"\bA{profile['attacks']}\b", hint_text):
            return profile
    return variants[sorted(variants)[0]]


def linked_weapons(pages: List[str]) -> List[Tuple[str, str, dict]]:
    """(unit name or "", weapon name, profile) for every profile in the book.

    Scoped to the card it's printed under, so the same name under two units
    becomes two rows rather than one profile guessed to cover both. A profile
    found outside any card - e.g. on a shared armoury page - is generic and
    comes back with an empty unit name.

    A starting weapon is the exception: its name lives on the unit's own
    card, but its profile only ever appears, unattributed, in inline
    ``Name (...)`` form on the roster page - the two are stitched back
    together by name via ``_default_weapon_names``/``_pick_variant`` rather
    than by the roster's row order, which ``pdftotext -layout`` does not
    reliably preserve for a wrapped entry.
    """
    spans, leftover = _partition(pages[3:])
    rows = [
        (unit, name, dict(profile, cost=SWAP_WEAPON_COST))
        for unit, text in spans for name, profile in find_weapons(text).items()
    ]

    roster_pool = find_weapons("\n".join(pages[:3]))
    for unit, text in spans:
        for name in _default_weapon_names(text):
            profile = _pick_variant(name, roster_pool, text)
            if profile is not None:
                # A pooled profile is shared between every unit that starts
                # with the weapon, so price a copy rather than the pool's own.
                rows.append((unit, name, dict(profile, cost=STARTING_WEAPON_COST)))

    rows += [
        ("", name, dict(profile, cost=SWAP_WEAPON_COST))
        for name, profile in find_weapons(leftover).items()
    ]

    # The roster's base-weapon line and a card's own options can both name the
    # same weapon with the same profile for the same unit; only the source
    # differs, so keep one row rather than a redundant duplicate key. Price is
    # left out of the key and the cheaper row wins, because a weapon found both
    # ways is one the unit starts with - already paid for in the unit's cost.
    best: Dict[tuple, Tuple[str, str, dict]] = {}
    for unit, name, profile in rows:
        key = (unit, name, tuple(sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in profile.items() if k != "cost"
        )))
        if key not in best or profile["cost"] < best[key][2]["cost"]:
            best[key] = (unit, name, profile)
    return list(best.values())


def linked_upgrades(pages: List[str]) -> List[Tuple[str, str, List[str]]]:
    """(unit name or "", upgrade name, granted rules) for every option found."""
    spans, leftover = _partition(pages[3:])
    rows = [
        (unit, name, granted)
        for unit, text in spans for name, granted in parse_upgrades(text)
    ]
    rows += [("", name, granted) for name, granted in parse_upgrades(leftover)]
    return rows


# --------------------------------------------------------------------------
# special rules and upgrades
# --------------------------------------------------------------------------

def _columns_of(cells: List[Tuple[int, int, str]], tolerance: int = 12) -> List[int]:
    """Cluster cell start positions into column anchors.

    Derived from the page rather than hardcoded, so a book laid out in two or
    four columns parses as readily as this one's three.
    """
    anchors: List[int] = []
    for column in sorted({start for _, start, _ in cells}):
        if not anchors or column - anchors[-1] > tolerance:
            anchors.append(column)
    return anchors


def parse_special_rules(page: str) -> List[Tuple[str, str]]:
    """Read ``Name: definition`` entries out of a multi-column rules page."""
    cells = [
        (i, start, text)
        for i, line in enumerate(page.split("\n"))
        for start, text in _chunks(line)
    ]
    anchors = _columns_of(cells)

    rules: List[Tuple[str, str]] = []
    for anchor in anchors:
        column = [
            (i, text) for i, start, text in cells
            if min(anchors, key=lambda a: abs(a - start)) == anchor
        ]
        current = None
        for _, text in sorted(column):
            if match := DEFINITION.match(text):
                if current:
                    rules.append(current)
                current = (match.group(1), match.group(2))
            elif current:
                current = (current[0], f"{current[1]} {text}".strip())
        if current:
            rules.append(current)

    merged: Dict[str, str] = {}
    for name, text in rules:
        # A wrapped definition can restart in the next column; keep the longest.
        if len(text) > len(merged.get(name, "")):
            merged[name] = re.sub(r"\s+", " ", text).strip()
    return sorted(merged.items())


def parse_upgrades(text: str) -> List[Tuple[str, List[str]]]:
    """Read ``Name (Granted Rule, Other Rule)`` upgrade options."""
    upgrades: Dict[str, List[str]] = {}
    for match in re.finditer(r"\(", text):
        close = _balanced(text, match.start())
        if close < 0:
            continue
        body = text[match.start() + 1:close]
        if re.search(r"\bA\d+\b|\d+\"", body):
            continue  # a weapon, not a granted rule

        granted = _split_top_level(body)
        if not granted or not all(RULE_TOKEN.fullmatch(g) for g in granted):
            continue
        name = _clean_name(text[:match.start()])
        if name and len(name) <= 40:
            upgrades.setdefault(name, granted)
    return sorted(upgrades.items())


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------

def detect_faction(text: str) -> Optional[str]:
    """The faction this book describes, from its running page header.

    Typing the faction by hand is the one mistake that fails quietly: a
    different spelling or capitalisation appends a second faction instead of
    replacing the first, leaving units nothing can select.
    """
    match = BOOK_HEADER.search(text)
    return match.group(1).strip().title() if match else None


def is_url(source: str) -> bool:
    return urlparse(str(source)).scheme in ("http", "https")


def cache_name(url: str) -> str:
    """A safe, stable filename for a downloaded book.

    Only the final path segment is used, so a crafted URL cannot write outside
    the cache directory.
    """
    name = PurePosixPath(urlparse(url).path).name or "army-book"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


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


def _gutter(words: List[dict], lo: float, hi: float) -> Optional[float]:
    """Centre of the widest blank vertical strip strictly between ``lo``/``hi``.

    A card's own price column sits at its far right, well past the middle of
    the two cards' *header* anchors - the headers are centred over their card,
    so the midpoint between them lands inside the left card's price column
    rather than in the gutter separating the two cards. Splitting there both
    loses a card its own prices and hands them to its neighbour. The blank
    strip the layout actually leaves between the cards is unambiguous in word
    coordinates (30+ points wide on every card page of these books, against 19
    for the widest gap that occurs *inside* a card), so the split is measured
    from the page rather than guessed from the anchors.
    """
    if not words:
        return None
    best: Optional[Tuple[float, float]] = None
    edge = lo
    for x0, x1 in sorted((w["x0"], w["x1"]) for w in words):
        if x0 >= hi:
            break
        if x0 > edge and (best is None or x0 - edge > best[1] - best[0]):
            best = (edge, x0)
        edge = max(edge, x1)
    if edge < hi and (best is None or hi - edge > best[1] - best[0]):
        best = (edge, hi)
    return None if best is None else (best[0] + best[1]) / 2


def _band_bounds(
    xs: List[float], words: Optional[List[dict]] = None, gap: float = 40
) -> List[Tuple[float, float]]:
    """One (low, high) span per clustered x-anchor, covering -inf..inf overall.

    Mirrors the character-column clustering ``_columns_of`` already does for
    the special-rules page, but in PDF point-space rather than text columns -
    the two are not on the same scale, so this is a separate small helper
    rather than a shared one.

    Given ``words`` (the page's own words), neighbouring bands are split on the
    blank strip actually between them - see ``_gutter``. Without them the split
    falls back to the anchor midpoint, which is only ever right when the
    anchors sit at their bands' left edges.
    """
    anchors: List[float] = []
    for x in sorted(xs):
        if not anchors or x - anchors[-1] > gap:
            anchors.append(x)

    edges: List[float] = []
    for a, b in zip(anchors, anchors[1:]):
        centre = _gutter(words or [], a, b)
        edges.append((a + b) / 2 if centre is None else centre)

    return [
        (-1.0 if i == 0 else edges[i - 1],
         float("inf") if i == len(anchors) - 1 else edges[i])
        for i in range(len(anchors))
    ]


def _match_prices(card_rows: List[Tuple[float, str]], option_names: List[str]) -> Dict[str, int]:
    """Attach a scraped price to as many of ``option_names`` as can be done
    with confidence, out of one card's rows.

    Layer 1: a priced row is read as one printed option. Its price is the
    first ``+Npts`` token *after* the longest option name on the row - the
    card's price column is always to the right of its option text, so a token
    sitting ahead of the name prices something else (a neighbouring row's
    price can land one bucket early, the same vertical mis-clustering the
    module docstring warns about) and taking one anyway invents a cost.

    An option row often bundles several weapons for one price ("Storm Rifle
    (24", A3, AP(1)), CCW (A1) +75pts"), and the sheet has one row per weapon
    name with nowhere to record that they were bought together, so every name
    the row bundles takes the printed price. A name merely *contained* in the
    longest one is a spelling overlap rather than a second item ('Storm Rifle'
    inside 'Champion Storm Rifle'), and takes nothing.

    A name the book prices in more than one place has no single answer, so it
    is reported unmatched unless the places agree. A row that prices the
    option on its own outranks a bundle it also appears in, since that is the
    option's own printed cost.

    Layer 2: if that leaves exactly one option and one price unclaimed, they
    are paired - the common case is a name too long for its own row, wrapping
    the price onto the next one. Only an option named on no priced row at all
    is eligible: one that *was* named on a priced row but lost it to a longer
    or bundled-with name has already been seen to be priced somewhere, and
    pairing it with a spare price from elsewhere on the card contradicts what
    the page shows. Anything else (zero, or more than one, of either side) is
    left unmatched rather than guessed; the caller reports these.
    """
    def value(found: "re.Match") -> int:
        return 0 if found.group(0) == "Free" else int(found.group(1))

    alone: Dict[str, set] = {}
    bundled: Dict[str, set] = {}
    named_on_a_priced_row: set = set()
    unclaimed_prices: List[int] = []

    for _, text in card_rows:
        prices = list(PRICE.finditer(text))
        if not prices:
            continue
        candidates = [n for n in option_names if n in text]
        if not candidates:
            unclaimed_prices += [value(found) for found in prices]
            continue
        named_on_a_priced_row.update(candidates)
        longest = max(candidates, key=len)
        after = [
            found for found in prices
            if found.start() >= text.index(longest) + len(longest)
        ]
        if not after:
            continue
        priced = [longest] + [n for n in candidates if n not in longest]
        for name in priced:
            seen = alone if len(priced) == 1 else bundled
            seen.setdefault(name, set()).add(value(after[0]))

    matches = {}
    for name in option_names:
        found = alone.get(name) or bundled.get(name) or set()
        if len(found) == 1:
            matches[name] = next(iter(found))

    unclaimed_names = [n for n in option_names if n not in named_on_a_priced_row]
    if len(unclaimed_names) == 1 and len(unclaimed_prices) == 1:
        matches[unclaimed_names[0]] = unclaimed_prices[0]
    return matches


def _find_card_anchor(name: str, size: int, cost: int, words: List[dict]) -> Optional[Tuple[float, float]]:
    """(x0, top) of this unit's card header on one page, or None.

    Looks for the exact printed header - "Name [size] - costpts" - built the
    same way CARD's own text is: a plain unit name never contains the
    characters CARD's regex itself excludes, so this string is unambiguous.

    The anchor is the word the *needle* starts at, located by character offset
    rather than by name: two cards printed side by side share a row, and their
    names routinely share a first word ("Havoc Bikers" next to "Havoc APC"),
    so picking the row's first word of that spelling anchors the second card
    on top of the first and hands it its neighbour's whole column.
    """
    needle = f"{name} [{size}] - {cost}pts"
    rows: Dict[int, List[dict]] = {}
    for w in words:
        rows.setdefault(round(w["top"]), []).append(w)
    for top, row_words in rows.items():
        row_words = sorted(row_words, key=lambda w: w["x0"])
        starts, offset = [], 0
        for w in row_words:
            starts.append(offset)
            offset += len(w["text"]) + 1
        index = " ".join(w["text"] for w in row_words).find(needle)
        if index >= 0:
            anchor = max(
                (p for p in zip(starts, row_words) if p[0] <= index), key=lambda p: p[0]
            )[1]
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
        # Only the card area below the topmost header can belong to a card, and
        # only it should shape the gutter - the running page header spans the
        # full width and would blank the gutter out.
        first_top = min(top for _, _, top in entries)
        body = [w for w in pages_words[page_index] if w["top"] >= first_top]
        bounds = _band_bounds([x0 for _, x0, _ in entries], body)
        for name, x0, top in entries:
            x_min, x_max = next((lo, hi) for lo, hi in bounds if lo <= x0 < hi)
            same_band_tops = sorted(t for n2, x2, t in entries if x_min <= x2 < x_max)
            next_top = next((t for t in same_band_tops if t > top), page_heights[page_index])
            regions[name] = (page_index, x_min, x_max, top, next_top)
    return regions


def apply_real_prices(
    pdf_path: Path,
    units: List[dict],
    weapon_links: List[Tuple[str, str, dict]],
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

    Weapons and upgrades are matched together, in one pass per card, rather
    than a pass each: they compete for the same printed prices, and a pass
    that can't see the other category's names reads a price already spoken
    for as unclaimed and hands it to a leftover name of its own.
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

    by_unit: Dict[str, set] = {}
    for unit, name, profile in weapon_links:
        if profile["cost"] == SWAP_WEAPON_COST:
            by_unit.setdefault(unit, set()).add(name)
    for unit, name in upgrade_names:
        by_unit.setdefault(unit, set()).add(name)
    matched = {
        unit: _match_prices(card_rows(unit), sorted(names))
        for unit, names in by_unit.items()
    }

    def price_weapons() -> List[Tuple[str, str, dict]]:
        priced = []
        for unit, name, profile in weapon_links:
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
