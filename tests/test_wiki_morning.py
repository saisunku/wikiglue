"""runner/wiki-morning: trip selection and the plumbing around the model's answers."""

import importlib.machinery
import importlib.util
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "runner" / "wiki-morning"
loader = importlib.machinery.SourceFileLoader("wiki_morning", str(SCRIPT))
wm = importlib.util.module_from_spec(importlib.util.spec_from_loader("wiki_morning", loader))
loader.exec_module(wm)


def trip(vault: Path, name: str, start: str, end: str, kind: str = "trip") -> None:
    p = vault / "wiki" / "trips" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: \"{name.title()}\"\ntype: {kind}\nstart: {start}\nend: {end}\n---\n# {name}\n")


def test_upcoming_trips(tmp_path):
    trip(tmp_path, "past", "2026-10-01", "2026-10-05")
    trip(tmp_path, "now", "2026-10-30", "2026-11-02")
    trip(tmp_path, "soon", "2027-01-28", "2027-02-01")
    trip(tmp_path, "later", "2027-02-12", "2027-02-15")
    trip(tmp_path, "merged", "2026-11-01", "2026-11-03", kind="redirect")
    got = [t[1] for t in wm.upcoming_trips(tmp_path, date(2026, 10, 31))]
    assert got == ["Now", "Soon"]


def test_check_trip_keeps_gap_lines_and_retries(tmp_path, monkeypatch):
    replies = iter(["", "Thinking about it...\n`- no lodging the night of Mon 4 Jan in Banff`\n"])
    calls = []
    def fake(vault, task, text, step):
        calls.append((task, text, step))
        return next(replies)
    monkeypatch.setattr(wm, "run_task", fake)
    gaps = wm.check_trip(tmp_path, Path("2027-01-banff.md"), "Banff",
                         date(2026, 12, 31), date(2027, 1, 5))
    assert gaps == "- no lodging the night of Mon 4 Jan in Banff"
    assert [c[2] for c in calls] == ["2027-01-banff-1", "2027-01-banff-2"]
    assert "Nights: Thu 31 Dec, Fri 1 Jan, Sat 2 Jan, Sun 3 Jan, Mon 4 Jan" in calls[0][1]


def test_check_trip_ok_and_no_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(wm, "run_task", lambda *a: "OK")
    assert wm.check_trip(tmp_path, Path("t.md"), "T", date(2026, 12, 4), date(2026, 12, 7)) == ""
    monkeypatch.setattr(wm, "run_task", lambda *a: "")
    assert wm.check_trip(tmp_path, Path("t.md"), "T", date(2026, 12, 4), date(2026, 12, 7)) is None


def test_main_fills_in_trips(tmp_path, monkeypatch, capsys):
    trip(tmp_path, "bend", "2026-12-04", "2026-12-07")
    monkeypatch.setattr(wm, "date", type("D", (date,), {"today": staticmethod(lambda: date(2026, 10, 31))}))
    def fake(vault, task, text, step):
        if task == "trip-check":
            return "- no lodging the night of Fri 4 Dec in Sisters"
        return "**To do**\nNothing.\n\n**Trips to finish booking**\nTRIPS\n\n**Needs**\nNothing."
    monkeypatch.setattr(wm, "run_task", fake)
    monkeypatch.setattr("sys.argv", ["wiki-morning", str(tmp_path)])
    wm.main()
    out = capsys.readouterr().out
    assert "**Trips to finish booking**\n- Bend, Fri 4 Dec–Mon 7 Dec:\n  no lodging the night of Fri 4 Dec in Sisters\n" in out
    assert "TRIPS" not in out


def test_merge_nights():
    gaps = "\n".join([f"- no lodging the night of {d} in Austin" for d in
                      ("Sat 21 Nov", "Sun 22 Nov", "Mon 23 Nov")]
                     + ["- no flight Austin → Chicago on Sun 29 Nov",
                        "- no lodging the night of Fri 27 Nov in Austin"])
    assert wm.merge_nights(gaps, date(2026, 11, 21), date(2026, 11, 29)) == [
        "no lodging the nights of Sat 21 Nov – Mon 23 Nov in Austin",
        "no flight Austin → Chicago on Sun 29 Nov",
        "no lodging the night of Fri 27 Nov in Austin"]
