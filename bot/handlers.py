"""Telegram side: DM in -> style buttons -> Claude -> preview with buttons -> final post in the DM.

Draft document (collection ``drafts``):
  {_id, user_id, chat_id, raw_text, photo_file_id, style, text, preview_msg_id,
   awaiting_edit, status: new|ready|done|cancelled, created_at, updated_at}
Callback data: ``st:<draft>:<style>``, ``re:<draft>``, ``ed:<draft>``, ``ok:<draft>``, ``x:<draft>``.
"""

from __future__ import annotations

import contextlib
import logging
import secrets
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot import texts
from bot.access import Access
from bot.ai import AIError, PostAI
from bot.config import Config
from bot.db import Database
from bot.styles import STYLES
from bot.utils import CAPTION_LIMIT, TEXT_LIMIT, h, utcnow

log = logging.getLogger(__name__)
TEXT_TARGET = TEXT_LIMIT - 96  # leave room: the posting bot adds its own footer


def style_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(texts.BTN_SPITTING, callback_data=f"st:{draft_id}:spitting"),
         InlineKeyboardButton(texts.BTN_GEOSIGHT, callback_data=f"st:{draft_id}:geosight")],
        [InlineKeyboardButton(texts.BTN_CANCEL, callback_data=f"x:{draft_id}")],
    ])


def result_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(texts.BTN_REGEN, callback_data=f"re:{draft_id}"),
         InlineKeyboardButton(texts.BTN_EDIT, callback_data=f"ed:{draft_id}")],
        [InlineKeyboardButton(texts.BTN_DONE, callback_data=f"ok:{draft_id}")],
    ])


class Formatter:
    def __init__(self, cfg: Config, db: Database, bot: Any, ai: PostAI, access: Access) -> None:
        self.cfg = cfg
        self.db = db
        self.bot = bot
        self.ai = ai
        self.access = access
        self.busy: set[str] = set()
        self.albums_seen: dict[str, None] = {}

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
        body = h(text)
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
    async def on_content(self, msg: Message) -> None:
        uid = msg.from_user.id
        editing = await self.db.drafts.find_one({"user_id": uid, "awaiting_edit": True},
                                                sort=[("updated_at", -1)])
        if editing is not None and msg.text:
            await self.apply_edit(editing, msg.text)
            return

        if msg.media_group_id:
            if msg.media_group_id in self.albums_seen:
                return
            self.albums_seen[msg.media_group_id] = None
            while len(self.albums_seen) > 200:
                self.albums_seen.pop(next(iter(self.albums_seen)))
            await msg.reply_text(texts.ALBUM_FIRST_ONLY)

        raw = msg.text or msg.caption or ""
        photo_id = msg.photo[-1].file_id if msg.photo else None
        if not raw.strip() and not photo_id:
            await msg.reply_text(texts.UNSUPPORTED, parse_mode=ParseMode.HTML)
            return
        draft_id = secrets.token_hex(5)
        now = utcnow()
        await self.db.drafts.insert_one({
            "_id": draft_id, "user_id": uid, "chat_id": msg.chat_id, "raw_text": raw, "photo_file_id": photo_id,
            "style": None, "text": None, "preview_msg_id": None, "awaiting_edit": False,
            "status": "new", "created_at": now, "updated_at": now,
        })
        await msg.reply_text(texts.CHOOSE_STYLE, reply_markup=style_keyboard(draft_id))

    async def run_format(self, draft: dict, *, regenerate: bool = False, instruction: str | None = None) -> None:
        style = STYLES[draft["style"]]
        status = await self._status(draft["chat_id"], texts.WORKING.format(style=h(style.label)))
        try:
            image = await self._photo_bytes(draft.get("photo_file_id"))
            text = await self.ai.format_post(
                style, draft.get("raw_text") or "", limit=self.limit_for(draft), image_bytes=image,
                previous=draft.get("text") if (regenerate or instruction) else None, instruction=instruction,
            )
        except AIError as e:
            await self._clear_status(draft["chat_id"], status)
            await self.bot.send_message(draft["chat_id"], texts.ERROR.format(error=h(e)) + "\n" + texts.FAILED_RETRY,
                                        parse_mode=ParseMode.HTML,
                                        reply_markup=result_keyboard(draft["_id"]) if draft.get("text")
                                        else style_keyboard(draft["_id"]))
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
            if action == "st" and len(parts) == 3 and parts[2] in STYLES:
                with contextlib.suppress(TelegramError):
                    await q.edit_message_reply_markup(reply_markup=None)
                await self._update(draft_id, style=parts[2])
                draft["style"] = parts[2]
                await self.run_format(draft)
            elif action == "re" and draft.get("text"):
                await self.run_format(draft, regenerate=True)
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
        await self.bot.send_message(draft["chat_id"], texts.FINAL_NOTE, parse_mode=ParseMode.HTML)

    async def cancel_edit(self, user_id: int) -> bool:
        res = await self.db.drafts.update_many({"user_id": user_id, "awaiting_edit": True},
                                               {"$set": {"awaiting_edit": False}})
        return res.modified_count > 0


