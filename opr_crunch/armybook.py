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
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

#: Every page of an army book carries "<system> - <FACTION> V<version>".
BOOK_HEADER = re.compile(r"^\s*[A-Za-z]{2,4}\s*-\s*(.+?)\s+V[\d.]+\s*$", re.M)

#: Rules that get their own numeric column rather than a name in the text.
PARAMETERISED = {"AP", "Blast", "Deadly", "Impact", "Ravage", "Tough"}

#: Placeholder prices. A unit's own cost is read from its card, but the real
#: price of a swap or an upgrade lives in the card's ``+Npts`` column, which
#: ``pdftotext -layout`` does not keep aligned with the rows it prices - on
#: some cards every price lands above the weapon it belongs to. Matching them
#: by position would mis-assign prices silently, so they are seeded flat until
#: the importer can read word coordinates. A weapon the unit starts with is
#: already covered by the unit's own cost and so is free either way.
STARTING_WEAPON_COST = 0
SWAP_WEAPON_COST = 10
UPGRADE_COST = 10

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
