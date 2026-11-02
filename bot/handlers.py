"""Telegram side: /format + content (owner DM or the allowed group) -> Claude -> preview with buttons ->
final post (bold heading) in the same chat. Messages without /format are ignored, except the edit instruction.

Draft document (collection ``drafts``):
  {_id, user_id, chat_id, raw_text, photo_file_id, text, preview_msg_id,
   awaiting_edit, status: new|ready|done|cancelled, created_at, updated_at}
Callback data: ``re:<draft>``, ``ed:<draft>``, ``ok:<draft>``, ``x:<draft>``.
"""

from __future__ import annotations

import contextlib
import logging
import re
import secrets
from typing import Any

from telegram import ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot import texts
from bot.access import Access
from bot.ai import AIError, PostAI
from bot.config import Config
from bot.db import Database
from bot.styles import POST
from bot.usage import UsageStore
from bot.utils import CAPTION_LIMIT, TEXT_LIMIT, h, utcnow

log = logging.getLogger(__name__)
TEXT_TARGET = TEXT_LIMIT - 96  # leave room: the posting bot adds its own footer


_FORMAT = re.compile(r"^\s*/format(?:@(\w+))?(?=\s|$)", re.IGNORECASE)


def parse_format(text: str | None, bot_username: str | None) -> str | None:
    """'/format some text' -> 'some text'; None if the text is not a /format command (for this bot)."""
    m = _FORMAT.match(text or "")
    if m is None:
        return None
    if m.group(1) and bot_username and m.group(1).lower() != bot_username.lower():
        return None  # /format@some_other_bot
    return (text or "")[m.end():].strip()


def result_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(texts.BTN_REGEN, callback_data=f"re:{draft_id}"),
         InlineKeyboardButton(texts.BTN_EDIT, callback_data=f"ed:{draft_id}")],
        [InlineKeyboardButton(texts.BTN_DONE, callback_data=f"ok:{draft_id}"),
         InlineKeyboardButton(texts.BTN_CANCEL, callback_data=f"x:{draft_id}")],
    ])


def retry_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(texts.BTN_RETRY, callback_data=f"re:{draft_id}"),
                                  InlineKeyboardButton(texts.BTN_CANCEL, callback_data=f"x:{draft_id}")]])


def post_html(text: str) -> str:
    """The post as Telegram HTML: line 1 (the heading) in bold, the rest unchanged."""
    heading, sep, rest = text.partition("\n")
    return f"<b>{h(heading)}</b>{sep}{h(rest)}" if heading.strip() else h(text)


