"""Karakeep -> vault: copy each new bookmark into raw/ and queue an ingest job.

For every user with a Karakeep API key, poll their newest bookmarks. A bookmark
is written once Karakeep has finished with it (link crawled, file uploaded):

    raw/YYYY/MM/<slug>/source.md     readable text, with a short header
    raw/YYYY/MM/<slug>/meta.json     title, url, added_by, added_at, kind, karakeep_id
    raw/YYYY/MM/<slug>/<file>        the image or PDF, if any
    raw/YYYY/MM/<slug>/page-N.jpg    a scanned PDF's pages, for the vision model

Then an ingest job for that folder goes into wiki-runner's queue.

Long sources would overflow the model's 32k context in one pass, so their text
is also split, at the article's own headings, into part-1.md … part-N.md. Part 1
goes through the normal `ingest` task and each later part through `ingest-part`,
as separate jobs in order. Every job starts with a fresh context; nothing has
to be summarized away mid-job.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import mimetypes
import re
import subprocess
import time
import unicodedata
from pathlib import Path

import aiohttp

from . import pagefacts
from .config import Config, User
from .jobs import Jobs
from .karakeep import Karakeep, KarakeepError
from .state import State

log = logging.getLogger(__name__)

POLL_SECONDS = 30
# Give up waiting for a crawl after this long and ingest whatever there is.
CRAWL_WAIT_SECONDS = 3600
# Karakeep marks a crawl done before it saves the full-page archive (pagefacts.py
# reads it). Wait this long after first seeing a link for the archive to appear.
ARCHIVE_WAIT_SECONDS = 180
# Sources with more text than this are ingested in parts of at most PART_CHARS
# (~4k tokens each, leaving room for the wiki pages the model reads and edits).
SPLIT_THRESHOLD_CHARS = 20_000
PART_CHARS = 15_000
HEADING_RE = re.compile(r"^#{1,3} \S")
# A PDF without a text layer (a scan) is rendered to images for the vision model: at most
# this many pages, each at most this many pixels on its long side.
SCAN_PAGES = 6
SCAN_PIXELS = 1600


def slugify(text: str, max_len: int = 60) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "untitled"


def first_line(text: str | None, ocr: bool = False) -> str:
    """First line with a few words in it, trimmed to 80 characters.

    With ocr=True (text read off a photo or screenshot), skip lines that look like
    OCR noise: a phone's status bar ("2:09 wil = @»"), icons read as letters. The line
    needs two words of three or more letters, and mostly letters."""
    for line in (text or "").splitlines():
        line = line.strip(" #*-|\t")
        if len(line.split()) < 2:
            continue
        if ocr:
            words = [w for w in re.findall(r"[^\W\d_]+", line) if len(w) >= 3]
            chars = [ch for ch in line if not ch.isspace()]
            if len(words) < 2 or sum(ch.isalpha() for ch in chars) < 0.6 * len(chars):
                continue
        return line[:80]
    return ""


def describe(bm: dict) -> tuple[str, str, str | None]:
    """(kind, title, url) for a Karakeep bookmark."""
    c = bm.get("content") or {}
    kind = c.get("type", "unknown")
    if kind == "asset":
        kind = c.get("assetType", "file")
    url = c.get("url") or c.get("sourceUrl")
    # Uploaded files often have no title, or a camera name like IMG_1234.jpg: then
    # the first line of the OCR'd or extracted text names it better.
    file_name = c.get("fileName")
    if file_name and re.match(r"^(IMG|DSC|PXL|Screenshot|image)[\W_]", file_name, re.I):
        file_name = None
    title = (bm.get("title") or c.get("title") or first_line(c.get("text"))
             or first_line(c.get("content"), ocr=kind in ("image", "pdf")) or file_name
             or c.get("fileName") or url or "untitled")
    if kind == "text" and not bm.get("title"):
        kind = "note"
    return kind, title.strip(), url


def is_ready(bm: dict, first_seen: float | None) -> bool:
    c = bm.get("content") or {}
    if c.get("type") != "link":
        return True
    waited = time.time() - first_seen if first_seen is not None else 0
    if c.get("crawlStatus") == "success":
        return Karakeep.archive_id(bm) is not None or waited > ARCHIVE_WAIT_SECONDS
    if c.get("crawlStatus") == "failure":
        return True
    return waited > CRAWL_WAIT_SECONDS


def scan_pages(pdf: Path) -> tuple[list[str], int]:
    """Render a PDF's first pages to page-N.jpg beside it; returns (file names, page count)."""
    try:
        info = subprocess.run(["pdfinfo", pdf.name], cwd=pdf.parent, capture_output=True,
                              text=True, timeout=60)
        total = int(re.search(r"^Pages:\s+(\d+)", info.stdout, re.M).group(1))
        subprocess.run(["pdftoppm", "-jpeg", "-scale-to", str(SCAN_PIXELS), "-l", str(SCAN_PAGES),
                        pdf.name, "page"], cwd=pdf.parent, capture_output=True, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError, AttributeError) as e:
        log.warning("%s: couldn't render pages (%s)", pdf, e)
        return [], 0
    return sorted(p.name for p in pdf.parent.glob("page-*.jpg")), total


