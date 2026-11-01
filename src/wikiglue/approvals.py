"""Research requests: the only path from a model suggestion to the internet.

The wiki agent appends suggestions to _review/research-requests.md:

    - [ ] Baguette proofing times — source: https://… — suggested search: "…" (…)

An admin approves one by ticking its box in Obsidian or sending `approve N` in
chat (N counts the open requests, as `requests` lists them). wikiglue then saves
the suggested source link to Karakeep as that admin, which leads to a normal
ingest, and marks the line "— approved <date>". A request without a link gets a
search link back instead: a person picks the source.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

ITEM_RE = re.compile(r"^(\s*- \[)([ xX])(\] )(.*)$")
URL_RE = re.compile(r"https?://[^\s<>()\"']+[^\s<>()\"'.,;:!?]")
SEARCH_RE = re.compile(r'suggested search:\s*"([^"]+)"')
DONE_MARK = "— approved "

REQUESTS_FILE = Path("_review") / "research-requests.md"


@dataclass
class Request:
    line_no: int
    text: str
    checked: bool

    @property
    def handled(self) -> bool:
        return DONE_MARK in self.text

    @property
    def url(self) -> str | None:
        m = URL_RE.search(self.text)
        return m.group(0) if m else None

    @property
    def title(self) -> str:
        return re.split(r"\s+—\s+", self.text, maxsplit=1)[0].strip()

    @property
    def search_link(self) -> str:
        m = SEARCH_RE.search(self.text)
        query = m.group(1) if m else self.title
        return "https://duckduckgo.com/?q=" + urllib.parse.quote_plus(query)


class ResearchRequests:
    def __init__(self, vault: Path):
        self.path = vault / REQUESTS_FILE

    def read(self) -> tuple[list[str], list[Request]]:
        try:
            lines = self.path.read_text(encoding="utf-8").split("\n")
        except FileNotFoundError:
            return [], []
        items = []
        for i, line in enumerate(lines):
            if m := ITEM_RE.match(line):
                items.append(Request(i, m.group(4), m.group(2) != " "))
        return lines, items

    def open_requests(self) -> list[Request]:
        return [r for r in self.read()[1] if not r.checked and not r.handled]

    def approve(self, n: int) -> Request | None:
        """Tick the n-th open request (1-based). The watcher then acts on it."""
        open_ = self.open_requests()
        if not 1 <= n <= len(open_):
            return None
        req = open_[n - 1]
        self._edit({req.line_no: lambda line: ITEM_RE.sub(r"\1x\3\4", line)}, expect=req)
        req.checked = True
        return req

    def ticked_unhandled(self) -> list[Request]:
        return [r for r in self.read()[1] if r.checked and not r.handled]

    def mark_handled(self, req: Request, note: str) -> None:
        mark = f" {DONE_MARK}{dt.date.today().isoformat()}, {note}"
        self._edit({req.line_no: lambda line: line.rstrip() + mark}, expect=req)

    def _edit(self, changes: dict, expect: Request) -> None:
        """Rewrite the file atomically, re-reading it first so a concurrent edit by
        the agent (or Obsidian) isn't overwritten."""
        lines, _ = self.read()
        if expect.line_no >= len(lines) or expect.text not in lines[expect.line_no]:
            raise RuntimeError("research-requests.md changed underneath; try again")
        for i, fn in changes.items():
            lines[i] = fn(lines[i])
        tmp = self.path.with_name(f".{self.path.name}.wikiglue-tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        os.replace(tmp, self.path)
