"""Picking a chat command for a plain message with the local model.

Only used when a message matches no prefix. The model sees the first
ROUTER_WORDS words of the message and the descriptions of the commands the
sender may use, and must answer with JSON that fits a schema llama-server
enforces while generating: one to three command names from that list, each
with optional short items ("eggs", "butter: out"). It has no tools and never
sees the vault. Whatever it answers, wikiglue only runs those commands, with
the same role checks as typed prefixes, and task/bookmark commands get the
sender's full original message, not anything the model wrote.

llama-server runs two slots (--parallel 2), so a routing request takes the
free one instead of waiting behind a running pi job. Each request goes to the
free slot whose cached prompt matches best, which keeps routing and pi apart.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

ROUTER_WORDS = 100
TIMEOUT_SECONDS = 30
CONNECT_SECONDS = 3   # a server that's off: move on to the next one quickly
MAX_ACTIONS = 3
MAX_ITEMS = 10
ITEM_CHARS = 60
STATUSES = ("out", "low", "ok")

SYSTEM = """\
You route chat messages sent to a family wiki bot. Pick the commands the message \
asks for and extract their items. Most messages need exactly one command; use more \
only when the message clearly asks for several things. If unsure, use {fallback}.

Commands:
{commands}

Answer with JSON only."""


@dataclass(frozen=True)
class Item:
    name: str
    status: str | None = None


@dataclass(frozen=True)
class Route:
    command: str
    items: tuple[Item, ...] = ()


def schema(names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"actions": {
            "type": "array", "minItems": 1, "maxItems": MAX_ACTIONS,
            "items": {
                "type": "object",
                "properties": {
                    "command": {"enum": names},
                    "items": {"type": "array", "maxItems": MAX_ITEMS, "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "maxLength": ITEM_CHARS},
                                       "status": {"enum": list(STATUSES)}},
                        "required": ["name"],
                    }},
                },
                "required": ["command"],
            },
        }},
        "required": ["actions"],
    }


class Router:
    def __init__(self, session: aiohttp.ClientSession, urls: Sequence[str]):
        """`urls`: llama.cpp servers, first choice first; the next is tried if one can't be reached."""
        self.session = session
        self.urls = [u.rstrip("/") + "/v1/chat/completions" for u in urls]
        self._lock = asyncio.Lock()  # one at a time, so routing never takes both slots

    async def route(self, text: str, choices: dict[str, str], fallback: str) -> list[Route] | None:
        """Commands for `text`, chosen from `choices` (name -> description).

        None when the model can't be reached or answers nonsense; the caller
        then uses its default.
        """
        words = " ".join(text.split()[:ROUTER_WORDS])
        names = list(choices)
        system = SYSTEM.format(fallback=fallback,
                               commands="\n".join(f"- {n}: {d}" for n, d in choices.items()))
        body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": words}],
            "temperature": 0,
            "max_tokens": 300,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "route", "schema": schema(names)}},
        }
        answer = None
        async with self._lock:
            for url in self.urls:
                try:
                    async with self.session.post(
                        url, json=body,
                        timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS, sock_connect=CONNECT_SECONDS),
                    ) as resp:
                        resp.raise_for_status()
                        answer = (await resp.json())["choices"][0]["message"]["content"]
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError, ValueError) as e:
                    log.warning("routing via %s failed: %s", url, e)
        if answer is None:
            log.warning("routing failed, using the default")
            return None
        routes = parse(answer, names)
        log.info("routed %d words -> %s", len(words.split()), routes)
        return routes


def parse(answer: str, names: list[str]) -> list[Route] | None:
    """The model's JSON as Routes; re-checked here rather than trusting the grammar."""
    try:
        actions = json.loads(answer)["actions"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(actions, list):
        return None
    routes = []
    for a in actions[:MAX_ACTIONS]:
        if not isinstance(a, dict) or a.get("command") not in names:
            continue
        items = []
        for i in (a.get("items") or [])[:MAX_ITEMS]:
            if not isinstance(i, dict):
                continue
            name = clean(str(i.get("name", "")))
            if name:
                status = i.get("status")
                items.append(Item(name, status if status in STATUSES else None))
        routes.append(Route(a["command"], tuple(items)))
    return routes or None


def clean(name: str) -> str:
    """One short plain line: no markdown table/list/link syntax, no newlines."""
    for ch in "|[]\\`*#<>":
        name = name.replace(ch, " ")
    return " ".join(name.split())[:ITEM_CHARS].strip(" -")
