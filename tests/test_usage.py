"""Spend tracking and the owner's /wallet report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from bot.ai import PostAI
from bot.handlers import Formatter
from bot.styles import POST
from bot.usage import UsageStore, cost_usd
from tests.conftest import OWNER, STRANGER, make_config, text_msg


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 15, 6, 0, tzinfo=UTC)  # 11:30 IST

    def __call__(self) -> datetime:
        return self.now


def test_cost_usd():
    assert cost_usd("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
    assert cost_usd("claude-opus-5-5", 0, 1_000_000) == pytest.approx(20.0)
    assert cost_usd("claude-haiku-5-5", 1000, 500) == pytest.approx(0.00035)
    assert cost_usd("claude-opus-5-5", 0, 0, cache_write=1_000_000, cache_read=1_000_000) == pytest.approx(5.4)
    assert cost_usd("some-new-model", 1_000_000, 0) == pytest.approx(10.0)  # never under-report


async def test_calls_are_recorded_and_summed(db, claude):
    clock = Clock()
    store = UsageStore(db.usage, clock=clock)
    ai = PostAI(make_config(), client=claude, usage=store)
    await ai.format_post(POST, "raw", limit=1000)            # today
    clock.now -= timedelta(days=3)
    await ai.format_post(POST, "raw", limit=1000)            # this month
    await store.record_post()
    clock.now -= timedelta(days=30)
    await ai.format_post(POST, "raw", limit=1000)            # last month
    clock.now += timedelta(days=33)

    one = cost_usd("claude-opus-5-5", 1000, 500)  # $0.014
    t = await store.summary()
    assert t["today"].calls == 1 and t["today"].usd == pytest.approx(one) and t["today"].posts == 0
    assert t["month"].calls == 2 and t["month"].posts == 1
    assert t["total"].calls == 3 and t["total"].usd == pytest.approx(3 * one)
    doc = await db.usage.find_one({"type": "call"})
    assert doc["model"] == "claude-opus-5-5" and doc["input_tokens"] == 1000 and doc["cache_read_input_tokens"] == 0


async def test_refused_call_is_still_counted(db, claude):
    store = UsageStore(db.usage)
    ai = PostAI(make_config(), client=claude, usage=store)
    claude.outputs.append(("refusal", ""))
    with pytest.raises(Exception, match="declined"):
        await ai.format_post(POST, "raw", limit=1000)
    assert await db.usage.count_documents({"type": "call"}) == 1


async def test_done_counts_a_post_and_wallet_text(cfg, db, bot, claude):
    from tests.test_flow import send

    store = UsageStore(db.usage)
    fmt = Formatter(cfg, db, bot, PostAI(cfg, client=claude, usage=store), store)
    await send(fmt, text_msg(OWNER, "/format news", bot))
    d = await db.drafts.find_one({})
    from tests.conftest import button

    await fmt.on_button(button(OWNER, f"ok:{d['_id']}", bot))
    text = await fmt.wallet_text()
    assert "Today:</b> $0.014 (≈ ₹1) · 1 posts · 1 AI requests" in text
    assert "claude-opus-5-5" in text and "platform.claude.com" in text


async def test_wallet_command_is_owner_only(cfg, db, bot, claude, access):
    from telegram import Update
    from telegram.ext import Application, CommandHandler

    from bot.handlers import register

    store = UsageStore(db.usage)
    fmt = Formatter(cfg, db, bot, PostAI(cfg, client=claude, usage=store), store)
    app = Application.builder().token("123:TEST").build()
    register(app, cfg, fmt, access)
    wallet = next(h for h in app.handlers[0] if isinstance(h, CommandHandler) and "wallet" in h.commands).callback

    n = len(bot.calls)
    await wallet(Update(update_id=1, message=text_msg(STRANGER, "/wallet", bot)), SimpleNamespace(args=[]))
    assert len(bot.calls) == n
    await wallet(Update(update_id=2, message=text_msg(OWNER, "/wallet", bot)), SimpleNamespace(args=[]))
    assert "Claude spend" in bot.of("send_message")[-1]["text"]
