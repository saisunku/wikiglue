"""Talking to wiki-runner through its folders (see runner/wiki-runner).

wikiglue drops job files into <jobs_dir>/queue/ and reads results from
<jobs_dir>/done/. It never runs the model itself and the runner never talks to
Matrix: this folder is the only link between them.

When one runner serves several wikis, each wiki has its own wikiglue with
`vault_name` set: it marks its jobs with that name and posts only their results.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
from pathlib import Path

TASK_RE = re.compile(r"^[a-z0-9_-]+$")


class Jobs:
    def __init__(self, jobs_dir: Path, vault_name: str | None = None):
        self.vault_name = vault_name
        self.queue = jobs_dir / "queue"
        self.done = jobs_dir / "done"
        self.status_file = jobs_dir / "status.json"

    def submit(self, task: str, input: str = "", *, priority: str = "interactive",
               submitted_by: str = "wikiglue", meta: dict | None = None) -> str:
        """Queue a job; returns its id. Same format as runner/wiki-job.

        priority: "chat" (pauses a running ingest), "interactive" or "background"."""
        if priority not in ("chat", "interactive", "background"):
            raise ValueError(f"bad priority {priority!r}")
        if not TASK_RE.match(task):
            raise ValueError(f"bad task name {task!r}")
        now = dt.datetime.now()
        job_id = f"{now:%Y%m%dT%H%M%S%f}-{task}-{secrets.token_hex(3)}"
        job = {
            "task": task,
            "input": input,
            "priority": priority,
            "submitted": now.astimezone().isoformat(timespec="seconds"),
            "submitted_by": submitted_by,
            "meta": meta or {},
        }
        if self.vault_name:
            job["vault"] = self.vault_name
        tmp = self.queue / f".{job_id}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w") as f:
            json.dump(job, f, ensure_ascii=False)
        os.chmod(tmp, 0o644)  # the runner (wikibot) reads it as "other"
        os.replace(tmp, self.queue / f"{job_id}.job")
        return job_id

    def results(self) -> list[dict]:
        """Finished jobs (this wiki's, if vault_name is set), oldest first."""
        out = []
        for p in sorted(self.done.glob("*.json")):
            try:
                result = json.loads(p.read_text())
            except (OSError, ValueError):
                continue  # being written or unreadable; the runner writes atomically
            if not self.vault_name or result.get("vault") == self.vault_name:
                out.append(result)
        return out

    def status(self) -> dict | None:
        """wiki-runner's status.json: running, paused and waiting jobs."""
        try:
            return json.loads(self.status_file.read_text())
        except (OSError, ValueError):
            return None

    def describe_status(self) -> str:
        status = self.status()
        if status is None:
            return "Can't see the job runner's status."

        def label(job: dict) -> str:
            text = job.get("input") or ""
            if job.get("task") == "ingest":
                text = Path(text).name  # raw/2026/10/2026-10-rye-bread -> the slug
            text = text if len(text) <= 60 else text[:57] + "…"
            other = job.get("vault") if job.get("vault") not in (None, self.vault_name) else None
            return (f"[{other}] " if other else "") + f"{job.get('task')} {text}".strip()

        def minutes(job: dict) -> str:
            try:
                started = dt.datetime.fromisoformat(job["started"])
            except (KeyError, TypeError, ValueError):
                return ""
            mins = int((dt.datetime.now(started.tzinfo) - started).total_seconds() // 60)
            return f" ({mins} min)"

        lines = []
        if status.get("running"):
            lines.append(f"Running: {label(status['running'])}{minutes(status['running'])}")
        for job in status.get("paused", []):
            lines.append(f"Paused: {label(job)}")
        waiting = status.get("waiting", [])
        if waiting:
            lines.append(f"Waiting ({len(waiting)}): " + ", ".join(label(j) for j in waiting[:5])
                         + (", …" if len(waiting) > 5 else ""))
        return "\n".join(lines) or "Idle: no jobs running or waiting."


def task_name(path_or_name: str) -> str:
    """"_tasks/query.md" -> "query" (commands.toml names task files by path)."""
    return Path(path_or_name).stem
