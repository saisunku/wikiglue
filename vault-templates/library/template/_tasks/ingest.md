---
# Measured with a 35B-A3B model: 2.7x faster than low, no facts lost.
thinking: off
# A reasonable source takes 20-90 s; a stuck job shouldn't hold the queue for long.
time-limit-minutes: 5
---
# Task: ingest a source

Source folder: `$INPUT`

1. Read `_config/library.md`, then `meta.json` and the source (`source.md`, and look at any
   images) in that folder.
   If the folder has `part-1.md`, the source is long and is ingested in parts: read `part-1.md`
   instead of `source.md` (later parts are separate tasks), add `Covers: part 1 of <total>` under
   the summary of the source page, and log `## <today> ingest <slug> (part 1 of <total>)`.
2. Read `wiki/index.md`. If `wiki/sources/<slug>.md` already exists, this is a **re-ingest**: the
   source has been updated since. Compare it line by line with the source page and the pages that
   cite it, and fold in every fact that's missing (steps 3–5 apply to those facts only). Don't stop
   at "already ingested". Log it as `## <today> re-ingest <slug>`.
3. Write `wiki/sources/<slug>.md` (slug = the folder name) from `_config/templates/source.md`:
   `url`, `added_by`, `added_at` from meta.json; `kind`, `authors`, `published` and `venue` from
   the source (leave out what it doesn't say). A video or talk page often has only a description
   or a partial transcript: say so in the summary, and don't describe what the video might contain.
   If the item is outside the library's scope (`_config/library.md`), write the source page only,
   with `tags: [out-of-scope]`, and skip to step 6.
4. Decide which pages this source should change (usually 1–5):
   - `wiki/topics/`: the ideas, techniques and problems it covers substantially;
   - `wiki/tools/`: software it evaluates, explains or reports using in earnest (not passing mentions);
   - `wiki/entities/`: its authors or organisation only if they already have a page, or the source
     is substantially about them.
   Update existing pages first; create new ones (from `_config/templates/topic.md` for topics)
   only for subjects the source covers substantially. `grep -ril` the wiki for each name and its
   abbreviations before creating anything.
5. Edit each of those pages: add what the source says, attributed and cited to
   `[[sources/<slug>]]`, add the slug to front matter `sources`, bump `updated`, add the source to
   the topic's `## Reading` list, and add `Related` links both ways. Fill the source page's
   `## Pages it informs`.
6. Give each page you created a `summary:` in its front matter (one line, for the index), and
   update the `summary:` of pages whose scope changed. Don't edit `wiki/index.md`: it's generated.
7. Add to the top of `wiki/log.md`, right under `# Log`: `## <today> ingest <slug>` then one bullet
   per page touched.
8. If the source refers to things that aren't in the folder (a figure, table or chart with no
   numbers in the text, a benchmark described but not given, slides that weren't captured), don't
   guess them. Append one line to `_review/missing-from-sources.md`:
   `- <today> [[raw/YYYY/MM/<slug>/source|<slug>]] — <what's missing, e.g. "latency figure 3 not in the text">`
9. If the source leans on another work you'd need to understand it (the paper it replies to, the
   original design doc), suggest it in `_review/research-requests.md`, unless it's there already:
   `- [ ] <title> — source: <url> — suggested search: "<query>" (cited by [[sources/<slug>]], <today>)`
   (`source: <url>` only if the source gives the link).

Reply with the list of pages created/updated.
