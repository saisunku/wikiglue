"""Inbox, jobs, approvals and result posting, with fake Karakeep and Matrix."""

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from wikiglue import app
from wikiglue.approvals import ResearchRequests
from wikiglue.commands import Attachment, Dispatcher, React, Services
from wikiglue.config import Config, User
from wikiglue.inbox import Inbox, describe, is_ready, render_source, scan_pages, slugify
from wikiglue.jobs import Jobs
from wikiglue.karakeep import Asset
from wikiglue.state import State

ALEX = User("alex", "Alex", "admin", "@alex:x", karakeep_key="k-alex")
KID = User("kid", "Kid", "member", "@kid:x", karakeep_key="k-kid")
NOKEY = User("gran", "Gran", "member", "@gran:x")

COMMANDS = """
announce = ["shopping", "digest"]
[commands."?"]
prefix = "?"
action = "task"
task = "_tasks/query.md"
reply = "result"
[commands.trip]
action = "task"
task = "_tasks/trip.md"
format = "{text} ({sender}, {date})"
[commands.approve]
prefix = "approve "
action = "builtin"
roles = ["admin"]
[commands.requests]
prefix = "requests"
action = "builtin"
[commands.announce]
prefix = "announce"
action = "builtin"
roles = ["admin"]
[commands.queue]
prefix = "queue"
action = "builtin"
[default]
action = "bookmark"
"""


class FakeKarakeep:
    def __init__(self):
        self.created = []
        self.bookmarks = []

    async def add_link(self, url, note=None):
        self.created.append(("link", url, note))
        return {"id": f"bm{len(self.created)}"}

    async def add_text(self, text):
        self.created.append(("text", text, None))
        return {"id": f"bm{len(self.created)}"}

    async def add_file(self, data, filename, content_type, note=None):
        self.created.append(("file", filename, note))
        return {"id": f"bm{len(self.created)}"}

    async def recent_bookmarks(self, limit=50, cursor=None):
        return list(reversed(self.bookmarks)), None

    async def readable_content(self, bookmark_id):
        return "Body text of the article.", False

    async def asset(self, asset_id):
        if asset_id == "archive1":
            return Asset(PAGE_ARCHIVE.encode(), "text/html")
        return Asset(b"\xff\xd8jpeg", "image/jpeg")


PAGE_ARCHIVE = """<html><body><article><p>Body text of the article.</p></article>
<aside><dl class="summary"><dt>Exercise</dt><dd>Up to 1 hour per day</dd>
<dt>Lifespan</dt><dd>Over 12 years</dd></dl></aside></body></html>"""


class FakeServices(Services):
    def __init__(self, jobs, state, kk):
        super().__init__(jobs, state, session=None, karakeep_url="http://kk")
        self.kk = kk

    def karakeep(self, user):
        return self.kk if user.karakeep_key else None


class FakeTransport:
    def __init__(self):
        self.sent = []

    async def send(self, room_id, text, reply_to=None):
        self.sent.append((room_id, text, reply_to))


@pytest.fixture
def env(tmp_path):
    vault = tmp_path / "vault"
    (vault / "_config").mkdir(parents=True)
    (vault / "_config" / "commands.toml").write_text(COMMANDS)
    (vault / "_review").mkdir()
    jobs_dir = tmp_path / "jobs"
    (jobs_dir / "queue").mkdir(parents=True)
    (jobs_dir / "done").mkdir()
    state = State(tmp_path / "glue.db")
    jobs = Jobs(jobs_dir)
    kk = FakeKarakeep()
    d = Dispatcher(vault, vault / "_config" / "commands.toml", FakeServices(jobs, state, kk))
    config = Config(vault=vault, state_dir=tmp_path, matrix=None, users=(ALEX, KID),
                    jobs_dir=jobs_dir, karakeep_url="http://kk")
    return {"vault": vault, "jobs_dir": jobs_dir, "state": state, "jobs": jobs, "kk": kk,
            "d": d, "config": config}


def queued(env):
    return [json.loads(p.read_text()) for p in sorted((env["jobs_dir"] / "queue").glob("*.job"))]


