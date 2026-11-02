"""Config, styles, AI helper, access and lease."""

from __future__ import annotations

from datetime import timedelta

import anthropic
import httpx2
import pytest

from bot.access import Access
from bot.ai import AIError, PostAI, clean_output
from bot.config import ConfigError, load_config
from bot.lease import Lease
from bot.styles import POST, load_examples, system_prompt
from bot.utils import RedactFilter
from tests.conftest import ADMIN, GROUP, OWNER, STRANGER, make_config

BASE_ENV = {"BOT_TOKEN": "1:x", "OWNER_ID": "8322550258", "ANTHROPIC_API_KEY": "sk-ant-x", "MONGO_URL": "mongodb://x"}


def _err(cls, status, body=None):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=req), body=body)


# ---- config --------------------------------------------------------------------------------------
def test_config_defaults():
    cfg = load_config(BASE_ENV)
    assert cfg.mongo_db_name == "post_formatter_bot"
    assert cfg.ai_model == "claude-haiku-5-5" and cfg.ai_effort == "low"
    assert cfg.max_runtime_minutes == 0


def test_config_github_actions_runtime_and_model_override():
    cfg = load_config({**BASE_ENV, "GITHUB_ACTIONS": "true", "AI_MODEL": "claude-haiku-5-5"})
    assert cfg.runtime_profile == "github_actions" and cfg.max_runtime_minutes == 340
    assert cfg.ai_model == "claude-haiku-5-5"


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "OWNER_ID", "ANTHROPIC_API_KEY", "MONGO_URL"])
def test_config_required(missing):
    env = {k: v for k, v in BASE_ENV.items() if k != missing}
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_refuses_old_bots_database():
    with pytest.raises(ConfigError, match="channel-posting bot"):
        load_config({**BASE_ENV, "MONGO_DB_NAME": "channel_poster_bot"})


# ---- styles --------------------------------------------------------------------------------------
def test_load_examples(tmp_path):
    (tmp_path / "post_examples.txt").write_text(
        "# comment\n🇮🇳 First\n▪️ point\n---\n# another comment\nSecond post\n---\n\n", encoding="utf-8")
    assert load_examples("post", tmp_path) == ["🇮🇳 First\n▪️ point", "Second post"]
    assert load_examples("missing", tmp_path) == []


def test_repo_example_files_parse():
    assert isinstance(load_examples("post"), list)


def test_system_prompt_contents():
    p = system_prompt(POST, 1024, examples=["🇮🇳 Example post"])
    assert "1024" in p and "▪️" in p and "🔹" in p and "🔺" in p and "flag" in p
    assert "🇮🇳 Example post" in p and "never invent" in p and "crisp" in p
    assert "English" in p and "translate" in p
    assert "Example" not in system_prompt(POST, 4000, examples=[])


# ---- ai ------------------------------------------------------------------------------------------
def test_clean_output():
    assert clean_output("```\n**Head**\n<b>body</b>\n```") == "Head\nbody"
    assert clean_output('"Quoted post"') == "Quoted post"
    assert clean_output("a\n\n\n\nb") == "a\n\nb"


async def test_format_retries_when_too_long(claude):
    ai = PostAI(make_config(), client=claude)
    claude.outputs += ["x" * 200, "short version"]
    assert await ai.format_post(POST, "raw", limit=100) == "short version"
    assert "Shorten" in claude.prompt(1)


async def test_format_fails_when_still_too_long(claude):
    ai = PostAI(make_config(), client=claude)
    claude.outputs += ["x" * 200, "y" * 200]
    with pytest.raises(AIError, match="Edit"):
        await ai.format_post(POST, "raw", limit=100)


async def test_fallback_only_on_models_that_accept_it(claude):
    ai = PostAI(make_config(ai_model="claude-opus-5-5"), client=claude)
    await ai.format_post(POST, "raw", limit=1000)
    assert claude.calls[0]["fallbacks"] == "default"
    assert claude.calls[0]["betas"] == ["server-side-fallback-2026-07-01"]


