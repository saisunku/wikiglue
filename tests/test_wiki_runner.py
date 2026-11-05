"""runner/wiki-runner: which job runs, which is paused, and what resumes first."""

import importlib.machinery
import importlib.util
import time
from pathlib import Path

import pytest

from wikiglue.jobs import Jobs

SCRIPT = Path(__file__).resolve().parents[1] / "runner" / "wiki-runner"
loader = importlib.machinery.SourceFileLoader("wiki_runner", str(SCRIPT))
wr = importlib.util.module_from_spec(importlib.util.spec_from_loader("wiki_runner", loader))
loader.exec_module(wr)


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault, root = tmp_path / "vault", tmp_path / "jobs"
    (vault / "_tasks").mkdir(parents=True)
    for task in ("ingest", "query", "lint"):
        (vault / "_tasks" / f"{task}.md").write_text(f"# {task}\n")
    for d in ("queue", "running", "done", "transcripts"):
        (root / d).mkdir(parents=True)
    fake = tmp_path / "run-task.sh"   # sleeps for <input> seconds, then answers
    fake.write_text('#!/bin/sh\nsleep "$3"\necho "done $2"\n')
    fake.chmod(0o755)
    monkeypatch.setattr(wr, "first_ready", lambda servers: "local")
    monkeypatch.setattr(wr.Runner, "update_index", lambda self, force=False: None)
    runner = wr.Runner(root, vault, fake)
    return runner, Jobs(root)


def task_of(job):
    return job and job.data["task"]


def step_until(runner, cond, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        runner.step()
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_chat_pauses_an_ingest_which_resumes_before_newer_ingests(env):
    runner, jobs = env
    jobs.submit("ingest", "1.5", priority="interactive")
    runner.step()
    first = runner.current
    assert task_of(first) == "ingest"

    jobs.submit("ingest", "0.1", priority="interactive")   # arrives later, waits its turn
    jobs.submit("query", "0.2", priority="chat")
    runner.step()
    assert task_of(runner.current) == "query" and runner.paused == [first]

    step_until(runner, lambda: runner.current is first)    # the paused ingest, not the newer one
    assert not first.paused and len(runner.waiting()) == 1
    step_until(runner, lambda: runner.current is not first and runner.current is not None)
    assert runner.current.data["input"] == "0.1"
    step_until(runner, lambda: runner.current is None)
    statuses = [r["status"] for r in jobs.results()]
    assert statuses == ["ok", "ok", "ok"]


def test_ingest_pauses_lint_and_chat_pauses_both(env):
    runner, jobs = env
    jobs.submit("lint", "1", priority="background")
    runner.step()
    lint = runner.current
    jobs.submit("ingest", "1", priority="interactive")
    runner.step()
    ingest = runner.current
    jobs.submit("query", "0.1", priority="chat")
    runner.step()
    assert task_of(runner.current) == "query" and runner.paused == [lint, ingest]
    step_until(runner, lambda: runner.current is ingest)
    step_until(runner, lambda: runner.current is lint)
    step_until(runner, lambda: runner.current is None)


def test_equal_priority_never_pauses(env):
    runner, jobs = env
    jobs.submit("query", "0.5", priority="chat")
    runner.step()
    first = runner.current
    jobs.submit("query", "0.1", priority="chat")
    runner.step()
    assert runner.current is first and runner.paused == []
    step_until(runner, lambda: runner.current is None)


def test_one_queue_serves_several_wikis(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    for d in ("queue", "running", "done", "transcripts"):
        (root / d).mkdir(parents=True)
    vaults = {}
    for name in ("family", "work"):
        (tmp_path / name / "_tasks").mkdir(parents=True)
        (tmp_path / name / "_tasks" / "query.md").write_text("# query\n")
        vaults[name] = tmp_path / name
    fake = tmp_path / "run-task.sh"   # answers with the vault folder it was given
    fake.write_text('#!/bin/sh\necho "$1"\n')
    fake.chmod(0o755)
    monkeypatch.setattr(wr, "first_ready", lambda servers: "local")
    monkeypatch.setattr(wr.Runner, "update_index", lambda self, force=False: None)
    runner = wr.Runner(root, vaults, fake)
    family, work, either = Jobs(root, "family"), Jobs(root, "work"), Jobs(root)

    ids = {"work": work.submit("query", ""), "family": family.submit("query", ""),
           "first": either.submit("query", "")}
    bad = (root / "queue" / "x.job")
    bad.write_text('{"task": "query", "vault": "../etc"}')
    step_until(runner, lambda: len(list((root / "done").glob("*.json"))) == 4)

    replies = {r["id"]: r for r in either.results()}
    assert replies[ids["work"]]["reply"] == str(vaults["work"])
    assert replies[ids["family"]]["reply"] == str(vaults["family"])
    assert replies[ids["first"]]["reply"] == str(vaults["family"])   # no name: the first
    assert replies["x"]["status"] == "rejected"
    assert [r["id"] for r in work.results()] == [ids["work"]]       # each sees only its own


def test_queue_hides_other_wikis_job_text(tmp_path):
    (tmp_path / "status.json").write_text(
        '{"running": {"task": "query", "vault": "work", "input": "salary bands"},'
        ' "paused": [], "waiting": [{"task": "query", "vault": "home", "input": "eggs?"}]}')
    text = Jobs(tmp_path, "home").describe_status()
    assert "salary" not in text and "[work] query" in text and "query eggs?" in text
