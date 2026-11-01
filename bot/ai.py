"""Claude API call that formats a post. The model comes from env (AI_MODEL, default claude-opus-5-5).

Every failure is turned into ``AIError`` with a short English message that is safe to show to the admin;
the key never reaches a message.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import anthropic

from bot.config import Config
from bot.styles import Style, system_prompt
from bot.usage import UsageStore

log = logging.getLogger(__name__)

# models that accept the server-side refusal fallback (`fallbacks: "default"`)
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")
_TAG = re.compile(r"</?(b|i|u|s|strong|em|code|pre|blockquote|a)(\s[^>]*)?>", re.IGNORECASE)


class AIError(Exception):
    """Claude could not do the job (message is safe to show to the user)."""


def clean_output(text: str) -> str:
    """Strip what models sometimes add anyway: code fences, wrapping quotes, HTML tags, **bold**."""
    text = (text or "").strip()
    text = _FENCE.sub("", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    text = _TAG.sub("", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _map_error(e: Exception) -> AIError:
    if isinstance(e, anthropic.AuthenticationError):
        log.error("Claude: invalid API key")
        return AIError("The Claude API key is invalid – the owner should check ANTHROPIC_API_KEY.")
    if isinstance(e, anthropic.PermissionDeniedError):
        log.error("Claude: permission denied (%s)", getattr(e, "message", e))
        return AIError("The Claude API key has no access to this model.")
    if isinstance(e, anthropic.NotFoundError):
        log.error("Claude: model not found (%s)", getattr(e, "message", e))
        return AIError("Claude model not found – the owner should check AI_MODEL.")
    if isinstance(e, anthropic.RateLimitError):
        return AIError("Claude is busy right now – try again in a minute.")
    if isinstance(e, anthropic.BadRequestError):
        msg = str(getattr(e, "message", "") or "")
        log.warning("Claude: bad request (%s)", msg)
        if "credit" in msg.lower() or "billing" in msg.lower():
            return AIError("The Claude account is out of credits – check billing on platform.claude.com.")
        return AIError("Claude couldn't process this content.")
    if isinstance(e, anthropic.APIConnectionError):
        return AIError("Couldn't reach Claude – try again in a little while.")
    if isinstance(e, anthropic.APIStatusError):
        log.warning("Claude: API error %s", e.status_code)
        return AIError("Claude had a problem – try again in a little while.")
    log.exception("Claude: unexpected error")
    return AIError("Something went wrong – please try again.")


class PostAI:
    def __init__(self, cfg: Config, client: Any = None, usage: UsageStore | None = None) -> None:
        self.cfg = cfg
        self.client = client or anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key, timeout=120.0,
                                                         max_retries=2)
        self.usage = usage

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            await close()

    async def _ask(self, system: str, content: list[dict]) -> str:
        kwargs: dict[str, Any] = {}
        if self.cfg.ai_effort:
            kwargs["output_config"] = {"effort": self.cfg.ai_effort}
        if self.cfg.ai_model in FALLBACK_MODELS:
            # if the model declines, the API retries on Anthropic's recommended model inside the same call
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        try:
            resp = await self.client.beta.messages.create(
                model=self.cfg.ai_model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": content}],
                **kwargs,
            )
        except anthropic.AnthropicError as e:
            raise _map_error(e) from None
        if self.usage is not None and getattr(resp, "usage", None) is not None:
            try:  # billed even when refused; the model that answered may be a fallback model
                await self.usage.record_call(getattr(resp, "model", None) or self.cfg.ai_model, resp.usage)
            except Exception:
                log.warning("could not record API usage", exc_info=True)
        if resp.stop_reason == "refusal":
            raise AIError("Claude declined to format this content.")
        text = "".join(b.text for b in resp.content if b.type == "text")
        return clean_output(text)

    async def format_post(self, style: Style, raw_text: str, *, limit: int, image_bytes: bytes | None = None,
                          previous: str | None = None, instruction: str | None = None) -> str:
        """Format ``raw_text`` in ``style``. With ``previous`` + ``instruction`` it edits an earlier result."""
        system = system_prompt(style, limit)
        if previous and instruction:
            prompt = (f"Original raw content:\n{raw_text or '(no text, only the photo)'}\n\n"
                      f"Your current version of the post:\n{previous}\n\n"
                      f"The admin wants these changes (follow them, keep all hard rules):\n{instruction}\n\n"
                      "Return the full updated post.")
        else:
            prompt = f"Raw content to format:\n{raw_text or '(no text - write the post from the photo only)'}"
            if previous:
                prompt += f"\n\nYour previous version was:\n{previous}\nWrite a fresh, different version."
        content: list[dict] = []
        if image_bytes:  # Telegram photos are JPEG
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.standard_b64encode(image_bytes).decode()}})
        content.append({"type": "text", "text": prompt})

        text = await self._ask(system, content)
        if len(text) > limit:  # one retry, then give up
            content = [{"type": "text",
                        "text": f"Shorten this post to at most {limit - 50} characters, same style and language, "
                                f"keep the key facts:\n\n{text}"}]
            text = await self._ask(system, content)
        if not text:
            raise AIError("Claude returned an empty answer – please try again.")
        if len(text) > limit:
            raise AIError(f"The post is longer than {limit} characters – use ✏️ Edit and ask for a shorter version.")
        return text
