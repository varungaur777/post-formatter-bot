"""Who may use the bot: the owner, SUBMITTER_IDS from env, and users the owner added with /adduser."""

from __future__ import annotations

from bot.config import Config
from bot.db import Database
from bot.utils import utcnow


class Access:
    def __init__(self, cfg: Config, db: Database) -> None:
        self.cfg = cfg
        self.db = db
        self.added: set[int] = set()

    async def load(self) -> None:
        self.added = {int(d["_id"]) async for d in self.db.users.find({})}

    def allowed(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        return self.cfg.is_owner(user_id) or user_id in self.cfg.submitter_ids or user_id in self.added

    async def add(self, user_id: int, by: int) -> bool:
        if self.allowed(user_id):
            return False
        await self.db.users.update_one({"_id": user_id}, {"$set": {"added_by": by, "added_at": utcnow()}},
                                       upsert=True)
        self.added.add(user_id)
        return True

    async def remove(self, user_id: int) -> str:
        """'removed' | 'env' (only in SUBMITTER_IDS, can't remove here) | 'owner' | 'missing'"""
        if self.cfg.is_owner(user_id):
            return "owner"
        if user_id in self.added:
            await self.db.users.delete_one({"_id": user_id})
            self.added.discard(user_id)
            return "removed"
        if user_id in self.cfg.submitter_ids:
            return "env"
        return "missing"

    def listing(self) -> tuple[list[int], list[int]]:
        return sorted(self.cfg.submitter_ids), sorted(self.added - set(self.cfg.submitter_ids))
