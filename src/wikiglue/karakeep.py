"""Minimal Karakeep API client (REST /api/v1, bearer API key per user).

Each family member has their own Karakeep account and API key, so a bookmark
made from chat belongs to the person who sent it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import aiohttp

# How much readable text to pull per source. The model's context is 32k tokens;
# ~60k characters (~15k tokens) leaves room for the wiki pages it edits.
MAX_CONTENT_CHARS = 60_000
# Pages can inline images as base64 data: URIs (one Hoh Rain Forest page had a 54 KB PNG),
# which the model can't use and which would eat the budget above. They're stripped, and
# at most this much raw text is fetched looking for MAX_CONTENT_CHARS of real text.
MAX_RAW_CHARS = 4 * MAX_CONTENT_CHARS
INLINE_IMAGE = re.compile(r"!\[([^\]]*)\]\(data:[^)]*\)?")
DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]*")


def strip_inline_data(text: str) -> str:
    """Drop base64 data: URIs; an inline image keeps its alt text as "[image: ...]"."""
    text = INLINE_IMAGE.sub(lambda m: f"[image: {m.group(1).strip()}]" if m.group(1).strip() else "", text)
    return DATA_URI.sub("", text)


class KarakeepError(Exception):
    pass


@dataclass
class Asset:
    data: bytes
    content_type: str


class Karakeep:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str):
        self.session = session
        self.base = base_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def _json(self, method: str, path: str, **kw) -> dict:
        async with self.session.request(method, self.base + path, headers=self.headers, **kw) as r:
            if r.status >= 400:
                raise KarakeepError(f"{method} {path}: HTTP {r.status}: {(await r.text())[:200]}")
            return await r.json()

    # --- reading ---

    async def recent_bookmarks(self, limit: int = 50, cursor: str | None = None) -> tuple[list[dict], str | None]:
        params = {"sortOrder": "desc", "limit": str(limit), "includeContent": "true"}
        if cursor:
            params["cursor"] = cursor
        data = await self._json("GET", "/bookmarks", params=params)
        return data["bookmarks"], data.get("nextCursor")

    async def bookmark(self, bookmark_id: str) -> dict:
        return await self._json("GET", f"/bookmarks/{bookmark_id}", params={"includeContent": "true"})

    async def readable_content(self, bookmark_id: str) -> tuple[str, bool]:
        """The bookmark's readable text as markdown (inline image data stripped),
        and whether it was cut short."""
        raw, cursor = "", None
        while True:
            params = {"format": "markdown", "maxChars": "50000"}
            if cursor:
                params["cursor"] = cursor
            try:
                data = await self._json("GET", f"/bookmarks/{bookmark_id}/content", params=params)
            except KarakeepError:
                return strip_inline_data(raw), bool(cursor)  # e.g. an image without OCR text
            raw += data.get("content") or ""
            cursor = data.get("nextCursor")
            text = strip_inline_data(raw)
            if not cursor:
                return text, False
            if len(text) >= MAX_CONTENT_CHARS or len(raw) >= MAX_RAW_CHARS:
                return text[:MAX_CONTENT_CHARS], True

    @staticmethod
    def archive_id(bm: dict) -> str | None:
        """The full-page archive Karakeep kept (CRAWLER_FULL_PAGE_ARCHIVE=true), if any."""
        for a in bm.get("assets") or []:
            if a.get("assetType") in ("fullPageArchive", "precrawledArchive"):
                return a.get("id")
        return None

    async def asset(self, asset_id: str) -> Asset:
        async with self.session.get(f"{self.base}/assets/{asset_id}", headers=self.headers) as r:
            if r.status >= 400:
                raise KarakeepError(f"GET asset {asset_id}: HTTP {r.status}")
            return Asset(await r.read(), r.headers.get("Content-Type", "application/octet-stream"))

    # --- writing (bookmarks made from chat) ---

    async def add_link(self, url: str, note: str | None = None) -> dict:
        body = {"type": "link", "url": url, "source": "api"}
        if note:
            body["note"] = note
        return await self._json("POST", "/bookmarks", json=body)

    async def add_text(self, text: str) -> dict:
        return await self._json("POST", "/bookmarks", json={"type": "text", "text": text, "source": "api"})

    async def add_file(self, data: bytes, filename: str, content_type: str, note: str | None = None) -> dict:
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type=content_type)
        asset = await self._json("POST", "/assets", data=form)
        kind = "pdf" if content_type == "application/pdf" else "image"
        body = {"type": "asset", "assetType": kind, "assetId": asset["assetId"],
                "fileName": filename, "source": "api"}
        if note:
            body["note"] = note
        return await self._json("POST", "/bookmarks", json=body)