class Formatter:
    def __init__(self, cfg: Config, db: Database, bot: Any, ai: PostAI, usage: UsageStore | None = None) -> None:
        self.cfg = cfg
        self.db = db
        self.bot = bot
        self.ai = ai
        self.usage = usage
        self.busy: set[str] = set()

    # ---- helpers -----------------------------------------------------------------------------
    @staticmethod
    def limit_for(draft: dict) -> int:
        return CAPTION_LIMIT if draft.get("photo_file_id") else TEXT_TARGET

    async def _update(self, draft_id: str, **fields: Any) -> None:
        await self.db.drafts.update_one({"_id": draft_id}, {"$set": {**fields, "updated_at": utcnow()}})

    async def _photo_bytes(self, file_id: str | None) -> bytes | None:
        if not file_id:
            return None
        try:
            f = await self.bot.get_file(file_id)
            return bytes(await f.download_as_bytearray())
        except TelegramError as e:
            log.warning("could not download photo for the model: %s", e)
            return None

    async def _drop_keyboard(self, chat_id: int, message_id: int | None) -> None:
        if message_id:
            with contextlib.suppress(TelegramError):
                await self.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)

    async def send_post(self, chat_id: int, text: str, photo: Any = None,
                        markup: InlineKeyboardMarkup | None = None) -> Message:
        """Send the post (photo + caption, or text). Returns the message that carries the buttons."""
        body = post_html(text)
        if photo is None:
            return await self.bot.send_message(chat_id, body, parse_mode=ParseMode.HTML, reply_markup=markup)
        return await self.bot.send_photo(chat_id, photo=photo, caption=body, parse_mode=ParseMode.HTML,
                                         reply_markup=markup)

    async def show_preview(self, draft: dict) -> dict:
        await self._drop_keyboard(draft["chat_id"], draft.get("preview_msg_id"))
        msg = await self.send_post(draft["chat_id"], draft["text"], draft.get("photo_file_id"),
                                   result_keyboard(draft["_id"]))
        fields: dict[str, Any] = {"preview_msg_id": msg.message_id, "status": "ready"}
        await self._update(draft["_id"], **fields)
        draft.update(fields)
        return draft

    async def _status(self, chat_id: int, text: str) -> Message | None:
        try:
            return await self.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        except TelegramError:
            return None

    async def _clear_status(self, chat_id: int, msg: Message | None) -> None:
        if msg is not None:
            with contextlib.suppress(TelegramError):
                await self.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)

    # ---- incoming content --------------------------------------------------------------------
    async def on_text(self, msg: Message) -> bool:
        """A plain message (no /format): used only as the edit instruction for a draft. True if used."""
        if not msg.text:
            return False
        editing = await self.db.drafts.find_one(
            {"user_id": msg.from_user.id, "chat_id": msg.chat_id, "awaiting_edit": True}, sort=[("updated_at", -1)])
        if editing is None:
            return False
        await self.apply_edit(editing, msg.text)
        return True

    async def on_format(self, msg: Message, extra: str) -> None:
        """/format: the content is the text after the command, or the message it replies to (plus that text)."""
        source = msg.reply_to_message
        if source is not None and (source.text or source.caption or source.photo):
            raw = source.text or source.caption or ""
            if source.text and source.text.lstrip().lower().startswith("/format"):
                raw = parse_format(source.text, None) or ""
            if extra:
                raw = f"{raw}\n\n{extra}".strip()
            photo_id = source.photo[-1].file_id if source.photo else None
        else:
            raw = extra
            photo_id = msg.photo[-1].file_id if msg.photo else None
        if not raw.strip() and not photo_id:
            await msg.reply_text(texts.FORMAT_USAGE, parse_mode=ParseMode.HTML)
            return
        draft_id = secrets.token_hex(5)
        now = utcnow()
        await self.db.drafts.insert_one({
            "_id": draft_id, "user_id": msg.from_user.id, "chat_id": msg.chat_id, "raw_text": raw,
            "photo_file_id": photo_id, "text": None, "preview_msg_id": None, "awaiting_edit": False,
            "status": "new", "created_at": now, "updated_at": now,
        })
        draft = await self.db.drafts.find_one({"_id": draft_id})
        self._claim(draft_id)
        try:
            await self.run_format(draft)
        finally:
            self.busy.discard(draft_id)

    async def run_format(self, draft: dict, *, regenerate: bool = False, instruction: str | None = None) -> None:
        status = await self._status(draft["chat_id"], texts.WORKING)
        try:
            image = await self._photo_bytes(draft.get("photo_file_id"))
            text = await self.ai.format_post(
                POST, draft.get("raw_text") or "", limit=self.limit_for(draft), image_bytes=image,
                previous=draft.get("text") if (regenerate or instruction) else None, instruction=instruction,
            )
        except AIError as e:
            await self._clear_status(draft["chat_id"], status)
            await self.bot.send_message(draft["chat_id"], texts.ERROR.format(error=h(e)) + "\n" + texts.FAILED_RETRY,
                                        parse_mode=ParseMode.HTML,
                                        reply_markup=result_keyboard(draft["_id"]) if draft.get("text")
                                        else retry_keyboard(draft["_id"]))
            return
        await self._clear_status(draft["chat_id"], status)
        await self._update(draft["_id"], text=text, awaiting_edit=False)
        draft["text"] = text
        await self.show_preview(draft)

    async def apply_edit(self, draft: dict, instruction: str) -> None:
        if not self._claim(draft["_id"]):
            await self.bot.send_message(draft["chat_id"], texts.BUSY)
            return
        await self._update(draft["_id"], awaiting_edit=False)
        try:
            await self.run_format(draft, instruction=instruction)
        finally:
            self.busy.discard(draft["_id"])

    def _claim(self, draft_id: str) -> bool:
        if draft_id in self.busy:
            return False
        self.busy.add(draft_id)
        return True

    # ---- buttons -----------------------------------------------------------------------------
    async def on_button(self, update: Update) -> None:
        q = update.callback_query
        parts = (q.data or "").split(":")
        action, draft_id = parts[0], parts[1] if len(parts) > 1 else ""
        draft = await self.db.drafts.find_one({"_id": draft_id})
        if draft is None or draft["user_id"] != q.from_user.id or draft.get("status") in ("done", "cancelled"):
            await q.answer(texts.STALE, show_alert=True)
            with contextlib.suppress(TelegramError):
                await q.edit_message_reply_markup(reply_markup=None)
            return
        if not self._claim(draft_id):
            await q.answer(texts.BUSY)
            return
        try:
            await q.answer()
            if action == "re":
                if not draft.get("text"):  # "Try again" after an error
                    with contextlib.suppress(TelegramError):
                        await q.edit_message_reply_markup(reply_markup=None)
                await self.run_format(draft, regenerate=bool(draft.get("text")))
            elif action == "ed" and draft.get("text"):
                await self._update(draft_id, awaiting_edit=True)
                await self.bot.send_message(draft["chat_id"], texts.ASK_EDIT, parse_mode=ParseMode.HTML)
            elif action == "ok" and draft.get("text"):
                await self.finish(draft)
            elif action == "x":
                await self._update(draft_id, status="cancelled", awaiting_edit=False)
                with contextlib.suppress(TelegramError):
                    await q.edit_message_reply_markup(reply_markup=None)
                await self.bot.send_message(draft["chat_id"], texts.CANCELLED)
        finally:
            self.busy.discard(draft_id)

    async def finish(self, draft: dict) -> None:
        await self._drop_keyboard(draft["chat_id"], draft.get("preview_msg_id"))
        await self.send_post(draft["chat_id"], draft["text"], draft.get("photo_file_id"))
        await self._update(draft["_id"], status="done", awaiting_edit=False)
        if self.usage is not None:
            await self.usage.record_post()
        await self.bot.send_message(draft["chat_id"], texts.FINAL_NOTE, parse_mode=ParseMode.HTML)

    async def wallet_text(self) -> str:
        """Owner's spend report (estimate from token counts)."""
        totals = await self.usage.summary() if self.usage is not None else {}

        def line(label: str, key: str) -> str:
            t = totals[key]
            return texts.WALLET_LINE.format(label=label, usd=t.usd, inr=t.usd * self.cfg.usd_inr, calls=t.calls,
                                            posts=t.posts)

        return texts.WALLET.format(today=line("Today", "today"), month=line("This month", "month"),
                                   total=line("All time", "total"), model=h(self.cfg.ai_model),
                                   rate=self.cfg.usd_inr)

    async def cancel_edit(self, user_id: int) -> bool:
        res = await self.db.drafts.update_many({"user_id": user_id, "awaiting_edit": True},
                                               {"$set": {"awaiting_edit": False}})
        return res.modified_count > 0


