---
tools: read,edit,grep,find,ls
---
# Task: answer a question from the library

Question: $INPUT

1. Search the wiki (`wiki/index.md`, then `grep`/`find`) for relevant pages and read them: topic
   and tool pages first, then the source pages they cite for detail.
2. Answer from what the wiki says, in a few sentences or bullets, citing pages as `[[path]]`.
   Say whose claim each point is when the sources are opinions or measurements, and where they
   disagree. If asked what to read, recommend sources from the wiki, with a line on why each.
3. If the wiki doesn't cover it, say so plainly. Do not answer from general knowledge.
   If it's worth reading up on, append a line to `_review/research-requests.md`:
   `- [ ] <short description> — source: <url> — suggested search: "<query>" (from a question asked <today>)`
   Include `source: <url>` only if you know a specific, reputable page that covers it (the paper,
   the project's docs). An approved request fetches exactly that page. Otherwise leave it out.

When asked a question, do not edit the wiki pages. Reply with the answer only.

When explicitly asked to edit a page, edit the specified page only. Do not edit other pages.
Record such edits in the log: add to the top of `wiki/log.md`, right under `# Log`,
`## <today> edit <page>` then one bullet per change.
