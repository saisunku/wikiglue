"""Service configuration: /etc/wikiglue/wikiglue.toml.

Example:

    vault = "/srv/wiki/vault"            # bind-mounted by the systemd drop-in
    state_dir = "/var/lib/wikiglue"
    jobs_dir = "/var/lib/wiki-jobs"      # wiki-runner's queue

    [karakeep]
    url = "http://127.0.0.1:3000"

    [model]                              # llama.cpp servers, for routing plain chat messages:
    urls = ["http://127.0.0.1:8080"]     # the first that answers

    [matrix]
    homeserver = "http://127.0.0.1:8008"
    user_id = "@wiki:chat.example.org"
    access_token_file = "/etc/wikiglue/matrix_token"

    [users.alex]
    name = "Alex"
    role = "admin"
    matrix = "@alex:chat.example.org"
    karakeep_key_file = "/etc/wikiglue/karakeep/alex.key"   # the user's own Karakeep API key
    maildir = "/var/lib/wikimail/alex/Family Wiki"          # their "Family Wiki" Gmail label (mail.py)
    emails = ["alex@example.com"]                           # addresses they send from (shared mailboxes)

    [mailboxes.familywiki]                 # an address anyone can send to; only family's mail is used
    address = "familywiki@example.org"
    maildir = "/var/lib/wikimail/familywiki/INBOX"
    auth_server = "mx.zohomail.com"        # whose Authentication-Results header to trust
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROLES = frozenset({"admin", "member"})


@dataclass(frozen=True)
class User:
    key: str
    name: str
    role: str
    matrix: str | None = None
    karakeep_key: str | None = None
    maildir: Path | None = None
    emails: tuple[str, ...] = ()   # lowercase sending addresses

    def __repr__(self) -> str:  # keep the API key out of logs
        return f"User({self.key!r}, role={self.role!r})"


@dataclass(frozen=True)
class MatrixConfig:
    homeserver: str
    user_id: str
    access_token: str


@dataclass(frozen=True)
class Mailbox:
    """A shared address (e.g. familywiki@...): emails count only from users' own addresses."""
    key: str
    address: str
    maildir: Path
    auth_server: str


@dataclass(frozen=True)
class Config:
    vault: Path
    state_dir: Path
    matrix: MatrixConfig | None
    users: tuple[User, ...]
    jobs_dir: Path = Path("/var/lib/wiki-jobs")
    karakeep_url: str | None = None
    model_urls: tuple[str, ...] = ()
    mailboxes: tuple[Mailbox, ...] = ()

    @property
    def commands_path(self) -> Path:
        return self.vault / "_config" / "commands.toml"

    def user_by_matrix_id(self, mxid: str) -> User | None:
        return next((u for u in self.users if u.matrix == mxid), None)

    def user_by_key(self, key: str) -> User | None:
        return next((u for u in self.users if u.key == key), None)


class ConfigError(Exception):
    pass


def load_config(path: Path) -> Config:
    with path.open("rb") as f:
        raw = tomllib.load(f)

    try:
        vault = Path(raw["vault"])
        state_dir = Path(raw.get("state_dir", "/var/lib/wikiglue"))
    except KeyError as e:
        raise ConfigError(f"{path}: missing required key {e}") from None

    users = []
    for key, u in raw.get("users", {}).items():
        role = u.get("role", "member")
        if role not in ROLES:
            raise ConfigError(f"{path}: users.{key}.role must be one of {sorted(ROLES)}")
        karakeep_key = None
        if key_file := u.get("karakeep_key_file"):
            try:
                karakeep_key = Path(key_file).read_text().strip() or None
            except FileNotFoundError:
                pass  # not linked yet; their chat bookmarks get a friendly error
        users.append(User(key=key, name=u.get("name", key), role=role,
                          matrix=u.get("matrix"), karakeep_key=karakeep_key,
                          maildir=Path(u["maildir"]) if u.get("maildir") else None,
                          emails=tuple(e.strip().lower() for e in u.get("emails", []))))

    mailboxes = []
    for key, m in raw.get("mailboxes", {}).items():
        try:
            mailboxes.append(Mailbox(key=key, address=m["address"], maildir=Path(m["maildir"]),
                                     auth_server=m.get("auth_server", "mx.zohomail.com")))
        except KeyError as e:
            raise ConfigError(f"{path}: mailboxes.{key} is missing {e}") from None

    matrix = None
    if m := raw.get("matrix"):
        token_file = Path(m["access_token_file"])
        matrix = MatrixConfig(
            homeserver=m["homeserver"],
            user_id=m["user_id"],
            access_token=token_file.read_text().strip(),
        )

    return Config(
        vault=vault,
        state_dir=state_dir,
        matrix=matrix,
        users=tuple(users),
        jobs_dir=Path(raw.get("jobs_dir", "/var/lib/wiki-jobs")),
        karakeep_url=raw.get("karakeep", {}).get("url"),
        model_urls=tuple(raw.get("model", {}).get("urls")
                         or filter(None, [raw.get("model", {}).get("url")])),
        mailboxes=tuple(mailboxes),
    )
