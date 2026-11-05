"""agent/wiki-lint: what it finds without the model, how it batches, and the log entry."""

import importlib.machinery
import importlib.util
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "runner" / "wiki-lint"
loader = importlib.machinery.SourceFileLoader("wiki_lint", str(SCRIPT))
wl = importlib.util.module_from_spec(importlib.util.spec_from_loader("wiki_lint", loader))
loader.exec_module(wl)

TODAY = date(2026, 11, 4)


def page(vault: Path, rel: str, body: str, front: str = 'title: T\nsummary: S') -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{front}\n---\n{body}\n")


def make(tmp_path: Path) -> Path:
    v = tmp_path
    (v / "raw/2026/10/2026-10-thing").mkdir(parents=True)
    (v / "raw/2026/10/2026-10-thing/source.md").write_text("x")
    (v / "raw/2026/10/2026-10-other").mkdir(parents=True)
    (v / "raw/2026/10/2026-10-other/source.md").write_text("x")
    page(v, "wiki/topics/bread.md", "[[topics/sourdough]] [[entities/king-arthur]] [[sources/2026-10-thing]]")
    page(v, "wiki/topics/sourdough.md", "[[topics/bread]] [[topics/sourdogh-starter]] "
         "[[../raw/2026/10/2026-10-thing|original]] `[[not/a/link]]` ![[raw/2026/10/2026-10-thing/source]]")
    page(v, "wiki/entities/king-arthur.md", "[[credits]]\n![logo](https://e.com/x.png?d=1)\n<img src='http://e.com/y'>\n![[raw/2026/10/2026-10-thing/source]]")
    page(v, "wiki/topics/lonely.md", "nothing links here", front='title: "Order #4: "big""\nsummary: a: b')
    page(v, "wiki/sources/2026-10-thing.md", "no summary [[source|original]]", front="title: Thing")
    (v / "wiki/credits.md").write_text(
        "---\ntitle: Credits\nsummary: s\n---\n| Retailer | Kind | Expires | Holder |\n|---|---|---|---|\n"
        "| Old | gift card | 2026-11-01 | Alex |\n| New | gift card | 2026-12-01 | Alex |\n| Never | card | none | Alex |\n")
    (v / "wiki/log.md").write_text(
        "---\ntitle: Log\n---\n# Log\n\n## 2026-11-03 ingest x\n- Updated [[topics/bread]], [[sources/2026-10-thing]]\n"
        "## 2026-11-03 lint\n- [[topics/sourdough]]: old\n")
    (v / "wiki/index.md").write_text("[[topics/missing]]")
    return v


def test_finds_problems_without_the_model(tmp_path):
    v = make(tmp_path)
    pages = wl.wiki_pages(v)
    broken = wl.broken_links(v, pages)
    assert sorted(p for p, _ in broken) == ["wiki/sources/2026-10-thing.md", "wiki/topics/sourdough.md",
                                            "wiki/topics/sourdough.md"]
    msgs = dict(broken)
    by = [w for p, w in broken if p == "wiki/topics/sourdough.md"]
    assert "closest pages: topics/sourdough" in by[0]
    assert "the right target is [[raw/2026/10/2026-10-thing/source]]" in by[1]
    # [[source]] could be either source's file: on a source page it means that source's own
    assert "[[source]] points at nothing; the right target is [[raw/2026/10/2026-10-thing/source]]" in msgs["wiki/sources/2026-10-thing.md"]
    fm = wl.front_matter_problems(pages)
    assert ("wiki/sources/2026-10-thing.md", "front matter has no `summary:`") in fm
    assert any(p == "wiki/topics/lonely.md" and "double quote" in w for p, w in fm)
    assert any(p == "wiki/topics/lonely.md" and "needs quotes" in w for p, w in fm)
    assert wl.remote_images(pages) == [("wiki/entities/king-arthur.md", "line 6: an image loaded from the internet"),
                                       ("wiki/entities/king-arthur.md", "line 7: an image loaded from the internet")]
    assert wl.orphans(pages) == [("wiki/topics/lonely.md", "orphan: no other page links to it")]
    rows = wl.past_rows(v, TODAY)
    assert len(rows) == 1 and "2026-11-01 has passed: Old" in rows[0][1]
    assert wl.changed_since_last_lint(v, pages, TODAY) == ["wiki/topics/bread.md"]


def test_batches_keep_a_page_together():
    probs = [("a", "1"), ("a", "2"), ("b", "3"), ("c", "4"), ("c", "5")]
    assert [b.count("  - ") for b in wl.batches(probs, 3)] == [3, 2]


def test_main_runs_jobs_and_writes_one_log_entry(tmp_path, monkeypatch, capsys):
    v = make(tmp_path)
    calls = []
    def fake(vault, task, text, step):
        calls.append((task, step))
        return "- [[topics/x]]: fixed\nchatter" if task == "lint-fix" else "No changes."
    monkeypatch.setattr(wl, "run_task", fake)
    monkeypatch.setattr(wl, "date", type("D", (date,), {"today": staticmethod(lambda: TODAY)}))
    monkeypatch.setattr("sys.argv", ["wiki-lint", str(v)])
    wl.main()
    assert [c[0] for c in calls][-1] == "lint-review" and calls[0][1] == "01-lint-fix"
    log = (v / "wiki/log.md").read_text()
    assert log.index("## 2026-11-04 lint\n- [[topics/x]]: fixed") < log.index("## 2026-11-03 ingest")
    assert "chatter" not in log
    assert "changes" in capsys.readouterr().out
