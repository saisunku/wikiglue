---
tools: read,edit,grep,find,ls
---
# Task: answer a question from the projects wiki

Question: $INPUT

1. Search the wiki (`wiki/index.md`, then `grep`/`find`) for relevant pages and read them. For a
   question about a project, its page first.
2. Answer from what the wiki says, in a few sentences or bullets, citing pages as `[[path]]`.
   - "Where is it" / "what's next" / "where was I": from Files and folders, Next steps (open
     items) and Current status, with the latest Claude Code session.
   - Spending: add up the matching Purchases rows, show the rows, and say what currency and
     period (subscriptions) they're in. Don't convert currencies.
3. If the wiki doesn't cover it, say so plainly. Do not answer from general knowledge.
   If it's worth looking up, append a line to `_review/research-requests.md`:
   `- [ ] <short description> — source: <url> — suggested search: "<query>" (from a question asked <today>)`
   Include `source: <url>` only if you know a specific, reputable page that covers it.

When asked a question, do not edit the wiki pages. Reply with the answer only.

When explicitly asked to edit a page, edit the specified page only. Do not edit other pages.
Record such edits in the log: add to the top of `wiki/log.md`, right under `# Log`,
`## <today> edit <page>` then one bullet per change.
