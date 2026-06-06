# Changelog

All notable changes to Sleeplens are documented in this file.

## 0.1.0 (2026-06-06)

First public release.

Highlights:
- Provider-agnostic AI connector that talks to any OpenAI-compatible
  endpoint (NVIDIA NIM with DeepSeek V4 by default, plus OpenAI, Anthropic
  via a compatible proxy, Ollama, LM Studio, and custom URLs).
- Edge-TTS rendering for the default voice, with sidechain-ducked ambient
  bed mixing in the ffmpeg filter graph.
- Dynamic timing engine: the final runtime is the sum of every paragraph's
  audio length plus a configurable per-paragraph silent pause.
- Frame-accurate progress bar (#00FF00) painted with the geq filter, so it
  stays in sync with the timeline on multi-hour renders.
- Auto-generated dark backdrop with a subtle star field, painted on the
  fly when no user asset is supplied.
- CustomTkinter dark-mode GUI with drag-and-drop media, dropdown provider
  switching, live progress, and a manual cancel button.
- Bundled ffmpeg fallback for fresh checkouts: drop `ffmpeg.exe` into
  `cache/` and the studio is ready to go.
- 15 unit and end-to-end tests covering timing, ambient selection, the AI
  connector's retry policy, the visual fallback, and a full mini-render.
