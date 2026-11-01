"""Facts that article extraction drops: key/value boxes and small tables.

Karakeep's readable text (Mozilla Readability) keeps the article and drops
anything that looks like page furniture. That includes summary boxes such as
a breed's size and exercise needs or a product's specs, usually marked up as
<dl> lists or small <table>s. When Karakeep keeps a full copy of the page
(CRAWLER_FULL_PAGE_ARCHIVE=true), this pulls those out of it so they can go
into source.md next to the article.

Only <dl> and <table> are recovered, outside <nav>, <header> and <footer>,
only when their text isn't already in the article, and not when they're
mostly links (navigation boxes like Wikipedia's "Dogs originating in Germany").

Some pages draw facts that aren't text at all: a rating as five shaded blocks,
a chart, a gauge. The numbers behind them often ship with the page as JSON (a
data-* attribute, JSON-LD, a <script type="application/json">). So a list of
three or more similar JSON records also becomes a table, when one field is a
label shown on the page (outside nav/header/footer), another holds a number,
and the records share some text with the article. Menus, settings and tracking
data drop out: their labels aren't shown, they have no numbers other than ids,
or none of their text is in the article.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

SKIP_INSIDE = {"nav", "header", "footer", "script", "style", "noscript", "template", "svg"}
MAX_CELL_CHARS = 200
MAX_TABLE_ROWS = 40
MAX_CHARS = 6000
MAX_LINK_SHARE = 0.5
MIN_JSON_CHARS = 100          # smaller attribute values aren't worth parsing
MIN_RECORDS = 3
MAX_RECORDS = 60
MAX_LABEL_CHARS = 80
MAX_SHORT_CHARS = 40          # list items and context strings in JSON tables
MAX_COLUMNS = 8
MIN_ID = 10_000               # integer columns entirely above this are ids, not facts
# Numbers that order or identify records rather than describe them.
ID_KEY = re.compile(r"(^|_)id$|Id$|^id[A-Z_]|(^|_)(ts|timestamp|time|date|index|order|position|sort|weight)$"
                    r"|^(level|depth)$", re.I)
JSON_SCRIPT_TYPES = {"application/ld+json", "application/json"}


def _norm(text: str) -> str:
    return " ".join(text.split())


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0                 # depth inside SKIP_INSIDE elements
        self.lists: list[list[tuple[str, str]]] = []
        self.tables: list[list[list[str]]] = []
        self.link_share: dict[int, float] = {}  # id(list or rows) -> share of text inside <a>
        self._in_a = 0
        self._text = self._link_text = 0       # characters in open dl/table cells, and inside links
        self._dl: list[list] | None = None   # stack of open <dl>s: [pairs, current key]
        self._table: list[list[list[str]]] = []
        self._table_counts: list[tuple[int, int]] = []   # text/link counts when each open table began
        self._buf: list[str] | None = None   # text of the open dt/dd/td/th
        self._cell_tag: str | None = None
        self.visible: list[str] = []         # page text outside SKIP_INSIDE
        self.json: list[str] = []            # embedded JSON: attribute values, JSON scripts
        self._script: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        for _, value in attrs:
            if value and len(value) >= MIN_JSON_CHARS and value.lstrip()[:1] in ("{", "["):
                self.json.append(value)
        if tag == "script" and (dict(attrs).get("type") or "").lower() in JSON_SCRIPT_TYPES:
            self._script = []
        if tag in SKIP_INSIDE:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "a":
            self._in_a += 1
        elif tag == "dl":
            self._dl = self._dl or []
            self._dl.append([[], None, self._text, self._link_text])
        elif tag in ("dt", "dd") and self._dl:
            self._close_cell()
            self._buf, self._cell_tag = [], tag
        elif tag == "table":
            self._table.append([])
            self._table_counts.append((self._text, self._link_text))
        elif tag == "tr" and self._table:
            self._close_cell()
            self._table[-1].append([])
        elif tag in ("td", "th") and self._table:
            self._close_cell()
            if not self._table[-1]:
                self._table[-1].append([])
            self._buf, self._cell_tag = [], tag
        elif tag == "br" and self._buf is not None:
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.json.append("".join(self._script))
            self._script = None
        if tag in SKIP_INSIDE:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "a":
            self._in_a = max(0, self._in_a - 1)
        elif tag in ("dt", "dd", "td", "th") and tag == self._cell_tag:
            self._close_cell()
        elif tag == "dl" and self._dl:
            self._close_cell()
            pairs, _, text0, link0 = self._dl.pop()
            if len(pairs) >= 2:
                self.lists.append(pairs)
                self.link_share[id(pairs)] = self._share(text0, link0)
        elif tag == "table" and self._table:
            self._close_cell()
            rows = [r for r in self._table.pop() if any(r)]
            text0, link0 = self._table_counts.pop()
            if 2 <= len(rows) <= MAX_TABLE_ROWS:
                self.tables.append(rows)
                self.link_share[id(rows)] = self._share(text0, link0)

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        if not self.skip:
            self.visible.append(data)
        if not self.skip and self._buf is not None:
            self._buf.append(data)
            n = len(data.strip())
            self._text += n
            if self._in_a:
                self._link_text += n

    def _share(self, text0: int, link0: int) -> float:
        text = self._text - text0
        return (self._link_text - link0) / text if text else 1.0

    def _close_cell(self):
        if self._buf is None:
            return
        text, tag = _norm("".join(self._buf))[:MAX_CELL_CHARS], self._cell_tag
        self._buf = self._cell_tag = None
        if tag == "dt" and self._dl:
            self._dl[-1][1] = text
        elif tag == "dd" and self._dl:
            key = self._dl[-1][1]
            if key and text:
                self._dl[-1][0].append((key, text))
            self._dl[-1][1] = None
        elif tag in ("td", "th") and self._table and self._table[-1]:
            self._table[-1][-1].append(text)


def _json_tables(blobs: list[str], visible: str, article: str) -> list[str]:
    """Markdown tables for lists of similar JSON records labelled with text shown on the page.

    `visible` and `article` are normalized and lowercased."""
    tables: list[str] = []

    def shown(v) -> bool:
        return isinstance(v, str) and 2 < len(v) <= MAX_LABEL_CHARS and _norm(v).lower() in visible

    def number(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def short_list(v) -> bool:
        return isinstance(v, list) and len(v) <= 10 and all(
            shown(x) and len(x) <= MAX_SHORT_CHARS for x in v)

    def in_article(r: dict) -> bool:
        return any(isinstance(v, str) and len(v) > 3 and _norm(v).lower() in article
                   for v in r.values())

    def table(recs: list[dict]) -> str | None:
        keys = [k for k in dict.fromkeys(k for r in recs for k in r)
                if sum(k in r for r in recs) * 2 >= len(recs)]
        # The label: the field with the most distinct values shown on the page.
        label, best = None, 0
        for k in keys:
            n = len({r[k] for r in recs if shown(r.get(k))})
            if n > best:
                label, best = k, n
        rows = [r for r in recs if label and shown(r.get(label))]
        if len(rows) < MIN_RECORDS or (article and sum(map(in_article, rows)) * 2 < len(rows)):
            return None

        def varies(k) -> bool:
            return len({json.dumps(r.get(k), sort_keys=True) for r in rows}) > 1

        def ids(k) -> bool:
            return all(isinstance(r.get(k), int) and r[k] >= MIN_ID for r in rows if k in r)

        numbers = [k for k in keys if k != label and not ID_KEY.search(k) and varies(k) and not ids(k)
                   and all(k not in r or r[k] is None or number(r[k]) for r in rows)]
        if not numbers:
            return None
        lists = [k for k in keys if varies(k) and any(r.get(k) for r in rows)
                 and all(k not in r or short_list(r[k]) for r in rows)]
        # Short strings shown on the page, such as the ends of a rating scale.
        context = [k for k in keys if k != label and varies(k)
                   and all(k not in r or isinstance(r[k], str) for r in rows)
                   and sum(shown(r.get(k)) and len(r[k]) <= MAX_SHORT_CHARS for r in rows) * 2 >= len(rows)]
        cols = [label] + (numbers + lists + context)[:MAX_COLUMNS - 1]

        def cell(v) -> str:
            if v is None or v == [] or (isinstance(v, str) and not shown(v)):
                return ""
            text = ", ".join(v) if isinstance(v, list) else str(v)
            return _norm(text).replace("|", "\\|")

        lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(cell(r.get(k)) for k in cols) + " |" for r in rows]
        return "\n".join(lines)

    def walk(o, depth=0):
        if depth > 30:
            return
        children = list(o.values()) if isinstance(o, dict) else o if isinstance(o, list) else []
        recs = [c for c in children if isinstance(c, dict)]
        if MIN_RECORDS <= len(recs) <= MAX_RECORDS:
            t = table(recs)
            if t and t not in tables:
                tables.append(t)
        for c in children:
            walk(c, depth + 1)

    for blob in blobs:
        try:
            walk(json.loads(blob))
        except (ValueError, RecursionError):
            continue
    return tables


def extract(html: str, article: str = "") -> str:
    """Markdown for the <dl>s and tables in `html` that `article` doesn't already contain."""
    c = _Collector()
    try:
        c.feed(html)
        c.close()
    except Exception:  # malformed pages: keep whatever was collected
        pass
    seen = _norm(article).lower()

    def new(texts: list[str]) -> bool:
        # Skip a block when most of its values are already in the article text.
        values = [t for t in texts if len(t) > 3]
        missing = [t for t in values if t.lower() not in seen]
        return bool(values) and len(missing) > len(values) / 2

    blocks = []
    def links(block) -> bool:
        return c.link_share.get(id(block), 0) > MAX_LINK_SHARE

    for pairs in c.lists:
        if not links(pairs) and new([v for _, v in pairs]):
            blocks.append("\n".join(f"- **{k.rstrip(':')}:** {v}" for k, v in pairs))
    for rows in c.tables:
        if not links(rows) and new([cell for r in rows for cell in r]):
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            esc = [[cell.replace("|", "\\|") for cell in r] for r in rows]
            lines = ["| " + " | ".join(esc[0]) + " |", "|" + "---|" * width]
            lines += ["| " + " | ".join(r) + " |" for r in esc[1:]]
            blocks.append("\n".join(lines))
    # Not checked against the article: the labels are in it, the values aren't.
    blocks += _json_tables(c.json, _norm(" ".join(c.visible)).lower(), seen)

    out, total = [], 0
    for b in blocks:
        if total + len(b) > MAX_CHARS:
            break
        out.append(b)
        total += len(b)
    return "\n\n".join(out)
