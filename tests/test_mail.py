"""Emails in a user's "Family Wiki" Maildir -> raw/ sources and ingest jobs."""

import json
import mailbox
import shutil
import subprocess
from email.message import EmailMessage
from pathlib import Path

import pytest

from wikiglue import mail
from wikiglue.config import Config, Mailbox, User
from wikiglue.jobs import Jobs
from wikiglue.mail import MailInbox, Source, parse, verified_sender
from wikiglue.state import State

BOOKING_HTML = """<html><body>
<div style="display:none">Your stay is confirmed&#847;&zwnj;&#847;&zwnj;</div>
<table><tr><td><img src="https://track.example/logo.png"></td></tr>
<tr><td><h1>Your stay at Home in Bend is confirmed</h1>
<p>Check-in <b>Sat, Dec 5</b> 4:00 PM &middot; Checkout Mon, Dec 7 11:00 AM</p>
<p><a href="https://track.example/r?u=abc">Manage booking</a></p>
<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"></td></tr></table>
</body></html>"""


def email(subject: str, msg_id: str, html: str | None = None, text: str = "Plain text.",
          attachments: tuple = ()) -> bytes:
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subject, "Airbnb <automated@airbnb.com>", "alex@example.com"
    m["Date"], m["Message-ID"] = "Wed, 28 Oct 2026 10:00:00 -0700", msg_id
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    for data, maintype, subtype, name in attachments:
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return bytes(m)


class FakeKarakeep:
    files: list = []

    def __init__(self, session, url, key):
        pass

    async def add_file(self, data, filename, content_type, note=None):
        FakeKarakeep.files.append((filename, content_type, len(data), note))
        return {"id": "bm1"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "jobs" / "queue").mkdir(parents=True)
    maildir = tmp_path / "wikimail" / "alex" / "Family Wiki"
    maildir.parent.mkdir(parents=True)
    box = mailbox.Maildir(maildir, create=True)
    user = User("alex", "Alex", "admin", karakeep_key="k", maildir=maildir)
    config = Config(vault=vault, state_dir=tmp_path, matrix=None, users=(user,),
                    jobs_dir=tmp_path / "jobs", karakeep_url="http://kk")
    FakeKarakeep.files = []
    monkeypatch.setattr(mail, "Karakeep", FakeKarakeep)
    inbox = MailInbox(config, State(tmp_path / "glue.db"), Jobs(tmp_path / "jobs"), session=None)
    return {"box": box, "inbox": inbox, "user": user, "vault": vault, "jobs": tmp_path / "jobs" / "queue"}


def queued(env):
    return [json.loads(p.read_text()) for p in sorted(env["jobs"].glob("*.job"))]


async def test_only_emails_labelled_after_setup(env):
    env["box"].add(email("Old newsletter", "<old@x>"))
    await env["inbox"].poll(Source.label(env["user"]))          # first read: the baseline
    assert queued(env) == [] and not (env["vault"] / "raw").exists()

    photo = b"\xff\xd8\xff" + b"x" * 30_000
    env["box"].add(email("Fwd: Reservation confirmed - Home in Bend", "<new@x>", html=BOOKING_HTML,
                         attachments=((photo, "image", "jpeg", "cabin.jpg"),
                                      (b"\x89PNG" + b"x" * 500, "image", "png", "logo.png"),
                                      (b"%PDF-1.4 receipt", "application", "pdf", "Receipt.pdf"),
                                      (b"BEGIN:VCALENDAR\nSUMMARY:Bend\nEND:VCALENDAR", "text", "calendar", "invite.ics"),
                                      (b"PK", "application", "vnd.openxmlformats-officedocument.wordprocessingml.document", "rules.docx"))))
    await env["inbox"].poll(Source.label(env["user"]))
    await env["inbox"].poll(Source.label(env["user"]))          # seen emails aren't written twice

    [job] = queued(env)
    assert job["task"] == "ingest" and job["meta"] == {"user": "alex"}
    folder = env["vault"] / job["input"]
    assert folder.name.endswith("-reservation-confirmed-home-in-bend")
    assert sorted(p.name for p in folder.iterdir()) == ["cabin.jpg", "meta.json", "source.md"]
    src = (folder / "source.md").read_text()
    assert src.startswith("# Reservation confirmed - Home in Bend\n\n"
                          'An email labelled "Family Wiki" in Gmail, added by Alex on ')
    assert ("From: Airbnb <automated@airbnb.com>  \nTo: alex@example.com  \n"
            "Date: Wed, 28 Oct 2026 10:00:00 -0700  \n") in src
    assert "|" not in src.split("---", 1)[1].split("## Calendar")[0]   # no layout-table debris
    assert "Check-in **Sat, Dec 5** 4:00 PM · Checkout Mon, Dec 7 11:00 AM" in src
    assert "track.example" not in src and "data:image" not in src and "‌" not in src
    assert "PDF attachments: receipt.pdf (added to the wiki as sources of their own)." in src
    assert "Other attachments, not kept: rules.docx (couldn't be read)." in src
    assert "## Calendar invite: invite.ics" in src and "SUMMARY:Bend" in src
    assert src.rstrip().endswith("![[cabin.jpg]]")
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["kind"] == "email" and meta["added_by"] == "Alex" and meta["url"] is None
    assert FakeKarakeep.files == [("receipt.pdf", "application/pdf", 16,
                                   'Attachment of the email "Reservation confirmed - Home in Bend" '
                                   "from Airbnb <automated@airbnb.com>")]


