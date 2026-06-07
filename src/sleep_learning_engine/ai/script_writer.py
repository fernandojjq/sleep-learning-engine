"""Script generation and parsing."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..core import ConfigError
from .connector import AIConnector, ChatMessage

# --------------------------------------------------------------------- scripts

SYSTEM_PROMPT = (
    "You are an experienced teacher writing an audio lesson for a curious "
    "adult who is listening with their eyes closed, in bed, in the dark, "
    "with no screen and no visual aid of any kind. Your job is to teach, "
    "not to relax them.\n"
    "\n"
    "Audio-only constraint (the most important rule):\n"
    "- The listener is NOT looking at a screen. There is no image, no "
    "diagram, no chart, no video, no list, no bullet point, no table, no "
    "highlight, no cursor, no scrollbar. They are hearing your words "
    "through earbuds or a speaker. Whatever they understand, they have to "
    "build entirely in their own head from your words alone.\n"
    "- Never say 'as you can see', 'look at the diagram', 'on the screen', "
    "'on the slide', 'in the picture', 'below', 'above', 'to the right', "
    "'highlighted in yellow', or any phrase that references a visual aid. "
    "If the listener cannot tell from your words alone that something is "
    "'to the right' or 'highlighted', the phrase is wrong. Remove it.\n"
    "- When you describe a person, place, object, or number, give enough "
    "concrete detail to paint a clear mental picture: size, shape, color, "
    "sound, smell, feeling, approximate date, or number. 'A small wooden "
    "box about the size of a microwave' is better than 'a small box'.\n"
    "- Spelled-out numbers beat digits for audio ('about twelve thousand' "
    "beats '12,000'). The ear remembers spoken numbers more reliably.\n"
    "- Spell out symbols and units ('percent' not '%', 'kilometers' not "
    "'km'). The narrator will read them aloud.\n"
    "\n"
    "Style:\n"
    "- Explain like you are talking to a smart friend who is curious but "
    "not an expert. Plain English. Short sentences. Concrete examples "
    "over abstractions.\n"
    "- Use analogies from everyday life (cooking, sports, weather, money, "
    "family, walking down the street) so the listener can picture each "
    "one. Avoid analogies that need a picture to make sense.\n"
    "- Repeat key terms and names the first time you use them, then use the "
    "short form afterwards. Spaced repetition helps memory.\n"
    "- For every concept, give a concrete example or a short story. Then a "
    "one-sentence recap of why it matters.\n"
    "\n"
    "Structure:\n"
    "- Open by framing the topic in one or two sentences. Why is it "
    "interesting? Why does it matter? What will the listener be able to "
    "understand or remember by the end?\n"
    "- Walk through the topic in small chunks (one idea per paragraph). "
    "Use a clear progression: background, then idea, then example, then "
    "why it matters, then what comes next.\n"
    "- Use clear transitions: 'Next', 'Building on that', 'Here is where "
    "it gets interesting', 'Now the surprising part', 'Going back to the "
    "big picture for a moment'.\n"
    "- End with a short recap of the three or four things the listener "
    "should remember. Do not try to make them sleepy. Do not end with a "
    "good night or rest line. The listener is here to learn.\n"
    "\n"
    "Voice:\n"
    "- Second person ('you') is fine for direct address, but mostly use "
    "third person for historical or scientific content.\n"
    "- Active voice, present tense for current facts, past tense for "
    "history.\n"
    "- No dramatic tension, no cliffhangers, no rhetorical questions "
    "designed to provoke. Calm and clear beats dramatic. The listener is "
    "trying to learn, not to be entertained."
)

USER_TEMPLATE = """Write an audio lesson about the topic below for a curious
adult who is listening with their eyes closed, in bed, in the dark,
with no screen of any kind.

Topic:
\"\"\"{topic}\"\"\"

Target word count: approximately {word_count} words.
Language: {language}.

Format requirements:
- Plain prose. No bullet points, no lists, no headings, no markdown,
  no tables, no numbered lists.
