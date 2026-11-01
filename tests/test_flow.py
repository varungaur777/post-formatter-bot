"""End-to-end flow through the Formatter with Telegram and Claude mocked."""

from __future__ import annotations

from bot.handlers import Formatter, parse_format
from tests.conftest import ADMIN, GROUP, OWNER, button, last_markup_data, photo_msg, text_msg


async def send(fmt: Formatter, msg) -> None:
    await fmt.on_format(msg, parse_format(msg.text or msg.caption, None))


async def _draft_id(fmt: Formatter) -> str:
    d = await fmt.db.drafts.find_one({}, sort=[("created_at", -1)])
    return d["_id"]


async def test_text_post_full_flow(fmt, bot, claude):
    claude.outputs.append("🇮🇳 Chandrayaan 5 launched\n\n▪️ India launched it today at 3 pm")
    await send(fmt, text_msg(OWNER, "/format india ne aaj chandrayaan 5 launch kiya, 3 baje", bot))
    did = await _draft_id(fmt)
    call = claude.calls[-1]
    assert call["model"] == "claude-opus-5-5"
    assert "English" in call["system"] and "▪️" in call["system"]
    assert "chandrayaan 5" in claude.prompt()
    assert call["output_config"] == {"effort": "low"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    preview = bot.of("send_message")[-1]
    assert preview["text"] == "<b>🇮🇳 Chandrayaan 5 launched</b>\n\n▪️ India launched it today at 3 pm"
    assert last_markup_data(bot) == [f"re:{did}", f"ed:{did}", f"ok:{did}", f"x:{did}"]

    # edit with an instruction
    await fmt.on_button(button(OWNER, f"ed:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["awaiting_edit"] is True
    claude.outputs.append("🇮🇳 Chandrayaan 5\n\n▪️ India launched it today at 3 pm")
    await fmt.on_text(text_msg(OWNER, "make the heading shorter", bot))
    prompt = claude.prompt()
    assert "make the heading shorter" in prompt and "Chandrayaan 5 launched" in prompt
    d = await fmt.db.drafts.find_one({"_id": did})
    assert d["text"].startswith("🇮🇳 Chandrayaan 5\n") and d["awaiting_edit"] is False
    assert await fmt.db.drafts.count_documents({}) == 1  # the edit did not start a new draft

    # done -> clean final post (no buttons) + forward note
    await fmt.on_button(button(OWNER, f"ok:{did}", bot))
    final, note = bot.of("send_message")[-2:]
    assert final["text"].startswith("<b>🇮🇳 Chandrayaan 5</b>\n") and final.get("reply_markup") is None
    assert "Priyanshipostbot" in note["text"]
    assert (await fmt.db.drafts.find_one({"_id": did}))["status"] == "done"

    # buttons of a finished draft are stale
    await fmt.on_button(button(OWNER, f"re:{did}", bot))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True


async def test_photo_post_uses_caption_limit_and_sends_photo_to_model(fmt, bot, claude):
    claude.outputs.append("🇯🇵 Japan earthquake\n\n▪️ Magnitude 7.1")
    await send(fmt, photo_msg(OWNER, "/format Japan me bhukamp 7.1", bot))
    did = await _draft_id(fmt)
    call = claude.calls[-1]
    assert "1024 characters" in call["system"]
    image = call["messages"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"
    assert bot.of("get_file")[-1]["file_id"] == "big-photo"
    preview = bot.of("send_photo")[-1]
    assert preview["photo"] == "big-photo" and preview["caption"].startswith("<b>🇯🇵 Japan earthquake</b>")

    await fmt.on_button(button(OWNER, f"ok:{did}", bot))
    final = bot.of("send_photo")[-1]
    assert final["photo"] == "big-photo" and final.get("reply_markup") is None


async def test_html_is_escaped_in_preview(fmt, bot, claude):
    claude.outputs.append("Maths fact\na < b & c")
    await send(fmt, text_msg(OWNER, "/format a < b & c", bot))
    assert "a &lt; b &amp; c" in bot.of("send_message")[-1]["text"]


async def test_regenerate_passes_previous_version(fmt, bot, claude):
    claude.outputs += ["First version\nbody", "Second version\nbody"]
    await send(fmt, text_msg(OWNER, "/format raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(OWNER, f"re:{did}", bot))
    assert "First version" in claude.prompt()
    assert (await fmt.db.drafts.find_one({"_id": did}))["text"].startswith("Second version")


async def test_ai_error_is_shown_with_retry_buttons(fmt, bot, claude):
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    claude.outputs.append(anthropic.BadRequestError("Your credit balance is too low",
                                                    response=httpx2.Response(400, request=req), body=None))
    await send(fmt, text_msg(OWNER, "/format raw", bot))
    did = await _draft_id(fmt)
    err = bot.of("send_message")[-1]
    assert "credits" in err["text"]
    assert last_markup_data(bot) == [f"re:{did}", f"x:{did}"]  # Try again / Cancel
    claude.outputs.append("Heading\nbody")
    await fmt.on_button(button(OWNER, f"re:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["text"] == "Heading\nbody"


async def test_other_users_cannot_press_my_buttons(fmt, bot):
    await send(fmt, text_msg(OWNER, "/format raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(ADMIN, f"re:{did}", bot))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True


async def test_cancel_and_cancel_edit(fmt, bot, claude):
    await send(fmt, text_msg(OWNER, "/format raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(OWNER, f"ed:{did}", bot))
    assert await fmt.cancel_edit(OWNER) is True
    assert await fmt.cancel_edit(OWNER) is False
    await fmt.on_button(button(OWNER, f"x:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["status"] == "cancelled"


async def test_format_by_reply_and_usage(fmt, bot):
    from datetime import UTC, datetime

    from telegram import Chat, Message

    original = photo_msg(ADMIN, "Japan me bhukamp", bot, chat_id=GROUP)
    cmd = Message(message_id=999_001, date=datetime.now(UTC), chat=Chat(id=GROUP, type="supergroup"),
                  from_user=original.from_user, text="/format magnitude 7.1", reply_to_message=original)
    cmd.set_bot(bot)
    await send(fmt, cmd)
    d = await fmt.db.drafts.find_one({})
    assert d["raw_text"] == "Japan me bhukamp\n\nmagnitude 7.1" and d["photo_file_id"] == "big-photo"

    await send(fmt, text_msg(OWNER, "/format", bot))
    assert "Nothing to format" in bot.of("send_message")[-1]["text"]
    assert await fmt.db.drafts.count_documents({}) == 1


async def test_plain_messages_are_ignored_without_edit(fmt, bot):
    assert await fmt.on_text(text_msg(ADMIN, "normal group chat", bot, chat_id=GROUP)) is False
    assert await fmt.db.drafts.count_documents({}) == 0


def test_parse_format():
    from bot.handlers import parse_format

    assert parse_format("/format hello\nworld", "Bot") == "hello\nworld"
    assert parse_format("/format@Bot hi", "bot") == "hi"
    assert parse_format("/format@OtherBot hi", "Bot") is None
    assert parse_format("/formatting hi", "Bot") is None
    assert parse_format("hello /format", "Bot") is None
    assert parse_format("/FORMAT", "Bot") == ""


async def test_refusal_is_reported(fmt, bot, claude):
    claude.outputs.append(("refusal", ""))
    await send(fmt, text_msg(OWNER, "/format raw", bot))
    assert "declined" in bot.of("send_message")[-1]["text"]


async def test_group_flow_stays_in_group_and_per_user(fmt, bot, claude):
    claude.outputs.append("🇮🇳 Heading\n\n▪️ point")
    await send(fmt, text_msg(ADMIN, "/format group member ka content", bot, chat_id=GROUP))
    did = await _draft_id(fmt)
    assert bot.of("send_message")[-1]["chat_id"] == GROUP
    # another member cannot press the first member's buttons
    await fmt.on_button(button(OWNER, f"ok:{did}", bot, chat_id=GROUP))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True
    # edit: only the same user's next message in the same chat counts as the instruction
    await fmt.on_button(button(ADMIN, f"ed:{did}", bot, chat_id=GROUP))
    await send(fmt, text_msg(OWNER, "/format kisi aur ka naya post", bot, chat_id=GROUP))
    assert await fmt.db.drafts.count_documents({}) == 2
    claude.outputs.append("🇮🇳 Short\n\n▪️ point")
    await fmt.on_text(text_msg(ADMIN, "make it shorter", bot, chat_id=GROUP))
    assert (await fmt.db.drafts.find_one({"_id": did}))["text"].startswith("🇮🇳 Short")
    await fmt.on_button(button(ADMIN, f"ok:{did}", bot, chat_id=GROUP))
    final, note = bot.of("send_message")[-2:]
    assert "Priyanshipostbot" in note["text"]
    assert final["chat_id"] == GROUP and final["text"].startswith("<b>🇮🇳 Short</b>")


async def test_handlers_access_rules(cfg, fmt, bot, access):
    from types import SimpleNamespace

    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler

    from bot.handlers import register
    from tests.conftest import OTHER_GROUP, STRANGER

    app = Application.builder().token("123:TEST").build()
    register(app, cfg, fmt, access)
    handlers = app.handlers[0]
    content = next(h for h in handlers if isinstance(h, MessageHandler)).callback  # the /format handler
    cmd = {name: h.callback for h in handlers if isinstance(h, CommandHandler) for name in h.commands}

    def upd(uid, text, chat_id=None):
        if text == "hello":
            text = "/format hello"
        return Update(update_id=1, message=text_msg(uid, text, bot, chat_id=chat_id))

    # DM: only the owner
    await content(upd(STRANGER, "hello"), None)
    assert f"<code>{STRANGER}</code>" in bot.of("send_message")[-1]["text"]
    assert await fmt.db.drafts.count_documents({}) == 0
    await content(upd(OWNER, "hello"), None)
    assert await fmt.db.drafts.count_documents({}) == 1

    # allowed group: any member
    await content(upd(STRANGER, "hello", chat_id=GROUP), None)
    assert await fmt.db.drafts.count_documents({}) == 2

    # other group: ignored silently
    n = len(bot.calls)
    await content(upd(OWNER, "hello", chat_id=OTHER_GROUP), None)
    assert await fmt.db.drafts.count_documents({}) == 2 and len(bot.calls) == n

    # /id shows the group chat id (works anywhere, so the owner can find the id)
    await cmd["id"](upd(STRANGER, "/id", chat_id=OTHER_GROUP), SimpleNamespace(args=[]))
    assert f"<code>{OTHER_GROUP}</code>" in bot.of("send_message")[-1]["text"]


def test_post_html_bolds_only_the_heading():
    from bot.handlers import post_html

    assert post_html("🇮🇳 A < B\n\n▪️ x & y") == "<b>🇮🇳 A &lt; B</b>\n\n▪️ x &amp; y"
    assert post_html("Only heading") == "<b>Only heading</b>"