# ---- handler wiring ------------------------------------------------------------------------------
def register(app: Application, cfg: Config, fmt: Formatter, access: Access) -> None:
    where = filters.ChatType.PRIVATE | filters.ChatType.GROUPS  # which groups are allowed is checked by guard()

    async def guard(update: Update) -> bool:
        user, chat = update.effective_user, update.effective_chat
        if access.allowed(chat, user.id if user else None):
            return True
        if update.callback_query:
            await update.callback_query.answer("⛔", show_alert=False)
        elif chat is not None and chat.type == chat.PRIVATE and update.effective_message and user:
            await update.effective_message.reply_text(texts.NOT_ALLOWED.format(uid=user.id), parse_mode=ParseMode.HTML)
        return False  # other groups: stay quiet

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        await update.effective_message.reply_text(texts.HELP, parse_mode=ParseMode.HTML)

    async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = texts.YOUR_ID.format(uid=update.effective_user.id)
        chat = update.effective_chat
        if chat.type != chat.PRIVATE:
            text += "\n" + texts.CHAT_ID.format(cid=chat.id)
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        done = await fmt.cancel_edit(update.effective_user.id)
        await update.effective_message.reply_text(texts.EDIT_CANCELLED if done else texts.NOTHING_TO_CANCEL)

    async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not cfg.is_owner(update.effective_user.id):
            return
        await update.effective_message.reply_text(await fmt.wallet_text(), parse_mode=ParseMode.HTML)

    async def format_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        extra = parse_format(msg.text or msg.caption, msg.get_bot().username)
        if extra is None:
            return
        if not await guard(update):
            chat = update.effective_chat
            if chat.type != chat.PRIVATE and cfg.is_owner(update.effective_user.id):
                await msg.reply_text(texts.AUTH_FIRST)
            return
        await fmt.on_format(msg, extra)

    async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
        if not cfg.is_owner(user.id):
            await msg.reply_text(texts.AUTH_OWNER_ONLY)
            return
        if chat.type == chat.PRIVATE:
            await msg.reply_text(texts.AUTH_IN_GROUP)
            return
        bot = msg.get_bot()
        try:
            member = await bot.get_chat_member(chat.id, bot.id)
        except TelegramError as e:
            log.warning("could not check my admin rights: %s", e)
            await msg.reply_text(texts.AUTH_NOT_ADMIN)
            return
        if member.status not in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
            await msg.reply_text(texts.AUTH_NOT_ADMIN)
            return
        await access.authorize(chat.id, chat.title or "", user.id)
        await msg.reply_text(texts.AUTH_OK, parse_mode=ParseMode.HTML)

    async def unauth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
        if not cfg.is_owner(user.id):
            await msg.reply_text(texts.AUTH_OWNER_ONLY)
            return
        if chat.type == chat.PRIVATE:
            await msg.reply_text(texts.AUTH_IN_GROUP)
            return
        result = await access.revoke(chat.id)
        await msg.reply_text({"removed": texts.UNAUTH_OK, "env": texts.UNAUTH_ENV,
                              "missing": texts.UNAUTH_MISSING}[result])

    async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not cfg.is_owner(update.effective_user.id):
            return
        lines = [texts.GROUP_LINE.format(title=h(title), cid=cid) for cid, title in access.listing()]
        await update.effective_message.reply_text(
            texts.GROUPS.format(groups="\n".join(lines)) if lines else texts.GROUPS_EMPTY, parse_mode=ParseMode.HTML)

    async def migrated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if msg.migrate_to_chat_id:
            await access.migrate(msg.chat_id, msg.migrate_to_chat_id)

    async def plain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Messages without /format: only edit instructions. In the group everything else is ignored."""
        if not await guard(update):
            return
        msg = update.effective_message
        if await fmt.on_text(msg):
            return
        if update.effective_chat.type == update.effective_chat.PRIVATE:
            await msg.reply_text(texts.FORMAT_HINT, parse_mode=ParseMode.HTML)

    async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        await fmt.on_button(update)

    app.add_handler(CommandHandler(["start", "help"], start, filters=where))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("cancel", cancel, filters=where))
    app.add_handler(CommandHandler(["wallet", "usage"], wallet, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("groups", list_groups, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("auth", auth, filters=where))
    app.add_handler(CommandHandler("unauth", unauth, filters=where))
    is_format = filters.Regex(_FORMAT) | filters.CaptionRegex(_FORMAT)
    app.add_handler(MessageHandler(where & is_format, format_cmd))
    app.add_handler(MessageHandler(where & ~filters.COMMAND & ~filters.StatusUpdate.ALL, plain))
    app.add_handler(MessageHandler(filters.StatusUpdate.MIGRATE, migrated))
    app.add_handler(CallbackQueryHandler(button))