# --- chat -> Karakeep -------------------------------------------------------

async def test_link_message_becomes_link_bookmark_with_note(env):
    reply = await env["d"].handle(ALEX, "https://example.com/a  great read", room_id="!r", event_id="$e")
    assert isinstance(reply, React)
    assert env["kk"].created == [("link", "https://example.com/a", "great read")]
    assert env["state"].get_notify("bm1") == ("!r", "$e")


async def test_plain_text_becomes_text_bookmark(env):
    await env["d"].handle(KID, "Grandma's tip: rest the dough overnight")
    assert env["kk"].created == [("text", "Grandma's tip: rest the dough overnight", None)]


async def test_photo_with_caption(env):
    att = Attachment(b"jpg", "IMG_1.jpg", "image/jpeg")
    await env["d"].handle(ALEX, "our loaf", attachment=att)
    assert env["kk"].created == [("file", "IMG_1.jpg", "our loaf")]


async def test_user_without_karakeep_key(env):
    assert "isn't set up for you" in await env["d"].handle(NOKEY, "https://example.com")


# --- chat -> job queue ------------------------------------------------------

async def test_question_queues_interactive_job(env):
    reply = await env["d"].handle(KID, "? how long to proof", room_id="!r", event_id="$e")
    assert isinstance(reply, React)
    [job] = queued(env)
    assert job["task"] == "query" and job["input"] == "how long to proof"
    assert job["priority"] == "chat" and job["submitted_by"] == "wikiglue:kid"
    assert job["meta"] == {"room": "!r", "event": "$e", "reply": "result"}


async def test_task_input_format(env):
    await env["d"].handle(KID, "trip: day 3, Nishiki market")
    [job] = queued(env)
    assert job["task"] == "trip"
    assert job["input"] == f"day 3, Nishiki market (Kid, {dt.date.today().isoformat()})"


# --- Karakeep -> raw/ -------------------------------------------------------

def test_screenshot_title_skips_ocr_noise():
    ocr = "2:09 wil = @»\n&\nCREE EE 5, ea,\nsR a Rs i Wa\n4 ¢ “ 2 x 3 Fatt bl\nHome in Bend\nHosted by Christian"
    bm = {"content": {"type": "asset", "assetType": "image", "fileName": "Screenshot 2026-10-28 at 2.09.42 PM.png",
                      "content": ocr}}
    assert describe(bm) == ("image", "Home in Bend", None)
    # Typed notes keep their first line, short words and all.
    assert describe({"content": {"type": "text", "text": "Go to Rome\nin May"}})[1] == "Go to Rome"


def test_describe_and_slugify():
    link = {"title": None, "content": {"type": "link", "url": "https://x.org/p", "title": "Proofing 101"}}
    assert describe(link) == ("link", "Proofing 101", "https://x.org/p")
    img = {"content": {"type": "asset", "assetType": "image", "assetId": "a", "fileName": "IMG_2.jpg"}}
    assert describe(img)[:2] == ("image", "IMG_2.jpg")
    assert slugify("Ünïcode & Spaces: A Title!") == "unicode-spaces-a-title"
    shot = {"content": {"type": "asset", "assetType": "image", "assetId": "a", "fileName": "IMG_7.png",
                        "content": "a2\nLAKESIDE | Alumni\nSpringfield\nOctober Networking Event"}}
    assert describe(shot)[1] == "LAKESIDE | Alumni"
    named = {"content": {"type": "asset", "assetType": "pdf", "assetId": "a", "fileName": "lease.pdf"}}
    assert describe(named)[1] == "lease.pdf"


