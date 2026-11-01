"""Chat command handling, driven by <vault>/_config/commands.toml.

A message that starts with a command's prefix runs that command; no model is
involved. With top-level `route = true`, any other plain message is routed by
the local model (see router.py): it picks among the commands that have a
`description` and that the sender may use, plus the default. Admin-only
commands are never routed. Each command names an action:

    append   write one line to a vault file (one per item when routed)
    pantry   set items to out/low/ok in the pantry table (see pantry.py)
    task     queue a pi task prompt with the message as its input; reply with the result
             (optional `format`, e.g. "{text} ({sender}, {date})", shapes that input)
    bookmark save to Karakeep as the sender; the inbox then copies it into raw/ and ingests it
    builtin  handled in code (ping, help, approve, requests, announce, queue)

Top-level `announce = ["shopping", "digest", "morning"]` lists scheduled tasks whose
results are posted to the room chosen with the `announce` command.

Example:

    [commands.need]
    prefix = "need:"            # default: "<name>:"
    action = "append"
    file   = "lists/needs.md"
    format = "- [ ] {text} — {sender}, {date}"
    roles  = ["admin", "member"]
    reply  = "Added to needs ✓"

    [default]                   # plain text: a question for the wiki
    description = "A question about anything in the wiki, or anything else"
    action = "task"
    task   = "_tasks/query.md"
    reply  = "result"

A message starting with a link, and every photo or PDF, is always saved
(bookmark), whatever the default says.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from . import pantry
from .approvals import ResearchRequests
from .config import ROLES, User
from .jobs import Jobs, task_name
from .karakeep import Karakeep, KarakeepError
from .router import Item, Route, Router
from .state import State

log = logging.getLogger(__name__)

ACTIONS = frozenset({"append", "pantry", "task", "bookmark", "builtin"})
BUILTINS = frozenset({"ping", "help", "approve", "requests", "announce", "queue"})
URL_RE = re.compile(r"^(https?://\S+)(?:\s+(.*))?$", re.S)


class React(str):
    """A reply sent as an emoji reaction to the message instead of a new message."""


@dataclass(frozen=True)
class Attachment:
    data: bytes
    filename: str
    content_type: str


@dataclass
class Services:
    """What the bookmark/task/approval actions need; absent in plain unit tests."""
    jobs: Jobs
    state: State
    session: aiohttp.ClientSession
    karakeep_url: str | None

    def karakeep(self, user: User) -> Karakeep | None:
        if not (self.karakeep_url and user.karakeep_key):
            return None
        return Karakeep(self.session, self.karakeep_url, user.karakeep_key)


@dataclass(frozen=True)
class Command:
    name: str
    prefix: str
    action: str
    roles: frozenset[str] = ROLES
    options: dict = field(default_factory=dict)

    @property
    def reply(self) -> str | None:
        return self.options.get("reply")

    @property
    def description(self) -> str | None:
        return self.options.get("description")


class CommandConfigError(Exception):
    pass


@dataclass(frozen=True)
class CommandSet:
    commands: tuple[Command, ...]
    default: Command
    announce: frozenset[str] = frozenset()
    route: bool = False

    @classmethod
    def parse(cls, raw: dict) -> CommandSet:
        commands = [_parse_command(name, spec) for name, spec in raw.get("commands", {}).items()]
        # Longest prefix first so "need more:" can't be shadowed by "need:".
        commands.sort(key=lambda c: len(c.prefix), reverse=True)
        default = _parse_command("default", raw.get("default", {"action": "bookmark"}), is_default=True)
        announce = raw.get("announce", [])
        if not (isinstance(announce, list) and all(isinstance(t, str) for t in announce)):
            raise CommandConfigError("announce must be a list of task names")
        route = raw.get("route", False)
        if not isinstance(route, bool):
            raise CommandConfigError("route must be true or false")
        return cls(tuple(commands), default, frozenset(announce), route)

    def routable(self, user: User) -> dict[str, Command]:
        """Commands the model may pick for this user's plain message, by name."""
        out = {c.name: c for c in self.commands
               if c.description and user.role in c.roles and c.roles != {"admin"}}
        out["default"] = self.default
        return out

    @classmethod
    def load(cls, path: Path) -> CommandSet:
        with path.open("rb") as f:
            return cls.parse(tomllib.load(f))

    def match(self, text: str) -> tuple[Command, str]:
        stripped = text.lstrip()
        lowered = stripped.lower()
        for cmd in self.commands:
            if lowered.startswith(cmd.prefix) and _ends_at_boundary(lowered, cmd.prefix):
                return cmd, stripped[len(cmd.prefix):].strip()
        return self.default, text.strip()


