"""A minimal evaluator for the formula subset opr_crunch emits.

Test-only. The generated workbook cannot be recalculated in CI (no Excel, no
Google Sheets, no LibreOffice), so this interprets the formula strings directly
and lets the suite prove the spreadsheet translation matches the reference model.

Supports exactly what opr_crunch.formulas and opr_crunch.build produce: IF, AND,
OR, NOT, MIN, MAX, ABS, ISNUMBER, SEARCH, INDEX, MATCH, IFERROR, TEXTJOIN,
comparisons, arithmetic, & concatenation, and cross-sheet cell and whole-column
references.
"""

import re

SHEET = r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))!"
COLUMN_RANGE = re.compile(rf"(?:{SHEET})?\$([A-Z]{{1,3}}):\$([A-Z]{{1,3}})")
QUALIFIED_CELL = re.compile(rf"{SHEET}\$?([A-Z]{{1,3}})\$?(\d+)\b")
LOCAL_CELL = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)\b")
#: An Excel string literal, where "" inside the quotes is an escaped literal
#: quote (used to build a single "" character, e.g. a range shown as 18").
STRING = re.compile(r'"(?:[^"]|"")*"')
COMPARISON = re.compile(r"(?<![<>=!])=(?!=)")

FUNCTIONS = [
    "ISNUMBER", "SEARCH", "IFERROR", "INDEX", "MATCH",
    "IF", "AND", "OR", "NOT", "MIN", "MAX", "ABS", "TEXTJOIN",
]

#: Rows of a whole-column reference the evaluator materialises. Must reach
#: past the largest data tab, or lookups silently miss their target rows.
COLUMN_DEPTH = 340


class Err:
    """Stands in for a spreadsheet error value."""

    def __repr__(self):
        return "_ERR"

    def __bool__(self):
        return False


ERR = Err()


class Blank:
    """An empty cell: equal to both "" and 0, and inert in arithmetic."""

    def __repr__(self):
        return "_BLANK"

    def __eq__(self, other):
        return isinstance(other, Blank) or other == "" or other == 0

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return 0

    def __bool__(self):
        return False

    # Blank concatenates as "" but adds as 0, which is what a sheet does.
    def __add__(self, other):
        return other if isinstance(other, str) else 0 + other

    def __radd__(self, other):
        return other if isinstance(other, str) else other + 0

    def __sub__(self, other):
        return 0 - other

    def __rsub__(self, other):
        return other - 0

    def __mul__(self, other):
        return 0

    __rmul__ = __mul__

    def __truediv__(self, other):
        return 0

    def __lt__(self, other):
        return 0 < other

    def __gt__(self, other):
        return 0 > other

    def __le__(self, other):
        return 0 <= other

    def __ge__(self, other):
        return 0 >= other


BLANK = Blank()


def _display(value) -> str:
    """Excel's implicit text coercion for &, e.g. the number 18 becomes "18"."""
    if isinstance(value, Blank):
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class Txt(str):
    """A parked string literal, distinguished from a plain str.

    & is translated to Python's + for reuse, but a bare int + str raises
    TypeError where Excel would coerce the number to text. Wrapping every
    string literal in Txt gives + something to dispatch to on either side,
    exactly where a "&" chain features a literal next to a numeric cell.
    """

    def __add__(self, other):
        return Txt(str(self) + _display(other))

    def __radd__(self, other):
        return Txt(_display(other) + str(self))


def _search(needle, haystack):
    if not isinstance(haystack, str):
        return ERR
    index = haystack.upper().find(str(needle).upper())
    return index + 1 if index >= 0 else ERR


def _match(value, values, _mode=0):
    for i, candidate in enumerate(values, start=1):
        if candidate == value:
            return i
    return ERR


def _index(values, position):
    if position is ERR or not isinstance(position, int):
        return ERR
    if not 1 <= position <= len(values):
        return ERR
    return values[position - 1]


def _iferror(value, fallback):
    return fallback if value is ERR else value