async def test_inbox_writes_raw_folder_and_queues_ingest(env, monkeypatch):
    monkeypatch.setattr("wikiglue.inbox.ARCHIVE_WAIT_SECONDS", -1)  # these links have no archive
    env["kk"].bookmarks = [
        {"id": "b1", "title": None, "note": "for the bread page",
         "content": {"type": "link", "url": "https://x.org/proof", "title": "Proofing 101",
                     "crawlStatus": "success", "author": "A. Baker"}},
        {"id": "b2", "content": {"type": "link", "url": "https://x.org/slow", "crawlStatus": "pending"}},
        {"id": "b3", "content": {"type": "asset", "assetType": "image", "assetId": "a1",
                                 "fileName": "IMG_9.jpg"}},
    ]
    inbox = Inbox(env["config"], env["state"], env["jobs"], session=None)
    inbox.client = lambda user: env["kk"]
    await inbox.poll(ALEX)

    jobs = queued(env)
    assert [j["meta"]["bookmark"] for j in jobs] == ["b1", "b3"]  # b2 still crawling
    folder = env["vault"] / jobs[0]["input"]
    assert folder.parent.parent.parent.name == "raw" and folder.name.endswith("proofing-101")
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["added_by"] == "Alex" and meta["url"] == "https://x.org/proof" and meta["kind"] == "link"
    src = (folder / "source.md").read_text()
    assert "Note from Alex: for the bread page" in src and "Author: A. Baker" in src
    assert "Body text of the article." in src
    image_folder = env["vault"] / jobs[1]["input"]
    assert (image_folder / "image.jpg").read_bytes() == b"\xff\xd8jpeg"
    assert "![[image.jpg]]" in (image_folder / "source.md").read_text()

    # Second poll: nothing new is written; b2 is written once its crawl finishes.
    await inbox.poll(ALEX)
    assert len(queued(env)) == 2
    env["kk"].bookmarks[1]["content"]["crawlStatus"] = "success"
    await inbox.poll(ALEX)
    assert [j["meta"]["bookmark"] for j in queued(env)][-1] == "b2"


# --- research approvals -----------------------------------------------------

REQUESTS = """# Research requests

- [x] Done one — approved 2026-10-01, fetching https://a.org
- [ ] Baguette proofing — source: https://en.wikipedia.org/wiki/Baguette — suggested search: "baguette proof" (lint 2026-10-25)
- [ ] Rye ratios — suggested search: "rye sourdough hydration" (from a question asked 2026-10-25)
"""


async def test_requests_list_and_approve_with_link(env):
    (env["vault"] / "_review" / "research-requests.md").write_text(REQUESTS)
    listing = await env["d"].handle(ALEX, "requests")
    assert listing.startswith("1. Baguette proofing (https://en.wikipedia.org/wiki/Baguette)")
    assert "2. Rye ratios" in listing

    reply = await env["d"].handle(ALEX, "approve 1", room_id="!r", event_id="$e")
    assert "fetching https://en.wikipedia.org/wiki/Baguette" in reply
    assert env["kk"].created == [("link", "https://en.wikipedia.org/wiki/Baguette",
                                  "Research request: Baguette proofing")]
    text = (env["vault"] / "_review" / "research-requests.md").read_text()
    assert "- [x] Baguette proofing" in text and "— approved " in text
    # Now "Rye ratios" is number 1.
    assert (await env["d"].handle(ALEX, "requests")).startswith("1. Rye ratios")


async def test_approve_without_link_returns_search(env):
    (env["vault"] / "_review" / "research-requests.md").write_text(REQUESTS)
    reply = await env["d"].handle(ALEX, "approve 2")
    assert "duckduckgo.com/?q=rye+sourdough+hydration" in reply
    assert env["kk"].created == []


async def test_member_cannot_approve(env):
    (env["vault"] / "_review" / "research-requests.md").write_text(REQUESTS)
    assert "isn't available" in await env["d"].handle(KID, "approve 1")


async def test_obsidian_tick_is_picked_up(env):
    path = env["vault"] / "_review" / "research-requests.md"
    path.write_text(REQUESTS.replace("- [ ] Baguette", "- [x] Baguette"))
    messages = await env["d"].research_ticked(ALEX)
    assert len(messages) == 1 and "fetching" in messages[0]
    assert await env["d"].research_ticked(ALEX) == []  # handled once
    assert ResearchRequests(env["vault"]).open_requests()[0].title == "Rye ratios"


# --- results -> chat --------------------------------------------------------

