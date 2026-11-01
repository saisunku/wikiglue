#!/usr/bin/env bash
# Run one wiki task with pi, headless.
#
#   runner/run-task.sh <vault> <task-name> [input]
#
# <task-name> is a prompt in <vault>/_tasks/<task-name>.md; "$INPUT" in it is
# replaced with [input]. Prints pi's final reply on stdout.
#
# pi gets file tools only (no bash, no MCP, no skills), runs offline,
# and loads AGENTS.md from the vault as its rules. system-prompt.md (next to this script)
# replaces pi's own coding-agent system prompt, which speaks of running commands. Its one extension, no-overwrite.ts,
# lets `write` create files but not replace existing ones. Network and filesystem
# isolation are enforced outside pi: runner/wiki-runner runs this as the wikibot user
# inside examples/systemd/wiki-runner.service (nftables + IPAddressDeny, vault ACLs).
set -euo pipefail

VAULT="$(cd "$1" && pwd)"; TASK="$2"; INPUT="${3:-}"
[[ $TASK =~ ^[a-z0-9_-]+$ ]] || { echo "bad task name: $TASK" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$VAULT/_tasks/$TASK.md"
[[ -f $PROMPT_FILE ]] || { echo "no such task: $PROMPT_FILE" >&2; exit 2; }

# A task whose front matter says `script: <name>` runs that script instead (it may run other
# tasks through this one). Only the scripts listed here, next to this one, can be named, so a
# task file can't name a command.
SCRIPT="$(awk 'NR==1 && $0!="---" {exit} NR>1 && $0=="---" {exit} NR>1 && /^script:/ {print $2}' "$PROMPT_FILE")"
case $SCRIPT in
  "") ;;
  wiki-morning) exec python3 "$HERE/wiki-morning" "$VAULT" ;;
  wiki-lint) exec python3 "$HERE/wiki-lint" "$VAULT" ;;
  *) echo "unknown script in $PROMPT_FILE: $SCRIPT" >&2; exit 2 ;;
esac

export PI_CODING_AGENT_DIR="${PI_CODING_AGENT_DIR:-$HERE/pi-home}"
export PI_OFFLINE=1 PI_SKIP_VERSION_CHECK=1 PI_TELEMETRY=0
PI="${PI_BIN:-$HERE/pi-runtime/node_modules/.bin/pi}"
# NODE_BIN: where node lives, if it is not on the service's PATH (e.g. an nvm install).
if [[ -n ${NODE_BIN:-} ]]; then export PATH="$NODE_BIN:$PATH"; fi

# A task file may start with a front-matter block choosing pi's tools and
# thinking level, e.g.
#   ---
#   tools: read,edit,grep,find,ls
#   thinking: off
#   ---
# (no "write": the task can only make targeted edits). Defaults: all file tools,
# thinking low. Anything beyond the six file tools is ignored. PI_THINKING in the
# environment overrides the task's level (handy for benchmarks).
{ read -r TOOLS; read -r THINKING; IFS= read -r -d '' prompt || true; } < <(INPUT="$INPUT" python3 -c '
import os, re, sys
text = open(sys.argv[1]).read()
tools = "read,edit,write,grep,find,ls"
thinking = "low"
m = re.match(r"---\n(.*?)\n---\n", text, re.S)
if m:
    text = text[m.end():]
    t = re.search(r"^tools:\s*([a-z,]+)\s*$", m.group(1), re.M)
    if t:
        tools = t.group(1)
    t = re.search(r"^thinking:\s*(off|minimal|low|medium|high)\s*$", m.group(1), re.M)
    if t:
        thinking = t.group(1)
# Never more than the file tools, whatever the task file says.
allowed = {"read", "edit", "write", "grep", "find", "ls"}
print(",".join(x for x in tools.split(",") if x in allowed) or "read")
print(thinking)
print(text.replace("$INPUT", os.environ["INPUT"]), end="")
' "$PROMPT_FILE")
prompt="Today is $(date +%F) (ISO week $(date +%G-W%V)).

$prompt"

# PI_SESSION_DIR (set by wiki-runner) keeps the transcript for later inspection.
if [[ -n ${PI_SESSION_DIR:-} ]]; then SESSION_ARGS=(--session-dir "$PI_SESSION_DIR"); else SESSION_ARGS=(--no-session); fi
# PI_PROVIDER (set by wiki-runner): the llama.cpp server to use, a provider in models.json.
# Without it, pi uses the default one in settings.json.
MODEL_ARGS=()
if [[ -n ${PI_PROVIDER:-} ]]; then
  model="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["defaultModel"])' \
    "$PI_CODING_AGENT_DIR/settings.json")"
  MODEL_ARGS=(--provider "$PI_PROVIDER" --model "$model")
fi

# PI_SYSTEM_PROMPT set but empty: pi's own system prompt instead (to compare them).
SYSTEM_PROMPT="${PI_SYSTEM_PROMPT-$HERE/system-prompt.md}"
PROMPT_ARGS=()
[[ -n $SYSTEM_PROMPT ]] && PROMPT_ARGS=(--system-prompt "$SYSTEM_PROMPT")

cd "$VAULT"
# stdin must be closed: in print mode pi reads piped stdin as extra prompt and
# would otherwise wait forever when launched from a non-tty parent.
exec </dev/null
exec "$PI" -p \
  "${SESSION_ARGS[@]}" "${MODEL_ARGS[@]}" --no-mcp --no-extensions --no-skills --no-prompt-templates --no-themes \
  -e "$HERE/no-overwrite.ts" \
  "${PROMPT_ARGS[@]}" \
  --no-approve \
  --tools "$TOOLS" \
  --thinking "${PI_THINKING:-$THINKING}" \
  -- "$prompt"
