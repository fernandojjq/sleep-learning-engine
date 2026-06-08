"""Script generation and parsing."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from ..core import ConfigError
from .connector import AIConnector, ChatMessage

# --------------------------------------------------------------------- scripts


def _load_default_prompt() -> str:
    """Load the default system prompt from the public Sleeping Dev file.

    The default for this project is the **Sleeping Dev** prompt
    (``docs/prompts/sleeping_dev.md`` in the source tree,
    ``sleep_learning_engine/prompts/sleeping_dev.md`` in the
    installed wheel): a 458-line long-form software engineering
    masterclass prompt tuned for audio-only sleep-learning
    narration. It was written for the project owner's YouTube
    channel and is the default unless the caller passes
    ``system_prompt=`` to ``ScriptWriter.write()`` or sets
    ``system_prompt`` in their ``.sleeplens.toml``.

    Resolution order:

    1. ``$SLEEP_LEARNING_ENGINE_HOME/docs/prompts/sleeping_dev.md``
       (or the legacy ``$SLEEPLENS_HOME``). The Colab / Kaggle /
       Drive notebooks set this to their writable work dir, so
       dropping the prompt file in there lets the user edit the
       default without touching the package install.
    2. **Package data** shipped with the wheel
       (``sleep_learning_engine/prompts/sleeping_dev.md``). This
       is what `pip install` from the public tarball gets you -
       the prompt travels with the package, so every install gets
       the same default without any extra setup.
    3. **Repo root** relative to this file
       (``<repo>/docs/prompts/sleeping_dev.md``). This is what
       `uv run` from a source checkout gets you, before the
       wheel has been built.
    4. A small one-paragraph **built-in fallback** with a
       warning to stderr. The module still imports and the
       script writer still works, just with a much shorter
       default prompt. Restore any of the above paths to
       re-enable the full Sleeping Dev prompt.
    """
    # 1. Env-var override (notebook workflow)
    env_home = os.environ.get("SLEEP_LEARNING_ENGINE_HOME") or os.environ.get("SLEEPLENS_HOME")
    if env_home:
        candidate = Path(env_home) / "docs" / "prompts" / "sleeping_dev.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()

    # 2. Package data (pip install from the public tarball)
    try:
        packaged = resources.files("sleep_learning_engine").joinpath(
            "prompts", "sleeping_dev.md"
        )
        if packaged.is_file():
            return packaged.read_text(encoding="utf-8").strip()
    except (ModuleNotFoundError, AttributeError):
        # Older Python or unusual install layout. Skip silently.
        pass

    # 3. Repo root (uv run from a source checkout)
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "docs" / "prompts" / "sleeping_dev.md"
    if candidate.exists():
        return candidate.read_text(encoding="utf-8").strip()

    # 4. Built-in fallback
    print(
        "[sleep_learning_engine] WARNING: default prompt not found in any "
        "of the expected locations (env var, package data, repo root). "
        "Falling back to a small built-in prompt. The full Sleeping Dev "
        "prompt ships in the public repo at docs/prompts/sleeping_dev.md "
        "and in the wheel under sleep_learning_engine/prompts/.",
        file=sys.stderr,
    )
    return _BUILTIN_FALLBACK_PROMPT


_BUILTIN_FALLBACK_PROMPT = (
    "You are an experienced teacher writing an audio lesson for a curious "
    "adult who is listening with their eyes closed, in bed, in the dark, "
    "with no screen and no visual aid of any kind. The listener cannot see "
    "code, diagrams, slides, or documentation. Every concept must be "
    "understandable through audio alone. Teach one deep, well-structured "
    "software engineering topic, going from fundamental idea to expert-level "
    "reasoning. Use concrete examples, real-world tradeoffs, and "
    "engineering judgment. Output only the words that should be spoken by "
    "the narrator. Do not write titles, bullet points, or stage directions."
)


SYSTEM_PROMPT = _load_default_prompt()

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

