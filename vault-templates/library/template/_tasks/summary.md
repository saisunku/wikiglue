---
# Combining many sources is reasoning, so thinking stays on (the default, low).
time-limit-minutes: 15
---
# Task: a summary page from a chosen set of sources

Request: $INPUT

The request starts with the summary's title. After it may come the sources to use (links like
`[[sources/<slug>]]`, slugs, or `raw/` folders), or a description of which sources to use, or
nothing.

1. **The page.** `wiki/summaries/<name>.md`, `<name>` the title in lowercase with hyphens. If a page
   in `wiki/summaries/` already has this title (or nearly), that's the page.
2. **The sources.** Exactly one of:
   - The request lists sources: use those, plus the ones already in the page's `sources:` if it exists.
     Find each one's `wiki/sources/<slug>.md` (a `raw/` folder's name is its slug). One you can't
     find: leave it out and name it in your reply. Never swap in a different source.
   - The request describes the sources: search `wiki/index.md` and `wiki/sources/` (`grep -ril`
     names, places, dates, senders) and take every source page that fits, and no others.
   - The request gives only the title and the page exists: use exactly the page's `sources:` list.
     A person may have edited it; it is the definition of the summary.
   - The request gives only the title and there's no page: change nothing, and reply asking which
     sources to use.
3. **Read** each source page. Open its `raw/` source only for details the source page leaves out
   (amounts, dates, names, terms). Use nothing that isn't in these sources: no other wiki pages,
   no general knowledge.
4. **Write the page.** Front matter: `title`, `type: summary`, a one-line `summary`, `sources:`
   (the slugs, in date order), `updated`. Then `# <title>` and:
   - A short overview (2–4 sentences): what these sources are about, the period they cover.
   - Sections by theme, as the material needs. A table where the sources hold comparable facts
     (quotes, prices, dates, options); a timeline where order matters. Cite every fact
     `([[sources/<slug>]])`.
   - **Open questions**: where sources disagree (cite both), and what's missing or undecided.
   - **Sources**: one line per source, `- [[sources/<slug>]] — <one line on what it adds>`.
   A new page: `write` it. A page that exists can't be overwritten: `edit` it section by section
   until it says what a fresh page would, with `sources:` set as decided in step 2.
5. Change no other page. Add to the top of `wiki/log.md`, right under `# Log`:
   `## <today> summary <name>` and one bullet: how many sources, and which were added or dropped.

Reply with: the page as `[[summaries/<name>]]`, then the sources used (one per line, their titles),
then any you couldn't find. If you picked the sources from a description, end with: "Edit
`sources:` on the page and send `summary: <title>` to rebuild it from exactly that list."