- Separate paragraphs with a single blank line.
- Each paragraph should be two to four short sentences.
- Every concept must be fully understandable from the audio alone.
  No 'as you can see', no 'on the screen', no 'in the picture', no
  'below', no 'highlighted', no 'to the right'. The listener has no
  visual aid.
- Spelled-out numbers beat digits ('about twelve thousand' not
  '12,000'). Spell out units ('percent' not '%').
- Open by framing the topic. End with a short recap of the key
  takeaways. Do NOT end with a 'good night' or 'fall asleep' line -
  the listener wants to remember, not to rest.
"""


@dataclass
class Script:
    """A narration script broken into renderable paragraphs."""

    title: str
    paragraphs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.paragraphs = [p.strip() for p in self.paragraphs if p and p.strip()]

    @property
    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)

    def plain_text(self) -> str:
        return "\n\n".join(self.paragraphs)

    def to_file(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.plain_text() + "\n", encoding="utf-8")
        return path


def load_script_from_file(path: Path) -> Script:
    """Read a script from disk and split it into paragraphs."""
    if not path.exists():
        raise ConfigError(f"Script file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ConfigError(f"Script file is empty: {path}")
    paragraphs = _split_paragraphs(text)
    title = path.stem.replace("_", " ").replace("-", " ").title()
    return Script(title=title, paragraphs=paragraphs)


def _split_paragraphs(text: str) -> list[str]:
    raw = re.split(r"\n\s*\n+", text)
    return [chunk.strip() for chunk in raw if chunk.strip()]


# ----------------------------------------------------------- public surface


class ScriptWriter:
    """High-level facade for generating a Script from a topic or file."""

    def __init__(self, connector: AIConnector) -> None:
        self._connector = connector

    def write(
        self,
        *,
        topic: str,
        target_word_count: int = 4500,
        language: str = "en",
        feedback: str | None = None,
        system_prompt: str | None = None,
        on_chunk=None,
    ) -> Script:
        """Generate a fresh script for the given topic.

        If ``system_prompt`` is provided, it replaces the built-in default
        for this single call. Pass an empty string to fall back to the
        built-in ``SYSTEM_PROMPT``.

        If ``on_chunk`` is provided, it is called with every text delta
        as the model streams the response. This gives the caller live
        progress during long generations.
        """
        if not topic.strip():
            raise ConfigError("Topic cannot be empty.")
        prompt = (system_prompt.strip() if system_prompt else "") or SYSTEM_PROMPT
        messages: list[ChatMessage] = [
            ChatMessage("system", prompt),
            ChatMessage(
                "user",
                USER_TEMPLATE.format(
                    topic=topic.strip(),
                    word_count=target_word_count,
                    language=language,
                ),
            ),
        ]
        if feedback:
            messages.append(
                ChatMessage(
                    "user",
                    "Refine the previous answer using this guidance: " + feedback.strip(),
                )
            )
        body = self._connector.chat(
            messages,
            temperature=0.7,
            max_tokens=max(1024, min(8192, target_word_count * 2)),
            on_chunk=on_chunk,
        )
        paragraphs = _split_paragraphs(_strip_markdown(body))
        if not paragraphs:
            raise ConfigError("Provider returned an empty script.")
        title = topic.strip().splitlines()[0][:80].title() or "Sleep Lesson"
        return Script(title=title, paragraphs=paragraphs)

    def split_into_cues(self, paragraphs: Iterable[str]) -> list[dict[str, str]]:
        """Turn a list of paragraphs into renderable cues.

        Each cue carries the paragraph text plus a stable id used for log
        correlation. The renderer consumes the cues sequentially.
        """
        return [
            {"id": f"para-{i:04d}", "text": paragraph}
            for i, paragraph in enumerate(p for p in paragraphs if p.strip())
        ]


_MARKDOWN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*]+)\*"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),
    (re.compile(r"^\s*\d+\.\s+", re.MULTILINE), ""),
)


def _strip_markdown(text: str) -> str:
    cleaned = text
    for pattern, replacement in _MARKDOWN_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned

