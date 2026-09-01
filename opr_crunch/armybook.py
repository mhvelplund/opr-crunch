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
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

#: Every page of an army book carries "<system> - <FACTION> V<version>".
BOOK_HEADER = re.compile(r"^\s*[A-Za-z]{2,4}\s*-\s*(.+?)\s+V[\d.]+\s*$", re.M)

#: Rules that get their own numeric column rather than a name in the text.
PARAMETERISED = {"AP", "Blast", "Deadly", "Impact", "Ravage", "Tough"}

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


def _rules_near(lines: List[str], first: int, column: int) -> List[str]:
    """Find the comma-separated rules cell below a unit's stats line."""
    for line in lines[first:first + 5]:
        for start, text in _chunks(line):
            if _band(start) != _band(column) or "," not in text:
                continue
            tokens = [t.strip() for t in text.split(",")]
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
            cards += [(i, m.start(), m.group(1), int(m.group(2))) for m in CARD.finditer(line)]
            for m in STATS.finditer(line):
                if d := DEFENSE.search(line[m.end():]):
                    stats.append((i, m.start(), int(m.group(1)), int(d.group(1))))

        for line_no, column, name, size in cards:
            match = next(
                (s for s in stats if s[0] > line_no and _band(s[1]) == _band(column)), None
            )
            if match is None:
                continue
            stat_line, stat_col, quality, defense = match
            raw = _rules_near(lines, stat_line + 1, stat_col)

            unit = dict(
                name=name, size=size, quality=quality, defense=defense,
                tough=0, ravage=0, rules=[],
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


def _roster_linked(text: str, known_units: Iterable[str]) -> List[Tuple[str, str, dict]]:
    """Weapons on the roster page, attributed to the unit each row is under.

    A unit's starting weapon(s) only ever appear in the inline ``Name (...)``
    form ``find_weapons`` can match on the roster page - the per-unit cards
    print them as a plain table with no parentheses at all, so they never
    show up as a weapon match there. Card boundaries in the CARD/[size]-Npts
    sense don't exist on the roster, but each row still starts with a known
    unit's name, wrapping onto the next line for a second weapon - so the
    most recently seen name is enough to attribute a row correctly.

    Lines are grouped into one block per run of a unit's name before being
    handed to ``find_weapons``, rather than matched one line at a time: some
    books repeat an identical weapon across several of a unit's lines (a
    multi-mount vehicle listing the same gun per hardpoint), and only a
    single call sees enough of the text at once to dedupe that the way
    ``find_weapons`` already does within a call.
    """
    names = sorted(set(known_units), key=len, reverse=True)
    rows: List[Tuple[str, str, dict]] = []
    current, block = "", []

    def flush():
        if block:
            rows.extend((current, n, p) for n, p in find_weapons("\n".join(block)).items())

    for line in text.split("\n"):
        stripped = line.strip()
        matched = next((n for n in names if stripped.startswith(n)), None)
        if matched and matched != current:
            flush()
            current, block = matched, []
        block.append(line)
    flush()
    return rows


def linked_weapons(pages: List[str], known_units: Iterable[str] = ()) -> List[Tuple[str, str, dict]]:
    """(unit name or "", weapon name, profile) for every profile in the book.

    Scoped to the card - or, for a starting weapon, the roster row - it's
    printed under, so the same name under two units becomes two rows rather
    than one profile guessed to cover both. A profile found outside any of
    that - e.g. on a shared armoury page - is generic and comes back with an
    empty unit name.
    """
    spans, leftover = _partition(pages[3:])
    rows = [
        (unit, name, profile)
        for unit, text in spans for name, profile in find_weapons(text).items()
    ]
    rows += _roster_linked("\n".join(pages[:3]), known_units)
    rows += [("", name, profile) for name, profile in find_weapons(leftover).items()]

    # The roster's base-weapon line and a card's own options can both name the
    # same weapon with the same profile for the same unit; only the source
    # differs, so keep one row rather than a redundant duplicate key.
    seen = set()
    deduped = []
    for unit, name, profile in rows:
        key = (unit, name, tuple(sorted(
            (k, tuple(v) if isinstance(v, list) else v) for k, v in profile.items()
        )))
        if key not in seen:
            seen.add(key)
            deduped.append((unit, name, profile))
    return deduped


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
