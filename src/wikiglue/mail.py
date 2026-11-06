"""Email -> vault: each new email in a user's "Family Wiki" Gmail label becomes a raw/ source.

mbsync (as its own user, e.g. wikimail) downloads only that label into a
Maildir and never changes anything in Gmail. wikiglue reads the Maildir here: it
never sees the mail password or the rest of the mailbox. For each email it hasn't
handled yet it writes

    raw/YYYY/MM/<slug>/source.md    subject, sender, date and the text (HTML -> Markdown)
    raw/YYYY/MM/<slug>/meta.json    title, added_by, added_at, kind "email", from, date
    raw/YYYY/MM/<slug>/<image>      photo attachments (not small logos and icons)

and queues an ingest, like a Karakeep bookmark (inbox.py). PDF attachments are saved
to Karakeep as the user, like a PDF sent in chat: Karakeep's worker extracts their
text, and they come back through the Karakeep inbox as sources of their own.
Calendar invites (.ics) and text attachments (.txt, .csv, .md, .json, .html) are added
to source.md as text, and so are documents (.docx, .odt, .rtf, .epub), converted to
Markdown by pandoc: run with --sandbox (it can read only its input), a timeout and a
memory cap, since the attachment is untrusted. Spreadsheets, slides and other files
are listed but not kept.

A shared address ([mailboxes.<name>] in wikiglue.toml, e.g. familywiki@example.org) works
the same way, except that anyone can send to it. An email there counts only if it's
from an address a family member listed (users.<key>.emails), who is then its
"added by", and only if the receiving mail server's Authentication-Results header
says that address's domain vouched for it (DMARC, or a DKIM signature by that
domain): a From line alone is easy to forge. Other emails are logged and skipped.

Emails already in a Maildir the first time it's read are recorded and skipped: only
emails that arrive after setup are ingested. A Maildir that appears while wikiglue runs
(a label created after setup) is new, so everything in it is ingested.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import mailbox
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path

import aiohttp
import html2text

from .config import Config, Mailbox, User
from .inbox import new_raw_dir, queue_ingest, slugify, write_parts
from .jobs import Jobs
from .karakeep import MAX_CONTENT_CHARS, Karakeep, KarakeepError, strip_inline_data
from .state import State

log = logging.getLogger(__name__)

POLL_SECONDS = 30
MIN_IMAGE_BYTES = 20_000      # smaller images are logos, icons and tracking pixels
MAX_CALENDAR_CHARS = 5_000
MAX_ATTACHMENT_BYTES = 10_000_000   # larger documents aren't converted
PANDOC_SECONDS = 30
# Attachments pandoc turns into Markdown, by extension and by MIME type.
PANDOC_FORMATS = {
    ".docx": "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    ".odt": "odt", "application/vnd.oasis.opendocument.text": "odt",
    ".rtf": "rtf", "application/rtf": "rtf", "text/rtf": "rtf",
    ".epub": "epub", "application/epub+zip": "epub",
}
TEXT_TYPES = {".txt": "text/plain", ".csv": "text/csv", ".md": "text/markdown",
              ".json": "application/json", ".html": "text/html", ".htm": "text/html"}
# Zero-width and soft-hyphen characters that marketing emails pad their previews with.
INVISIBLE = re.compile("[­͏​-‏⁠﻿]")
REPLY_PREFIX = re.compile(r"^\s*((re|fwd?|fw)\s*:\s*)+", re.I)


@dataclass
class Email:
    subject: str
    sender: str
    to: str
    cc: str
    date: str
    body: str
    images: list[tuple[str, bytes]] = field(default_factory=list)
    pdfs: list[tuple[str, bytes]] = field(default_factory=list)
    calendars: list[tuple[str, str]] = field(default_factory=list)
    documents: list[tuple[str, str]] = field(default_factory=list)   # (file name, text)
    not_kept: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return REPLY_PREFIX.sub("", self.subject).strip() or self.subject

    def text(self) -> str:
        """The body, then each document and calendar invite under its own heading."""
        out = [self.body or "(no text)"]
        for name, text in self.documents:
            out += [f"## Attachment: {name}", text or "(empty)"]
        for name, text in self.calendars:
            out += [f"## Calendar invite: {name}", f"```\n{text.strip()}\n```"]
        return "\n\n".join(out)[:MAX_CONTENT_CHARS]


def html_to_markdown(html: str) -> str:
    h = html2text.HTML2Text()
    h.body_width = 0          # no hard wrapping
    h.unicode_snob = True     # keep ¥, ½, accents (by default it turns them into ASCII)
    h.ignore_images = True    # attachments are handled separately; inline ones are logos
    h.ignore_links = True     # email links are mostly tracking redirects
    text = h.handle(html).replace("\u00a0", " ")
    return "\n".join(_flatten_row(line) for line in text.splitlines())


def _flatten_row(line: str) -> str:
    """Emails lay out with tables, which come out as rows like "| | | **Name** Account: 2009|"
    and "---|---". Keep each row's non-empty cells, joined by " | "; drop rows with none."""
    line = re.sub(r"(?<=\S)[ \t]{2,}", " ", line)   # cells padded with non-breaking spaces
    if re.fullmatch(r"\s*:?-{3,}:?\s*", line):        # a one-column table's rule (html2text
        return ""                                      # writes real rules as "* * *")
    if "|" not in line:
        return line
    cells = [c.strip() for c in line.split("|")]
    cells = [c for c in cells if c and not re.fullmatch(r":?-+:?", c)]
    return " | ".join(cells)


