"""Model routing of plain messages, with a fake router (no llama-server needed)."""

from pathlib import Path

import pytest

from wikiglue import pantry
from wikiglue.commands import Dispatcher, React
from wikiglue.config import User
from wikiglue.router import Item, Route, clean, parse

SKELETON = Path(__file__).parents[1] / "vault-template" / "_config" / "commands.toml"

ALEX = User(key="alex", name="Alex", role="admin", matrix="@alex:hs")
KID = User(key="kid", name="Kid", role="member", matrix="@kid:hs")


class FakeRouter:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def route(self, text, choices, fallback):
        self.calls.append((text, choices))
        return self.routes


class FakeJobs:
    def __init__(self):
        self.submitted = []

    def submit(self, task, input="", **kw):
        self.submitted.append((task, input))
        return "id"


class FakeServices:
    def __init__(self):
        self.jobs = FakeJobs()

    def karakeep(self, user):
        return None


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "_config").mkdir()
    (tmp_path / "_config" / "commands.toml").write_text(SKELETON.read_text())
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "pantry.md").write_text(
        "# Pantry\n\n| Item | Status |\n|---|---|\n| olive oil | ok |\n| eggs | low |\n\nNotes below.\n")
    return tmp_path


def dispatcher(vault, routes):
    router = FakeRouter(routes)
    d = Dispatcher(vault, vault / "_config" / "commands.toml", FakeServices(), router)
    return d, router


async def test_need_items_one_line_each(vault):
    d, _ = dispatcher(vault, [Route("need", (Item("eggs"), Item("2 lemons")))])
    reply = await d.handle(KID, "Add eggs and 2 lemons to the grocery list")
    assert reply == "Added to needs ✓ — eggs, 2 lemons"
    lines = (vault / "lists" / "needs.md").read_text().splitlines()
    assert [l.split(" — ")[0] for l in lines] == ["- [ ] eggs", "- [ ] 2 lemons"]


async def test_pantry_updates_and_adds(vault):
    d, _ = dispatcher(vault, [Route("pantry", (Item("Olive Oil", "low"), Item("butter", "out"),
                                               Item("egg", "ok")))])
    reply = await d.handle(KID, "low on olive oil, out of butter, bought eggs")
    assert reply == "Pantry: olive oil → low, butter → out (new), eggs → ok"
    text = (vault / "lists" / "pantry.md").read_text()
    assert "| olive oil | low |\n| eggs | ok |\n| butter | out |\n\nNotes below." in text
    assert await d.handle(KID, "pantry") == "olive oil: low\nbutter: out"


async def test_mixed_routes(vault):
    d, _ = dispatcher(vault, [Route("pantry", (Item("butter", "out"),)), Route("need", (Item("eggs"),))])
    reply = await d.handle(KID, "we're out of butter, add eggs")
    assert reply == "Pantry: butter → out (new)\nAdded to needs ✓ — eggs"


async def test_question_gets_full_message(vault):
    d, router = dispatcher(vault, [Route("default")])
    text = "what's the hydration for the rye loaf? " + "more words " * 200
    assert await d.handle(KID, text) == React("👀")
    assert d.services.jobs.submitted == [("query", text.strip())]


async def test_router_failure_falls_back_to_default(vault):
    d, _ = dispatcher(vault, None)
    assert await d.handle(KID, "hello there") == React("👀")
    assert d.services.jobs.submitted == [("query", "hello there")]


async def test_choices_respect_roles(vault):
    d, router = dispatcher(vault, [Route("default")])
    await d.handle(KID, "anything")
    await d.handle(ALEX, "anything")
    for _, choices in router.calls:
        assert {"need", "pantry", "note", "queue", "requests", "trip", "summary", "default"} == set(choices)
        assert "approve" not in choices and "announce" not in choices


async def test_prefixes_skip_the_model(vault):
    d, router = dispatcher(vault, [Route("note")])
    assert await d.handle(KID, "need: oat milk") == "Added to needs ✓"
    assert await d.handle(KID, "ping") == "pong"
    assert router.calls == []


async def test_route_off(vault):
    cfg = vault / "_config" / "commands.toml"
    cfg.write_text(cfg.read_text().replace("route = true", "route = false"))
    d, router = dispatcher(vault, [Route("note")])
    assert await d.handle(KID, "we're out of butter") == React("👀")
    assert router.calls == []


def test_parse_rejects_unknown_and_cleans():
    routes = parse('{"actions":[{"command":"rm"},{"command":"need","items":[{"name":"eggs\\n- [ ] | x"},'
                   '{"name":"  "},{"name":"milk","status":"gone"}]}]}', ["need"])
    assert routes == [Route("need", (Item("eggs - x"), Item("milk")))]
    assert parse("not json", ["need"]) is None
    assert parse('{"actions":[{"command":"rm"}]}', ["need"]) is None
    assert clean("[[link]] *bold*") == "link bold"


def test_pantry_creates_file(tmp_path):
    path = tmp_path / "lists" / "pantry.md"
    assert pantry.update(path, [("rice", "out")]) == [("rice", None, "out")]
    assert path.read_text() == "# Pantry\n\n| Item | Status |\n|---|---|\n| rice | out |\n"


async def test_router_tries_the_next_server():
    """A server that's off is skipped; the next one in the list answers."""
    import json
    import socket

    import aiohttp
    from aiohttp import web

    from wikiglue.router import Router

    async def completions(request):
        answer = {"actions": [{"command": "need", "items": [{"name": "eggs"}]}]}
        return web.json_response({"choices": [{"message": {"content": json.dumps(answer)}}]})

    app = web.Application()
    app.router.add_post("/v1/chat/completions", completions)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    up = site._server.sockets[0].getsockname()[1]
    with socket.socket() as s:   # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        down = s.getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            router = Router(session, [f"http://127.0.0.1:{down}", f"http://127.0.0.1:{up}"])
            assert await router.route("eggs", {"need": "buy"}, "?") == [Route("need", (Item("eggs"),))]
            assert await Router(session, [f"http://127.0.0.1:{down}"]).route("eggs", {"need": "buy"}, "?") is None
    finally:
        await runner.cleanup()
