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

- A model that writes plausible but wrong facts into the wiki. Read what it writes;
  `lint` flags contradictions and stale claims.
- Someone who can already send messages as a family member, or edit the vault.
- Karakeep's crawler fetching a malicious page. It runs in its own container with
  no access to the vault or the model.