def _isnumber(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _textjoin(delimiter, ignore_empty, *values):
    parts = [v for v in values if not (ignore_empty and (v == "" or v is BLANK))]
    return delimiter.join(str(p) for p in parts)


ENV = {
    "_ERR": ERR,
    "_BLANK": BLANK,
    "_TXT": Txt,
    "_ISNUMBER": _isnumber,
    "_SEARCH": _search,
    "_MATCH": _match,
    "_INDEX": _index,
    "_IFERROR": _iferror,
    "_IF": lambda c, a, b: a if c else b,
    "_AND": lambda *a: all(a),
    "_OR": lambda *a: any(a),
    "_NOT": lambda v: not v,
    "_MIN": min,
    "_MAX": max,
    "_ABS": abs,
    "_TEXTJOIN": _textjoin,
    "TRUE": True,
    "FALSE": False,
}


class WorkbookEvaluator:
    """Evaluates formula cells across the workbook, memoising as it goes."""

    def __init__(self, wb, default_sheet: str):
        self.wb = wb
        self.default = default_sheet
        self._cache = {}

    # -- references --------------------------------------------------------

    def cell(self, sheet: str, address: str):
        key = (sheet, address)
        if key in self._cache:
            return self._cache[key]

        raw = self.wb[sheet][address].value
        if not isinstance(raw, str) or not raw.startswith("="):
            result = BLANK if raw is None else raw
        else:
            self._cache[key] = 0  # guard against accidental cycles
            result = eval(self.translate(raw, sheet), dict(ENV))  # noqa: S307

        self._cache[key] = result
        return result

    def column(self, sheet: str, letter: str):
        """A whole-column reference, with formula cells evaluated.

        The generated Key columns are formulas, so returning raw cell contents
        would make every keyed lookup miss.
        """
        return [
            self.cell(sheet, f"{letter}{row}") for row in range(1, COLUMN_DEPTH + 1)
        ]

    # -- translation -------------------------------------------------------

    def translate(self, formula: str, sheet: str) -> str:
        """Translate one Excel formula into a Python expression.

        Resolved values are parked behind placeholders rather than spliced in
        directly. A weapon called "CCW (A1)" would otherwise be re-scanned and
        its name mistaken for a cell reference.
        """
        body = formula[1:] if formula.startswith("=") else formula
        # openpyxl-emitted formulas prefix post-2007 functions (TEXTJOIN) with
        # _xlfn. so Excel/Sheets recognise them; strip it before translating.
        body = body.replace("_xlfn.", "")
        parked: List[str] = []

        def park(text: str) -> str:
            parked.append(text)
            return f"\x00{len(parked) - 1}\x00"

        def on_string(m: "re.Match") -> str:
            # Excel escapes a literal quote inside a string as "", which
            # Python's repr() won't produce, so unescape it ourselves. Wrapped
            # in _TXT so a later "&" (translated to +) against a numeric cell
            # coerces the number to text instead of raising a TypeError.
            content = m.group(0)[1:-1].replace('""', '"')
            return park(f"_TXT({content!r})")

        body = STRING.sub(on_string, body)
        body = COMPARISON.sub("==", body)
        body = body.replace("<>", "!=")

        def on_range(m):
            target = m.group(1) or m.group(2) or sheet
            return park(repr(self.column(target, m.group(3))))

        def on_qualified(m):
            target = m.group(1) or m.group(2)
            return park(repr(self.cell(target, f"{m.group(3)}{m.group(4)}")))

        def on_local(m):
            return park(repr(self.cell(sheet, f"{m.group(1)}{m.group(2)}")))

        body = COLUMN_RANGE.sub(on_range, body)
        body = QUALIFIED_CELL.sub(on_qualified, body)
        body = LOCAL_CELL.sub(on_local, body)

        for name in FUNCTIONS:
            body = re.sub(rf"\b{name}\(", f"_{name}(", body)
        body = body.replace("&", "+")

        return re.sub(r"\x00(\d+)\x00", lambda m: parked[int(m.group(1))], body)


class SheetEvaluator:
    """Single-sheet convenience wrapper."""

    def __init__(self, ws):
        self._inner = WorkbookEvaluator(ws.parent, ws.title)
        self._sheet = ws.title

    def value(self, address: str):
        return self._inner.cell(self._sheet, address)
