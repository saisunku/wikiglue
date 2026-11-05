---
tools: read,edit,grep,find,ls
time-limit-minutes: 8
---
# Task: review a few wiki pages for the nightly lint

Pages (why each is here):

$INPUT

Look at each page in turn, and finish one (make its edits) before starting the next. Don't read
the whole wiki or `wiki/log.md`: use `wiki/index.md`, `grep -ril` (file names only) and the pages
named below.

- **(changed)**: the page changed since the last lint.
  1. **Duplicates.** In `wiki/index.md`, look for another page about the same thing (same person,
     product, place, subject; a different name or spelling). If there is one, read it. If they're
     the same, merge into the better-named one: keep all citations and `sources`, point links to
     the other page at the kept one (`grep -rl` for them), replace the other's body with
     `Merged into [[...]].` and its front matter `type` with `redirect`.
     Trip pages (`wiki/trips/`): `grep` the other trips' `start:` and `end:`. Two trips whose dates
     overlap and that share a traveller (or don't list any) are one trip: merge them the same way,
     keeping every booking and itinerary day, with the title, `destination`, `start`/`end` and
     summary covering both.
     Pages in `wiki/summaries/` are never merged.
  2. **Contradictions.** Read the pages it links to under `Related` (at most five). Where a claim
     disagrees with one of them, or with another part of the page, make the disagreement explicit
     on both pages, with both citations. Don't pick a side unless one source is plainly newer and
     says it replaces the other.
- **(stale)**: not updated in over a year. Claims about things that change (prices, versions,
  "latest", "currently", stats) whose newest source is over a year old: mark them
  `(as of <source date>)`. For important ones, append a research suggestion to
  `_review/research-requests.md`, unless it's already there:
  `- [ ] <topic>: <what may be outdated> — source: <url> — suggested search: "<query>" (lint <today>)`
  (`source: <url>` only for a specific, reputable page you know covers it).

Don't edit `wiki/log.md`: the lint writes one entry for the night from your reply.

Reply with one line per change, and nothing else:
`- [[<page>]]: <what you changed>`
If nothing needed changing, reply `No changes.`
