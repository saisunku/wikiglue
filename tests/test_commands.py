from pathlib import Path

import pytest

from wikiglue.commands import CommandConfigError, CommandSet, Dispatcher
from wikiglue.config import User

SKELETON = Path(__file__).parents[1] / "vault-template" / "_config" / "commands.toml"

ALEX = User(key="alex", name="Alex", role="admin", matrix="@alex:hs")
KID = User(key="kid", name="Kid", role="member", matrix="@kid:hs")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "_config").mkdir()
    (tmp_path / "_config" / "commands.toml").write_text(SKELETON.read_text())
    return tmp_path


@pytest.fixture
def dispatcher(vault: Path) -> Dispatcher:
    return Dispatcher(vault, vault / "_config" / "commands.toml")


def test_skeleton_parses():
    cs = CommandSet.load(SKELETON)
    assert {c.name for c in cs.commands} == {"need", "pantry", "?", "approve", "requests", "announce", "queue", "note", "ping", "help", "trip", "summary"}
    assert cs.announce == {"shopping", "digest", "morning"}
    assert cs.default.action == "task"
    assert cs.route


@pytest.mark.parametrize(
    "text, name, arg",
    [
        ("need: oat milk", "need", "oat milk"),
        ("NEED:eggs", "need", "eggs"),
        ("  ? what is X", "?", "what is X"),
        ("approve 3", "approve", "3"),
        ("need some help with this article", "default", "need some help with this article"),
        ("https://example.com/a", "default", "https://example.com/a"),
        ("helpful article about bread", "default", "helpful article about bread"),
        ("ping", "ping", ""),
    ],
)
def test_match(text, name, arg):
    cmd, rest = CommandSet.load(SKELETON).match(text)
    assert (cmd.name, rest) == (name, arg)


def test_longest_prefix_wins():
    cs = CommandSet.parse(
        {
            "commands": {
                "need": {"action": "append", "file": "a.md"},
                "needsoon": {"prefix": "need soon:", "action": "append", "file": "b.md"},
            }
        }
    )
    assert cs.match("need soon: batteries")[0].name == "needsoon"


@pytest.mark.parametrize(
    "spec",
    [
        {"action": "nope"},
        {"action": "append"},
        {"action": "task"},
        {"action": "builtin"},  # name "x" isn't a builtin
        {"action": "append", "file": "a.md", "roles": ["root"]},
    ],
)
def test_invalid_specs(spec):
    with pytest.raises(CommandConfigError):
        CommandSet.parse({"commands": {"x": spec}})


async def test_append_writes_one_line(dispatcher: Dispatcher, vault: Path):
    reply = await dispatcher.handle(KID, "need: oat milk\n- [ ] injected item")
    assert reply == "Added to needs ✓"
    lines = (vault / "lists" / "needs.md").read_text().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("- [ ] oat milk - [ ] injected item — Kid, ")


async def test_append_requires_text(dispatcher: Dispatcher):
    assert (await dispatcher.handle(ALEX, "need:")).startswith("Usage")


async def test_roles_enforced(dispatcher: Dispatcher):
    assert "isn't available" in await dispatcher.handle(KID, "approve 1")
    assert "isn't available" not in await dispatcher.handle(ALEX, "approve 1")


async def test_append_outside_vault_rejected(vault: Path, dispatcher: Dispatcher):
    (vault / "_config" / "commands.toml").write_text(
        '[commands.x]\naction = "append"\nfile = "../escape.md"\n'
    )
    with pytest.raises(CommandConfigError):
        await dispatcher.handle(ALEX, "x: hi")
    assert not (vault.parent / "escape.md").exists()


async def test_bad_reload_keeps_previous_config(vault: Path, dispatcher: Dispatcher):
    assert await dispatcher.handle(ALEX, "ping") == "pong"
    path = vault / "_config" / "commands.toml"
    path.write_text("this is [not toml")
    import os
    os.utime(path, (1, 1))  # force a different mtime
    assert await dispatcher.handle(ALEX, "ping") == "pong"


async def test_help_lists_only_allowed(dispatcher: Dispatcher):
    assert "approve" not in await dispatcher.handle(KID, "help")
    assert "approve" in await dispatcher.handle(ALEX, "help")
