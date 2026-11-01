"""What the bot spends on Claude: every API call's tokens go to collection ``usage`` with an estimated cost.

The cost is estimated from the token counts the API returns and the list prices below (USD per 1M tokens);
the exact bill and the remaining balance are only on platform.claude.com -> Billing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bot.utils import as_utc, utcnow

# input, output (USD per 1M tokens) - Anthropic list prices
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
UNKNOWN_PRICE = (10.0, 50.0)  # unknown model: assume the most expensive tier rather than under-report
CACHE_WRITE, CACHE_READ = 1.25, 0.10  # multipliers of the input price
TZ = ZoneInfo("Asia/Kolkata")


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    price_in, price_out = PRICES.get(model, UNKNOWN_PRICE)
    return (input_tokens * price_in + cache_write * price_in * CACHE_WRITE + cache_read * price_in * CACHE_READ
            + output_tokens * price_out) / 1_000_000


@dataclass(slots=True)
class Totals:
    usd: float = 0.0
    calls: int = 0
    posts: int = 0


class UsageStore:
    def __init__(self, coll: Any, clock: Callable[[], datetime] = utcnow) -> None:
        self.coll = coll
        self.clock = clock

    async def record_call(self, model: str, usage: Any) -> float:
        """Store one Claude call. ``usage`` is the response's ``usage`` object."""
        tokens = {k: int(getattr(usage, k, 0) or 0) for k in
                  ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        usd = cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],
                       tokens["cache_creation_input_tokens"], tokens["cache_read_input_tokens"])
        await self.coll.insert_one({"type": "call", "at": self.clock(), "model": model, **tokens, "usd": usd})
        return usd

    async def record_post(self) -> None:
        await self.coll.insert_one({"type": "post", "at": self.clock()})

    async def summary(self) -> dict[str, Totals]:
        now = self.clock().astimezone(TZ)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month = day.replace(day=1)
        out = {"today": Totals(), "month": Totals(), "total": Totals()}
        async for d in self.coll.find({}):
            at = as_utc(d["at"]).astimezone(TZ)
            buckets = ["total"] + (["month"] if at >= month else []) + (["today"] if at >= day else [])
            for b in buckets:
                t = out[b]
                if d["type"] == "call":
                    t.usd += d.get("usd", 0.0)
                    t.calls += 1
                elif d["type"] == "post":
                    t.posts += 1
        return out