async def test_missing_maildir_waits(env, tmp_path):
    user = User("robin", "Robin", "member", maildir=tmp_path / "nowhere")
    await env["inbox"].poll(Source.label(user))
    await env["inbox"].poll(Source.label(user))
    assert env["inbox"].missing == {"robin"}


def test_plain_text_email_and_bad_charset():
    raw = (b"Subject: Note\r\nFrom: me\r\nContent-Type: text/plain; charset=bogus-8\r\n\r\n"
           b"Pack the \xe9 adapters\r\n")
    e = parse(raw)
    assert e.title == "Note" and e.body == "Pack the � adapters"


@pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc not installed")
def test_documents_become_text(tmp_path):
    md = tmp_path / "in.md"
    md.write_text("# Packing list\n\n| Item | Qty |\n|---|---|\n| Adapters | 2 |\n\nCafé ½ cup.\n")
    subprocess.run(["pandoc", "-o", str(tmp_path / "list.docx"), str(md)], check=True)
    docx = (tmp_path / "list.docx").read_bytes()
    raw = email("Packing", "<p@x>", attachments=(
        (docx, "application", "vnd.openxmlformats-officedocument.wordprocessingml.document", "Packing List.docx"),
        (b"item,qty\nadapters,2\n", "text", "csv", "gear.csv"),
        (b"PK\x03\x04", "application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet", "budget.xlsx")))
    e = parse(raw)
    assert [n for n, _ in e.documents] == ["Packing List.docx", "gear.csv"]
    text = e.text()
    assert "## Attachment: Packing List.docx\n\n# Packing list" in text
    assert "| Adapters | 2   |" in text and "Café ½ cup." in text
    assert "## Attachment: gear.csv\n\nitem,qty\nadapters,2" in text
    assert e.not_kept == ["budget.xlsx"]


ZOHO = "mx.zohomail.com"


def sent(sender: str, results: str | None, msg_id: str, fake: str | None = None) -> bytes:
    """An email as it lands in the shared mailbox: the receiving server's result on top."""
    m = EmailMessage()
    if results is not None:
        m["Authentication-Results"] = f"{ZOHO}; {results}"
    if fake:
        m["Authentication-Results"] = fake
    m["Subject"], m["From"], m["To"] = "Fwd: Hotel booking", sender, "familywiki@example.org"
    m["Message-ID"] = msg_id
    m.set_content("Check-in Feb 13.")
    return bytes(m)


def test_verified_sender():
    ok = "spf=pass smtp.mailfrom=gmail.com; dkim=pass header.i=@gmail.com; dmarc=pass header.from=gmail.com"
    assert verified_sender(sent("Robin <Robin@gmail.com>", ok, "<1@x>"), ZOHO) == ("robin@gmail.com", None)
    assert verified_sender(sent("a@b.example", "dkim=pass header.d=b.example", "<2@x>"), ZOHO)[1] is None
    zoho_style = "dkim=pass header.i=@gmail.com; spf=pass smtp.mailfrom=r@gmail.com; dmarc=pass(p=none) header.from=<r@gmail.com>"
    assert verified_sender(sent("r@gmail.com", zoho_style, "<6@x>"), ZOHO)[1] is None
    assert "didn't vouch" in verified_sender(sent("x@gmail.com", "spf=pass; dkim=none; dmarc=fail", "<3@x>"), ZOHO)[1]
    # A DKIM pass for some other domain doesn't vouch for this From.
    assert "didn't vouch" in verified_sender(sent("x@gmail.com", "dkim=pass header.d=evil.example", "<4@x>"), ZOHO)[1]
    assert "no Authentication-Results" in verified_sender(sent("x@gmail.com", None, "<5@x>"), ZOHO)[1]


async def test_shared_mailbox_takes_only_verified_family_mail(env, tmp_path):
    maildir = tmp_path / "wikimail" / "familywiki" / "INBOX"
    maildir.parent.mkdir(parents=True)
    box = mailbox.Maildir(maildir, create=True)
    robin = User("robin", "Robin", "member", emails=("robin@gmail.com",))
    inbox = env["inbox"]
    inbox.config = Config(vault=env["vault"], state_dir=tmp_path, matrix=None, users=(env["user"], robin),
                          jobs_dir=tmp_path / "jobs", mailboxes=(Mailbox("familywiki", "familywiki@example.org", maildir, ZOHO),))
    [source] = [s for s in inbox.sources() if s.key == "familywiki"]
    box.add(sent("Robin <robin@gmail.com>", "dmarc=pass header.from=gmail.com", "<before@x>"))
    await inbox.poll(source)                                     # baseline
    ok = "dkim=pass header.i=@gmail.com; dmarc=pass header.from=gmail.com"
    box.add(sent("Robin <robin@gmail.com>", ok, "<good@x>"))
    box.add(sent("Stranger <spam@example.com>", "dmarc=pass header.from=example.com", "<spam@x>"))
    box.add(sent("Robin <robin@gmail.com>", "spf=fail; dkim=none; dmarc=fail header.from=gmail.com", "<forged@x>"))
    box.add(sent("Robin <robin@gmail.com>", "spf=fail; dmarc=fail", "<planted@x>",
                 fake=f"{ZOHO}; dmarc=pass header.from=gmail.com"))   # below Zoho's real result
    await inbox.poll(source)

    [job] = queued(env)
    assert job["meta"] == {"user": "robin"}
    src = (env["vault"] / job["input"] / "source.md").read_text()
    assert "An email sent to familywiki@example.org, added by Robin on " in src
    assert [inbox.state.mail_status(f"familywiki:<{i}@x>") for i in ("before", "good", "spam", "forged", "planted")] == \
        ["skipped", "written", "rejected", "rejected", "rejected"]
