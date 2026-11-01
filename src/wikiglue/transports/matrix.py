"""Matrix transport: the @wiki bot on the tailnet-only Synapse.

Only users listed in wikiglue.toml are served. The bot joins rooms they invite
it to and ignores everyone else.

End-to-end encryption: Element X encrypts DMs and private rooms, so the bot runs
a full Olm/Megolm machine (mautrix + libolm). Keys live in SQLite under the
state dir. On first start the bot sets up cross-signing and signs its own
device, because current clients won't encrypt for devices their owner hasn't
signed. The recovery key is saved next to the crypto DB.

Photos and PDFs are downloaded from Synapse (on localhost), decrypted, and handed
to the dispatcher as attachments.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from pathlib import Path

from mautrix.client import Client
from mautrix.crypto.attachments import decrypt_attachment
from mautrix.client.encryption_manager import DecryptionDispatcher
from mautrix.client.state_store.asyncpg import PgStateStore
from mautrix.crypto import OlmMachine, PgCryptoStore
from mautrix.errors import DecryptionError, SessionNotFound
from mautrix.types import (
    EncryptedEvent,
    EventType,
    MediaMessageEventContent,
    Membership,
    MessageEvent,
    MessageType,
    StateEvent,
    TextMessageEventContent,
)
from mautrix.util.async_db import Database

from ..commands import Attachment, React
from ..config import Config, MatrixConfig
from .base import MessageHandler

log = logging.getLogger(__name__)

# How long to wait for a sender's room key to arrive before giving up on a message.
KEY_WAIT_SECONDS = 10
# Attachments accepted from chat (Karakeep stores images and PDFs).
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


def _read_or_create_secret(path: Path) -> str:
    """A random secret persisted with 0600 permissions (created on first use)."""
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        value = secrets.token_urlsafe(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value + "\n")
        return value


class WaitingDecryptionDispatcher(DecryptionDispatcher):
    """Like mautrix's dispatcher, but waits briefly for keys that arrive after the message."""

    async def handle(self, evt: EncryptedEvent) -> None:
        crypto = self.client.crypto
        try:
            try:
                decrypted = await crypto.decrypt_megolm_event(evt)
            except SessionNotFound:
                if not await crypto.wait_for_session(
                    evt.room_id, evt.content.session_id, timeout=KEY_WAIT_SECONDS
                ):
                    raise
                decrypted = await crypto.decrypt_megolm_event(evt)
        except DecryptionError as e:
            log.warning("matrix: can't decrypt %s from %s: %s", evt.event_id, evt.sender, e)
            return
        self.client.dispatch_event(decrypted, evt.source)


