# wikiglue

Inspired by [Karpathy's LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
but for multiple users (e.g. families)

Keep an Obsidian wiki up to date with a local model, from what your household
sends it (links, photos, PDFs, emails, chat messages), without ever giving that
model the internet.

wikiglue is the glue around a headless coding agent
([pi](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)) and a local
[llama.cpp](https://github.com/ggml-org/llama.cpp) server:

- **Chat.** A Matrix bot with end-to-end encryption that works with Element X.
  Commands come from a TOML file in the vault. Plain messages are routed by the
  local model to one of those commands, through a JSON schema and with no tools.
- **Bookmarks.** New [Karakeep](https://karakeep.app) bookmarks (share sheet,
  browser extension, links and photos sent in chat) become sources in `raw/`.
  They include images, PDFs, and the fact boxes and small tables that article
  extraction drops.
- **Email.** Messages in a Gmail label (downloaded by mbsync), or sent to a shared
  address, become sources too. Booking confirmations land on the trip's page.
- **One job queue.** Ingests, questions and scheduled tasks all go through a
  folder queue to a single runner. Scheduled tasks include a nightly lint, a weekly
  shopping list, a weekly digest and a morning message. More urgent work
  pauses less urgent work (see [The job queue](#2-the-job-queue)).
- **Summaries on demand.** `summary: Kitchen remodel` plus a list of sources, or a
  description of them, writes one page from just those sources. The page's
  `sources:` list defines it: edit the list in Obsidian and send the title again to
  rebuild it.
- **Research requests.** The model can suggest a source to fetch, but nothing is
  fetched until a person approves it.

## How it fits together

```
 Matrix ──┐                         ┌─► raw/YYYY/MM/<slug>/   sources, never edited
 Karakeep ├─► wikiglue ─────────────┤
 Maildir ─┘   network: chat,        └─► jobs/queue/*.job
              Karakeep, localhost              │
                     ▲                         ▼
                     │                    wiki-runner ──► pi ──► llama-server
                     │                    network: the model server only
                     │                         │
                     └── jobs/done/*.json ◄────┤
                         (replies to post)     ▼
                                  wiki/  lists/  _review/   the only writable folders
```

| Folder | What it is |
|---|---|
| `src/wikiglue/` | The service: chat transport, commands, model routing, Karakeep and mail inboxes, approvals, the results poster |
| `runner/` | `wiki-runner` (the queue), `wiki-job` (submit a job), `run-task.sh` (one pi run), `wiki-index` (rebuilds `wiki/index.md`), `wiki-morning` and `wiki-lint` (scheduled tasks done in small steps), pi's config and system prompt |
| `vault-template/` | `AGENTS.md` (the wiki's rules for the model), `_tasks/` (one prompt per job type), `_config/` (chat commands, page templates) |
| `vault-starter/` | Empty lists and review pages for a new vault |
| `examples/` | systemd units, nftables rules, Docker Compose files for Synapse and Karakeep, cron schedule, vault ACLs, hourly git snapshots |
| `docs/` | [The job protocol](docs/protocol.md) and [the security model](docs/security.md) |

## Security model

The model reads untrusted text: web pages, emails, other people's messages. So the
design assumes a prompt injection will eventually succeed, and limits what it can
do when it does.

- **The process that runs the model** (`wiki-runner` and pi, as user `wikibot`) can
  reach only the llama.cpp server. It can write only `wiki/`, `lists/` and
  `_review/`. pi gets file tools and no shell. The worst outcome is bad edits to
  wiki pages, and a git snapshot of the vault can undo those.
- **The process that talks to the outside** (wikiglue) never runs the agent. It
  asks the model only for a routing choice, constrained to JSON, and then runs
  that command with the same permission checks as a typed one.
- **The job folder is the only link between them.** A job names a task file in
  `_tasks/` and gives it some text; it can't name a command.
- **The internet is reached only on a person's say-so.** Karakeep's crawler fetches
  what people bookmark, and what an admin approves from `_review/research-requests.md`.

`examples/systemd/` and `examples/nftables/` enforce this with per-user egress
rules, `IPAddressDeny`, `ProtectSystem=strict` and vault ACLs. More in
[docs/security.md](docs/security.md).

## Requirements

- Linux with systemd, Python 3.12+, and libolm (for Matrix encryption)
- llama.cpp `llama-server` with a model that handles tool calls well (and vision,
  for photos). Developed with a 35B-A3B mixture-of-experts model on one 24 GB GPU;
  an ingest takes 20–90 s.
- Node.js 22.19 or newer, for pi
- Synapse and Karakeep (`examples/compose/`), and mbsync if you want email
- An Obsidian vault, synced however you like

## Try it first

The agent and the queue run from a checkout as your own user, with no services, no
root and no chat. All you need is a llama-server on `127.0.0.1:8080` whose `--alias`
matches the model `id` in `runner/pi-home/models.json` (edit either).

```sh
git clone <this repo> wikiglue && cd wikiglue
(cd runner/pi-runtime && npm ci)
mkdir -p ~/wiki-try/vault ~/wiki-try/jobs
cp -r vault-template/. vault-starter/. ~/wiki-try/vault/      # a new, empty vault

cp -r runner/pi-home ~/wiki-try/pi-home
export PI_CODING_AGENT_DIR=~/wiki-try/pi-home WIKI_JOBS=~/wiki-try/jobs
runner/wiki-runner --root ~/wiki-try/jobs --vault ~/wiki-try/vault &

runner/wiki-job --wait query "What's in the wiki so far?"
```

To ingest something without Karakeep or chat, write a source the way wikiglue does
([docs/protocol.md](docs/protocol.md)) and queue it:

```sh
d=~/wiki-try/vault/raw/2026/11/2026-11-sourdough-note && mkdir -p $d
echo "Feed the starter 1:1:1 twelve hours before mixing; it's ready when it has doubled." > $d/source.md
echo '{"title": "Sourdough note", "url": null, "added_by": "Alex", "added_at": "2026-11-04", "kind": "note"}' > $d/meta.json
runner/wiki-job --wait ingest raw/2026/11/2026-11-sourdough-note
```

Open `~/wiki-try/vault` in Obsidian to see the pages it wrote. This mode has none of the
sandboxing below: pi runs as you, so try it on a vault you don't mind losing.

## Installing as services

With the sandbox: separate users, the network rules and the vault ACLs. Every path
below is the one the examples use; change them together if you change one.

1. **Users:** `sudo cp examples/sysusers/wiki.conf /etc/sysusers.d/ && sudo systemd-sysusers`.
2. **Network rules:** `sudo cp examples/nftables/wikiguard.nft /etc/`, then the
   `wikiguard-nft` unit. Check the model server's address and port in the file.
3. **The model server:** adapt `examples/systemd/llama-server.service` (model, device, alias).
4. **The runner and pi:**
   ```sh
   (cd runner/pi-runtime && npm ci)      # as yourself: npm runs package scripts
   sudo cp -r runner /opt/wiki-runner
   sudo install -d -o root -g wikibot -m 1770 /var/lib/wikibot/pi-home
   sudo cp runner/pi-home/*.json /var/lib/wikibot/pi-home/
   sudo install -d -o wikibot -g wiki -m 2770 /var/lib/wiki-jobs /var/lib/wiki-jobs/{queue,done}
   sudo install -d -o wikibot -g wikibot -m 700 /var/lib/wiki-jobs/running
   ```
   If node isn't on the service's `PATH` (an nvm install, say), copy it to
   `/opt/wiki-runner/node/bin/` or change `NODE_BIN` in the unit.
5. **The vault:** a new one with `cp -r vault-template/. vault-starter/. <vault>/`. Then
   `sudo examples/lockdown/vault-acl.sh <vault> <you>` sets who may write where. The
   services see it at `/srv/wiki/vault`, through a drop-in for `wiki-runner` and `wikiglue`:
   `/etc/systemd/system/<unit>.service.d/vault.conf` holding `[Service]` and
   `BindPaths=<vault>:/srv/wiki/vault`.
6. **wiki-runner:** `examples/systemd/wiki-runner.service`, and `examples/cron/wiki-jobs` as
   `/etc/cron.d/wiki-jobs` for the schedules. Test it:
   `sudo -u wikibot /opt/wiki-runner/wiki-job --wait query "What's in the wiki so far?"`.
7. **wikiglue:**
   ```sh
   sudo python3 -m venv /opt/wikiglue/venv && sudo /opt/wikiglue/venv/bin/pip install .
   sudo install -d -o root -g wiki -m 750 /etc/wikiglue
   sudo cp examples/wikiglue.toml /etc/wikiglue/      # then edit: users, Matrix, Karakeep, mail
   ```
   Synapse and Karakeep come from `examples/compose/`. Put the bot's Matrix access token in
   `/etc/wikiglue/matrix_token` and each person's Karakeep API key in the file their entry
   names, all readable by group `wiki` only. Then `examples/systemd/wikiglue.service`.

`examples/history/snapshot.sh` keeps a git history of the vault, so a bad edit can be undone.

## Chat commands

Commands live in the vault, so you edit them in Obsidian and wikiglue reloads them
on save. The model can't change them.

```toml
[commands.need]                 # "need: oat milk", or just "we're out of oat milk"
description = "Add things to the shopping list."
action = "append"
file   = "lists/needs.md"
format = "- [ ] {text} — {sender}, {date}"
```

Actions: `append` (a line to a file), `pantry` (set items to out/low/ok),
`task` (run a `_tasks/` prompt with the message), `bookmark` (save to Karakeep,
then ingest) and built-ins (`help`, `queue`, `requests`, `approve`, `announce`).
The full reference is at the top of
[vault-template/_config/commands.toml](vault-template/_config/commands.toml).

## From message to answer

Every message takes the same path: pick a command, then, if the command needs the
agent, queue a job. Only the second step can be slow, and the queue makes sure it
is slow for the nightly lint rather than for a question in chat.

### 1. Picking a command

Nobody remembers prefixes. A message that starts with one (`need: oat milk`) runs
that command directly, with no model involved. Any other message (`we're out of
oat milk and the dog food is low`) is routed by the local model, set by
`route = true` in `commands.toml`:

- **Choices:** the model sees the first 100 words of the message and the
  `description` of each command the sender may use. Commands without a
  description, and admin-only commands, are never offered. `[default]` is the
  fallback; in the template it asks the wiki a question.
- **Constrained answers:** llama-server enforces a JSON schema while generating:
  one to three command names from that list, each with up to ten short items
  (`"oat milk"`, `"dog food: low"`). The model has no tools, never sees the
  vault, and answers without thinking first (temperature 0, thinking off).
- **Nothing the model writes is trusted:** wikiglue parses the answer again, drops
  unknown commands, and strips Markdown from items before appending them. It then
  runs the chosen commands with the same role checks as typed prefixes. `task` and
  `bookmark` commands get the sender's original message, never the model's version.
- **Failure is harmless:** if no server answers, or the answer doesn't parse, the
  message goes to the default command.

Write descriptions for the model, with an example of what the items should look
like; they are the routing prompt.

`append` and `pantry` commands finish here. `task` and `bookmark` commands queue a job.

### 2. The job queue

One model server, one job at a time, and jobs of very different urgency: a question
in chat should get an answer in seconds, while the nightly lint can take ten
minutes. `wiki-runner` handles this with three priorities and preemption.

| Priority | Jobs | Behaviour |
|---|---|---|
| `chat` | questions and notes sent in chat | first in line; **pauses** a running ingest or background job |
| `interactive` | ingests, `wiki-job` from a shell | next; **pauses** a running background job |
| `background` | lint, shopping list, digest, morning message | last |

- **Routing never waits for a job:** llama-server runs two slots (`--parallel 2`).
  Jobs use one; routing uses the other, one request at a time, so a message is
  routed straight away even while a long ingest runs.
- **Pausing:** when a job arrives with a higher priority than the running one, the
  runner sends `SIGSTOP` to the running job's whole process group, runs the more
  urgent work, then sends `SIGCONT`. No restart, no lost context: the paused job
  continues mid-thought. Jobs of equal priority never pause each other.
- **Fair resumption:** a paused job resumes before any newer job of its own
  priority starts. A long article split into several ingest jobs is paused for a
  chat question, then carries on, ahead of the next bookmark. Paused jobs stack:
  chat can pause an ingest that had paused lint, and they resume in that order.
- **Time limits count running time only:** a paused job doesn't time out, and the
  result file records `active_seconds` and `paused_seconds` separately.
- **No stale overwrites:** while a job is paused, the job that pre-empted it may
  change the same pages. Existing pages change only through pi's `edit`, which
  replaces an exact piece of text, so if the page changed underneath, the edit
  fails and the model re-reads the page. `runner/no-overwrite.ts` stops `write`
  from replacing an existing file. Background tasks don't get `write` at all
  (`tools:` in the task's front matter).
- **Limits:** each task sets `time-limit-minutes:` (default 30); a job that runs over
  is killed and reported as `timeout`. A job interrupted by a crash or reboot is
  retried once.
- **Fallback servers:** each job runs on the first llama.cpp server in pi's
  `models.json` that answers `/health`. When none answers, jobs wait.
- **Reloading:** `systemctl reload wiki-runner` (SIGHUP) finishes the current job,
  then re-executes the runner with new code.

wikiglue's `queue` chat command shows what's running, paused and waiting.

## Reading the wiki

The vault is plain Markdown, so Obsidian is enough. To let the household read the
wiki in a browser, without Obsidian or access to the vault, serve it as a static
site with [Quartz](https://quartz.jzhao.xyz):

- **Content:** copy `wiki/` (as the site root), `lists/` and, if you like, the
  sources in `raw/` into Quartz's content folder, then run `npx quartz build`.
  Rebuild whenever the vault changes; a timer every minute or so is enough.
- **Leave out retired pages:** the agent can't delete files, so it turns
  merged or retired pages into `type: redirect`. Skip those when copying.
- **Check front matter while copying:** the agent writes the YAML headers, and one
  bad header fails the whole Quartz build. Quote values with an unquoted `: `,
  or drop the header and log it.
- **Make remote images links:** on every page, not just clipped sources, turn
  `![…](https://…)` and `<img src="https://…">` into plain links, so a page the agent
  was tricked into writing can't send data out through an image URL
  ([docs/security.md](docs/security.md)).
- **Keep it offline:** build as a user with no network, and in `quartz.config.ts` set
  `analytics: null`, `fontOrigin: "local"` and `cdnCaching: false`, so the site
  contacts no third parties.
- **Serve it locally:** any static file server on `127.0.0.1`, behind the same reverse
  proxy as Synapse and Karakeep.

The site build isn't part of this repo yet.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

## Status

Built for, and run by, one household on one machine. Matrix is the only chat
transport so far; `src/wikiglue/transports/base.py` is the interface for others.
Prompts and tasks are in English, and the task prompts are tuned to the model it
was developed with.

## License

MIT
