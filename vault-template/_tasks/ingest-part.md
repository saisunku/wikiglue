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
4. Decide which topic/entity pages this part's facts belong on: update existing ones,
   create new ones only for subjects this part covers substantially.
   `grep -ril` the wiki for key names before creating anything.
5. Edit each of those pages: add the facts with citations to `[[sources/<slug>]]`, add the slug
   to frontmatter `sources` if missing, bump `updated`, and add `Related` links both ways.
5b. Facts about someone listed in `_config/family_data.md` (by any of their names) go on their page,
   under the matching section of `_config/templates/person.md` (food, health, sizes and gifts,
   dates, frequent flyer and travel programmes, trips, notes), cited like any other fact.
6. Give new pages a one-line `summary:` in their front matter, and update the `summary:` of pages
   whose scope changed. Don't edit `wiki/index.md`: it's generated.
7. Add to the top of `wiki/log.md`, right under `# Log`:
   `## <today> ingest <slug> (part <n> of <total>)` then one bullet per page touched.
8. If the part refers to values that aren't anywhere in it (a rating scale's two ends, like
   `IndependentLovey-Dovey`, with no score for it in the text or under "Details from the page";
   a chart or table mentioned with no numbers; a figure that isn't in the folder), don't guess
   them from the labels. Append one line to
   `_review/missing-from-sources.md`:
   `- <today> [[raw/YYYY/MM/<slug>/source|<slug>]] — <what's missing, e.g. "6 trait ratings shown only as scale ends">`

Reply with the list of pages created/updated.
