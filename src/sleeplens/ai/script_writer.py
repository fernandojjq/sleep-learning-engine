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
    "You are a senior scriptwriter who specialises in calm, hypnotic "
    "narration designed to be listened to as someone falls asleep. "
    "Write in short, soothing sentences. Use a warm, second-person voice. "
    "Avoid dramatic tension, jump scares, or stressful imagery. Weave in "
    "gentle repetition. Insert clear paragraph breaks every two to three "
    "sentences so the narrator can breathe."
)

USER_TEMPLATE = """Write a sleep-learning narration about the topic below.

Topic:
\"\"\"{topic}\"\"\"

Target word count: approximately {word_count} words.
Language: {language}.

Format requirements:
- Plain prose. No bullet points, no lists, no headings, no markdown.
- Separate paragraphs with a single blank line.
- Each paragraph must be one to three short sentences.
- End with a soft, sleepy call to rest.
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