async def test_results_are_posted_once(env):
    t = FakeTransport()
    env["state"].add_notify("bm7", "!r2", "$e2")
    env["state"].put("announce_room", "!announce")
    done = env["jobs_dir"] / "done"
    results = [
        {"id": "j1", "task": "query", "status": "ok", "reply": "42 [[topics/x]]",
         "meta": {"room": "!r", "event": "$e", "reply": "result"}},
        {"id": "j2", "task": "ingest", "status": "ok", "reply": "Created sources/x.md",
         "meta": {"bookmark": "bm7"}},
        {"id": "j3", "task": "shopping", "status": "ok", "reply": "Produce:\n- eggs"},
        {"id": "j4", "task": "lint", "status": "ok", "reply": "clean"},
        {"id": "j5", "task": "query", "status": "timeout", "reply": "",
         "meta": {"room": "!r", "event": "$f", "reply": "result"}},
        {"id": "j6", "task": "ingest", "status": "ok", "meta": {"user": "alex"},   # emailed in
         "reply": "- sources/y.md — created\n**Question: which year is the 1 Aug flight "
                  "(sources/y)? Answer with \"trip: <year> for sources/y\"**"},
        {"id": "j7", "task": "ingest", "status": "ok", "reply": "- sources/z.md — created"},
    ]
    for r in results:
        (done / f"{r['id']}.json").write_text(json.dumps(r))
    for r in env["jobs"].results():
        await app.post_result(r, env["state"], env["d"], t)
    assert t.sent == [
        ("!r", "42 [[topics/x]]", "$e"),
        ("!r2", "Added to the wiki:\nCreated sources/x.md", "$e2"),
        ("!announce", "Produce:\n- eggs", None),
        ("!r", "Sorry, that didn't work (timeout).", "$f"),
        ("!announce", 'Question: which year is the 1 Aug flight (sources/y)? '
                      'Answer with "trip: <year> for sources/y"', None),
    ]
    assert env["state"].get_notify("bm7") is None


async def test_announce_command_sets_room(env):
    await env["d"].handle(ALEX, "announce", room_id="!fam")
    assert env["state"].get("announce_room") == "!fam"


# --- queue status -----------------------------------------------------------

async def test_queue_command(env):
    assert "Can't see" in await env["d"].handle(KID, "queue")
    (env["jobs_dir"] / "status.json").write_text(json.dumps({
        "running": {"task": "ingest", "input": "raw/2026/10/2026-10-rye-bread",
                    "started": "2026-10-25T23:05:51-07:00"},
        "paused": [{"task": "lint", "input": ""}],
        "waiting": [{"task": "ingest", "input": "raw/2026/10/2026-10-untitled"},
                    {"task": "query", "input": "how long to proof"}],
    }))
    reply = await env["d"].handle(KID, "queue")
    assert reply.startswith("Running: ingest 2026-10-rye-bread (")
    assert "Paused: lint" in reply
    assert "Waiting (2): ingest 2026-10-untitled, query how long to proof" in reply
    (env["jobs_dir"] / "status.json").write_text(json.dumps({"running": None, "paused": [], "waiting": []}))
    assert (await env["d"].handle(KID, "queue")).startswith("Idle")


# --- questions by default -----------------------------------------------------

async def test_plain_text_is_a_question_but_links_are_saved(env):
    path = env["vault"] / "_config" / "commands.toml"
    path.write_text(COMMANDS.replace('[default]\naction = "bookmark"',
                                     '[commands.note]\naction = "bookmark"\n'
                                     '[default]\naction = "task"\ntask = "_tasks/query.md"\nreply = "result"'))
    await env["d"].handle(ALEX, "what do you know about rye bread", room_id="!r", event_id="$e")
    [job] = queued(env)
    assert job["task"] == "query" and job["input"] == "what do you know about rye bread"
    await env["d"].handle(ALEX, "https://example.com/rye  for the bread page")
    await env["d"].handle(ALEX, "note: rest the dough overnight")
    assert env["kk"].created == [("link", "https://example.com/rye", "for the bread page"),
                                 ("text", "rest the dough overnight", None)]
    assert len(queued(env)) == 1


