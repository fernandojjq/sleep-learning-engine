# Changelog

All notable changes to Sleep Learning Engine are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## 1.0.1 (2026-06-12)

### Fixed
- **Fixed Long-Render Cutoff Bug**: Automatic paragraph chunking in [tts.py](file:///D:/proyectos/Proyectos%20Github/sleeplens/src/sleep_learning_engine/audio/tts.py). Long scripts with paragraphs exceeding 3000 characters (e.g., scripts formatted without double newlines) are now automatically split at sentence boundaries before being sent to the Edge-TTS API. This prevents connection timeouts and truncated audio files from the Microsoft translation server, ensuring multi-hour renders finish completely without cutting off mid-word.
- **Added test for text chunker**: Added `test_chunk_text` to [test_studio.py](file:///D:/proyectos/Proyectos%20Github/sleeplens/tests/test_studio.py) to verify that long prose is split correctly at sentence endings.

## 1.0.0 (2026-06-08) - Minimax contest release

This is the production-stable release submitted to the **Minimax contest**.
The cloud path is one click, the ambient library ships with the repo for a
frictionless judge experience, the encoder canary is fixed at 256x256
(above NVENC's 145 px H.264 minimum), and the project is
provider-agnostic out of the box. **45/45 tests green.** MIT licensed.

### Highlights
- **Three ways to run, all free**: local desktop GUI, Google Colab one-click,
  Kaggle with guaranteed 2x T4. No paid tier required for the core path.
- **Provider-agnostic**: any OpenAI-compatible endpoint works for script
  generation - Minimax API (M3 / M2-her / M2.1), NVIDIA NIM (DeepSeek V4),
  OpenAI, Anthropic via proxy, Ollama, LM Studio. Swap the URL + key, the
  pipeline does not care.
- **Speech 2.8 ready**: `tts_voice` accepts any Edge TTS voice id by
  default. Swap in **Minimax Speech 2.8** for production-grade narration
  (17+ presets, 40+ languages, emotion + sound-tag control) by setting
  `SLEEP_LEARNING_ENGINE_TTS_VOICE` to a Speech 2.8 voice or wiring a
  custom TTS backend.
- **Music 2.6 ready**: the 97 ambient tracks bundled for the contest
  were generated externally with **Minimax Music 2.6** and ship in
  `assets/ambient/` for the contest window. To swap in fresh
  per-video beds, generate them with the [Minimax audio](https://www.minimax.io/audio)
  web app or the API at `https://api.minimaxi.com/v1` and drop the
  output `.mp3` files straight into `assets/ambient/`. No code
  change needed - the studio picks up new files on the next render.
- **Hardware-accelerated encode**: NVENC on NVIDIA (1-2 min for a 6-min
  1080p video on a T4), QuickSync on Intel, AMF on AMD, libx264 fallback.
  The encoder canary probes 256x256 (above NVENC's 145 px H.264 minimum)
  so the probe reports the truth on every GPU.
- **Architecture diagram**: `docs/architecture-minimax.svg` shows the full
  Minimax-integrated pipeline end-to-end, in a single 1600x1100 view.
- **Contest-period ambient bundle**: the 97 procedural mp3s ship with
  the repo for the duration of the contest window so judges can clone,
  install, and render an MP4 without running the generator first. See
  `docs/CONTEST_NOTICE.md` for the rationale and `scripts/strip_ambient.py`
  for the post-contest cleanup.

### Changed
- **Default script-generation system prompt is the "Sleeping Dev"
  master-class prompt** (`docs/prompts/sleeping_dev.md`). The
  studio used to ship a ~100-line built-in prompt inline in
  `script_writer.py`. It now reads a 458-line long-form prompt
  tuned for audio-only software engineering masterclasses from
  `docs/prompts/sleeping_dev.md` (resolved relative to the
  project root at import time). The file is part of the public
  tree so anyone can read what the script writer tells the AI
  on every call. If the file is missing (e.g. a pip install
  without the docs, or someone moved it), the module falls
  back to a small one-paragraph built-in prompt and logs a
  warning to stderr. Callers can still override per-render via
  `ScriptWriter.write(system_prompt=...)` or per-config via
  `system_prompt = "..."` in `.sleeplens.toml`.
- **Project renamed** from `sleeplens` to **Sleep Learning Engine**.
  Convention: `sleep_learning_engine` is the Python module (snake_case
  is the Python rule, hyphens are not allowed in module names),
  `Sleep Learning Engine` is the display name, `sleep-learning-engine`
  is the distribution name, the GitHub repo is
  `fernandojjq/sleep-learning-engine`. The config file is kept as
  `.sleeplens.toml` because the 4-letter suffix is faster to type than
  `.sleep_learning_engine.toml`; the loader accepts the new name
  `.sleep_learning_engine.toml` and the legacy `.sleeplens.toml`
  interchangeably, with a fallback to the legacy name on existing
  checkouts so the user's existing API key file keeps working without
  a rename. The env var `SLEEPLENS_HOME` is also still accepted; the
  new name is `SLEEP_LEARNING_ENGINE_HOME`. The env var
  `SLEEPLENS_API_KEY` is unchanged so the existing `.env` files keep
  working.
- **Default TTS voice is now `en-US-BrianNeural`** (deep male, top pick
  for sleep narration). Aria and the other 45 voices are still selectable
  by editing `.sleeplens.toml` or by setting
  `SLEEP_LEARNING_ENGINE_TTS_VOICE` in the env. The cloud notebooks
  expose `VOICE = "en-US-BrianNeural"` at the top of cell 1 so a single
  edit swaps the narration voice without touching the config.
- **Env-var overrides on `load_settings`**: the env var
  `SLEEP_LEARNING_ENGINE_TTS_VOICE` (and the legacy
  `SLEEPLENS_TTS_VOICE`) wins over both the TOML value and the
  `AppSettings` default. The cloud notebooks use this so a notebook
  run is a per-run override of the durable config.
- **Cloud notebooks now export `SLEEP_LEARNING_ENGINE_HOME`** in the
  render cell's subprocess env. This is the fix for the
  "video renders without ambient music" report: `paths.ambient_dir`
  was resolving to the pip-install location
  (`/usr/local/lib/python3.12/dist-packages/.../assets/ambient`) which
  is empty, because the 97 mp3s are git-ignored. With the env var
  pointing at the notebook's working dir, ambient_dir, output_dir,
  cache_dir and log_dir all land in the writable place the notebook
  already uses. The cell 5 dual-path workaround is no longer needed
  and was reverted.
- **Status is now Production/Stable** (was Beta). The project runs
  end-to-end on the three documented paths (local / Colab / Kaggle),
  has 45/45 tests, and ships the docs, the architecture diagram, and
  the contest-period ambient bundle in the same tree.

### Added
- **Low-RAM cloud rendering.** The 1080p H.264 encode needs ~700 MB
  of free RAM on top of the OS, and a 7-8 GB Windows box OOMs even
  with the most frugal libx264 settings. Three notebooks ship in the
  repo so a low-RAM user has a real path forward:
  - `docs/cloud/low_ram_render.ipynb` - Google Colab. One click,
    no setup. 12.7 GB system RAM, T4 GPU when available.
  - `docs/cloud/drive_render.ipynb` - Personal Colab with a Drive-
    mounted ambient library. The 97 ambient tracks live in Drive and
    are pulled on every session so the only thing uploaded per
    render is the script + background.
  - `docs/cloud/kaggle_render.ipynb` - Kaggle. The same pipeline on
    a guaranteed 2x T4 (30 GB VRAM, 30 GPU hours per week), with
    persistent datasets. Recommended for recurring renders.
- **`sleep_learning_engine cloud` CLI subcommand**
  (`src/sleep_learning_engine/cli.py`). Validates local state and
  opens the Colab notebook URL in the default browser. Flags:
  `--no-browser`, `--repo`, `--branch`.
- **Public config template** `.sleep_learning_engine.toml.example`
  (and the legacy `.sleeplens.toml.example` for back-compat).
- **Volume normalisation script** `scripts/normalize_ambient.py`.
  Two-pass EBU R128 `loudnorm` over every audio file in
  `assets/ambient/`, bringing integrated loudness to -23 LUFS
  (broadcast standard) and true peak to -1.5 dBTP. Keeps a 30-day
  backup in `assets/ambient/.loudnorm-backup/`. Standalone script
  - run once on your own collection to bring all tracks to the
  same level.
- **Random ambient playlist without repetition**
  (`build_ambient_playlist` in `src/sleep_learning_engine/audio/mixer.py`).
  Filters the library to the keyword pool that matches the script,
  shuffles with a deterministic seed, and repeats the shuffled list
  end-to-end. The ffmpeg `concat` demuxer with `-stream_loop -1` on
  the concat input is used for playlists of 2+ files.
- **Hardware-accelerated encoder canary** in
  `src/sleep_learning_engine/video/builder.py`. `pick_hardware` runs
  a one-second canary encode for each candidate (NVENC, QSV, AMF) in
  order. The first one that initializes successfully wins. The
  canary uses 256x256 / 24 fps / 1 s / yuv420p / -bf 0 (above
  NVENC's 145 px H.264 minimum, so the probe reports the truth on
  every GPU). The build path also retries once with `libx264` if
  the chosen HW encoder fails at full-encode time.
- **Hardware requirements section** in `README.md` and a dedicated
  `docs/HARDWARE.md` page that spell out when to use local GUI vs
  Colab vs Kaggle, with a concrete memory and GPU table and the
  encoder-specific gotchas.
- **Troubleshooting entry** in `docs/MI_TUTORIAL.md` for
  `ffmpeg exited with code 4294967284` (the ENOMEM marker rendered
  as an unsigned 32-bit integer) that points the user at the cloud
  render path or the 720p+ultrafast local fallback.
- **Architecture diagram** `docs/architecture-minimax.svg`. 1600x1100
  SVG that shows the full Minimax-integrated pipeline end-to-end,
- **`docs/prompts/sleeping_dev.md`**: the default system prompt for
  the script writer, shipped in the public tree so it is auditable
  and editable. 458 lines, master-class software engineering script
  style for audio-only sleep-learning narration. Used as the default
  by `ScriptWriter.write()` unless overridden by the caller's
  `system_prompt=` argument or the config file's `system_prompt`
  field.
  with INPUT, SCRIPT (M3 / M2-her), three parallel columns
  (Speech 2.8, Music 2.6, Visual), MIX, ENCODE (NVENC / QSV / AMF
  / libx264), and the final MP4 output. Used in the contest
  submission to communicate the pipeline at a glance.
- **Contest-period ambient bundle**: the 97 ambient tracks shipped
  with the repo were generated externally with **Minimax Music 2.6**
  (rain, ocean, forest, fire, wind, river, brown noise, pink noise,
  alpha binaural, alpha pulse, lofi, night crickets, cafe murmur,
  ...) and are bundled for the duration of the Minimax contest
  window. See `docs/CONTEST_NOTICE.md` and `scripts/strip_ambient.py`
  for the post-contest cleanup.
- **Personal Colab notebook** `docs/cloud/drive_render.ipynb` with
  generator `scripts/generate_drive_notebook.py`. Defaults to
  per-session upload (Mode B): the script and image change per
  project, only the ambient is persistent in Drive.

### Fixed
- **NVENC canary false negative on real T4 hardware.** The probe in
  `_verify_encoder_works` was using 64x64 then 128x128, both of
  which are below NVENC's 145 px H.264 minimum (FFmpeg trac #9251,
  144x144 fails, 145x145 succeeds). The probe now uses 256x256,
  1 second at 24 fps, explicit `-pix_fmt yuv420p`, and `-bf 0`.
  Without this fix, a real T4 was being rejected by the canary
  and the pipeline fell through to libx264 CPU encoding, which is
  5-10x slower. The actual real encodes (720p/1080p) were always
  above the floor; only the canary was ever affected.
- **3 cloud-notebook issues caught during a real Colab Pro run:**
    1. The GPU check cell used to print `"NVENC available:"` with
       a trailing colon and nothing after, which was misleading.
       Replaced with `nvidia-smi` as the real test, and added a
       clear "NO GPU DETECTED" error with the runtime fix steps.
    2. The render subprocess did not inherit the `LD_LIBRARY_PATH`
       that points at the NVIDIA driver libraries. Added a multi-
       path patch in cell 1 of every cloud notebook.
    3. `subprocess.run(..., capture_output=True)` buffered the entire
       render and only flushed stdout at the end, looking frozen.
       Switched to `subprocess.Popen` with line-buffered stdout
       merged with stderr.
- **Kaggle notebook `env` line typo**: the f-string attempted to
  interpolate `CACHE` at generator scope. Replaced with a plain
  string that references the CACHE variable defined in cell 2.
- **Per-session upload default for drive notebook**: defaulted to
  "Mode A: pull from Drive", wrong for the actual workflow where
  script + background change per render.
- **`MixSpec.ambient_path` -> `MixSpec.ambient_paths`**: accepts a
  list (single-element for the simple "loop this one track" case,
  multi-element for the random-no-repeat playlist). The 3
  pre-existing tests that passed the old `ambient_path` keyword
  were updated.
- **Kaggle pip install**: switched from `git+https://` (fails on
  Kaggle) to a plain HTTPS tarball download.
- **4 hardcoded ffmpeg paths** in `tests/test_studio.py` baked the
  user's local directory name into the test source. Replaced with
  `ROOT / "cache" / ("ffmpeg.exe" if sys.platform == "win32" else
  "ffmpeg")` so the tests are portable.
- **Colab notebook `pip install` path**: switched to the tarball
  URL for the same reason as the Kaggle fix.
- **uv.lock package name**: `sleeplens` was still in the lock file
  after the rename in `79a8212`. Regenerated.
- **Drive notebook Spanish cell comments + BLINDAJE workaround**:
  regenerated from the generator. The previous committed version
  had Spanish cell comments and a "BLINDAJE" workaround that
  re-escalated the background image to 1920x1080 with LANCZOS
  to satisfy the (then-broken) NVENC canary. The canary fix at
  256x256 makes the BLINDAJE obsolete, and the script source
  already handles the image resize + crop in `_build_image_stream`,
  so the BLINDAJE was destructive. Regenerated version is the
  same 5 code cells + 2 markdown cells, in English, no BLINDAJE.

### Docs
- `README.md`: refresh of the Open in Colab and Open in Kaggle
  badges to point at the renamed GitHub repo.
- `docs/HARDWARE.md`: dedicated "NVENC H.264 minimum dimension
  (145 px)" section, plus a corrected verification snippet that
  uses 256x256 and documents both failure modes.
- `docs/COLAB_NVENC_DEBUG.md`: rewritten as a root-cause writeup.
  The 145 px NVENC minimum is identified as the actual cause; the
  6 prior attempts that "didn't work" are explained, and the
  verification plan for after the bump lands is laid out.
- `docs/MI_TUTORIAL.md`: full English translation (junior-dev
  style, no jargon, imperative voice). Replaced all `vos` /
  `ponés` / `dale Render` with `you write` / `paste` / `click
  Render`. Updated the launch command from the obsolete
  `python run.py` to the actual entry point
  `python -m sleep_learning_engine gui`.
- `docs/architecture-minimax.svg`: 1600x1100 SVG diagram for the
  contest submission, showing the full Minimax-integrated
  pipeline end-to-end.

### Tests
- 8 tests in `tests/test_encoder_fallback.py` covering the canary
  logic, the explicit-choice preservation, and the libx264
  fallback chain.
- 14 tests in `tests/test_ambient_playlist.py` covering cycle
  math, deterministic seeding, keyword filtering, fallback to the
  full library, and edge cases (empty library, zero duration).
- 6 tests in `tests/test_voice_env_var.py` covering the
  `SLEEP_LEARNING_ENGINE_TTS_VOICE` env var: default is Brian,
  env var beats default, env var beats TOML, legacy
  `SLEEPLENS_TTS_VOICE` still works, new env var wins over legacy,
  empty env var is treated as unset.
- **45/45 tests green** as of this entry. 5/5 cells in each of
  the Colab and Kaggle notebooks parse with `ast.parse`.

## 0.1.0 (2026-06-06)

First public release.

Highlights:
- Provider-agnostic AI connector that talks to any OpenAI-compatible
  endpoint (NVIDIA NIM with DeepSeek V4 by default, plus OpenAI,
  Anthropic via a compatible proxy, Ollama, LM Studio, and custom URLs).
- Edge-TTS rendering for the default voice, with sidechain-ducked
  ambient bed mixing in the ffmpeg filter graph.
- Dynamic timing engine: the final runtime is the sum of every
  paragraph's audio length plus a configurable per-paragraph silent
  pause.
- Frame-accurate progress bar (#00FF00) painted with the geq filter,
  so it stays in sync with the timeline on multi-hour renders.
- Auto-generated dark backdrop with a subtle star field, painted on
  the fly when no user asset is supplied.
- CustomTkinter dark-mode GUI with drag-and-drop media, dropdown
  provider switching, live progress, and a manual cancel button.
- Bundled ffmpeg fallback for fresh checkouts: drop `ffmpeg.exe`
  into `cache/` and the studio is ready to go.
- 15 unit and end-to-end tests covering timing, ambient selection,
  the AI connector's retry policy, the visual fallback, and a full
  mini-render.
