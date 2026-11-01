"""MongoDB access (motor). Database ``post_formatter_bot`` - separate from the channel-posting bot.

Collections:
  drafts  - one document per post being formatted (deleted automatically after DRAFT_TTL_DAYS)
  usage   - Claude API calls with tokens and estimated cost, and finished posts (see bot.usage)
  lease   - single-instance lease (see bot.lease)
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from bot.config import Config

log = logging.getLogger(__name__)


class Database:
    def __init__(self, db: Any, client: Any = None, ttl_days: int = 7) -> None:
        self.db = db
        self.client = client
        self.ttl_days = ttl_days
        self.drafts = db["drafts"]
        self.usage = db["usage"]
        self.lease = db["lease"]

    @classmethod
    async def connect(cls, cfg: Config) -> Database:
        client = AsyncIOMotorClient(cfg.mongo_url, tz_aware=True, serverSelectionTimeoutMS=15000)
        await client.admin.command("ping")
        log.info("connected to MongoDB (db=%s)", cfg.mongo_db_name)
        return cls(client[cfg.mongo_db_name], client, cfg.draft_ttl_days)

    async def ensure_indexes(self) -> None:
        await self.drafts.create_index("created_at", expireAfterSeconds=self.ttl_days * 86400)
        await self.drafts.create_index([("user_id", 1), ("awaiting_edit", 1)])
        await self.usage.create_index("at")

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
