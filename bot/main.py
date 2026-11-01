"""Entry point: ``python -m bot``.

Start-up: config -> logging -> MongoDB -> instance lease (wait if another copy is live) -> deleteWebhook ->
setMyCommands -> polling + lease heartbeat.
Shutdown (SIGTERM/SIGINT, MAX_RUNTIME_MINUTES reached, or lease lost): stop polling, let running handlers
finish, release the lease, close the AI client + DB. Exit codes: 0 normal stop, 1 crash, 2 bad configuration.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.error import InvalidToken
from telegram.ext import Application, ContextTypes

from bot import __version__, texts
from bot.access import Access
from bot.ai import PostAI
from bot.config import Config, ConfigError, load_config
from bot.db import Database
from bot.handlers import Formatter, register
from bot.lease import Lease
from bot.utils import setup_logging

log = logging.getLogger("bot")


def build_application(cfg: Config) -> Application:
    return (
        Application.builder()
        .token(cfg.bot_token)
        .concurrent_updates(True)
        .connect_timeout(15).read_timeout(60).write_timeout(60).pool_timeout(15)
        .get_updates_read_timeout(40)
        .build()
    )


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("error while handling an update: %s", context.error, exc_info=context.error)


async def run(cfg: Config) -> int:
    stop = asyncio.Event()

    def request_stop(why: str) -> None:
        if not stop.is_set():
            log.info("stopping: %s", why)
            stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop, sig.name)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(request_stop, f"signal {s}"))
    if cfg.max_runtime_minutes > 0:
        loop.call_later(cfg.max_runtime_minutes * 60, request_stop,
                        f"MAX_RUNTIME_MINUTES={cfg.max_runtime_minutes:g} reached")
        log.info("will stop by itself after %g minutes", cfg.max_runtime_minutes)

    db = await Database.connect(cfg)
    lease = Lease(db.lease, expiry_s=cfg.lease_expiry_seconds, heartbeat_s=cfg.lease_heartbeat_seconds)
    ai: PostAI | None = None
    try:
        await db.ensure_indexes()
        if not await lease.acquire(stop):
            log.info("stopped before the lease became free")
            return 0

        access = Access(cfg, db)
        await access.load()
        app = build_application(cfg)
        ai = PostAI(cfg)
        fmt = Formatter(cfg, db, app.bot, ai, access)
        register(app, cfg, fmt, access)
        app.add_error_handler(_on_error)

        async with app:  # initialize() ... shutdown()
            await app.bot.delete_webhook(drop_pending_updates=False)
            await app.bot.set_my_commands([BotCommand(c, d) for c, d in texts.BOT_COMMANDS])
            await app.start()
            await app.updater.start_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
            lease.start_heartbeat(request_stop)
            log.info("bot @%s v%s is polling (profile=%s, model=%s)", app.bot.username, __version__,
                     cfg.runtime_profile, cfg.ai_model)

            await stop.wait()

            log.info("shutting down gracefully...")
            await app.updater.stop()
            await app.stop()  # waits for running handlers
        return 0
    finally:
        await lease.release()
        if ai is not None:
            await ai.close()
        await db.close()
        log.info("bye")


def main() -> int:
    load_dotenv()
    try:
        cfg = load_config()
    except ConfigError as e:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("bot").error("configuration error: %s (see .env.example)", e)
        return 2
    setup_logging(cfg.log_level, secrets=(cfg.bot_token, cfg.anthropic_api_key, cfg.mongo_url))
    try:
        return asyncio.run(run(cfg))
    except InvalidToken:
        log.error("BOT_TOKEN is invalid - check it with @BotFather")
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception:
        log.exception("bot crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
