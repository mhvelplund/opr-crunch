"""Import an OPR army-book PDF into the csv/ tabs.

    python tools/import_army_book.py <url|book.pdf|book.txt> [--faction NAME]

Accepts an army-book URL or a local file. Downloaded books are cached in
books/ and reused; --refresh re-fetches. The faction is read from the book's
page header unless --faction overrides it.

Every existing row for that faction is replaced; other factions are untouched.
Special rules are merged rather than replaced, since the core rules live in the
same tab as the book's.

Requires `pdftotext` (poppler) when given a PDF.
"""

import argparse
import csv
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opr_crunch import armybook, layout  # noqa: E402
from opr_crunch.model import MODELLED_RULES, PARAMETERISED_RULES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "csv"
BOOKS_DIR = ROOT / "books"

#: Core rules the books assume rather than restate.
CORE_TEXT = {
    "Tough": (
        "This model must take X wounds before being killed. If a model with tough "
        "joins a unit without it, then it is removed last when the unit takes wounds."
    ),
}


def extract_text(source: Path) -> str:
    if source.suffix.lower() != ".pdf":
        return source.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "book.txt"
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(out)], check=True
        )
        return out.read_text(encoding="utf-8")


def read_csv(name: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(open(CSV_DIR / name, encoding="utf-8-sig")))
    return rows[0], rows[1:]


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    with open(CSV_DIR / name, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  csv/{name}: {len(rows)} rows")


def replace_faction(name: str, faction: str, new_rows: list[list]) -> None:
    """Swap out every row belonging to ``faction``, keeping the others."""
    header, rows = read_csv(name)
    kept = [r for r in rows if len(r) > 1 and r[1] != faction]
    write_csv(name, header, kept + new_rows)


def import_book(text: str, faction: str) -> None:
    pages = text.split("\f")
    unit_pages = pages[3:]  # the per-unit cards; page 2's roster table is a grid

    # --- units ------------------------------------------------------------
    units = armybook.parse_units(unit_pages)
    unit_rows = [
        [u["name"], faction, u["quality"], u["defense"], u["size"],
         u["tough"], u["ravage"], ", ".join(u["rules"])]
        for u in sorted(units, key=lambda u: u["name"])
    ]
    replace_faction("units.csv", faction, unit_rows)

    # --- weapons ----------------------------------------------------------
    weapons = armybook.find_weapons(text)
    weapon_rows = [
        [name, faction, w["range"], w["attacks"], w["ap"], w["blast"],
         w["deadly"], w["impact"], ", ".join(w["rules"])]
        for name, w in sorted(weapons.items())
    ]
    replace_faction("weapons.csv", faction, weapon_rows)

    # --- upgrades ---------------------------------------------------------
    upgrades = armybook.parse_upgrades("\n".join(unit_pages))
    upgrade_rows = [
        [name, faction, 0, 0, 0, 0, ", ".join(granted)]
        for name, granted in upgrades
    ]
    replace_faction("upgrades.csv", faction, upgrade_rows)

    # --- special rules (merged, not replaced) -----------------------------
    header, rows = read_csv("special_rules.csv")
    known = {r[0]: r for r in rows}
    for name, body in armybook.parse_special_rules(pages[2]):
        known.setdefault(name, [name, "", "", "", body])
    for name, body in CORE_TEXT.items():
        known.setdefault(name, [name, "", "", "", body])

    merged = []
    for name in sorted(known):
        text_col = known[name][-1]
        merged.append([
            name,
            "Yes" if name in PARAMETERISED_RULES else "No",
            MODELLED_RULES.get(name, "-"),
            "Yes" if name in MODELLED_RULES else "No",
            text_col,
        ])
    write_csv("special_rules.csv", layout.SPECIAL_RULES_COLUMNS, merged)

    # --- faction ----------------------------------------------------------
    fheader, frows = read_csv("factions.csv")
    if not any(r and r[0] == faction for r in frows):
        write_csv("factions.csv", fheader, frows + [[faction]])

    unmodelled = sorted(
        {r for u in units for r in u["rules"]}
        | {r for w in weapons.values() for r in w["rules"]}
    )
    unmodelled = [
        r for r in unmodelled
        if re.sub(r"\(\d+\)$", "", r) not in MODELLED_RULES
        and not any(m in r for m in MODELLED_RULES)
    ]
    print(f"\n  {len(units)} units, {len(weapons)} weapons, {len(upgrades)} upgrades")
    print(f"  reference-only rules in use: {', '.join(unmodelled)}")


def fetch(url: str, refresh: bool = False) -> Path:
    """Download an army book into books/, reusing an earlier download."""
    BOOKS_DIR.mkdir(exist_ok=True)
    target = BOOKS_DIR / armybook.cache_name(url)

    if target.exists() and not refresh:
        print(f"  using cached books/{target.name}")
        return target

    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "opr_crunch"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise SystemExit(f"{url} did not return a PDF (got {data[:16]!r})")

    target.write_bytes(data)
    print(f"  saved books/{target.name} ({len(data) // 1024} KB)")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="army book URL, or a local .pdf/.txt")
    parser.add_argument(
        "--faction", help="override the faction name read from the book header"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="re-download even if cached"
    )
    args = parser.parse_args()

    source = fetch(args.source, args.refresh) if armybook.is_url(args.source) else Path(args.source)
    text = extract_text(source)

    faction = args.faction or armybook.detect_faction(text)
    if not faction:
        raise SystemExit(
            "Could not read a faction name from the book header; pass --faction"
        )
    if not args.faction:
        print(f"  detected faction {faction!r}")

    print(f"Importing {source.name} as {faction!r}")
    import_book(text, faction)


if __name__ == "__main__":
    main()
