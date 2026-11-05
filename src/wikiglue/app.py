"""Runs wikiglue's parts side by side:

- the chat transport (commands, bookmarks from chat, questions)
- the Karakeep inbox (new bookmarks -> raw/ -> ingest job)
- the mail inbox (emails labelled "Family Wiki" -> raw/ -> ingest job)
- the results poster (finished jobs -> replies, scheduled lists -> announce room)
- the approvals watcher (research requests ticked in Obsidian -> fetched)

If any part crashes the whole service exits and systemd restarts it.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .commands import Dispatcher, Services
from .config import Config
from .inbox import Inbox
from .jobs import Jobs
from .mail import MailInbox
from .router import Router
from .state import State
from .transports.base import Transport
from .transports.matrix import MatrixTransport

log = logging.getLogger(__name__)

RESULTS_POLL_SECONDS = 2
APPROVALS_POLL_SECONDS = 10


async def run(config: Config) -> None:
    state = State(config.state_dir / "glue.db")
    jobs = Jobs(config.jobs_dir, config.vault_name)
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        router = Router(session, config.model_urls) if config.model_urls else None
        dispatcher = Dispatcher(config.vault, config.commands_path,
                                Services(jobs, state, session, config.karakeep_url), router)
        transport = MatrixTransport(config, config.matrix)
        inbox = Inbox(config, state, jobs, session)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(transport.run(dispatcher.handle))
            tg.create_task(inbox.run())
            tg.create_task(MailInbox(config, state, jobs, session).run())
            tg.create_task(post_results(state, jobs, dispatcher, transport))
            tg.create_task(watch_approvals(config, state, dispatcher, transport))


async def post_results(state: State, jobs: Jobs, dispatcher: Dispatcher, transport: Transport) -> None:
    while True:
        for result in jobs.results():
            job_id = result.get("id")
            if not job_id or state.result_handled(job_id):
                continue
            try:
                await post_result(result, state, dispatcher, transport)
            except Exception:
                # Most likely Matrix is unreachable: try again on the next round.
                log.exception("results: couldn't post %s", job_id)
                continue
            state.mark_result_handled(job_id)
        await asyncio.sleep(RESULTS_POLL_SECONDS)


async def post_result(result: dict, state: State, dispatcher: Dispatcher, transport: Transport) -> None:
    meta = result.get("meta") or {}
    status = result.get("status")
    reply = (result.get("reply") or "").strip()

    sent = False   # the whole reply went to a chat
    if meta.get("room"):  # a chat command (e.g. "? question")
        sent = True
        if status != "ok":
            text = f"Sorry, that didn't work ({status})."
        elif meta.get("reply", "result") == "result":
            text = reply or "(no answer)"
        else:
            text = meta["reply"]
        await transport.send(meta["room"], text, reply_to=meta.get("event") or None)

    elif meta.get("bookmark"):  # an ingest; tell whoever sent it from chat, if anyone
        target = state.get_notify(meta["bookmark"])
        if target:
            room_id, event_id = target
            text = (f"Added to the wiki:\n{reply}" if status == "ok"
                    else f"Saved, but updating the wiki failed ({status}).")
            await transport.send(room_id, text, reply_to=event_id or None)
            state.pop_notify(meta["bookmark"])
            sent = True

    elif result.get("task") in dispatcher.commands.announce:  # scheduled: shopping, digest
        room_id = state.get("announce_room")
        if room_id and status == "ok":
            await transport.send(room_id, reply)
        elif not room_id:
            log.info("results: %s finished but no announce room is set (send 'announce')",
                     result.get("task"))

    # The model asks something it can't work out (trip.md: which year a booking is for):
    # lines starting "Question:" go to the announce room when nobody saw the reply in chat.
    questions = [line.strip(" *-") for line in reply.splitlines()
                 if line.strip(" *-").startswith("Question:")]
    if questions and not sent and status == "ok":
        room_id = state.get("announce_room")
        if room_id:
            await transport.send(room_id, "\n".join(questions))
        else:
            log.info("results: %s asked a question but no announce room is set", result.get("id"))


async def watch_approvals(config: Config, state: State, dispatcher: Dispatcher,
                          transport: Transport) -> None:
    admin = next((u for u in config.users if u.role == "admin"), None)
    if admin is None:
        return
    while True:
        try:
            messages = await dispatcher.research_ticked(admin)
        except Exception:
            log.exception("approvals: failed")
            messages = []
        room_id = state.get("announce_room")
        for text in messages:
            log.info("approvals: %s", text)
            if room_id:
                await transport.send(room_id, text)
        await asyncio.sleep(APPROVALS_POLL_SECONDS)
