"""Who may use the bot: the owner in a private chat (DM), and every member of the group(s) in GROUP_CHAT_ID.

Anyone else's DM gets a short "not allowed" with their user ID; other groups are ignored.
"""

from __future__ import annotations

from telegram import Chat

from bot.config import Config


class Access:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def is_group(self, chat: Chat | None) -> bool:
        return chat is not None and chat.id in self.cfg.group_chat_ids

    def allowed(self, chat: Chat | None, user_id: int | None) -> bool:
        if chat is None or user_id is None:
            return False
        if chat.type == Chat.PRIVATE:
            return self.cfg.is_owner(user_id)
        return self.is_group(chat)
