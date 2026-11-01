"""Configuration from environment variables (python-dotenv loads a local .env first).

Every setting has one env var; see .env.example for the full list with comments.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

GITHUB_ACTIONS_DEFAULT_RUNTIME_MIN = 340
DEFAULT_DB_NAME = "post_formatter_bot"
# the channel-posting bot's database - this bot must never write there
FORBIDDEN_DB_NAMES = frozenset({"channel_poster_bot"})

DEFAULT_AI_MODEL = "claude-opus-5-5"


class ConfigError(Exception):
    """A required setting is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    owner_id: int
    group_chat_ids: frozenset[int]
    anthropic_api_key: str
    mongo_url: str
    mongo_db_name: str = DEFAULT_DB_NAME
    ai_model: str = DEFAULT_AI_MODEL
    ai_effort: str = "low"
    max_runtime_minutes: float = 0
    runtime_profile: str = "persistent"
    log_level: str = "INFO"
    lease_heartbeat_seconds: float = 30.0
    lease_expiry_seconds: float = 120.0
    draft_ttl_days: int = 7
    usd_inr: float = 88.0

    def is_owner(self, user_id: int | None) -> bool:
        return user_id is not None and user_id == self.owner_id


def _get(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or default).strip()


def _int(env: Mapping[str, str], name: str, *, default: int | None = None) -> int:
    raw = _get(env, name)
    if not raw:
        if default is None:
            raise ConfigError(f"{name} is required")
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from None


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = _get(env, name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


def parse_ids(raw: str) -> frozenset[int]:
    """'-100123, 456 789' -> {-100123, 456, 789}"""
    out: set[int] = set()
    for part in raw.replace(",", " ").split():
        try:
            out.add(int(part))
        except ValueError:
            raise ConfigError(f"invalid Telegram id {part!r}") from None
    return frozenset(out)


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    token = _get(env, "BOT_TOKEN")
    if not token:
        raise ConfigError("BOT_TOKEN is required")
    key = _get(env, "ANTHROPIC_API_KEY")
    if not key:
        raise ConfigError("ANTHROPIC_API_KEY is required")
    mongo_url = _get(env, "MONGO_URL") or _get(env, "MONGO_URI")
    if not mongo_url:
        raise ConfigError("MONGO_URL is required")
    db_name = _get(env, "MONGO_DB_NAME", DEFAULT_DB_NAME)
    if db_name in FORBIDDEN_DB_NAMES:
        raise ConfigError(f"MONGO_DB_NAME={db_name!r} belongs to the channel-posting bot - use another name")

    profile = _get(env, "RUNTIME_PROFILE").lower() or (
        "github_actions" if env.get("GITHUB_ACTIONS") == "true" else "persistent")
    runtime = _float(env, "MAX_RUNTIME_MINUTES",
                     GITHUB_ACTIONS_DEFAULT_RUNTIME_MIN if profile == "github_actions" else 0)

    heartbeat = _float(env, "LEASE_HEARTBEAT_SECONDS", 30)
    expiry = _float(env, "LEASE_EXPIRY_SECONDS", 120)
    if heartbeat <= 0 or expiry < 2 * heartbeat:
        raise ConfigError("need LEASE_EXPIRY_SECONDS >= 2 * LEASE_HEARTBEAT_SECONDS > 0")

    return Config(
        bot_token=token,
        owner_id=_int(env, "OWNER_ID"),
        group_chat_ids=parse_ids(_get(env, "GROUP_CHAT_ID")),
        anthropic_api_key=key,
        mongo_url=mongo_url,
        mongo_db_name=db_name,
        ai_model=_get(env, "AI_MODEL", DEFAULT_AI_MODEL),
        ai_effort=_get(env, "AI_EFFORT", "low").lower(),
        max_runtime_minutes=runtime,
        runtime_profile=profile,
        log_level=_get(env, "LOG_LEVEL", "INFO").upper(),
        lease_heartbeat_seconds=heartbeat,
        lease_expiry_seconds=expiry,
        draft_ttl_days=_int(env, "DRAFT_TTL_DAYS", default=7),
        usd_inr=_float(env, "USD_INR", 88.0),
    )