# ---- handler wiring ------------------------------------------------------------------------------
def register(app: Application, cfg: Config, fmt: Formatter, access: Access) -> None:
    private = filters.ChatType.PRIVATE

    async def guard(update: Update) -> bool:
        user = update.effective_user
        if access.allowed(user.id if user else None):
            return True
        if update.callback_query:
            await update.callback_query.answer("⛔", show_alert=False)
        elif update.effective_message and user:
            await update.effective_message.reply_text(texts.NOT_ALLOWED.format(uid=user.id), parse_mode=ParseMode.HTML)
        return False

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        extra = texts.OWNER_HELP if cfg.is_owner(update.effective_user.id) else ""
        await update.effective_message.reply_text(texts.HELP + extra, parse_mode=ParseMode.HTML)

    async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(texts.YOUR_ID.format(uid=update.effective_user.id),
                                                  parse_mode=ParseMode.HTML)

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        done = await fmt.cancel_edit(update.effective_user.id)
        await update.effective_message.reply_text(texts.EDIT_CANCELLED if done else texts.NOTHING_TO_CANCEL)

    def _target(context: ContextTypes.DEFAULT_TYPE) -> int | None:
        try:
            return int(context.args[0]) if context.args else None
        except ValueError:
            return None

    async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not cfg.is_owner(update.effective_user.id):
            await msg.reply_text(texts.OWNER_ONLY)
            return
        uid = _target(context)
        if uid is None:
            await msg.reply_text(texts.ADD_USAGE)
            return
        added = await access.add(uid, update.effective_user.id)
        await msg.reply_text((texts.ADDED if added else texts.ALREADY).format(uid=uid), parse_mode=ParseMode.HTML)

    async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not cfg.is_owner(update.effective_user.id):
            await msg.reply_text(texts.OWNER_ONLY)
            return
        uid = _target(context)
        if uid is None:
            await msg.reply_text(texts.REMOVE_USAGE)
            return
        result = await access.remove(uid)
        reply = {"removed": texts.REMOVED, "env": texts.REMOVE_ENV, "owner": texts.REMOVE_OWNER,
                 "missing": texts.REMOVE_MISSING}[result]
        await msg.reply_text(reply.format(uid=uid), parse_mode=ParseMode.HTML)

    async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not cfg.is_owner(update.effective_user.id):
            await msg.reply_text(texts.OWNER_ONLY)
            return
        env_ids, added = access.listing()

        def fmt_ids(ids: list[int]) -> str:
            return ", ".join(f"<code>{i}</code>" for i in ids) or "–"

        await msg.reply_text(texts.USERS.format(owner=cfg.owner_id, env=fmt_ids(env_ids), added=fmt_ids(added)),
                             parse_mode=ParseMode.HTML)

    async def content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        await fmt.on_content(update.effective_message)

    async def unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        await update.effective_message.reply_text(texts.UNSUPPORTED, parse_mode=ParseMode.HTML)

    async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        await fmt.on_button(update)

    app.add_handler(CommandHandler(["start", "help"], start, filters=private))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("cancel", cancel, filters=private))
    app.add_handler(CommandHandler("adduser", add_user, filters=private))
    app.add_handler(CommandHandler("removeuser", remove_user, filters=private))
    app.add_handler(CommandHandler("users", list_users, filters=private))
    app.add_handler(MessageHandler(private & (filters.TEXT & ~filters.COMMAND | filters.PHOTO), content))
    app.add_handler(MessageHandler(private & ~filters.COMMAND & ~filters.StatusUpdate.ALL, unsupported))
    app.add_handler(CallbackQueryHandler(button))