def _ends_at_boundary(text: str, prefix: str) -> bool:
    """A word-like prefix ("help") must be a whole word: "helpful tip" isn't "help"."""
    if not prefix[-1].isalnum() or len(text) == len(prefix):
        return True
    return text[len(prefix)].isspace()


def _parse_command(name: str, spec: dict, *, is_default: bool = False) -> Command:
    action = spec.get("action")
    if action not in ACTIONS:
        raise CommandConfigError(f"{name}: action must be one of {sorted(ACTIONS)}")
    if action == "builtin" and name not in BUILTINS:
        raise CommandConfigError(f"{name}: unknown builtin (have {sorted(BUILTINS)})")
    if action in ("append", "pantry") and "file" not in spec:
        raise CommandConfigError(f"{name}: {action} needs a 'file'")
    if action == "task" and "task" not in spec:
        raise CommandConfigError(f"{name}: task needs a 'task' prompt path")

    roles = frozenset(spec.get("roles", ROLES))
    if not roles <= ROLES:
        raise CommandConfigError(f"{name}: unknown roles {sorted(roles - ROLES)}")

    prefix = "" if is_default else spec.get("prefix", f"{name}:").lower()
    if not is_default and not prefix.strip():
        raise CommandConfigError(f"{name}: empty prefix")

    options = {k: v for k, v in spec.items() if k not in {"action", "roles", "prefix"}}
    return Command(name=name, prefix=prefix, action=action, roles=roles, options=options)


