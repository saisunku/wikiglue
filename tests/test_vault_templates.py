"""vault-templates/: each kind of wiki's commands load, its index renders and lint sees its folders."""

import importlib.machinery
import importlib.util
import shutil
from pathlib import Path

import pytest

from wikiglue.commands import CommandSet

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"household": (ROOT / "vault-template", ROOT / "vault-starter")} | {
    p.name: (p / "template", p / "starter") for p in sorted((ROOT / "vault-templates").iterdir())}


def load(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(ROOT / "runner" / name))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def new_vault(tmp_path: Path, kind: str) -> Path:
    template, starter = KINDS[kind]
    vault = tmp_path / kind
    shutil.copytree(template, vault)
    shutil.copytree(starter, vault, dirs_exist_ok=True)
    return vault


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_template_is_complete(tmp_path, kind):
    vault = new_vault(tmp_path, kind)
    cs = CommandSet.load(vault / "_config" / "commands.toml")
    for cmd in (*cs.commands, cs.default):
        if cmd.action == "task":
            assert (vault / cmd.options["task"]).is_file(), cmd.options["task"]
    for task in ("ingest", "ingest-part", "query", "lint", "lint-fix", "lint-review", "summary", "digest"):
        assert (vault / "_tasks" / f"{task}.md").is_file(), task
    for name in cs.announce:
        assert (vault / "_tasks" / f"{name}.md").is_file(), name
    for page in ("wiki/index.md", "wiki/log.md", "_review/research-requests.md"):
        assert (vault / page).is_file(), page


def test_projects_index_groups_by_status(tmp_path):
    vault = new_vault(tmp_path, "projects")
    for name, status in (("alpha", "active"), ("beta", "idea"), ("gamma", "done")):
        (vault / "wiki" / "projects").mkdir(exist_ok=True)
        (vault / "wiki" / "projects" / f"{name}.md").write_text(
            f"---\ntitle: {name.title()}\ntype: project\nstatus: {status}\nsummary: s\n---\n# {name}\n")
    text = load("wiki-index").render(vault)
    active, ideas, done = (text.index(h) for h in ("## Active projects", "## Ideas", "## Done and dropped"))
    assert active < text.index("Alpha") < ideas < text.index("Beta") < done < text.index("Gamma")


def test_library_index_sorts_sources_by_kind(tmp_path):
    vault = new_vault(tmp_path, "library")
    (vault / "wiki" / "sources").mkdir()
    for slug, kind in (("a-paper", "paper"), ("a-talk", "talk"), ("a-thread", "thread")):
        (vault / "wiki" / "sources" / f"{slug}.md").write_text(
            f"---\ntitle: {slug}\ntype: source\nkind: {kind}\nsummary: s\n---\n# {slug}\n")
    text = load("wiki-index").render(vault)
    assert text.index("## Papers") < text.index("a-paper") < text.index("## Posts")
    assert text.index("## Videos and talks") < text.index("a-talk") < text.index("## Books")
    assert text.index("## Other sources") < text.index("a-thread") < text.index("## Out of scope")


def test_lint_checks_each_kinds_folders(tmp_path):
    lint = load("wiki-lint")
    assert lint.folders(new_vault(tmp_path, "library"), "orphan-folders", "x") == "(topics|tools|entities)/"
    assert lint.folders(new_vault(tmp_path, "projects"), "review-folders", "x") == "(projects|topics|entities)/"
