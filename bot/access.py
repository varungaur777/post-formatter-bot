"""Who may use the bot: the owner in a private chat (DM), and every member of an authorized group.

Groups are authorized by GROUP_CHAT_ID (env) or by the owner sending /auth in the group (collection ``groups``,
so it survives restarts). Anyone else's DM gets a short "not allowed" with their user ID; other groups are ignored.
"""

from __future__ import annotations

from typing import Any

from telegram import Chat

from bot.config import Config
from bot.utils import utcnow


class Access:
    def __init__(self, cfg: Config, db: Any) -> None:
        self.cfg = cfg
        self.db = db
        self.authed: dict[int, str] = {}  # chat id -> title

    async def load(self) -> None:
        self.authed = {int(d["_id"]): d.get("title") or "" async for d in self.db.groups.find({})}

    def is_group(self, chat: Chat | None) -> bool:
        return chat is not None and (chat.id in self.cfg.group_chat_ids or chat.id in self.authed)

    def allowed(self, chat: Chat | None, user_id: int | None) -> bool:
        if chat is None or user_id is None:
            return False
        if chat.type == Chat.PRIVATE:
            return self.cfg.is_owner(user_id)
        return self.is_group(chat)

    async def authorize(self, chat_id: int, title: str, by: int) -> None:
        await self.db.groups.update_one({"_id": chat_id}, {"$set": {"title": title, "by": by, "at": utcnow()}},
                                        upsert=True)
        self.authed[chat_id] = title

    async def revoke(self, chat_id: int) -> str:
        """'removed' | 'env' (set by GROUP_CHAT_ID, can't be removed here) | 'missing'"""
        if chat_id in self.cfg.group_chat_ids:
            return "env"
        if chat_id not in self.authed:
            return "missing"
        await self.db.groups.delete_one({"_id": chat_id})
        del self.authed[chat_id]
        return "removed"

    async def migrate(self, old_id: int, new_id: int) -> None:
        """A group that became a supergroup gets a new chat id; keep it authorized."""
        if old_id in self.authed:
            title = self.authed[old_id]
            await self.db.groups.delete_one({"_id": old_id})
            del self.authed[old_id]
            await self.authorize(new_id, title, self.cfg.owner_id)

    def listing(self) -> list[tuple[int, str]]:
        ids = {i: "" for i in self.cfg.group_chat_ids} | self.authed
        return sorted(ids.items())
