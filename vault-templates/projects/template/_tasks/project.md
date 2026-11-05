---
tools: read,edit,write,grep,find,ls
thinking: off
time-limit-minutes: 5
---
# Task: update a project from chat

Message: $INPUT

The message is an update about one project (it ends with who sent it and when). It may hold any
mix of: progress, plans, a Claude Code session, files or folders, a purchase, links, a decision,
a change of status, or the start of a new project.

1. **Which project.** Read `wiki/index.md` (the project sections). Match the message to a project
   by its name, repo, folder or plain subject; `grep -ril` the project pages if unsure.
   - It names a new project ("new project: ...", "starting ..."), and none matches: create
     `wiki/projects/<name>.md` from `_config/templates/project.md`, status `idea` unless the
     message says work has started (`active`), `started` = the message date.
   - None matches and it isn't new, or it could be more than one: change nothing, and reply with
     one question naming the closest projects.
2. **Read the project page**, and `_config/workspace.md` if the message mentions files or folders.
3. **File each item** on the page, citing it `(chat, <message date>)` (not the sender's name):
   - Something done or reached → a `## Progress log` line (newest first); tick the matching
     `## Next steps` item with the date; rewrite `## Current status` if the picture changed.
   - Something to do next → `## Next steps`, in the order the message gives.
   - A Claude Code session (a `claude.ai/code/session_` link, a session name or ID, or "a Claude
     Code session") → a row in `## Claude Code sessions`: date, the link or ID, the folder if
     given, what it did. If it got something done, also a Progress log line linking the session.
   - A file or folder → a row in `## Files and folders`: the path exactly as given, in backticks;
     the machine as named in `_config/workspace.md` (the message's, or leave it blank); what's there.
     Don't add a path that's already listed; update its row instead.
   - A purchase → a row in `## Purchases`: date (the message's if none is given), item, kind,
     cost as given, seller. Never a full card number or license key.
   - A link (blog, website, docs, repo, video) → `## Links`, with why it matters if the message says.
   - A decision → `## Decisions`, with the reason given.
   - A status change (paused, done, dropped, picked up again) → `status:` in the front matter
     (and `finished:` for done or dropped), and a Progress log line.
   Anything else about the project goes under `## Notes`.
4. Bump `updated:`, and update `summary:` if the project's one-line state changed.
5. Add to the top of `wiki/log.md`, right under `# Log`: `## <today> project <name>` then one
   bullet per change.

Reply in one or two short lines: the project as `[[projects/<name>]]` and what was filed where
("progress, 1 session, 2 next steps"). If you created the project, say so.