def unique_dir(base: Path) -> Path:
    d, n = base, 2
    while d.exists():
        d, n = base.with_name(f"{base.name}-{n}"), n + 1
    return d


def render_source(bm: dict, user: User, kind: str, title: str, url: str | None,
                  body: str, truncated: bool, filename: str | None,
                  pages: tuple[list[str], int] = ([], 0)) -> str:
    c = bm.get("content") or {}
    lines = [f"# {title}", ""]
    if url:
        lines.append(f"Source: <{url}>")
    for label, key in (("Author", "author"), ("Publisher", "publisher"), ("Published", "datePublished")):
        if c.get(key):
            lines.append(f"{label}: {c[key]}")
    lines.append(f"Added by {user.name} on {dt.date.today().isoformat()}.")
    if bm.get("note"):
        lines += ["", f"Note from {user.name}: {bm['note'].strip()}"]
    if filename:
        lines += ["", f"![[{filename}]]" if kind == "image" else f"Attached file: [[{filename}]]"]
    images, total = pages
    if images:
        lines += ["", "The PDF is a scan with no text; its pages are these images:", ""]
        lines += [f"![[{name}]]" for name in images]
        if total > len(images):
            lines += ["", f"(Only the first {len(images)} of {total} pages are shown.)"]
    if c.get("type") == "link" and c.get("crawlStatus") != "success":
        lines += ["", "(The page could not be fetched; only the link and title are available.)"]
    if body.strip():
        lines += ["", "---", "", body.strip()]
    if truncated:
        lines += ["", "(Text truncated: the original is longer.)"]
    return "\n".join(lines) + "\n"


def split_text(text: str, max_chars: int = PART_CHARS) -> list[str]:
    """Split markdown into parts of at most max_chars, preferring heading boundaries,
    then paragraph boundaries; a single huge paragraph is cut hard."""
    sections, current = [], []
    for line in text.splitlines(keepends=True):
        if HEADING_RE.match(line) and current:
            sections.append("".join(current))
            current = []
        current.append(line)
    if current:
        sections.append("".join(current))

    pieces = []
    for section in sections:
        if len(section) <= max_chars:
            pieces.append(section)
            continue
        for para in re.split(r"(?<=\n\n)", section):
            pieces += [para[i:i + max_chars] for i in range(0, len(para), max_chars)]

    parts, buf = [], ""
    for piece in pieces:
        if buf and len(buf) + len(piece) > max_chars:
            parts.append(buf)
            buf = ""
        buf += piece
    if buf.strip():
        parts.append(buf)
    return parts


def outline(text: str, limit: int = 40) -> list[str]:
    """The article's headings, for orienting each part."""
    heads = [line.strip() for line in text.splitlines() if HEADING_RE.match(line)]
    return heads[:limit] + (["…"] if len(heads) > limit else [])


def render_part(title: str, n: int, total: int, heads: list[str], chunk: str) -> str:
    lines = [f"# {title} — part {n} of {total}", ""]
    if heads:
        lines += ["Sections of the whole article (this part is one stretch of them):", ""]
        lines += [f"- {h.lstrip('#').strip()}" for h in heads]
        lines.append("")
    lines += ["---", "", chunk.strip(), ""]
    return "\n".join(lines)


def new_raw_dir(vault: Path, title: str) -> Path:
    """A new, empty raw/YYYY/MM/<YYYY-MM>-<slug>/ folder."""
    today = dt.date.today()
    folder = unique_dir(vault / "raw" / f"{today:%Y}" / f"{today:%m}" / f"{today:%Y-%m}-{slugify(title)}")
    folder.mkdir(parents=True)
    return folder


def write_parts(folder: Path, title: str, body: str) -> int:
    """Split a long body into part-N.md files next to source.md; returns the number of parts."""
    chunks = split_text(body) if len(body) > SPLIT_THRESHOLD_CHARS else [body]
    if len(chunks) > 1:
        heads = outline(body)
        for n, chunk in enumerate(chunks, 1):
            (folder / f"part-{n}.md").write_text(
                render_part(title, n, len(chunks), heads, chunk), encoding="utf-8")
    return len(chunks)


def queue_ingest(jobs: Jobs, raw_dir: str, parts: int, user_key: str, bookmark: str | None = None) -> None:
    """One job per part, queued in order. Only the last one carries the bookmark id,
    so the "added to the wiki" chat reply comes when the whole source is in."""
    by = f"wikiglue:{user_key}"
    for n in range(1, parts + 1):
        meta = {"user": user_key}
        if n == parts and bookmark:
            meta["bookmark"] = bookmark
        if n == 1:
            jobs.submit("ingest", raw_dir, submitted_by=by, meta=meta)
        else:
            jobs.submit("ingest-part", f"{raw_dir}/part-{n}.md", submitted_by=by, meta=meta)


