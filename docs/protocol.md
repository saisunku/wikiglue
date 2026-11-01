# The job protocol

wikiglue and wiki-runner never call each other. They share two things: the vault's
`raw/` folder, and a jobs folder (`/var/lib/wiki-jobs` by default). Anything that
writes these files the same way can take wikiglue's place, and cron does exactly
that through `runner/wiki-job`.

## Sources: `raw/YYYY/MM/<slug>/`

One folder per source, written once and never edited afterwards. The agent can read
`raw/` but not write to it.

| File | Contents |
|---|---|
| `source.md` | Readable text with a short header: title, link, who added it and how, any note they sent with it |
| `meta.json` | `title`, `url` (or null), `added_by` (a person's name), `added_at` (YYYY-MM-DD), `kind` (`link`, `note`, `image`, `pdf`, `email`, …), and either `karakeep_id` or, for email, `from` and `date` |
| `<file>` | The image or PDF, if any, and photo attachments of emails |
| `page-N.jpg` | A scanned PDF's pages, for the vision model |
| `part-N.md` | A long article split at its own headings; part 1 goes through `ingest`, later parts through `ingest-part` |

## Jobs: `queue/<id>.job`

```json
{
  "task": "ingest",
  "input": "raw/2026/10/2026-10-rye-bread",
  "priority": "interactive",
  "submitted": "2026-10-31T09:12:03-07:00",
  "submitted_by": "wikiglue",
  "meta": {"user": "alex", "room": "!abc:example.org", "event": "$xyz"}
}
```

- `task`: `[a-z0-9_-]+`, the name of `<vault>/_tasks/<task>.md`. Anything else is rejected.
- `input`: text for the task, up to 8000 characters (a path, a question, a note).
- `priority`: `chat`, `interactive` or `background` (see the README's
  [queue section](../README.md#the-queue)).
- `meta`: anything the submitter wants back with the result. The runner doesn't read it.
- `<id>`: `<YYYYmmddTHHMMSSffffff>-<task>-<6 hex>`, so jobs sort by arrival.

Write the file under a dot-name in `queue/` first, then rename it to `<id>.job`, so
the runner never reads a half-written job.

## Results: `done/<id>.json`

The job, plus:

| Field | Meaning |
|---|---|
| `id` | The job id |
| `status` | `ok`, `failed`, `timeout` or `rejected` |
| `started`, `finished` | ISO timestamps |
| `active_seconds`, `paused_seconds` | Time running, and time paused for more urgent jobs |
| `exit_code` | pi's exit code |
| `reply` | pi's final answer (last 20,000 characters) |
| `error` | Why it was rejected or interrupted, if it was |

Results are kept for 14 days; pi's session for each job is kept for the same time,
under `transcripts/<id>/`.

## Status: `status.json`

The running job, any paused jobs and the waiting ones (`id`, `task`, `input`,
`priority`, `started`), rewritten whenever it changes. wikiglue's `queue` command
reads it.
