"""The pantry table in the vault (lists/pantry.md by default).

    # Pantry

    | Item | Status |
    |---|---|
    | olive oil | low |

Status is ok, low or out; the weekly shopping task buys the low and out ones.
Rows are matched by item name, ignoring case and a trailing "s"; unknown items
get a new row at the end of the table. Other columns and text are kept.
"""

from __future__ import annotations

import os
from pathlib import Path

HEADER = "# Pantry\n\n| Item | Status |\n|---|---|\n"


def _key(name: str) -> str:
    k = " ".join(name.lower().split())
    return k[:-1] if k.endswith("s") and not k.endswith("ss") else k


def _cells(line: str) -> list[str] | None:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    return [c.strip() for c in s[1:-1].split("|")]


def short(path: Path) -> list[tuple[str, str]]:
    """Items whose status is low or out."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = _cells(line)
        if cells and len(cells) >= 2 and cells[1].lower() in ("low", "out"):
            out.append((cells[0], cells[1].lower()))
    return out


def update(path: Path, changes: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    """Set (item, status) pairs; returns (item, old status or None if new, new status)."""
    text = path.read_text(encoding="utf-8") if path.exists() else HEADER
    lines = text.splitlines()

    rows = {}       # key -> line index
    last_row = None
    for i, line in enumerate(lines):
        cells = _cells(line)
        if cells is None or len(cells) < 2:
            continue
        if cells[0].lower() == "item" or set(cells[0]) <= set("-: "):
            last_row = i  # header or |---|: new rows go after them in an empty table
            continue
        rows[_key(cells[0])] = i
        last_row = i
    if last_row is None:  # no table at all: start one at the end
        lines += ["", "| Item | Status |", "|---|---|"]
        last_row = len(lines) - 1

    done = []
    added = []
    for name, status in changes:
        k = _key(name)
        if rows.get(k) == -1:
            continue
        if k in rows:
            cells = _cells(lines[rows[k]])
            old = cells[1]
            cells[1] = status
            lines[rows[k]] = "| " + " | ".join(cells) + " |"
            done.append((cells[0], old, status))
        else:
            row = f"| {name} | {status} |"
            added.append(row)
            rows[k] = -1  # added in this call: a second mention adds no second row
            done.append((name, None, status))
    lines[last_row + 1:last_row + 1] = added

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.wikiglue-tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return done
