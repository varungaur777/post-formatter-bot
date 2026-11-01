"""End-to-end flow through the Formatter with Telegram and OpenAI mocked."""

from __future__ import annotations

from bot.handlers import Formatter
from tests.conftest import ADMIN, FAKE_PNG, button, last_markup_data, photo_msg, text_msg


async def _draft_id(fmt: Formatter) -> str:
    d = await fmt.db.drafts.find_one({}, sort=[("created_at", -1)])
    return d["_id"]


async def test_text_post_full_flow(fmt, bot, oai):
    await fmt.on_content(text_msg(ADMIN, "india ne aaj chandrayaan 5 launch kiya, 3 baje", bot))
    did = await _draft_id(fmt)
    assert last_markup_data(bot) == [f"st:{did}:spitting", f"st:{did}:geosight", f"x:{did}"]

    oai.text_outputs.append("Chandrayaan 5 launch 🚀\nIndia ne aaj 3 baje launch kiya")
    await fmt.on_button(button(ADMIN, f"st:{did}:spitting", bot))
    call = oai.text_calls[-1]
    assert call["model"] == "gpt-6.1-terra"
    assert "@spitting_fact" in call["instructions"]
    assert "chandrayaan 5" in call["input"][0]["content"][0]["text"]
    assert call["reasoning"] == {"effort": "low"}
    preview = bot.of("send_message")[-1]
    assert preview["text"].startswith("Chandrayaan 5 launch")
    assert last_markup_data(bot) == [f"img:{did}", f"re:{did}", f"ed:{did}", f"ok:{did}"]

    # edit with an instruction
    await fmt.on_button(button(ADMIN, f"ed:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["awaiting_edit"] is True
    oai.text_outputs.append("Chandrayaan 5 🚀\nIndia ne aaj 3 baje launch kiya")
    await fmt.on_content(text_msg(ADMIN, "headline chhoti karo", bot))
    prompt = oai.text_calls[-1]["input"][0]["content"][0]["text"]
    assert "headline chhoti karo" in prompt and "Chandrayaan 5 launch 🚀" in prompt
    d = await fmt.db.drafts.find_one({"_id": did})
    assert d["text"].startswith("Chandrayaan 5 🚀") and d["awaiting_edit"] is False
    assert await fmt.db.drafts.count_documents({}) == 1  # the edit did not start a new draft

    # generate an image -> preview becomes a photo with the caption
    await fmt.on_button(button(ADMIN, f"img:{did}", bot))
    assert oai.image_calls[-1]["model"] == "gpt-image-2.5-flare"
    photo = bot.of("send_photo")[-1]
    assert photo["photo"] == FAKE_PNG and photo["caption"].startswith("Chandrayaan 5")
    d = await fmt.db.drafts.find_one({"_id": did})
    assert d["image_file_id"].startswith("generated-")

    # done -> clean final post (no buttons) using the stored file_id + forward note
    n_before = len(bot.calls)
    await fmt.on_button(button(ADMIN, f"ok:{did}", bot))
    final = bot.of("send_photo")[-1]
    assert final["photo"] == d["image_file_id"] and final.get("reply_markup") is None
    assert "Priyanshipostbot" in bot.of("send_message")[-1]["text"]
    assert "Join" not in final["caption"]
    assert len(bot.calls) > n_before
    assert (await fmt.db.drafts.find_one({"_id": did}))["status"] == "done"

    # buttons of a finished draft are stale
    await fmt.on_button(button(ADMIN, f"re:{did}", bot))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True


async def test_photo_post_uses_caption_limit_and_sends_photo_to_model(fmt, bot, oai):
    await fmt.on_content(photo_msg(ADMIN, "Japan me bhukamp 7.1", bot))
    did = await _draft_id(fmt)
    oai.text_outputs.append("🇯🇵 Japan earthquake\n\n▪️ Magnitude 7.1")
    await fmt.on_button(button(ADMIN, f"st:{did}:geosight", bot))
    call = oai.text_calls[-1]
    assert "1024 characters" in call["instructions"] and "@GeoSight" in call["instructions"]
    image_part = call["input"][0]["content"][1]
    assert image_part["type"] == "input_image" and image_part["image_url"].startswith("data:image/jpeg;base64,")
    assert bot.of("get_file")[-1]["file_id"] == "big-photo"
    preview = bot.of("send_photo")[-1]
    assert preview["photo"] == "big-photo" and preview["caption"].startswith("🇯🇵 Japan")


async def test_html_is_escaped_in_preview(fmt, bot, oai):
    await fmt.on_content(text_msg(ADMIN, "a < b & c", bot))
    did = await _draft_id(fmt)
    oai.text_outputs.append("Maths fact\na < b & c")
    await fmt.on_button(button(ADMIN, f"st:{did}:spitting", bot))
    assert "a &lt; b &amp; c" in bot.of("send_message")[-1]["text"]


async def test_regenerate_passes_previous_version(fmt, bot, oai):
    await fmt.on_content(text_msg(ADMIN, "raw", bot))
    did = await _draft_id(fmt)
    oai.text_outputs += ["First version\nbody", "Second version\nbody"]
    await fmt.on_button(button(ADMIN, f"st:{did}:spitting", bot))
    await fmt.on_button(button(ADMIN, f"re:{did}", bot))
    assert "First version" in oai.text_calls[-1]["input"][0]["content"][0]["text"]
    assert (await fmt.db.drafts.find_one({"_id": did}))["text"].startswith("Second version")


async def test_ai_error_is_shown_with_retry_buttons(fmt, bot, oai):
    import httpx2
    import openai

    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    oai.text_outputs.append(openai.RateLimitError("quota", response=httpx2.Response(429, request=req),
                                                  body={"code": "insufficient_quota"}))
    await fmt.on_content(text_msg(ADMIN, "raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(ADMIN, f"st:{did}:geosight", bot))
    err = bot.of("send_message")[-1]
    assert "billing" in err["text"]
    assert last_markup_data(bot)[0] == f"st:{did}:spitting"  # can pick a style again


async def test_other_users_cannot_press_my_buttons(fmt, bot):
    await fmt.on_content(text_msg(ADMIN, "raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(1, f"st:{did}:spitting", bot))
    assert bot.of("answer_callback_query")[-1]["show_alert"] is True


async def test_cancel_and_cancel_edit(fmt, bot, oai):
    await fmt.on_content(text_msg(ADMIN, "raw", bot))
    did = await _draft_id(fmt)
    await fmt.on_button(button(ADMIN, f"st:{did}:spitting", bot))
    await fmt.on_button(button(ADMIN, f"ed:{did}", bot))
    assert await fmt.cancel_edit(ADMIN) is True
    assert await fmt.cancel_edit(ADMIN) is False
    await fmt.on_button(button(ADMIN, f"x:{did}", bot))
    assert (await fmt.db.drafts.find_one({"_id": did}))["status"] == "cancelled"


async def test_album_only_first_photo(fmt, bot):
    await fmt.on_content(photo_msg(ADMIN, "cap", bot, group="g1"))
    await fmt.on_content(photo_msg(ADMIN, None, bot, group="g1"))
    assert await fmt.db.drafts.count_documents({}) == 1


async def test_long_text_with_generated_image_goes_as_two_messages(fmt, bot, oai):
    await fmt.on_content(text_msg(ADMIN, "raw", bot))
    did = await _draft_id(fmt)
    long_text = "Headline\n" + "x" * 1500
    oai.text_outputs.append(long_text)
    await fmt.on_button(button(ADMIN, f"st:{did}:spitting", bot))
    await fmt.on_button(button(ADMIN, f"img:{did}", bot))
    assert "caption" not in bot.of("send_photo")[-1]
    assert bot.of("send_message")[-1]["text"] == long_text
    assert (await fmt.db.drafts.find_one({"_id": did}))["image_file_id"]


async def test_handlers_guard_and_owner_commands(cfg, fmt, bot, access):
    from types import SimpleNamespace

    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler

    from bot.handlers import register
    from tests.conftest import OWNER, STRANGER

    app = Application.builder().token("123:TEST").build()
    register(app, cfg, fmt, access)
    handlers = app.handlers[0]
    content = next(h for h in handlers if isinstance(h, MessageHandler)).callback
    cmd = {name: h.callback for h in handlers if isinstance(h, CommandHandler) for name in h.commands}

    def upd(uid, text):
        return Update(update_id=1, message=text_msg(uid, text, bot))

    await content(upd(STRANGER, "hello"), None)
    assert f"<code>{STRANGER}</code>" in bot.of("send_message")[-1]["text"]
    assert await fmt.db.drafts.count_documents({}) == 0

    await cmd["adduser"](upd(ADMIN, "/adduser 99"), SimpleNamespace(args=["99"]))
    assert "owner" in bot.of("send_message")[-1]["text"]
    await cmd["adduser"](upd(OWNER, "/adduser 99"), SimpleNamespace(args=["99"]))
    assert access.allowed(STRANGER)
    await content(upd(STRANGER, "hello"), None)
    assert await fmt.db.drafts.count_documents({}) == 1
    await cmd["users"](upd(OWNER, "/users"), SimpleNamespace(args=[]))
    assert "<code>99</code>" in bot.of("send_message")[-1]["text"]
    await cmd["removeuser"](upd(OWNER, "/removeuser 99"), SimpleNamespace(args=["99"]))
    assert not access.allowed(STRANGER)
