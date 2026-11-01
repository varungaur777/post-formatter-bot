"""Config, styles, AI helper, access and lease."""

from __future__ import annotations

from datetime import timedelta

import httpx2
import openai
import pytest

from bot.access import Access
from bot.ai import AIError, PostAI, clean_output
from bot.config import ConfigError, load_config
from bot.lease import Lease
from bot.styles import GEOSIGHT, SPITTING, load_examples, system_prompt
from bot.utils import RedactFilter
from tests.conftest import ADMIN, OWNER, STRANGER, make_config

BASE_ENV = {"BOT_TOKEN": "1:x", "OWNER_ID": "7364684102", "OPENAI_API_KEY": "sk-x", "MONGO_URL": "mongodb://x"}


def _err(cls, status, body=None):
    req = httpx2.Request("POST", "https://api.openai.com/v1/x")
    return cls("boom", response=httpx2.Response(status, request=req), body=body)


# ---- config --------------------------------------------------------------------------------------
def test_config_defaults():
    cfg = load_config({**BASE_ENV, "SUBMITTER_IDS": "5, 6 7"})
    assert cfg.mongo_db_name == "post_formatter_bot"
    assert cfg.submitter_ids == {5, 6, 7}
    assert cfg.text_model == "gpt-6.1-terra" and cfg.image_model == "gpt-image-2.5-flare"
    assert cfg.max_runtime_minutes == 0


def test_config_github_actions_runtime_and_model_override():
    cfg = load_config({**BASE_ENV, "GITHUB_ACTIONS": "true", "OPENAI_TEXT_MODEL": "gpt-6-luna"})
    assert cfg.runtime_profile == "github_actions" and cfg.max_runtime_minutes == 340
    assert cfg.text_model == "gpt-6-luna"


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "OWNER_ID", "OPENAI_API_KEY", "MONGO_URL"])
def test_config_required(missing):
    env = {k: v for k, v in BASE_ENV.items() if k != missing}
    with pytest.raises(ConfigError):
        load_config(env)


def test_config_refuses_old_bots_database():
    with pytest.raises(ConfigError, match="channel-posting bot"):
        load_config({**BASE_ENV, "MONGO_DB_NAME": "channel_poster_bot"})


# ---- styles --------------------------------------------------------------------------------------
def test_load_examples(tmp_path):
    (tmp_path / "geosight_examples.txt").write_text(
        "# comment\n🇮🇳 First\n▪️ point\n---\n# another comment\nSecond post\n---\n\n", encoding="utf-8")
    assert load_examples("geosight", tmp_path) == ["🇮🇳 First\n▪️ point", "Second post"]
    assert load_examples("spitting", tmp_path) == []


def test_repo_example_files_parse():
    assert isinstance(load_examples("spitting"), list) and isinstance(load_examples("geosight"), list)


def test_system_prompt_contents():
    p = system_prompt(GEOSIGHT, 1024, examples=["🇮🇳 Example post"])
    assert "1024" in p and "▪️" in p and "🔹" in p and "🔺" in p and "flag" in p
    assert "🇮🇳 Example post" in p and "Never invent" in p
    s = system_prompt(SPITTING, 4000, examples=[])
    assert "@spitting_fact" in s and "Do not translate" in s and "Example" not in s


# ---- ai ------------------------------------------------------------------------------------------
def test_clean_output():
    assert clean_output("```\n**Head**\n<b>body</b>\n```") == "Head\nbody"
    assert clean_output('"Quoted post"') == "Quoted post"
    assert clean_output("a\n\n\n\nb") == "a\n\nb"


async def test_format_retries_when_too_long(oai):
    ai = PostAI(make_config(), client=oai)
    oai.text_outputs += ["x" * 200, "short version"]
    assert await ai.format_post(SPITTING, "raw", limit=100) == "short version"
    assert "Shorten" in oai.text_calls[1]["input"][0]["content"][0]["text"]


async def test_format_fails_when_still_too_long(oai):
    ai = PostAI(make_config(), client=oai)
    oai.text_outputs += ["x" * 200, "y" * 200]
    with pytest.raises(AIError, match="Edit"):
        await ai.format_post(SPITTING, "raw", limit=100)


async def test_reasoning_can_be_switched_off(oai):
    ai = PostAI(make_config(reasoning_effort=""), client=oai)
    await ai.format_post(SPITTING, "raw", limit=1000)
    assert "reasoning" not in oai.text_calls[0]


@pytest.mark.parametrize(("exc", "needle"), [
    (_err(openai.AuthenticationError, 401), "key galat"),
    (_err(openai.NotFoundError, 404), "model nahi mila"),
    (_err(openai.PermissionDeniedError, 403), "access nahi"),
    (_err(openai.RateLimitError, 429), "busy"),
    (_err(openai.RateLimitError, 429, {"code": "insufficient_quota"}), "billing"),
    (_err(openai.InternalServerError, 500), "problem"),
])
async def test_error_messages(oai, exc, needle):
    ai = PostAI(make_config(openai_api_key="sk-SECRET-KEY-123"), client=oai)
    oai.text_outputs.append(exc)
    with pytest.raises(AIError) as info:
        await ai.format_post(SPITTING, "raw", limit=1000)
    assert needle in str(info.value) and "sk-SECRET" not in str(info.value)


async def test_generate_image(oai):
    ai = PostAI(make_config(image_quality="low", image_size="1536x1024"), client=oai)
    oai.image_outputs.append(b"png!")
    assert await ai.generate_image(GEOSIGHT, "🇮🇳 India post") == b"png!"
    call = oai.image_calls[0]
    assert call["quality"] == "low" and call["size"] == "1536x1024" and "India post" in call["prompt"]
    assert "no text" in call["prompt"].lower() or "not put any text" in call["prompt"]


async def test_image_rejected(oai):
    ai = PostAI(make_config(), client=oai)
    oai.image_outputs.append(_err(openai.BadRequestError, 400))
    with pytest.raises(AIError, match="image nahi"):
        await ai.generate_image(SPITTING, "post")


# ---- access --------------------------------------------------------------------------------------
async def test_access(db):
    cfg = make_config()
    a = Access(cfg, db)
    await a.load()
    assert a.allowed(OWNER) and a.allowed(ADMIN) and not a.allowed(STRANGER) and not a.allowed(None)
    assert await a.add(STRANGER, OWNER) is True
    assert await a.add(STRANGER, OWNER) is False
    b = Access(cfg, db)
    await b.load()
    assert b.allowed(STRANGER)  # survives a restart
    assert await b.remove(STRANGER) == "removed" and not b.allowed(STRANGER)
    assert await b.remove(ADMIN) == "env"
    assert await b.remove(OWNER) == "owner"
    assert await b.remove(12345) == "missing"


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