async def test_haiku_without_fallback_and_default_effort(claude):
    ai = PostAI(make_config(ai_model="claude-haiku-5-5", ai_effort=""), client=claude)
    await ai.format_post(POST, "raw", limit=1000)
    call = claude.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in call and "betas" not in call and "output_config" not in call


@pytest.mark.parametrize(("exc", "needle"), [
    (_err(anthropic.AuthenticationError, 401), "key is invalid"),
    (_err(anthropic.NotFoundError, 404), "model not found"),
    (_err(anthropic.PermissionDeniedError, 403), "no access"),
    (_err(anthropic.RateLimitError, 429), "busy"),
    (_err(anthropic.BadRequestError, 400), "couldn't process"),
    (_err(anthropic.InternalServerError, 500), "problem"),
])
async def test_error_messages(claude, exc, needle):
    ai = PostAI(make_config(anthropic_api_key="sk-ant-SECRET-123"), client=claude)
    claude.outputs.append(exc)
    with pytest.raises(AIError) as info:
        await ai.format_post(POST, "raw", limit=1000)
    assert needle in str(info.value) and "SECRET" not in str(info.value)


# ---- access --------------------------------------------------------------------------------------
async def test_auth_groups_survive_restart_and_migrate(db):
    from telegram import Chat

    cfg = make_config()
    a = Access(cfg, db)
    new = Chat(id=-777, type="supergroup")
    assert not a.allowed(new, STRANGER)
    await a.authorize(-777, "News", OWNER)
    assert a.allowed(new, STRANGER)

    b = Access(cfg, db)  # after a restart
    await b.load()
    assert b.allowed(new, STRANGER) and (-777, "News") in b.listing()
    await b.migrate(-777, -100777)
    assert not b.allowed(new, STRANGER) and b.allowed(Chat(id=-100777, type="supergroup"), STRANGER)
    assert await b.revoke(-100777) == "removed" and not b.allowed(Chat(id=-100777, type="supergroup"), STRANGER)
    assert await b.revoke(-100777) == "missing"
    assert await b.revoke(GROUP) == "env" and b.allowed(Chat(id=GROUP, type="supergroup"), STRANGER)


def test_access(db):
    from telegram import Chat

    a = Access(make_config(), db)
    dm = Chat(id=5, type="private")
    assert a.allowed(dm, OWNER) and not a.allowed(dm, ADMIN) and not a.allowed(dm, STRANGER)
    assert a.allowed(Chat(id=GROUP, type="supergroup"), STRANGER)
    assert not a.allowed(Chat(id=-1, type="group"), OWNER)
    assert not a.allowed(None, OWNER) and not a.allowed(dm, None)


def test_config_group_ids():
    cfg = load_config({**BASE_ENV, "GROUP_CHAT_ID": "-1001234567890"})
    assert cfg.group_chat_ids == {-1001234567890}
    assert load_config(BASE_ENV).group_chat_ids == frozenset()


# ---- lease ---------------------------------------------------------------------------------------
async def test_lease_single_instance(db):
    clock = _Clock()
    a = Lease(db.lease, clock=clock, holder="a", expiry_s=120)
    b = Lease(db.lease, clock=clock, holder="b", expiry_s=120)
    assert await a.try_acquire() is True
    assert await b.try_acquire() is False
    clock.advance(seconds=60)
    assert await a.renew() is True
    clock.advance(seconds=121)  # a stopped heart-beating
    assert await b.try_acquire() is True
    assert await a.renew() is False
    await b.release()
    assert await db.lease.count_documents({}) == 0


class _Clock:
    def __init__(self):
        from datetime import UTC, datetime

        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


# ---- logging -------------------------------------------------------------------------------------
def test_redact_filter():
    import logging

    rec = logging.LogRecord("x", logging.INFO, "f", 1, "token %s key %s", ("123:ABCDEFGH", "sk-abcdefgh"), None)
    RedactFilter(["123:ABCDEFGH", "sk-abcdefgh"]).filter(rec)
    assert rec.getMessage() == "token <secret> key <secret>"
