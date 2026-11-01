"""End-to-end flow through the Formatter with Telegram and Claude mocked."""

from __future__ import annotations

from bot.handlers import Formatter
from tests.conftest import ADMIN, GROUP, OWNER, button, last_markup_data, photo_msg, text_msg


async def _draft_id(fmt: Formatter) -> str:
    d = await fmt.db.drafts.find_one({}, sort=[("created_at", -1)])
    return d["_id"]


async def test_text_post_full_flow(fmt, bot, claude):
    await fmt.on_content(text_msg(OWNER, "india ne aaj chandrayaan 5 launch kiya, 3 baje", bot))
    did = await _draft_id(fmt)
    assert last_markup_data(bot) == [f"st:{did}:spitting", f"st:{did}:geosight", f"x:{did}"]

    claude.outputs.append("Chandrayaan 5 launch 🚀\nIndia ne aaj 3 baje launch kiya")
    await fmt.on_button(button(OWNER, f"st:{did}:spitting", bot))
    call = claude.calls[-1]
    assert call["model"] == "claude-opus-5-5"
    assert "@spitting_fact" in call["system"]
    assert "chandrayaan 5" in claude.prompt()
    assert call["output_config"] == {"effort": "low"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    preview = bot.of("send_message")[-1]
    assert preview["text"].startswith("Chandrayaan 5 launch")
    assert last_markup_data(bot) == [f"re:{did}", f"ed:{did}", f"ok:{did}"]

    # edit with an instruction
    await fmt.on_button(button(OWNER, f"ed:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["awaiting_edit"] is True
    claude.outputs.append("Chandrayaan 5 🚀\nIndia ne aaj 3 baje launch kiya")
    await fmt.on_content(text_msg(OWNER, "headline chhoti karo", bot))
    prompt = claude.prompt()
    assert "headline chhoti karo" in prompt and "Chandrayaan 5 launch 🚀" in prompt
    d = await fmt.db.drafts.find_one({"_id": did})
    assert d["text"].startswith("Chandrayaan 5 🚀") and d["awaiting_edit"] is False
    assert await fmt.db.drafts.count_documents({}) == 1  # the edit did not start a new draft

    # done -> clean final post (no buttons) + forward note
    await fmt.on_button(button(OWNER, f"ok:{did}", bot))
    final, note = bot.of("send_message")[-2:]
    assert final["text"] == d["text"] and final.get("reply_markup") is None
    assert "Priyanshipostbot" in note["text"]
    assert (await fmt.db.drafts.find_one({"_id": did}))["status"] == "done"

    # buttons of a finished draft are stale
    await fmt.on_button(button(OWNER, f"re:{did}", bot))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True


async def test_photo_post_uses_caption_limit_and_sends_photo_to_model(fmt, bot, claude):
    await fmt.on_content(photo_msg(OWNER, "Japan me bhukamp 7.1", bot))
    did = await _draft_id(fmt)
    claude.outputs.append("🇯🇵 Japan earthquake\n\n▪️ Magnitude 7.1")
    await fmt.on_button(button(OWNER, f"st:{did}:geosight", bot))
    call = claude.calls[-1]
    assert "1024 characters" in call["system"] and "@GeoSight" in call["system"]
    image = call["messages"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"
    assert bot.of("get_file")[-1]["file_id"] == "big-photo"
    preview = bot.of("send_photo")[-1]
    assert preview["photo"] == "big-photo" and preview["caption"].startswith("🇯🇵 Japan")

    await fmt.on_button(button(OWNER, f"ok:{did}", bot))
    final = bot.of("send_photo")[-1]
    assert final["photo"] == "big-photo" and final.get("reply_markup") is None


async def test_html_is_escaped_in_preview(fmt, bot, claude):
    await fmt.on_content(text_msg(OWNER, "a < b & c", bot))
    did = await _draft_id(fmt)
    claude.outputs.append("Maths fact\na < b & c")
    await fmt.on_button(button(OWNER, f"st:{did}:spitting", bot))
    assert "a &lt; b &amp; c" in bot.of("send_message")[-1]["text"]


async def test_regenerate_passes_previous_version(fmt, bot, claude):
    await fmt.on_content(text_msg(OWNER, "raw", bot))
    did = await _draft_id(fmt)
    claude.outputs += ["First version\nbody", "Second version\nbody"]
    await fmt.on_button(button(OWNER, f"st:{did}:spitting", bot))
    await fmt.on_button(button(OWNER, f"re:{did}", bot))
    assert "First version" in claude.prompt()
    assert (await fmt.db.drafts.find_one({"_id": did}))["text"].startswith("Second version")


async def test_ai_error_is_shown_with_retry_buttons(fmt, bot, claude):
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    claude.outputs.append(anthropic.BadRequestError("Your credit balance is too low",
                                                    response=httpx2.Response(400, request=req), body=None))
    await fmt.on_content(text_msg(OWNER, "raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(OWNER, f"st:{did}:geosight", bot))
    err = bot.of("send_message")[-1]
    assert "credit" in err["text"]
    assert last_markup_data(bot)[0] == f"st:{did}:spitting"  # can pick a style again


async def test_other_users_cannot_press_my_buttons(fmt, bot):
    await fmt.on_content(text_msg(OWNER, "raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(ADMIN, f"st:{did}:spitting", bot))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True


async def test_cancel_and_cancel_edit(fmt, bot, claude):
    await fmt.on_content(text_msg(OWNER, "raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(OWNER, f"st:{did}:spitting", bot))
    await fmt.on_button(button(OWNER, f"ed:{did}", bot))
    assert await fmt.cancel_edit(OWNER) is True
    assert await fmt.cancel_edit(OWNER) is False
    await fmt.on_button(button(OWNER, f"x:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["status"] == "cancelled"


async def test_album_only_first_photo(fmt, bot):
    await fmt.on_content(photo_msg(OWNER, "cap", bot, group="g1"))
    await fmt.on_content(photo_msg(OWNER, None, bot, group="g1"))
    assert await fmt.db.drafts.count_documents({}) == 1


async def test_refusal_is_reported(fmt, bot, claude):
    await fmt.on_content(text_msg(OWNER, "raw", bot))
    did = await _draft_id(fmt)
    claude.outputs.append(("refusal", ""))
    await fmt.on_button(button(OWNER, f"st:{did}:spitting", bot))
    assert "mana" in bot.of("send_message")[-1]["text"]


async def test_group_flow_stays_in_group_and_per_user(fmt, bot, claude):
    await fmt.on_content(text_msg(ADMIN, "group member ka content", bot, chat_id=GROUP))
    did = await _draft_id(fmt)
    assert bot.of("send_message")[-1]["chat_id"] == GROUP
    # another member cannot press the first member's buttons
    await fmt.on_button(button(OWNER, f"st:{did}:geosight", bot, chat_id=GROUP))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True
    claude.outputs.append("🇮🇳 Heading\n\n▪️ point")
    await fmt.on_button(button(ADMIN, f"st:{did}:geosight", bot, chat_id=GROUP))
    assert bot.of("send_message")[-1]["chat_id"] == GROUP
    # edit: only the same user's next message in the same chat counts as the instruction
    await fmt.on_button(button(ADMIN, f"ed:{did}", bot, chat_id=GROUP))
    await fmt.on_content(text_msg(OWNER, "kisi aur ka naya post", bot, chat_id=GROUP))
    assert await fmt.db.drafts.count_documents({}) == 2
    claude.outputs.append("🇮🇳 Short\n\n▪️ point")
    await fmt.on_content(text_msg(ADMIN, "chhota karo", bot, chat_id=GROUP))
    assert (await fmt.db.drafts.find_one({"_id": did}))["text"].startswith("🇮🇳 Short")
    await fmt.on_button(button(ADMIN, f"ok:{did}", bot, chat_id=GROUP))
    final, note = bot.of("send_message")[-2:]
    assert "Priyanshipostbot" in note["text"]
    assert final["chat_id"] == GROUP and final["text"].startswith("🇮🇳 Short")


async def test_handlers_access_rules(cfg, fmt, bot, access):
    from types import SimpleNamespace

    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler

    from bot.handlers import register
    from tests.conftest import OTHER_GROUP, STRANGER

    app = Application.builder().token("123:TEST").build()
    register(app, cfg, fmt, access)
    handlers = app.handlers[0]
    content = next(h for h in handlers if isinstance(h, MessageHandler)).callback
    cmd = {name: h.callback for h in handlers if isinstance(h, CommandHandler) for name in h.commands}

    def upd(uid, text, chat_id=None):
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
