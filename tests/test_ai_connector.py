"""Unit tests for the AI connector, retry helper, and the timing engine."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sleep_learning_engine.ai.connector import AIConnector, ChatMessage  # noqa: E402
from sleep_learning_engine.core.exceptions import ProviderError  # noqa: E402
from sleep_learning_engine.core.retry import call_with_backoff  # noqa: E402


# ----------------------------------------------------- connector basics


def test_connector_rejects_blank_url() -> None:
    with pytest.raises(ProviderError):
        AIConnector(base_url="", api_key="x", model="y")


def test_connector_returns_assistant_text(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = AIConnector(base_url="https://example.com/v1", api_key="sk-x", model="m")
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = "  hello world  "
    fake_create = MagicMock(return_value=fake)
    monkeypatch.setattr(connector._client.chat.completions, "create", fake_create)

    text = connector.chat([ChatMessage("user", "hi")])
    assert text == "hello world"


def test_chat_json_parses_markdown_fenced(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = AIConnector(base_url="https://example.com/v1", api_key="sk-x", model="m")
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = '```json\n{"ok": true}\n```'
    fake_create = MagicMock(return_value=fake)
    monkeypatch.setattr(connector._client.chat.completions, "create", fake_create)
    parsed = connector.chat_json([ChatMessage("user", "go")])
    assert parsed == {"ok": True}


def test_chat_retries_on_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from openai import APIConnectionError

    connector = AIConnector(
        base_url="https://example.com/v1", api_key="sk-x", model="m", max_retries=3
    )
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = "ok"
    fake_create = MagicMock(side_effect=[APIConnectionError(request=MagicMock()), fake])
    monkeypatch.setattr(connector._client.chat.completions, "create", fake_create)
    text = connector.chat([ChatMessage("user", "hi")], temperature=0.5, max_tokens=10)
    assert text == "ok"
    assert fake_create.call_count == 2


# ----------------------------------------------------- retry helper


def test_call_with_backoff_eventually_succeeds() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    out = call_with_backoff(flaky, attempts=5, base_delay=0.001, max_delay=0.01)
    assert out == "ok"
    assert calls["n"] == 3


def test_call_with_backoff_raises_after_exhaustion() -> None:
    def always_fail() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        call_with_backoff(always_fail, attempts=2, base_delay=0.001, max_delay=0.01)