class Inbox:
    def __init__(self, config: Config, state: State, jobs: Jobs, session: aiohttp.ClientSession):
        self.config, self.state, self.jobs, self.session = config, state, jobs, session
        self.raw = config.vault / "raw"

    def client(self, user: User) -> Karakeep:
        return Karakeep(self.session, self.config.karakeep_url, user.karakeep_key)

    async def run(self) -> None:
        if not self.config.karakeep_url:
            log.info("inbox: no [karakeep] url configured; not polling")
            return
        while True:
            for user in self.config.users:
                if user.karakeep_key:
                    try:
                        await self.poll(user)
                    except (aiohttp.ClientError, KarakeepError, asyncio.TimeoutError) as e:
                        log.warning("inbox: polling %s failed: %s", user.key, e)
            await asyncio.sleep(POLL_SECONDS)

    async def poll(self, user: User) -> None:
        kk = self.client(user)
        cursor = None
        while True:
            bookmarks, cursor = await kk.recent_bookmarks(cursor=cursor)
            new = [b for b in bookmarks if self.state.bookmark_status(b["id"]) in (None, "pending")]
            for bm in reversed(new):  # oldest first
                await self.consider(user, kk, bm)
            # Stop paging once a page is entirely known: older ones were handled before.
            if not cursor or not new:
                return

    async def consider(self, user: User, kk: Karakeep, bm: dict) -> None:
        first_seen = self.state.bookmark_first_seen(bm["id"])
        if first_seen is None:
            self.state.set_bookmark(bm["id"], user.key, "pending")
        if not is_ready(bm, first_seen):
            return
        try:
            raw_dir, parts = await self.write(user, kk, bm)
        except Exception:
            log.exception("inbox: couldn't write bookmark %s", bm["id"])
            return
        self.state.set_bookmark(bm["id"], user.key, "written", raw_dir)
        queue_ingest(self.jobs, raw_dir, parts, user.key, bookmark=bm["id"])
        log.info("inbox: %s's bookmark %s -> %s, ingest queued%s, from %s", user.key, bm["id"], raw_dir,
                 f" in {parts} parts" if parts > 1 else "", self.came_from(bm))

    # Karakeep's own clients, by the bookmark's `source`. wikiglue itself saves through the API:
    # chat messages, research approvals and email PDFs (mail.py).
    SOURCES = {"mobile": "karakeep app", "extension": "browser extension", "web": "karakeep web",
               "singlefile": "browser extension"}

    def came_from(self, bm: dict) -> str:
        """How a bookmark got here, for the log (and the metrics dashboard)."""
        if (bm.get("note") or "").startswith("Research request:"):
            return "research approval"
        if self.state.get_notify(bm["id"]) is not None:
            return "chat"
        source = bm.get("source") or ""
        if source == "api":
            return "email PDF"
        return self.SOURCES.get(source, f"karakeep {source}".strip())

    async def with_page_facts(self, kk: Karakeep, bm: dict, body: str) -> str:
        """Put the page's fact boxes that article extraction dropped above the article."""
        archive = Karakeep.archive_id(bm)
        if archive is None:
            return body
        try:
            page = (await kk.asset(archive)).data.decode("utf-8", errors="replace")
        except (aiohttp.ClientError, KarakeepError) as e:
            log.warning("bookmark %s: no page archive (%s)", bm["id"], e)
            return body
        facts = await asyncio.to_thread(pagefacts.extract, page, body)
        if not facts:
            return body
        log.info("bookmark %s: recovered %d chars of page details", bm["id"], len(facts))
        return ("## Details from the page\n\n"
                "(Listed on the page but left out of the article text below.)\n\n"
                f"{facts}\n\n{body}")

    async def write(self, user: User, kk: Karakeep, bm: dict) -> tuple[str, int]:
        """Write the raw folder; returns (vault-relative folder, number of parts)."""
        kind, title, url = describe(bm)
        today = dt.date.today()
        folder = new_raw_dir(self.config.vault, title)

        c = bm.get("content") or {}
        filename = None
        if c.get("type") == "asset" and c.get("assetId"):
            asset = await kk.asset(c["assetId"])
            ext = mimetypes.guess_extension(asset.content_type.split(";")[0]) or ""
            base = slugify(Path(c.get("fileName") or kind).stem, 40)
            filename = f"{'image' if kind == 'image' else base}{ext}"
            (folder / filename).write_bytes(asset.data)

        if c.get("type") == "text":
            body, truncated = c.get("text") or "", False
        else:
            body, truncated = await kk.readable_content(bm["id"])
            body = await self.with_page_facts(kk, bm, body)

        pages = ([], 0)
        if kind == "pdf" and filename and not body.strip():
            pages = await asyncio.to_thread(scan_pages, folder / filename)

        (folder / "source.md").write_text(
            render_source(bm, user, kind, title, url, body, truncated, filename, pages),
            encoding="utf-8")
        parts = write_parts(folder, title, body)
        meta = {
            "title": title,
            "url": url,
            "added_by": user.name,
            "added_at": today.isoformat(),
            "kind": kind,
            "karakeep_id": bm["id"],
        }
        if bm.get("note"):
            meta["note"] = bm["note"]
        if parts > 1:
            meta["parts"] = parts
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
        return str(folder.relative_to(self.config.vault)), parts
