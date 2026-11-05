---
# Measured with a 35B-A3B model: 2.7x faster than low, no facts lost.
thinking: off
# A reasonable source takes 20-90 s; a stuck job shouldn't hold the queue for long.
time-limit-minutes: 5
---
# Task: ingest a source

Source folder: `$INPUT`

1. Read `meta.json` and the source (`source.md`, and look at any images) in that folder.
   If the folder has `part-1.md`, the source is long and is ingested in parts: read `part-1.md`
   instead of `source.md` (later parts are separate tasks), add `Covers: part 1 of <total>` under
   the summary of the source page, and log `## <today> ingest <slug> (part 1 of <total>)`.
2. Read `wiki/index.md`. If `wiki/sources/<slug>.md` already exists, this is a **re-ingest**: the
   source has been updated since. Fold in every fact that's missing from the pages that cite it
   (steps 3–5 apply to those facts only). Log it as `## <today> re-ingest <slug>`.
3. Write `wiki/sources/<slug>.md` (slug = the folder name). Front matter `type: source`, plus
   `url`, `added_by`, `added_at` from meta.json, and `projects: [<name>, ...]` once you know them.
   Body: 2–4 sentence summary, "Key points" (bullets), "Raw" link to the folder
   (`[[raw/YYYY/MM/<slug>/source|original]]`).
4. **Which project.** Find the project(s) the source is for: one it names, or whose subject,
   parts, tools or repo it's plainly about (`grep -ril` the project pages for its key names). A
   note sent with it ("for the home server") decides. Then, on each of those project pages:
   - A receipt, order confirmation or invoice → a row in `## Purchases` (date, item, kind, cost,
     seller), cited. Never a full card number or a license key.
   - An article, blog post, docs page, repo or video → a line in `## Links`: `[[sources/<slug>]]`
     and why it matters for the project.
   - Anything else (a spec sheet, a forum answer, an email) → the section it belongs in, usually
     `## Notes`, cited.
   Add the slug to the page's `sources`, and bump `updated`.
   If it fits no project, or you can't tell which, append to `_review/unfiled.md`:
   `- <today> [[sources/<slug>]]: <one line on what it is>`.
5. If the source teaches something that serves more than one project, or no project in
   particular (how a tool works, a technique), also add it to a `wiki/topics/` page: update an
   existing one, or create one if the source covers the subject substantially. `grep -ril`
   first. Cite `[[sources/<slug>]]`, list the projects under `## Used in`, add `Related` links
   both ways.
6. Give each page you created a `summary:` in its front matter (one line, for the index). Don't
   edit `wiki/index.md`: it's generated.
7. Add to the top of `wiki/log.md`, right under `# Log`: `## <today> ingest <slug>` then one
   bullet per page touched.
8. If the source refers to values that aren't in it (a table or chart with no numbers, an
   attachment that isn't in the folder), don't guess them. Append one line to
   `_review/missing-from-sources.md`:
   `- <today> [[raw/YYYY/MM/<slug>/source|<slug>]] — <what's missing>`

Reply with the list of pages created/updated, and the project(s) the source went to (or "unfiled").