def clean(text: str) -> str:
    text = strip_inline_data(INVISIBLE.sub("", text))
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _text(part: EmailMessage) -> str:
    try:
        return part.get_content()
    except (LookupError, ValueError):  # unknown or wrong charset
        return (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")


def pandoc(data: bytes, fmt: str) -> str:
    """Markdown for a document, or raise ValueError saying why it couldn't be read."""
    if not shutil.which("pandoc"):
        raise ValueError("pandoc isn't installed")
    try:
        r = subprocess.run(["pandoc", "--sandbox", "-f", fmt, "-t", "gfm", "--wrap=none",
                            "+RTS", "-M512m", "-RTS"],
                           input=data, capture_output=True, timeout=PANDOC_SECONDS)
    except subprocess.TimeoutExpired:
        raise ValueError("took too long to read") from None
    if r.returncode != 0:
        raise ValueError("couldn't be read")
    return clean(r.stdout.decode("utf-8", errors="replace"))


def _file_name(name: str, ext: str, taken: set[str]) -> str:
    stem = slugify(Path(name).stem, 40)
    out, n = f"{stem}{ext}", 2
    while out in taken:
        out, n = f"{stem}-{n}{ext}", n + 1
    taken.add(out)
    return out


def parse(data: bytes) -> Email:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    subject = " ".join(str(msg.get("Subject") or "").split()) or "(no subject)"
    body = ""
    part = msg.get_body(preferencelist=("html", "plain"))
    if part is not None:
        text = _text(part)
        body = html_to_markdown(text) if part.get_content_type() == "text/html" else text
    email = Email(subject, str(msg.get("From") or ""), str(msg.get("To") or ""), str(msg.get("Cc") or ""),
                  str(msg.get("Date") or ""), clean(body)[:MAX_CONTENT_CHARS])
    taken: set[str] = set()
    for att in msg.iter_attachments():
        ctype = att.get_content_type()
        name = att.get_filename() or ctype.replace("/", ".")
        if ctype == "message/rfc822":
            email.not_kept.append(f"{name} (a forwarded email)")
            continue
        payload = att.get_payload(decode=True) or b""
        if ctype == "application/pdf" or name.lower().endswith(".pdf"):
            email.pdfs.append((_file_name(name, ".pdf", taken), payload))
        elif ctype.startswith("image/"):
            if len(payload) >= MIN_IMAGE_BYTES:
                ext = Path(name).suffix.lower() or "." + ctype.split("/")[1]
                email.images.append((_file_name(name, ext, taken), payload))
        elif ctype == "text/calendar" or name.lower().endswith(".ics"):
            email.calendars.append((name, _text(att)[:MAX_CALENDAR_CHARS]))
        elif (ext := Path(name).suffix.lower()) in TEXT_TYPES or ctype in TEXT_TYPES.values():
            text = _text(att)
            is_html = ctype == "text/html" or TEXT_TYPES.get(ext) == "text/html"
            email.documents.append((name, clean(html_to_markdown(text) if is_html else text)))
        elif fmt := PANDOC_FORMATS.get(ext) or PANDOC_FORMATS.get(ctype):
            if len(payload) > MAX_ATTACHMENT_BYTES:
                email.not_kept.append(f"{name} (over {MAX_ATTACHMENT_BYTES // 1_000_000} MB)")
                continue
            try:
                email.documents.append((name, pandoc(payload, fmt)))
            except ValueError as e:
                email.not_kept.append(f"{name} ({e})")
        else:
            email.not_kept.append(name)
    return email


@dataclass(frozen=True)
class Source:
    """A Maildir to read: one person's "Family Wiki" label, or a shared address."""
    key: str                  # for wikiglue's state: the user's key, or the mailbox's
    maildir: Path
    how: str                  # for source.md: 'labelled "Family Wiki" in Gmail'
    user: User | None         # the label's owner; None: the (verified) sender decides
    auth_server: str = ""

    @classmethod
    def label(cls, user: User) -> "Source":
        # The Maildir folder is named after the label ("Family Wiki", "Work Wiki").
        return cls(user.key, user.maildir, f'labelled "{user.maildir.name}" in Gmail', user)

    @classmethod
    def shared(cls, box: Mailbox) -> "Source":
        return cls(box.key, box.maildir, f"sent to {box.address}", None, box.auth_server)


def verified_sender(data: bytes, auth_server: str) -> tuple[str, str | None]:
    """(From address, None) when the receiving server's Authentication-Results says the
    From domain passed DMARC or signed it with DKIM; else (address, why not)."""
    msg = BytesParser(policy=policy.default).parsebytes(data, headersonly=True)
    addrs = [a for _, a in getaddresses([str(msg.get("From") or "")]) if "@" in a]
    if len(addrs) != 1:
        return "", "it has no single From address"
    addr = addrs[0].lower()
    domain = addr.rsplit("@", 1)[1]
    # The receiving server adds its result on top; a sender can add fake ones below it.
    ours = next((str(h) for h in msg.get_all("Authentication-Results") or []
                 if str(h).split(";", 1)[0].strip().lower() == auth_server.lower()), None)
    if ours is None:
        return addr, f"it has no Authentication-Results from {auth_server}"
    def host(value: str) -> str:   # "gmail.com", "@gmail.com" or "<x@gmail.com>" -> "gmail.com"
        return value.strip("<>").rsplit("@", 1)[-1].lower()

    for m in re.finditer(r"\bdmarc=pass\b([^;]*)", ours, re.I):
        frm = re.search(r"header\.from=(\S+)", m.group(1), re.I)
        if not frm or host(frm.group(1)) == domain:
            return addr, None
    for m in re.finditer(r"\bdkim=pass\b[^;]*?header\.[di]=(\S+)", ours, re.I):
        d = host(m.group(1))
        if domain == d or domain.endswith("." + d):
            return addr, None
    return addr, f"{domain} didn't vouch for it (no DMARC or DKIM pass)"


def render(email: Email, user: User, how: str, pdf_note: str | None) -> str:
    lines = [f"# {email.title}", "",
             f"An email {how}, added by {user.name} on {dt.date.today().isoformat()}.", ""]
    for label, value in (("From", email.sender), ("To", email.to), ("Cc", email.cc), ("Date", email.date)):
        if value:
            lines.append(f"{label}: {value}  ")   # two spaces: a line break in Markdown
    if email.pdfs:
        lines.append(f"PDF attachments: {', '.join(n for n, _ in email.pdfs)} ({pdf_note}).")
    if email.images:
        lines.append(f"Photos attached: {', '.join(n for n, _ in email.images)} (below).")
    if email.documents:
        lines.append(f"Attachments included as text below: {', '.join(n for n, _ in email.documents)}.")
    if email.not_kept:
        lines.append(f"Other attachments, not kept: {', '.join(email.not_kept)}.")
    lines += ["", "---", "", email.text()]
    for name, _ in email.images:
        lines += ["", f"![[{name}]]"]
    return "\n".join(lines) + "\n"


class MailInbox:
    def __init__(self, config: Config, state: State, jobs: Jobs, session: aiohttp.ClientSession):
        self.config, self.state, self.jobs, self.session = config, state, jobs, session
        self.missing: set[str] = set()   # sources whose Maildir isn't there yet (logged once)

    def sources(self) -> list[Source]:
        return ([Source.label(u) for u in self.config.users if u.maildir]
                + [Source.shared(m) for m in self.config.mailboxes])

    async def run(self) -> None:
        sources = self.sources()
        if not sources:
            log.info("mail: no maildir or mailbox configured; not reading email")
            return
        while True:
            for source in sources:
                try:
                    await self.poll(source)
                except Exception:
                    log.exception("mail: reading %s failed", source.key)
            await asyncio.sleep(POLL_SECONDS)

    def sender(self, source: Source, data: bytes) -> tuple[User | None, str]:
        """Who an email counts as added by; (None, why) if it doesn't count."""
        if source.user:
            return source.user, ""
        addr, problem = verified_sender(data, source.auth_server)
        user = next((u for u in self.config.users if addr and addr in u.emails), None)
        if user is None:
            return None, f"{addr or 'an unknown sender'} isn't a family member's address"
        if problem:
            return None, f"{problem}, though it says it's from {user.name} ({addr})"
        return user, ""

    async def poll(self, source: Source) -> None:
        if not (source.maildir / "cur").is_dir():
            if source.key not in self.missing:
                log.warning("mail: no Maildir for %s yet (%s); has mbsync run?", source.key, source.maildir)
                self.missing.add(source.key)
            return
        appeared = source.key in self.missing   # created since we started: all of it is new
        self.missing.discard(source.key)
        box = mailbox.Maildir(source.maildir, factory=None, create=False)
        keys = sorted(box.keys())   # Maildir keys start with the delivery time
        baseline = f"mail_baseline:{source.key}"
        first_time = self.state.get(baseline) is None and not appeared
        for key in keys:
            with box.get_file(key) as f:
                data = f.read()
            mail_id = f"{source.key}:{self._message_id(data) or key}"
            if self.state.mail_status(mail_id) is not None:
                continue
            if first_time:
                self.state.set_mail(mail_id, source.key, "skipped")
                continue
            user, why = self.sender(source, data)
            if user is None:
                log.warning("mail: %s: skipped an email: %s", source.key, why)
                self.state.set_mail(mail_id, source.key, "rejected")
                continue
            try:
                raw_dir, parts = await self.write(user, source, data)
            except Exception:
                log.exception("mail: couldn't write %s's email %s", source.key, key)
                self.state.set_mail(mail_id, source.key, "failed")
                continue
            self.state.set_mail(mail_id, source.key, "written", raw_dir)
            queue_ingest(self.jobs, raw_dir, parts, user.key)
            log.info("mail: %s: %s's email -> %s, ingest queued", source.key, user.key, raw_dir)
        if first_time:
            self.state.put(baseline, dt.datetime.now().isoformat(timespec="seconds"))
            log.info("mail: %s: %d email(s) there before setup; skipped", source.key, len(keys))
        elif appeared and self.state.get(baseline) is None:
            self.state.put(baseline, dt.datetime.now().isoformat(timespec="seconds"))

    @staticmethod
    def _message_id(data: bytes) -> str:
        head = data.split(b"\r\n\r\n", 1)[0].split(b"\n\n", 1)[0]
        m = re.search(rb"^message-id:\s*(\S+)", head, re.I | re.M)
        return m.group(1).decode("ascii", errors="replace") if m else ""

    async def write(self, user: User, source: Source, data: bytes) -> tuple[str, int]:
        """Write the raw folder; returns (vault-relative folder, number of parts)."""
        email = await asyncio.to_thread(parse, data)
        pdf_note = await self.save_pdfs(user, email) if email.pdfs else None
        folder = new_raw_dir(self.config.vault, email.title)
        for name, payload in email.images:
            (folder / name).write_bytes(payload)
        (folder / "source.md").write_text(render(email, user, source.how, pdf_note), encoding="utf-8")
        parts = write_parts(folder, email.title, email.text())
        meta = {
            "title": email.title,
            "url": None,
            "added_by": user.name,
            "added_at": dt.date.today().isoformat(),
            "kind": "email",
            "from": email.sender,
            "to": email.to,
            "date": email.date,
            "via": source.how,
        }
        if parts > 1:
            meta["parts"] = parts
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
        return str(folder.relative_to(self.config.vault)), parts

    async def save_pdfs(self, user: User, email: Email) -> str:
        """Save PDF attachments to Karakeep as the user; returns a note for source.md."""
        if not (self.config.karakeep_url and user.karakeep_key):
            return "not added: no Karakeep key for this person"
        kk = Karakeep(self.session, self.config.karakeep_url, user.karakeep_key)
        note = f'Attachment of the email "{email.title}" from {email.sender}'
        try:
            for name, payload in email.pdfs:
                await kk.add_file(payload, name, "application/pdf", note=note)
        except (aiohttp.ClientError, KarakeepError) as e:
            log.warning("mail: couldn't save a PDF attachment to Karakeep: %s", e)
            return "couldn't be added to the wiki"
        return "added to the wiki as sources of their own"