class Dispatcher:
    """Turns an allowlisted user's message into an action and a reply."""

    def __init__(self, vault: Path, commands_path: Path, services: Services | None = None,
                 router: Router | None = None):
        self.vault = vault.resolve()
        self.commands_path = commands_path
        self.services = services
        self.router = router
        self.requests = ResearchRequests(self.vault)
        # Chat approvals and Obsidian ticks act on the same file; one at a time.
        self._research_lock = asyncio.Lock()
        self._commands: CommandSet | None = None
        self._mtime: float | None = None

    @property
    def commands(self) -> CommandSet:
        self._reload_if_changed()
        if self._commands is None:
            raise CommandConfigError(f"no valid command config at {self.commands_path}")
        return self._commands

    def _reload_if_changed(self) -> None:
        try:
            mtime = self.commands_path.stat().st_mtime
        except FileNotFoundError:
            log.error("command config %s is missing", self.commands_path)
            return
        if mtime == self._mtime:
            return
        try:
            self._commands = CommandSet.load(self.commands_path)
            log.info("loaded %d commands from %s", len(self._commands.commands), self.commands_path)
        except (tomllib.TOMLDecodeError, CommandConfigError) as e:
            # Keep serving the last good config; a typo in Obsidian shouldn't take the bot down.
            log.error("invalid %s, keeping previous config: %s", self.commands_path, e)
        self._mtime = mtime

    async def handle(self, user: User, text: str, *, room_id: str = "", event_id: str = "",
                     attachment: Attachment | None = None) -> str | None:
        if attachment is not None:
            # Images and PDFs always go to the wiki inbox; the caption becomes the note.
            return await self._bookmark(user, text.strip(), room_id, event_id, attachment)

        cmd, arg = self.commands.match(text)
        if cmd is self.commands.default and URL_RE.match(arg):
            # A message that starts with a link is always something to save, whatever
            # the default for plain text is (the rest of the message becomes its note).
            return await self._bookmark(user, arg, room_id, event_id)
        if cmd is self.commands.default and self.commands.route and self.router and arg:
            return await self._routed(user, arg, room_id, event_id)
        return await self._run(cmd, user, arg, room_id, event_id)

    async def _run(self, cmd: Command, user: User, arg: str, room_id: str, event_id: str) -> str | None:
        if user.role not in cmd.roles:
            return f"Sorry, '{cmd.name}' isn't available to you."

        match cmd.action:
            case "append":
                return self._append(cmd, user, arg)
            case "pantry":
                return self._pantry_status(cmd)
            case "builtin":
                return await self._builtin(cmd, user, arg, room_id, event_id)
            case "bookmark":
                return await self._bookmark(user, arg, room_id, event_id)
            case "task":
                return self._task(cmd, user, arg, room_id, event_id)

    async def _routed(self, user: User, text: str, room_id: str, event_id: str) -> str | None:
        """Let the model pick the commands for a plain message, then run them."""
        choices = self.commands.routable(user)
        descriptions = {n: c.description or "Anything that fits no other command."
                        for n, c in choices.items()}
        routes = await self.router.route(text, descriptions, fallback="default")
        if not routes:
            return await self._run(self.commands.default, user, text, room_id, event_id)

        replies: list[str | None] = []
        whole_message_used = False  # task/bookmark get the full message; only once
        for route in _merge(routes):
            cmd = choices[route.command]
            if cmd.action == "append":
                replies.append(self._append_items(cmd, user, route.items))
            elif cmd.action == "pantry":
                replies.append(self._pantry(cmd, route.items))
            elif cmd.action in ("task", "bookmark"):
                if not whole_message_used:
                    whole_message_used = True
                    replies.append(await self._run(cmd, user, text, room_id, event_id))
            else:
                replies.append(await self._run(cmd, user, "", room_id, event_id))

        texts = [r for r in replies if r and not isinstance(r, React)]
        if texts:
            return "\n".join(texts)
        return next((r for r in replies if r), None)

    def _append_items(self, cmd: Command, user: User, items: tuple[Item, ...]) -> str:
        if not items:
            return f"Not sure what to add to {cmd.options['file']}; try “{cmd.prefix} …”."
        for item in items:
            self._append(cmd, user, item.name)
        return f"{cmd.reply or '✓'} — " + ", ".join(i.name for i in items)

    def _pantry(self, cmd: Command, items: tuple[Item, ...]) -> str:
        changes = [(i.name, i.status) for i in items if i.status]
        if not changes:
            return "Not sure which pantry items you meant, or whether they're out, low or stocked."
        done = pantry.update(self._vault_path(cmd.options["file"]), changes)
        return "Pantry: " + ", ".join(
            f"{name} → {new}" + (" (new)" if old is None else "") for name, old, new in done)

    def _pantry_status(self, cmd: Command) -> str:
        short = pantry.short(self._vault_path(cmd.options["file"]))
        if not short:
            return "Nothing in the pantry is low or out."
        return "\n".join(f"{name}: {status}" for name, status in short)

    def _task(self, cmd: Command, user: User, arg: str, room_id: str, event_id: str) -> str | None:
        if self.services is None:
            return f"'{cmd.name}' isn't wired up here."
        if not arg:
            return f"Usage: {cmd.prefix} <text>"
        if "format" in cmd.options:
            arg = cmd.options["format"].format(text=arg, sender=user.name, date=dt.date.today().isoformat())
        self.services.jobs.submit(
            task_name(cmd.options["task"]), arg, priority="chat", submitted_by=f"wikiglue:{user.key}",
            meta={"room": room_id, "event": event_id, "reply": cmd.reply or "result"},
        )
        return React("👀")

    async def _bookmark(self, user: User, text: str, room_id: str, event_id: str,
                        attachment: Attachment | None = None) -> str | None:
        kk = self.services.karakeep(user) if self.services else None
        if kk is None:
            return "Saving to the wiki isn't set up for you yet (no Karakeep account linked)."
        if attachment is None and not text:
            return None
        try:
            if attachment is not None:
                bm = await kk.add_file(attachment.data, attachment.filename,
                                       attachment.content_type, note=text or None)
            elif m := URL_RE.match(text):
                bm = await kk.add_link(m.group(1), note=(m.group(2) or "").strip() or None)
            else:
                bm = await kk.add_text(text)
        except (aiohttp.ClientError, KarakeepError) as e:
            log.warning("bookmark for %s failed: %s", user.key, e)
            return "Couldn't save that to Karakeep; it's in the wikiglue log."
        if bm.get("alreadyExists"):
            return "Already saved earlier — it's in the wiki (or on its way)."
        self.services.state.add_notify(bm["id"], room_id, event_id)
        return React("📥")

    def _append(self, cmd: Command, user: User, arg: str) -> str:
        if not arg:
            return f"Usage: {cmd.prefix} <text>"
        target = self._vault_path(cmd.options["file"])
        # One message = one line, so a message can't inject extra list items or frontmatter.
        text = " ".join(arg.split())
        line = cmd.options.get("format", "- {text}").format(
            text=text, sender=user.name, date=dt.date.today().isoformat()
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return cmd.reply or "✓"

    async def _builtin(self, cmd: Command, user: User, arg: str, room_id: str, event_id: str) -> str:
        match cmd.name:
            case "ping":
                return "pong"
            case "help":
                usable = [c for c in self.commands.commands if user.role in c.roles]
                lines = [f"{c.prefix.strip()} …  ({c.action})" for c in usable]
                default = self.commands.default
                rest = ("asked as a question" if default.action == "task"
                        else "saved to the wiki" if default.action == "bookmark" else default.action)
                lines.append("a link, photo or PDF → saved to the wiki")
                if self.commands.route and self.router:
                    lines.append(f"anything else → I work out which of these you mean, or it's {rest}")
                else:
                    lines.append(f"anything else → {rest}")
                return "\n".join(lines)
            case "requests":
                open_ = self.requests.open_requests()
                if not open_:
                    return "No open research requests."
                return "\n".join(f"{i}. {r.title}" + (f" ({r.url})" if r.url else "")
                                 for i, r in enumerate(open_, 1))
            case "approve":
                if not arg.isdigit():
                    return "Usage: approve <number>  (send 'requests' to see the numbers)"
                async with self._research_lock:
                    req = self.requests.approve(int(arg))
                    if req is None:
                        return f"There's no open request #{arg}; send 'requests' to see them."
                    return await self.research(req, user, room_id, event_id)
            case "queue":
                if self.services is None:
                    return "Not available here."
                return self.services.jobs.describe_status()
            case "announce":
                if self.services is None:
                    return "Not available here."
                self.services.state.put("announce_room", room_id)
                return "Scheduled results (shopping list, digest) will be posted in this room."
            case _:
                return f"'{cmd.name}' isn't wired up yet."

    async def research_ticked(self, approver: User) -> list[str]:
        """Requests ticked in Obsidian: act on them as `approver`; returns messages."""
        async with self._research_lock:
            out = []
            for req in self.requests.ticked_unhandled():
                try:
                    out.append(await self.research(req, approver))
                except (aiohttp.ClientError, KarakeepError, RuntimeError) as e:
                    log.warning("research request %r failed: %s", req.title, e)
            return out

    async def research(self, req, user: User, room_id: str = "", event_id: str = "") -> str:
        """Act on an approved (ticked) research request; returns a message for the approver."""
        if req.url is None:
            self.requests.mark_handled(req, "needs a source link")
            return (f"Approved “{req.title}”, but it has no source link. "
                    f"Search: {req.search_link} — send me the link you pick and I'll add it.")
        kk = self.services.karakeep(user) if self.services else None
        if kk is None:
            return "Can't fetch it: no Karakeep account is linked for you."
        bm = await kk.add_link(req.url, note=f"Research request: {req.title}")
        self.requests.mark_handled(req, f"fetching {req.url}")
        if room_id and not bm.get("alreadyExists"):
            self.services.state.add_notify(bm["id"], room_id, event_id)
        return f"Approved “{req.title}” — fetching {req.url}"

    def _vault_path(self, rel: str) -> Path:
        path = (self.vault / rel).resolve()
        if not path.is_relative_to(self.vault):
            raise CommandConfigError(f"{rel!r} is outside the vault")
        return path


def _merge(routes: list[Route]) -> list[Route]:
    """One route per command, items combined, in first-mentioned order."""
    merged: dict[str, list[Item]] = {}
    for r in routes:
        merged.setdefault(r.command, []).extend(r.items)
    return [Route(name, tuple(items)) for name, items in merged.items()]
