"""Provider-agnostic connector for OpenAI-compatible APIs."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from ..core.exceptions import ProviderError
from ..core.retry import T, call_with_backoff
from ..utils.logging import get_logger

log = get_logger()


# Provider-specific error classes that are safe to retry on.
RETRIABLE: tuple[type[BaseException], ...] = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


@dataclass(frozen=True)
class ChatMessage:
    """A single turn in a chat history."""

    role: str
    content: str

    def to_openai(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class AIConnector:
    """Thin, provider-agnostic wrapper around an OpenAI-compatible endpoint.

    The class deliberately avoids locking users into a single vendor. Any
    service that exposes ``/v1/chat/completions`` (OpenAI, NVIDIA NIM, Ollama,
    LM Studio, LiteLLM proxies, custom gateways) can be addressed by passing
    a different ``base_url`` and ``api_key`` pair.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        max_retries: int = 6,
        organization: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if not base_url:
            raise ProviderError("base_url is required to talk to a provider.")
        if not model:
            raise ProviderError("model name is required.")
        # Ollama and LM Studio don't require auth, but the SDK still needs a
        # placeholder token.
        key = api_key or "sk-no-key-required"
        http_client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "sleep_learning_engine/0.1"},
        )
        self._client = OpenAI(
            base_url=base_url.rstrip("/"),
            api_key=key,
            http_client=http_client,
            organization=organization,
            default_headers=default_headers,
            max_retries=0,  # We handle retries ourselves for visibility.
        )
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """Run a chat completion and return the assistant text content.

        If ``on_chunk`` is provided, the connector streams the response
        and invokes the callback with every text delta as it arrives.
        This gives the user live feedback during long generations
        (large MoE models like DeepSeek V4 can take a while before
        the first byte) and avoids the silent 10-minute waits the
        fixed-timeout path used to produce.
        """
        payload_messages = [m.to_openai() for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if extra:
            kwargs.update(extra)
        if on_chunk is not None:
            kwargs["stream"] = True

        def _invoke() -> str:
            try:
                if on_chunk is not None:
                    return self._stream_invocation(kwargs, on_chunk)
                response = self._client.chat.completions.create(**kwargs)
            except AuthenticationError as exc:
                raise ProviderError(
                    f"Authentication failed: {exc}. Check your API key."
                ) from exc
            except APIStatusError as exc:
                # Surface 4xx/5xx bodies verbatim to help debugging.
                raise ProviderError(
                    f"Provider returned status {exc.status_code}: {exc.response.text[:400]}"
                ) from exc
            if not response.choices:
                raise ProviderError("Provider returned an empty choices list.")
            content = response.choices[0].message.content or ""
            return content.strip()

        def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            log.warning(
                "Chat completion retry {}/{} after {:.2f}s - {}",
                attempt,
                self.max_retries,
                delay,
                exc.__class__.__name__,
            )

        return call_with_backoff(
            _invoke,
            attempts=self.max_retries,
            retriable=RETRIABLE,
            on_retry=_on_retry,
        )

    def _stream_invocation(
        self, kwargs: dict[str, Any], on_chunk: Callable[[str], None]
    ) -> str:
        """Drive a streaming chat completion, forwarding each delta to ``on_chunk``.

        Returns the full concatenated text when the stream ends. The
        per-chunk timeout is the same as the global ``self.timeout``;
        the difference is that a chunk arriving later than that closes
        the stream and surfaces the timeout, so progress is visible
        throughout the call instead of being one big black box.
        """
        assembled: list[str] = []
        try:
            stream = self._client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise ProviderError(
                f"Authentication failed: {exc}. Check your API key."
            ) from exc
        except APIStatusError as exc:
            raise ProviderError(
                f"Provider returned status {exc.status_code}: {exc.response.text[:400]}"
            ) from exc

        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content or ""
            if delta:
                assembled.append(delta)
                on_chunk(delta)
        return "".join(assembled).strip()

    # ------------------------------------------------------------- structured
    def chat_json(
        self,
        messages: Iterable[ChatMessage],
        *,
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Request a JSON object and parse the response.

        Tries ``response_format={"type": "json_object"}`` first; if the
        provider rejects the argument (some local servers ignore it), falls
        back to a free-form call and parses the first JSON block found.
        """
        try:
            text = self.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return json.loads(text)
        except (ProviderError, json.JSONDecodeError):
            text = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
            return _extract_json(text)

    # ----------------------------------------------------------- introspection
    def list_models(self) -> list[str]:
        """Return the list of model ids the provider advertises, if any."""
        try:
            response = self._client.models.list()
            return sorted(m.id for m in getattr(response, "data", []))
        except (ProviderError, APIStatusError, APIConnectionError) as exc:
            log.warning("list_models() failed: {}", exc)
            return []

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 - shutdown must be best-effort.
            pass


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first balanced JSON object from a free-form response."""
    text = text.strip()
    if text.startswith("```"):
        # Strip the first ```json ... ``` block.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ProviderError(f"Could not find JSON object in response: {text[:200]}")
    return json.loads(text[start : end + 1])


__all__ = ["AIConnector", "ChatMessage", "ProviderError", "T"]
