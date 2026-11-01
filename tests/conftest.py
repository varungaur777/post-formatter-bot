"""Shared fixtures: config, mongomock database, a fake Telegram bot and a fake OpenAI client."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from mongomock_motor import AsyncMongoMockClient
from telegram import CallbackQuery, Chat, Message, PhotoSize, Update, User

from bot.access import Access
from bot.ai import PostAI
from bot.config import Config
from bot.db import Database
from bot.handlers import Formatter

OWNER, ADMIN, STRANGER = 1, 2, 99


def make_config(**over: Any) -> Config:
    base = dict(bot_token="123:TEST", owner_id=OWNER, submitter_ids=frozenset({ADMIN}),
                anthropic_api_key="sk-ant-test", mongo_url="mongodb://test", mongo_db_name="test")
    base.update(over)
    return Config(**base)


class FakeBot:
    """Records every call; every send_* returns a message-like object with a fresh id."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail: dict[str, list[BaseException]] = defaultdict(list)
        self._next = 1000
        self.defaults = None

    def _record(self, name: str, kw: dict) -> None:
        self.calls.append((name, kw))
        if self.fail[name]:
            raise self.fail[name].pop(0)

    def of(self, name: str) -> list[dict]:
        return [kw for n, kw in self.calls if n == name]

    async def send_message(self, chat_id: int, text: str, **kw: Any) -> Any:
        self._record("send_message", dict(chat_id=chat_id, text=text, **kw))
        self._next += 1
        return SimpleNamespace(message_id=self._next, photo=None)

    async def send_photo(self, chat_id: int, photo: Any, **kw: Any) -> Any:
        self._record("send_photo", dict(chat_id=chat_id, photo=photo, **kw))
        self._next += 1
        fid = photo if isinstance(photo, str) else f"generated-{self._next}"
        return SimpleNamespace(message_id=self._next, photo=[SimpleNamespace(file_id=fid)])

    async def get_file(self, file_id: str) -> Any:
        self._record("get_file", dict(file_id=file_id))

        async def download_as_bytearray() -> bytearray:
            return bytearray(b"jpeg-bytes")

        return SimpleNamespace(download_as_bytearray=download_as_bytearray)

    def __getattr__(self, name: str) -> Any:
        async def call(*args: Any, **kw: Any) -> Any:
            self._record(name, kw)
            return True

        return call


class FakeClaude:
    """Mimics AsyncAnthropic.beta.messages.create. Queue output texts or exceptions in ``outputs``."""

    def __init__(self) -> None:
        self.outputs: list[Any] = []
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kw: Any) -> Any:
        self.calls.append(kw)
        out = self.outputs.pop(0) if self.outputs else "Default headline\nDefault body"
        if isinstance(out, BaseException):
            raise out
        if isinstance(out, tuple):  # (stop_reason, text)
            return SimpleNamespace(stop_reason=out[0], content=[SimpleNamespace(type="text", text=out[1])])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=out)])

    def prompt(self, i: int = -1) -> str:
        return next(b["text"] for b in self.calls[i]["messages"][0]["content"] if b["type"] == "text")

    async def close(self) -> None:
        pass


@pytest.fixture
def cfg() -> Config:
    return make_config()


@pytest.fixture
def db() -> Database:
    return Database(AsyncMongoMockClient(tz_aware=True)["test"])


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def claude() -> FakeClaude:
    return FakeClaude()


@pytest.fixture
async def access(cfg: Config, db: Database) -> Access:
    a = Access(cfg, db)
    await a.load()
    return a


@pytest.fixture
def fmt(cfg: Config, db: Database, bot: FakeBot, claude: FakeClaude, access: Access) -> Formatter:
    return Formatter(cfg, db, bot, PostAI(cfg, client=claude), access)


_mid = iter(range(1, 10**6))


def user(uid: int) -> User:
    return User(id=uid, first_name=f"User{uid}", is_bot=False)


def text_msg(uid: int, text: str, bot: FakeBot) -> Message:
    m = Message(message_id=next(_mid), date=datetime.now(UTC), chat=Chat(id=uid, type="private"),
                from_user=user(uid), text=text)
    m.set_bot(bot)
    return m


def photo_msg(uid: int, caption: str | None, bot: FakeBot, group: str | None = None) -> Message:
    photo = (PhotoSize(file_id="small", file_unique_id="s", width=10, height=10),
             PhotoSize(file_id="big-photo", file_unique_id="b", width=100, height=100))
    m = Message(message_id=next(_mid), date=datetime.now(UTC), chat=Chat(id=uid, type="private"),
                from_user=user(uid), photo=photo, caption=caption, media_group_id=group)
    m.set_bot(bot)
    return m


def button(uid: int, data: str, bot: FakeBot) -> Update:
    msg = Message(message_id=next(_mid), date=datetime.now(UTC), chat=Chat(id=uid, type="private"))
    q = CallbackQuery(id=str(next(_mid)), from_user=user(uid), chat_instance="ci", data=data, message=msg)
    q.set_bot(bot)
    msg.set_bot(bot)
    return Update(update_id=next(_mid), callback_query=q)


def last_markup_data(bot: FakeBot) -> list[str]:
    """callback_data of the buttons on the most recent message that had buttons."""
    for _name, kw in reversed(bot.calls):
        markup = kw.get("reply_markup")
        if markup:
            return [b.callback_data for row in markup.inline_keyboard for b in row]
    return []
