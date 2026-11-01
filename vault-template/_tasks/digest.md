# Task: weekly digest

1. Read the entries in `wiki/log.md` from the last 7 days.
2. Read the `wiki/sources/` pages added this week (their `added_by` tells you who sent them).
3. Write `wiki/digests/<ISO year>-W<week>.md` (frontmatter `type: digest`):
   - **New this week** — each new source: one line, who added it (linked to their page if they're
     in `_config/family_data.md`), link.
   - **Wiki changes** — pages created and notably updated, with a few words on what changed.
   - **Cleanup** — a one-line summary of what lint fixed.
   - **Open research requests** — unchecked items in `_review/research-requests.md`.
   - **Gaps in sources** — lines from the last 7 days in `_review/missing-from-sources.md`
     (values the agent couldn't read from a source), if any.
4. Give the digest a one-line `summary:` in its front matter (the week and its highlights).

Reply with the digest text (under 250 words), nothing else.
