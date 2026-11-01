#!/usr/bin/env bash
# Apply the vault's access rules (POSIX ACLs, inherited by new files):
#
#   everyone below    read everything
#   <owner>           read/write everything, including files the services create
#   wikibot (pi)      write only wiki/ lists/ _review/
#   wikiglue          write only raw/ lists/ _review/
#   wikisite          read only (the Quartz site build)
#   group wiki        read only
#
#   sudo examples/lockdown/vault-acl.sh <vault> <owner>
#
# Idempotent; rerun after moving the vault (e.g. to the Google Drive folder).
set -euo pipefail
VAULT="$(cd "$1" && pwd)"; OWNER="$2"

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ -f $VAULT/AGENTS.md ]] || { echo "$VAULT doesn't look like the vault (no AGENTS.md)" >&2; exit 1; }

for d in raw wiki lists _review; do
  [[ -d $VAULT/$d ]] || install -d -o "$OWNER" -g "$OWNER" "$VAULT/$d"
done

# Start clean so a rerun never leaves stale grants behind.
setfacl -R -b "$VAULT"
read_all="u:$OWNER:rwX,u:wikibot:rX,u:wikiglue:rX,g:wiki:rX"
id wikisite >/dev/null 2>&1 && read_all+=",u:wikisite:rX"
setfacl -R -m "$read_all" "$VAULT"
find "$VAULT" -type d -exec setfacl -m \
  "d:u::rwX,d:g::rX,d:o::rX,${read_all//u:/d:u:}" {} +
find "$VAULT" -type d -exec setfacl -m "d:g:wiki:rX" {} +

grant() {  # grant <user> <dir>...
  local who=$1; shift
  for d in "$@"; do
    setfacl -R -m "u:$who:rwX" "$VAULT/$d"
    find "$VAULT/$d" -type d -exec setfacl -m "d:u:$who:rwX" {} +
  done
}
grant wikibot  wiki lists _review
grant wikiglue raw lists _review

echo "vault ACLs applied to $VAULT"
