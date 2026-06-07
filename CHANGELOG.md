# Changelog

All notable changes to Sleep Learning Engine are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## Unreleased

### Changed
- **Project renamed** from `sleeplens` to **Sleep Learning Engine**.
  Convention: `sleep_learning_engine` is the Python module (snake_case
  is the Python rule, hyphens are not allowed in module names),
  `Sleep Learning Engine` is the display name, `sleep-learning-engine`
  is the distribution name, the GitHub repo is still
  `fernandojjq/sleeplens` until the user renames it on GitHub. The
  config file is kept as `.sleeplens.toml` because the 4-letter suffix
  is faster to type than `.sleep_learning_engine.toml`; the loader
  accepts the new name `.sleep_learning_engine.toml` and the legacy
  `.sleeplens.toml` interchangeably, with a fallback to the legacy
  name on existing checkouts so the user's existing API key file
  keeps working without a rename. The env var `SLEEPLENS_HOME` is
  also still accepted; the new name is `SLEEP_LEARNING_ENGINE_HOME`.
  The env var `SLEEPLENS_API_KEY` is unchanged so the existing
  `.env` files keep working.

### Added
- **Low-RAM cloud rendering.** The 1080p H.264 encode needs ~700 MB
  of free RAM on top of the OS, and a 7-8 GB Windows box OOMs even
  with the most frugal libx264 settings. Two notebooks ship in the
  repo so a low-RAM user has a real path forward:
  - `docs/cloud/low_ram_render.ipynb` — Google Colab. One click,
    no setup. 12.7 GB system RAM, T4 GPU when available, ~5 min
    for a 6-minute video. Free tier GPU is best-effort and may
    show 0/15 GB during peak hours; the notebook falls back to
    `libx264` and the ffmpeg-build also retries the encode with
    a one-shot `libx264` fallback in the studio.
  - `docs/cloud/kaggle_render.ipynb` — Kaggle. The same pipeline
    on a guaranteed 2x T4 (30 GB VRAM, 30 GPU hours per week),
    with persistent datasets so a 50+ ambient track library
    uploaded once to `/kaggle/input/ambient/` survives every
    session. Working directory persists too. Recommended for
    recurring renders.
- **`sleeplens cloud` CLI subcommand** (`src/sleep_learning_engine/cli.py`).
  Validates local state and opens the Colab notebook URL in the
  default browser. Flags: `--no-browser`, `--repo`, `--branch`.
- **Public config template** `.sleep_learning_engine.toml.example`
  (and the legacy `.sleeplens.toml.example` for back-compat).
  Replaces the user's actual `.sleeplens.toml` as the only
  committed config artefact, so the API key never reaches GitHub.
  `gitignore` was already protecting the personal file; this
  change adds the example template.
- **Volume normalisation script** `scripts/normalize_ambient.py`.
  Two-pass EBU R128 `loudnorm` over every `.ogg`/`.wav`/`.mp3`
  in `assets/ambient/`, bringing integrated loudness to
  -23 LUFS (broadcast standard) and true peak to -1.5 dBTP.
  Keeps a 30-day backup in `assets/ambient/.loudnorm-backup/`.
  Wired into `generate_ambient.py --normalize` so a one-liner
  produces volume-matched tracks in a single command.
- **Random ambient playlist without repetition**
  (`build_ambient_playlist` in `src/sleep_learning_engine/audio/mixer.py`).
  Filters the library to the keyword pool that matches the script,
  shuffles with a deterministic seed, and repeats the shuffled
  list end-to-end. Each track plays once per cycle, so a 6-hour
  video with 14 tracks plays each track ~25 times spread evenly
  across the runtime, never the same track back-to-back. The
  ffmpeg `concat` demuxer with `-stream_loop -1` on the concat
  input is used for playlists of 2+ files; a single-element
  list keeps the legacy fast path.
- **Hardware-accelerated encoder canary** in
  `src/sleep_learning_engine/video/builder.py`. `pick_hardware`
  used to only check `ffmpeg -encoders` for `h264_nvenc`, which
  proves the encoder is compiled in but not that it can be
  initialised. A one-frame canary encode for each candidate
  (NVENC, QSV, AMF) catches the case where the CUDA runtime
  is missing or the driver is too old, before the TTS+mix step
  has already spent 5 minutes of work. The build path also
  retries once with `libx264` if the chosen HW encoder fails
  at full-encode time (e.g. a QSV build that passes the
  1-frame canary on software emulation but chokes at scale).
- **`sleeplens cloud` subcommand help text** in the CLI so
  `python -m sleep_learning_engine cloud --help` documents the
  Colab fallback for low-RAM machines.
- **Hardware requirements section** in `README.md` and a
  dedicated `docs/HARDWARE.md` page that spell out when to use
  local GUI vs Colab vs Kaggle, with a concrete memory and
  GPU table and the encoder-specific gotchas (NVENC needs the
  CUDA runtime, QSV needs an Intel GPU, etc.).
- **Troubleshooting entry** in `docs/MI_TUTORIAL.md` for
  `ffmpeg exited with code 4294967284` (the ENOMEM marker
  rendered as an unsigned 32-bit integer) that points the user
  at the cloud render path or the 720p+ultrafast local fallback.

### Fixed
- **`MixSpec.ambient_path` → `MixSpec.ambient_paths`**. The mixer
  now accepts a list (single-element list is the simple
  "loop this one track" case, multi-element list is the
  random-no-repeat playlist). The ffmpeg `concat` demuxer is
  used for the multi-file case with `-stream_loop -1` on the
  concat input. The 3 pre-existing tests that passed the old
  `ambient_path` keyword were updated.
- **Kaggle notebook `env` line**. The generator's f-string
  attempted to interpolate `CACHE` at module scope, where it
  was undefined, so the generated cell contained the literal
  text `"{CACHE}"` instead of the variable reference. Replaced
  with a plain string that references the CACHE variable
  defined in cell 2.
- **Kaggle pip install**. The notebook used
  `pip install -q "sleeplens @ git+https://..."`, which fails
  on Kaggle because pip cannot always git-clone with
  credentials. Switched to the tarball URL
  `https://github.com/fernandojjq/sleeplens/archive/refs/heads/main.tar.gz`,
  a plain HTTPS download that pip handles directly.
- **4 hardcoded ffmpeg paths** in `tests/test_studio.py` baked
  the user's local directory name into the test source. The
  rename from `sleeplens` to `sleep_learning_engine` would
  have left the tests looking in a non-existent path. Replaced
  with `ROOT / "cache" / ("ffmpeg.exe" if sys.platform ==
  "win32" else "ffmpeg")` so the tests are portable.
- **Colab notebook `pip install` path** in
  `docs/cloud/low_ram_render.ipynb`. The default-mode cell
  used `git+https://`, which fails on Colab. Switched to the
  tarball URL for the same reason as the Kaggle fix.

### Tests
- 8 new tests in `tests/test_encoder_fallback.py` covering the
  canary logic, the explicit-choice preservation, and the
  libx264 fallback chain.
- 14 new tests in `tests/test_ambient_playlist.py` covering
  cycle math, deterministic seeding, keyword filtering, fallback
  to the full library, and edge cases (empty library, zero
  duration).
- 38/38 tests green as of this entry. 5/5 cells in each of
  the Colab and Kaggle notebooks parse with `ast.parse`.

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
