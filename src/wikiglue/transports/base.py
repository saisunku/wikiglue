"""Chat transport interface. Matrix today; Telegram/Discord/Signal could slot in."""

from __future__ import annotations

from typing import Protocol

from ..commands import Attachment
from ..config import User


class MessageHandler(Protocol):
    """Dispatcher.handle: returns a reply (str), a React, or None."""

    async def __call__(self, user: User, text: str, *, room_id: str = "", event_id: str = "",
                       attachment: Attachment | None = None) -> str | None: ...


class Transport(Protocol):
    async def run(self, handler: MessageHandler) -> None: ...

    async def send(self, room_id: str, text: str, reply_to: str | None = None,
                   notify: bool = False) -> None: ...
