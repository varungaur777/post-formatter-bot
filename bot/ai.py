"""OpenAI calls: format a post (Responses API, text model) and generate an image (Images API).

Both models come from env (OPENAI_TEXT_MODEL / OPENAI_IMAGE_MODEL). Every failure is turned into
``AIError`` with a short Hinglish message that is safe to show to the admin; keys never reach a message.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import openai

from bot.config import Config
from bot.styles import Style, system_prompt

log = logging.getLogger(__name__)

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")
_TAG = re.compile(r"</?(b|i|u|s|strong|em|code|pre|blockquote|a)(\s[^>]*)?>", re.IGNORECASE)


class AIError(Exception):
    """OpenAI could not do the job (message is safe to show to the user)."""


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


def _map_error(e: Exception, what: str) -> AIError:
    if isinstance(e, openai.AuthenticationError):
        log.error("OpenAI: invalid API key")
        return AIError("OpenAI key galat hai – owner OPENAI_API_KEY check kare.")
    if isinstance(e, openai.PermissionDeniedError):
        log.error("OpenAI: permission denied for %s (%s)", what, getattr(e, "message", e))
        return AIError("OpenAI account ko is model ka access nahi hai (image ke liye Organization "
                       "Verification lag sakta hai).")
    if isinstance(e, openai.NotFoundError):
        log.error("OpenAI: model not found for %s (%s)", what, getattr(e, "message", e))
        return AIError("OpenAI model nahi mila – owner OPENAI_TEXT_MODEL / OPENAI_IMAGE_MODEL check kare.")
    if isinstance(e, openai.RateLimitError):
        if getattr(e, "code", None) == "insufficient_quota":
            log.error("OpenAI: insufficient quota (billing)")
            return AIError("OpenAI account mein balance/billing nahi hai – "
                           "platform.openai.com par billing check karein.")
        return AIError("OpenAI abhi busy hai – 1 minute baad try karein.")
    if isinstance(e, openai.BadRequestError):
        log.warning("OpenAI: bad request for %s (%s)", what, getattr(e, "message", e))
        if what == "image":
            return AIError("Is post ke liye image nahi ban saki (OpenAI ne request reject ki).")
        return AIError("OpenAI is content ko process nahi kar paya.")
    if isinstance(e, openai.APIConnectionError):
        return AIError("OpenAI se connect nahi ho paya – thodi der baad try karein.")
    if isinstance(e, openai.APIStatusError):
        log.warning("OpenAI: API error %s for %s", e.status_code, what)
        return AIError("OpenAI mein problem aayi – thodi der baad try karein.")
    log.exception("OpenAI: unexpected error for %s", what)
    return AIError("Kuch gadbad ho gayi – dobara try karein.")


class PostAI:
    def __init__(self, cfg: Config, client: Any = None) -> None:
        self.cfg = cfg
        self.client = client or openai.AsyncOpenAI(api_key=cfg.openai_api_key, timeout=120.0, max_retries=2)

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            await close()

    async def _respond(self, instructions: str, content: list[dict]) -> str:
        kwargs: dict[str, Any] = {}
        if self.cfg.reasoning_effort and self.cfg.reasoning_effort != "default":
            kwargs["reasoning"] = {"effort": self.cfg.reasoning_effort}
        try:
            resp = await self.client.responses.create(
                model=self.cfg.text_model,
                instructions=instructions,
                input=[{"role": "user", "content": content}],
                max_output_tokens=6000,
                **kwargs,
            )
        except openai.OpenAIError as e:
            raise _map_error(e, "text") from None
        return clean_output(resp.output_text or "")

    async def format_post(self, style: Style, raw_text: str, *, limit: int, image_bytes: bytes | None = None,
                          previous: str | None = None, instruction: str | None = None) -> str:
        """Format ``raw_text`` in ``style``. With ``previous`` + ``instruction`` it edits an earlier result."""
        instructions = system_prompt(style, limit)
        if previous and instruction:
            prompt = (f"Original raw content:\n{raw_text or '(no text, only the photo)'}\n\n"
                      f"Your current version of the post:\n{previous}\n\n"
                      f"The admin wants these changes (follow them, keep all hard rules):\n{instruction}\n\n"
                      "Return the full updated post.")
        else:
            prompt = f"Raw content to format:\n{raw_text or '(no text - write the post from the photo only)'}"
            if previous:
                prompt += f"\n\nYour previous version was:\n{previous}\nWrite a fresh, different version."
        content: list[dict] = [{"type": "input_text", "text": prompt}]
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}", "detail": "low"})

        text = await self._respond(instructions, content)
        if len(text) > limit:  # one retry, then give up
            content = [{"type": "input_text",
                        "text": f"Shorten this post to at most {limit - 50} characters, same style and language, "
                                f"keep the key facts:\n\n{text}"}]
            text = await self._respond(instructions, content)
        if not text:
            raise AIError("OpenAI ne khaali jawab diya – dobara try karein.")
        if len(text) > limit:
            raise AIError(f"Post {limit} characters se lamba ban raha hai – ✏️ Edit se chhota karne ko bolein.")
        return text

    async def generate_image(self, style: Style, post_text: str) -> bytes:
        prompt = (f"Create a {style.image_hint} for this Telegram channel post. "
                  "Do not put any text, letters, numbers, captions, logos or watermarks in the image. "
                  "Do not depict real, identifiable people's faces in a misleading way.\n\n"
                  f"Post:\n{post_text[:1500]}")
        try:
            result = await self.client.images.generate(
                model=self.cfg.image_model, prompt=prompt, size=self.cfg.image_size,
                quality=self.cfg.image_quality, n=1,
            )
        except openai.OpenAIError as e:
            raise _map_error(e, "image") from None
        data = (result.data or [None])[0]
        b64 = getattr(data, "b64_json", None)
        if not b64:
            raise AIError("OpenAI ne image nahi bheji – dobara try karein.")
        return base64.b64decode(b64)
