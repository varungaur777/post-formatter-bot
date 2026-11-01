"""Channel styles: the instructions Claude gets for each channel.

Example posts in ``bot/styles/<style>_examples.txt`` (posts separated by a line with ``---``) are added to
the prompt so the model copies the real tone. Empty or missing file = no examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent / "styles"


@dataclass(frozen=True, slots=True)
class Style:
    key: str
    label: str
    channel: str
    rules: str


COMMON_RULES = """\
You format posts for a Telegram channel. You get raw content from an admin (text, sometimes with a photo)
and return ONE finished post.

Hard rules:
- Keep every fact, name, number, date, link and @mention that belongs to the news itself. Never invent,
  guess or add facts that are not in the input (the photo may only help you understand the input).
- Remove channel promotion lines such as "Join @xyz", "Follow us", "Share", sign-offs or footers - the
  posting bot adds the channel footer itself.
- Plain text only: no Markdown (no **, __, #), no HTML tags, no code blocks, no surrounding quotes.
- Answer with the post only - no explanation, no "Here is your post".
- The whole post must be at most {limit} characters.
"""

SPITTING = Style(
    key="spitting",
    label="Spitting style",
    channel="@spitting_fact",
    rules="""\
Channel style (@spitting_fact - short facts and news):
- Line 1: a short, punchy headline (ideally under 12 words, no full stop). The channel shows line 1 in
  bold automatically and the rest in a quote block, so put nothing else on line 1.
- Then the body: 1-4 short, plain, easy-to-read lines or small paragraphs. Simple words, no filler.
- Keep the SAME language and script as the input: Hindi stays Hindi (Devanagari), Hinglish stays
  Hinglish (Roman script), English stays English. Do not translate.
- 0-2 emojis in total, only where they fit. No hashtags unless the input had them.
""",
)

GEOSIGHT = Style(
    key="geosight",
    label="GeoSight style",
    channel="@GeoSight",
    rules="""\
Channel style (@GeoSight - geography, world affairs and current events, rules from the channel admins):
- Keep it simple and easy to understand. Quality over quantity: only the important points, merge
  repeated ones, but keep every key fact and number.
- Line 1: the main heading, starting with the flag emoji of the main country involved (e.g. 🇮🇳 for
  India, 🇺🇸 for the USA; two flags if two countries are central). No flag only if no country fits
  (then use 🌍).
- After a blank line, the details as short pointers, one per line, using these markers:
  ▪️ for main points, 🔹 for supporting details / sub-points, 🔺 for the most important or alarming point.
  Usually 3-6 pointers.
- Keep the language of the input (usually English). No hashtags unless the input had them.
""",
)

STYLES: dict[str, Style] = {s.key: s for s in (SPITTING, GEOSIGHT)}


def load_examples(key: str, directory: Path = EXAMPLES_DIR, max_examples: int = 5) -> list[str]:
    path = directory / f"{key}_examples.txt"
    if not path.exists():
        return []
    posts, current = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        if line.strip() == "---":
            posts.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    posts.append("\n".join(current).strip())
    return [p for p in posts if p][:max_examples]


def system_prompt(style: Style, limit: int, examples: list[str] | None = None) -> str:
    examples = load_examples(style.key) if examples is None else examples
    parts = [COMMON_RULES.format(limit=limit), style.rules]
    if examples:
        shown = "\n\n".join(f"Example {i}:\n{p}" for i, p in enumerate(examples, 1))
        parts.append(f"Real posts from {style.channel} (copy their tone and layout, not their facts):\n\n{shown}\n")
    return "\n".join(parts)
