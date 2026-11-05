---
tools: read,edit,grep,find,ls
# Mechanical fixes with the answer mostly given. With thinking on, the model planned every edit
# before making the first and ran out of output tokens (2026-11-04).
thinking: off
time-limit-minutes: 8
---
# Task: fix problems the nightly lint found

Problems, by page:

$INPUT

Fix each one, editing only the pages listed. Work one page at a time: read it, make its edits,
then go on to the next. Fix only the problems listed, even if you notice others; the lint will
find those itself.

- **A link that points at nothing.** `[[a/b]]` needs `a/b.md` (or a file named exactly `a/b`, like
  an image).
  - Links into `raw/` must name a file in a source's folder, usually its `source.md`:
    `[[raw/YYYY/MM/<slug>/source|original]]`. When the problem gives the right target, use it.
    Never remove the brackets from a raw link.
  - Other links: if one of the closest pages listed is the page meant (read it to check), point the
    link there; if none is, or none is listed, `find` once for the page under another name, and
    otherwise remove the brackets and keep the text.
- **An image loaded from the internet.** Make it a plain link, keeping its text:
  `![chart](https://…)` or `<img src="https://…">` becomes `[image: chart](https://…)`.
- **No `title:` or `summary:`.** Read the page and add it: the title as in its `# ` heading, the
  summary one line on what the page covers (it's shown in the index). Don't edit `wiki/index.md`.
- **Front matter the website can't read.** Put the value in double quotes, with any double quotes
  inside it made single: `summary: "Order #486471: 2 items, 'express'"`. Change nothing else.
- **Orphan.** `grep -ril` the wiki for the page's main subject and add a `Related` link to it from
  the most relevant page (and one back, if the orphan has no `Related` section linking that page).
- **A credits row past its Expires date.** Delete the row and add a line under "Used or expired",
  as the page's comment there says. **A returns row past its Return by date:** move it under
  "Done" as "past return-by date".

Pages in `wiki/summaries/` keep their `sources:` list; fix only their links and front matter.
Don't edit `wiki/log.md`: the lint writes one entry for the night from your reply.

Reply with one line per change, and nothing else:
`- [[<page>]]: <what you changed>`
If a problem turned out not to need a change, leave it out. If nothing changed, reply `No changes.`
