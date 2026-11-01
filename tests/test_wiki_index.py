"""runner/wiki-index: wiki/index.md from the _config/index.md template."""

import importlib.machinery
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "runner" / "wiki-index"
loader = importlib.machinery.SourceFileLoader("wiki_index", str(SCRIPT))
wiki_index = importlib.util.module_from_spec(importlib.util.spec_from_loader("wiki_index", loader))
loader.exec_module(wiki_index)

TEMPLATE = """---
title: Index
---
# Index

<!--
Notes for whoever edits the template.
-->

## Household
- [[lists/needs|Needs]]

## Upcoming trips
<!-- pages: trips/ end>=today sort=start -->

## Past trips
<!-- pages: trips/ end<today sort=-start -->

## Dogs
<!-- pages: tags=dogs -->

## Other
<!-- pages: rest -->
"""


def page(vault: Path, rel: str, **front) -> None:
    p = vault / "wiki" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    head = "\n".join(f"{k}: {v}" for k, v in front.items())
    p.write_text(f"---\n{head}\n---\n# Heading\n")


def test_render(tmp_path: Path):
    (tmp_path / "_config").mkdir()
    (tmp_path / "_config" / "index.md").write_text(TEMPLATE)
    page(tmp_path, "trips/2027-03-japan.md", title='"Japan, March 2027"', summary="flights booked",
         start="2027-03-03", end="2027-03-13")
    page(tmp_path, "trips/2027-01-goa.md", title="Goa", start="2027-01-02", end="2027-01-09")
    page(tmp_path, "trips/2025-05-rome.md", title="Rome", start="2025-05-01", end="2025-05-08")
    page(tmp_path, "trips/2024-05-oslo.md", title="Oslo", start="2024-05-01", end="2024-05-08")
    page(tmp_path, "entities/pug.md", title="Pug", tags="[dogs, toy-breed]", summary="small dog")
    page(tmp_path, "topics/bread.md", title="Bread | baking", summary="loaves  # not a comment")
    page(tmp_path, "log.md", title="Log")
    page(tmp_path, "trips/2025-05-rome-2.md", title="Rome again", type="redirect", start="2025-05-02", end="2025-05-03")

    out = wiki_index.render(tmp_path, today="2026-10-28")
    assert out == """---
title: Index
---
<!-- Generated from _config/index.md by wiki-index: edit that file, not this one. -->
# Index

## Household
- [[lists/needs|Needs]]

## Upcoming trips
- [[trips/2027-01-goa|Goa]]
- [[trips/2027-03-japan|Japan, March 2027]] — flights booked

## Past trips
- [[trips/2025-05-rome|Rome]]
- [[trips/2024-05-oslo|Oslo]]

## Dogs
- [[entities/pug|Pug]] — small dog

## Other
- [[topics/bread|Bread – baking]] — loaves
"""


def test_write_only_when_changed(tmp_path: Path):
    (tmp_path / "_config").mkdir()
    (tmp_path / "_config" / "index.md").write_text("# Index\n<!-- pages: rest -->\n")
    page(tmp_path, "topics/a.md", title="A")
    assert wiki_index.write(tmp_path) is True
    assert wiki_index.write(tmp_path) is False
    assert "[[topics/a|A]]" in (tmp_path / "wiki" / "index.md").read_text()


def raw_source(vault: Path, folder: str, *files: str) -> None:
    d = vault / "raw" / folder
    d.mkdir(parents=True)
    (d / "source.md").write_text("# source\n")
    for f in files:
        (d / f).write_text("x")


def test_fix_raw_links(tmp_path):
    raw_source(tmp_path, "2026/10/2026-10-card-jpeg", "image.jpeg")
    raw_source(tmp_path, "2026/10/2026-10-good")
    p = tmp_path / "wiki" / "sources" / "a.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "- [[raw/2026/10/2026-10-card-jpeg|original]]\n"          # the folder
        "- [[raw/2026-10-card-jpeg]]\n"                           # no year/month
        "- [[raw/2026/10/card-jpeg/source]]\n"                    # slug without its date prefix
        "- [[raw/2026-10-card-jpeg/image.jpeg|photo]]\n"          # a file in the folder
        "- ![[raw/2026/10/2026-10-card-jpeg/image.jpeg]]\n"       # embeds are left alone
        "- [[raw/2026/10/2026-10-good/source|ok]]\n"              # already right
        "- [[raw/2026/10/2026-10-unknown]]\n")                    # no such folder: unchanged
    changes = wiki_index.fix_raw_links(tmp_path)
    assert len(changes) == 4
    assert p.read_text() == (
        "- [[raw/2026/10/2026-10-card-jpeg/source|original]]\n"
        "- [[raw/2026/10/2026-10-card-jpeg/source]]\n"
        "- [[raw/2026/10/2026-10-card-jpeg/source]]\n"
        "- [[raw/2026/10/2026-10-card-jpeg/image.jpeg|photo]]\n"
        "- ![[raw/2026/10/2026-10-card-jpeg/image.jpeg]]\n"
        "- [[raw/2026/10/2026-10-good/source|ok]]\n"
        "- [[raw/2026/10/2026-10-unknown]]\n")
    assert wiki_index.fix_raw_links(tmp_path) == []