class MatrixTransport:
    def __init__(self, config: Config, matrix: MatrixConfig):
        self.config = config
        self.state_dir = config.state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # One DB for both stores: mautrix shares the in-transaction connection between
        # Database objects (via a contextvar), so separate files break. The stores use
        # separate version tables and are designed to coexist.
        db_path = self.state_dir / "matrix.db"
        # Holds Olm/Megolm keys: owner-only. SQLite's -wal/-shm files copy this mode.
        os.close(os.open(db_path, os.O_CREAT | os.O_WRONLY, 0o600))
        db_path.chmod(0o600)
        self.db = Database.create(
            f"sqlite://{db_path}",
            upgrade_table=PgCryptoStore.upgrade_table,
        )
        pickle_key = _read_or_create_secret(self.state_dir / "matrix-pickle-key")
        self.crypto_store = PgCryptoStore(matrix.user_id, pickle_key, self.db)
        self.state_store = PgStateStore(self.db)

        self.client = Client(
            mxid=matrix.user_id,
            base_url=matrix.homeserver,
            token=matrix.access_token,
            # The crypto store doubles as the sync store, so the sync token and
            # the crypto state it depends on are always saved together.
            sync_store=self.crypto_store,
            state_store=self.state_store,
        )
        self.crypto = OlmMachine(self.client, self.crypto_store, self.state_store)
        self._ignore_before_ms = 0

    async def run(self, handler: MessageHandler) -> None:
        await self.db.start()
        await PgStateStore.upgrade_table.upgrade(self.db)
        try:
            await self._setup_crypto()

            # On the very first start, don't replay room history as new commands.
            # (Not ignore_initial_sync: that would also drop pending invites.)
            if not await self.crypto_store.get_next_batch():
                self._ignore_before_ms = int(time.time() * 1000)

            self.client.add_event_handler(EventType.ROOM_MEMBER, self._on_member)
            self.client.add_event_handler(
                EventType.ROOM_MESSAGE, lambda evt: self._on_message(evt, handler)
            )
            log.info("matrix: syncing as %s (device %s)", self.client.mxid, self.client.device_id)
            # mautrix retries failed syncs with backoff; systemd restarts us if we crash.
            await self.client.start(filter_data=None)
        finally:
            self.client.stop()
            await self.client.api.session.close()
            await self.db.stop()

    async def _setup_crypto(self) -> None:
        whoami = await self.client.whoami()
        if whoami.user_id != self.client.mxid:
            raise RuntimeError(f"token belongs to {whoami.user_id}, expected {self.client.mxid}")
        self.client.device_id = whoami.device_id

        stored_device = await self.crypto_store.get_device_id()
        if stored_device and stored_device != whoami.device_id:
            # New access token = new device; old Olm state is useless and would confuse peers.
            log.warning("matrix: device changed %s -> %s; resetting crypto store",
                        stored_device, whoami.device_id)
            await self.crypto_store.delete()
        await self.crypto_store.put_device_id(whoami.device_id)

        await self.crypto.load()
        self.client.crypto = self.crypto
        self.client.remove_dispatcher(DecryptionDispatcher)
        self.client.add_dispatcher(WaitingDecryptionDispatcher)
        await self.crypto.share_keys()
        await self._ensure_cross_signed()

    async def _ensure_cross_signed(self) -> None:
        recovery_path = self.state_dir / "matrix-recovery-key"
        marker = self.state_dir / f"matrix-cross-signed-{self.client.device_id}"
        if marker.exists():
            return

        if await self.crypto.get_own_cross_signing_public_keys() is None:
            log.info("matrix: no cross-signing keys yet; generating them")
            recovery_key = await self.crypto.generate_recovery_key()
            fd = os.open(recovery_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(recovery_key + "\n")
            log.info("matrix: cross-signing set up; recovery key saved to %s", recovery_path)
        elif recovery_path.exists():
            log.info("matrix: signing this device with the saved recovery key")
            await self.crypto.verify_with_recovery_key(recovery_path.read_text().strip())
        else:
            log.error(
                "matrix: account has cross-signing keys but %s is missing; this device "
                "stays unsigned and clients may refuse to encrypt for it", recovery_path
            )
            return
        marker.touch()

    async def _on_member(self, evt: StateEvent) -> None:
        if evt.state_key != self.client.mxid or evt.content.membership != Membership.INVITE:
            return
        if self.config.user_by_matrix_id(evt.sender) is None:
            log.warning("matrix: ignoring invite to %s from %s", evt.room_id, evt.sender)
            return
        log.info("matrix: joining %s (invited by %s)", evt.room_id, evt.sender)
        await self.client.join_room(evt.room_id)

    async def _on_message(self, evt: MessageEvent, handler: MessageHandler) -> None:
        if evt.sender == self.client.mxid or evt.timestamp < self._ignore_before_ms:
            return
        user = self.config.user_by_matrix_id(evt.sender)
        if user is None:
            log.warning("matrix: ignoring message from %s", evt.sender)
            return
        attachment = None
        text = evt.content.body or ""
        if evt.content.msgtype in (MessageType.IMAGE, MessageType.FILE):
            try:
                attachment = await self._download(evt.content)
            except Exception:
                log.exception("matrix: couldn't download attachment %s", evt.event_id)
                await self._reply(evt, "Couldn't download that file.")
                return
            if attachment is None:
                await self._reply(evt, "I can save photos and PDFs; that file type isn't supported.")
                return
            # The body of a media message is the file name unless a caption was added.
            text = text if text != attachment.filename else ""
        elif evt.content.msgtype not in (MessageType.TEXT, MessageType.NOTICE):
            await self._reply(evt, "I can handle text, photos and PDFs.")
            return

        try:
            reply = await handler(user, text, room_id=evt.room_id, event_id=evt.event_id,
                                  attachment=attachment)
        except Exception:
            log.exception("matrix: handler failed for %s", evt.event_id)
            reply = "Something went wrong handling that; it's in the wikiglue log."
        if isinstance(reply, React):
            await self.client.react(evt.room_id, evt.event_id, str(reply))
        elif reply:
            await self._reply(evt, reply)

    async def _download(self, content: MediaMessageEventContent) -> Attachment | None:
        info = content.info
        mimetype = (info.mimetype if info else None) or "application/octet-stream"
        if not (mimetype.startswith("image/") or mimetype == "application/pdf"):
            return None
        if info and info.size and info.size > MAX_ATTACHMENT_BYTES:
            return None
        filename = content.filename or content.body or "file"
        if content.file:  # encrypted room: the key travels in the (already decrypted) event
            data = await self.client.download_media(content.file.url)
            data = decrypt_attachment(data, content.file.key.key,
                                      content.file.hashes["sha256"], content.file.iv)
        else:
            data = await self.client.download_media(content.url)
        if len(data) > MAX_ATTACHMENT_BYTES:
            return None
        return Attachment(data=data, filename=filename, content_type=mimetype)

    async def _reply(self, evt: MessageEvent, text: str) -> None:
        await self.send(evt.room_id, text, reply_to=evt.event_id)

    async def send(self, room_id: str, text: str, reply_to: str | None = None) -> None:
        """Post a notice; as a reply when reply_to is given. Encrypted automatically
        when the room is encrypted."""
        content = TextMessageEventContent(msgtype=MessageType.NOTICE, body=text)
        if reply_to:
            content.set_reply(reply_to)
        await self.client.send_message(room_id, content)
