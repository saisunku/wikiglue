---
# Measured with a 35B-A3B model: 2.7x faster than low, no facts lost.
thinking: off
# A reasonable source takes 20-90 s; a stuck job shouldn't hold the queue for long.
time-limit-minutes: 5
---
# Task: ingest the next part of a long source

Part file: `$INPUT`

This source was too long for one pass, so it is ingested in parts, one task per part.
Earlier parts are already in the wiki. The source folder is the part file's folder,
and the slug is that folder's name.

1. Read the part file and the folder's `meta.json`. Don't read `source.md` or other parts.
2. Read `wiki/sources/<slug>.md` (written by the earlier parts, with its `projects:`) and
   `wiki/index.md`.
3. Add this part's key points to the source page. If this part changes the overall picture,
   adjust the summary. Update its `Covers:` line (e.g. `Covers: parts 1–3 of 5`).
4. File what this part adds as `_tasks/ingest.md` steps 4 and 5 say, on the same projects
   (and topics), cited to `[[sources/<slug>]]`. Bump `updated` on each page you change.
5. Add to the top of `wiki/log.md`, right under `# Log`:
   `## <today> ingest <slug> (part <n> of <total>)` then one bullet per page touched.

Reply with the list of pages created/updated.
