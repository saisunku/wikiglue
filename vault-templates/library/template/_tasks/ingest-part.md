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
2. Read `wiki/sources/<slug>.md` (written by the earlier parts) and `wiki/index.md`.
3. Add this part's key points to the source page. If this part changes the overall picture,
   adjust the summary. Update its `Covers:` line (e.g. `Covers: parts 1–3 of 5`).
4. Decide which topic, tool and entity pages this part's content belongs on, as in
   `_tasks/ingest.md` step 4: update existing ones, create new ones only for subjects this part
   covers substantially. `grep -ril` the wiki for key names before creating anything.
5. Edit each of those pages: add what this part says, attributed and cited to `[[sources/<slug>]]`,
   add the slug to front matter `sources` if missing, bump `updated`, add the source to the
   topic's `## Reading` list if missing, and add `Related` links both ways.
6. Give new pages a one-line `summary:` in their front matter, and update the `summary:` of pages
   whose scope changed. Don't edit `wiki/index.md`: it's generated.
7. Add to the top of `wiki/log.md`, right under `# Log`:
   `## <today> ingest <slug> (part <n> of <total>)` then one bullet per page touched.
8. If the part refers to things that aren't in it (a figure or table with no numbers in the
   text), don't guess them. Append one line to `_review/missing-from-sources.md`:
   `- <today> [[raw/YYYY/MM/<slug>/source|<slug>]] — <what's missing>`

Reply with the list of pages created/updated.