async def test_inbox_adds_page_details_from_archive(env):
    env["kk"].bookmarks = [
        {"id": "b1", "assets": [{"id": "shot", "assetType": "screenshot"},
                                {"id": "archive1", "assetType": "fullPageArchive"}],
         "content": {"type": "link", "url": "https://x.org/dog", "title": "Dachshund",
                     "crawlStatus": "success"}},
    ]
    inbox = Inbox(env["config"], env["state"], env["jobs"], session=None)
    inbox.client = lambda user: env["kk"]
    await inbox.poll(ALEX)
    src = (env["vault"] / queued(env)[0]["input"] / "source.md").read_text()
    details = src.index("## Details from the page")
    assert details < src.index("Body text of the article.")
    assert "- **Exercise:** Up to 1 hour per day" in src and "- **Lifespan:** Over 12 years" in src


def test_crawled_link_waits_for_its_archive(monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr("wikiglue.inbox.time.time", lambda: now)
    bm = {"content": {"type": "link", "crawlStatus": "success"}}
    assert not is_ready(bm, now - 60)
    assert is_ready(bm, now - 200)                       # gave up waiting: ingest without it
    bm["assets"] = [{"id": "a", "assetType": "fullPageArchive"}]
    assert is_ready(bm, now - 1)
    assert is_ready({"content": {"type": "link", "crawlStatus": "failure"}}, now)
    assert not is_ready({"content": {"type": "link", "crawlStatus": "pending"}}, now - 60)


# --- Karakeep content -------------------------------------------------------

async def test_readable_content_strips_inline_images(monkeypatch):
    from wikiglue import karakeep
    png = "data:image/png;base64," + "iVBORw0KGgo" * 3000
    chunks = [{"content": "Intro.\n\n![Trail map](" + png[:20000], "nextCursor": "c1"},
              {"content": png[20000:] + ")\n\nPets are not allowed. ![](" + png + ")\n\nEnd.", "nextCursor": None}]
    kk = karakeep.Karakeep(None, "http://x", "k")

    async def fake_json(method, path, params=None):
        return chunks.pop(0)
    monkeypatch.setattr(kk, "_json", fake_json)
    text, truncated = await kk.readable_content("bm1")
    assert text == "Intro.\n\n[image: Trail map]\n\nPets are not allowed. \n\nEnd."
    assert truncated is False


def test_strip_inline_data_cut_off_mid_image():
    from wikiglue.karakeep import strip_inline_data
    assert strip_inline_data("Text.\n\n![](data:image/png;base64,AAAA") == "Text.\n\n"


# Two blank pages and no text layer, like a scan; poppler rebuilds the missing xref table.
SCAN_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]>>endobj\n"
            b"4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs poppler-utils")
def test_scanned_pdf_pages_become_images(tmp_path, monkeypatch):
    monkeypatch.setattr("wikiglue.inbox.SCAN_PAGES", 1)
    (tmp_path / "scan.pdf").write_bytes(SCAN_PDF)
    pages = scan_pages(tmp_path / "scan.pdf")
    assert pages == (["page-1.jpg"], 2)
    src = render_source({}, ALEX, "pdf", "Scan", None, "", False, "scan.pdf", pages)
    assert "![[page-1.jpg]]" in src and "(Only the first 1 of 2 pages are shown.)" in src


def test_came_from(env):
    inbox = Inbox(env["config"], env["state"], env["jobs"], session=None)
    env["state"].add_notify("b-chat", "!room", "$event")
    assert inbox.came_from({"id": "b-chat", "source": "api"}) == "chat"
    assert inbox.came_from({"id": "b-r", "source": "api", "note": "Research request: rye"}) == "research approval"
    assert inbox.came_from({"id": "b-mail", "source": "api", "note": "From an email"}) == "email PDF"
    assert inbox.came_from({"id": "b-app", "source": "mobile"}) == "karakeep app"
    assert inbox.came_from({"id": "b-ext", "source": "extension"}) == "browser extension"
    assert inbox.came_from({"id": "b-old"}) == "karakeep"
