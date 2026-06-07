# Sleeplens

Turn a short topic into a multi-hour, sleep-friendly learning video. Sleeplens
generates calm narration, mixes in a soft ambient bed, paints a frame-accurate
progress bar, and writes a clean MP4 ready for YouTube, a podcast feed, or a
local media server. Zero platform lock-in, runs free or fully local.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/fernandojjq/sleeplens/blob/main/docs/cloud/low_ram_render.ipynb)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/managed%20by-uv-purple.svg)](https://docs.astral.sh/uv/)

> Out of the box: NVIDIA NIM free tier (DeepSeek V4) + Edge-TTS + a bundled
> ffmpeg. Swap any layer for OpenAI, Ollama, LM Studio, or your own endpoint
> by changing a dropdown and a base URL.

## Highlights

- **Provider-agnostic text generation.** Works with any OpenAI-compatible
  endpoint. Default is NVIDIA NIM with DeepSeek V4 (free tier, 40 RPM).
  Switch to OpenAI, Anthropic via a proxy, Ollama, LM Studio, or a custom
  URL with two form fields.
- **Free neural TTS by default.** Edge-TTS gives high quality voices with
  no key, no rate limit, and no quota. Bring your own voice list or swap
  in another backend later.
- **Dynamic runtime.** The final video length is the sum of every rendered
  paragraph plus the silent pause you specify between paragraphs. No more
  cutting narration to fit a clock.
- **Smart visual pipeline.** Drop a background image or a short loopable
  video into the field. The studio loops the clip to match the runtime.
  If nothing is provided, a dark, sleep-friendly backdrop is generated
  procedurally with no network call.
- **Acoustic ambience mixer.** The studio scans `assets/ambient/` for
  royalty-free loops, matches keywords from the script (rain, ocean,
  alpha, lofi, fire, brown noise, ...) and ducks the bed whenever
  the voice is active. A bundled generator script can synthesise 14
  procedural tracks locally if you do not have any.
- **Frame-accurate progress bar.** A clean #00FF00 bar painted with the
  `geq` filter, advanced by the current frame number. No drift, no
  precomputation, works on multi-hour renders.
- **Dark, modern GUI.** CustomTkinter with a midnight palette, drag-and-drop
  asset slots, provider dropdown, real-time stage log, and a cancel
  button you can actually click.
- **Hardware-accelerated encoding.** Auto-detects NVENC, QuickSync, and
  AMF. Falls back to libx264 on machines without a discrete GPU.

## Quickstart

The studio is built and run with [uv](https://docs.astral.sh/uv/), a single
Rust-powered tool that handles Python installs, virtualenvs, and locked
dependency resolution. If you do not have it yet:

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then clone and launch:

```bash
git clone https://github.com/fernandojjq/sleeplens.git
cd sleeplens

# Creates .venv and installs every dependency locked in uv.lock.
# This includes pytest, ruff, and mypy under the dev group.
uv sync

# Launch the desktop studio.
uv run python run.py
```

A first render with the bundled ffmpeg finishes in about 30 seconds on
a modern laptop. A 30 minute narration takes about 4 minutes with
NVENC, or 10 to 15 minutes with libx264 at 720p.

### FFmpeg

FFmpeg is the only system-level dependency. Any 6.x or 8.x build with
`libx264` enabled works. The studio looks in this order:

1. The path stored in the `FFMPEG_BIN` environment variable.
2. `cache/ffmpeg.exe` (Windows) or `cache/ffmpeg` (POSIX) inside the
   repo. This is the bundled location; drop a build there and forget
   about it.
3. Whatever is on `PATH`.

If you do not have ffmpeg, grab a static build for your platform from
https://www.gyan.dev/ffmpeg/builds/ (Windows) or
https://johnvansickle.com/ffmpeg/ (Linux). No installer required. Drop
the binary into the repo's `cache/` folder and you are done.

### First-time API setup

The first render uses Edge-TTS, so it works without any API key. To
generate the script from a topic instead of pasting your own, get a
free NVIDIA NIM key at https://build.nvidia.com and drop it in:

```bash
cp .env.example .env
# edit .env and paste your key into SLEEPLENS_API_KEY
```

You can also paste the key straight into the GUI (Provider tab) and
it gets persisted to `.sleeplens.toml` for next time.

## Hardware requirements

Sleeplens has two render paths. Pick the one that matches your machine.

### Local render (desktop GUI + bundled ffmpeg)

The desktop studio encodes on your own hardware. The encode is the
heavy step, so the memory and CPU budget below is what the final MP4
needs, not the TTS or the script generation.

| Component | Minimum | Comfortable | Notes |
|---|---|---|---|
| RAM (free) | 2 GB | 6 GB+ | 1080p libx264 medium peaks at ~700 MB working set |
| CPU | 4 cores | 8 cores | Single-threaded `geq` filter is the bottleneck |
| GPU | none | NVIDIA + CUDA | NVENC drops encode time by 5-10x |
| Disk | 500 MB | 2 GB+ | Working set for ffmpeg + cached TTS segments |
| OS | Windows 10, macOS 12, Ubuntu 20 | Windows 11, macOS 14, Ubuntu 22 | Bundled ffmpeg is Windows; macOS/Linux bring your own |

**Good fit:** a developer laptop, a gaming PC, any machine with 8+
GB of RAM and a modern CPU. The local path gives you full offline
control and zero upload steps.

**Bad fit:** 8 GB Windows laptops with Chrome open (the typical
office machine). The render OOMs at 1080p and the fallback to
720p + ultrafast still OOMs because the `geq` progress bar
filter holds ~150 MB of pixel buffers regardless of resolution.

### Cloud render (Google Colab)

A free Colab T4 instance has 12.7 GB of system RAM plus real NVENC
on a 16 GB T4 GPU. It finishes a 1080p encode in 1-2 minutes
because the memory headroom is comfortable and the encoder is GPU
hardware.

| Component | Provided by Colab | Notes |
|---|---|---|
| RAM (free) | 12.7 GB | Plenty for 1080p + medium preset + `geq` |
| GPU | NVIDIA T4 with NVENC | Real hardware encode, 5-10x faster than libx264 |
| CPU | 2 vCPU | Used only by Edge TTS + script generation |
| Disk | 78 GB | Wiped when the session ends |
| Cost | free | No credit card, just a Google account |
| Time cap | 12 h per session | Plenty for any single video |

**Good fit:** anyone with a Google account and a low-RAM machine.
The notebook lives in the repo and runs the full sleeplens
pipeline: Edge TTS, ambient mix, NVENC encode, MP4 download. Open
the Colab badge at the top of this README, click *Runtime -> Run
all*, upload the script and the background image, and the MP4
downloads to your machine in 5-10 minutes.

**Bad fit:** users who need offline access, batch automation, or
who want to render dozens of videos back-to-back. Colab sessions
are best-effort and free GPUs are not always available.

### How to pick

- I have 8+ GB of free RAM and a modern CPU: **local** with `auto`
  encoder. Drop the bundled ffmpeg into `cache/` and run
  `uv run python run.py gui`.
- I have 8 GB of RAM and Chrome open: **cloud**. Click the
  Colab badge.
- I want to script batch renders: **local** with the CLI
  (`uv run python run.py render --script foo.txt --output-stem bar`).
- I want a polished desktop app for non-technical users:
  **local**, but confirm the machine has 16+ GB of RAM first.

See [docs/CLOUD_RENDER.md](docs/CLOUD_RENDER.md) for the full
Colab walkthrough and [docs/HARDWARE.md](docs/HARDWARE.md) for
encoder-specific notes.

## Daily workflow

```bash
# Pull the latest source and dependencies.
git pull
uv sync

# Run the GUI.
uv run python run.py gui

# Run the test suite.
uv run pytest

# Lint and type-check.
uv run ruff check src tests
uv run mypy src

# Render a video without opening the GUI.
uv run python run.py render --topic "the discovery of penicillin" --output-stem penicillin
```

`uv run` is the one entry point. It resolves the right interpreter,
activates the project venv, and runs the command. No need to manually
`source` anything.

## Troubleshooting

- **`ffmpeg not found` when rendering.** Drop a static `ffmpeg.exe`
  into the `cache/` folder of your clone, or set `FFMPEG_BIN` to the
  full path of your system install.
- **`ModuleNotFoundError: sleeplens`.** You ran `python run.py`
  without `uv run`. Use `uv run python run.py` or activate the venv
  with `.venv\Scripts\activate` (Windows) / `source .venv/bin/activate`
  (POSIX) first.
- **NVIDIA NIM 401 / 403.** Your key is missing or expired. Re-paste it
  in the GUI Provider tab or in `.env`. The free tier allows 40 RPM,
  which is more than enough for a full script.
- **Edge-TTS fails to connect.** Edge-TTS reaches Microsoft over
  WebSocket. If you are behind a strict firewall, switch the TTS
  backend to `piper` (offline) or supply your own pre-rendered voice
  track.
- **PyTorch / CUDA optional extras.** If you want GPU text generation
  via `uv`, install the optional group with `uv pip install torch --extra-index-url https://download.pytorch.org/whl/cu121`
  inside the active venv.

## Why Sleeplens

Most "text to video" tools fall into two camps: locked-down cloud platforms
that bill you per minute, or local toolchains that demand a CS degree to
assemble. Sleeplens is the middle path.

- **Zero lock-in.** Every layer is swappable. The text generation speaks
  the OpenAI chat completions spec, the TTS is a thin engine wrapper, the
  visuals accept any image or loop, the audio mixer is a stock ffmpeg
  filter graph, and the encoder picks the best available hardware.
- **No per-minute billing.** Edge-TTS and the NVIDIA NIM free tier cover
  most use cases. Run 100% local with Ollama and Edge-TTS for a truly
  offline pipeline.
- **Sleep-optimised out of the box.** The default voice is slowed to
  `-5%`, the ambient bed ducks when narration is active, the procedural
  backdrop is calibrated for low light, and the bar stays in the bottom
  6 px so it never competes with the content.
- **One command, one window.** No web server, no Docker, no cloud
  account. Open the app, paste a topic, hit Render, get a video.

## Architecture at a glance

```
+--------------------------+
|  Sleeplens GUI (CustomTk)|
|  +-----------+ +-------+ |
|  | Prompt    | | API   | |
|  | + script  | | key   | |
|  +-----------+ +-------+ |
+----------+---------------+
           |
           v
+--------------------------+
|  Orchestrator            |
|  - script load / write   |
|  - TTS render (Edge)     |
|  - timing engine         |
|  - ambient scan + pick   |
|  - voice / bed mix       |
|  - visual resolve        |
|  - ffmpeg encode         |
+----------+---------------+
           |
           v
+--------------------------+
|  output/  *.mp4          |
+--------------------------+
```

Each subsystem lives in its own module under `src/sleeplens/` and is fully
unit tested.

## Stack

| Layer        | Choice                   | Why                                          |
| ------------ | ------------------------ | -------------------------------------------- |
| GUI          | CustomTkinter            | Modern look, dark theme native, low overhead |
| Drag & drop  | tkinterdnd2              | Drop files into the form, no boilerplate     |
| HTTP         | httpx + openai SDK      | Any OpenAI-compatible endpoint, typed        |
| TTS          | edge-tts                 | Free, high quality, no key                   |
| Audio mix    | ffmpeg filter graph      | Sidechain ducking, looping, no extra deps    |
| Encoding     | ffmpeg (libx264 / NVENC) | Battle-tested, hardware auto-detect          |
| Image fallback | Pillow                 | No network, deterministic, no API key        |
| Settings     | pydantic-settings        | Typed config, no YAML/TOML library cruft     |
| Retry        | tenacity                 | Exponential backoff with full jitter         |
| Logging      | loguru                   | One-line setup, rotation, retention          |

Every choice is replaceable. The connector and engine boundaries are small
enough to refactor in an afternoon.

## Running 100% local and free

```bash
# Install Ollama, then pull a small chat model.
ollama pull llama3.1

# In the GUI:
#   Provider  -> "Ollama (local, offline)"
#   Model     -> "llama3.1"
#   API key   -> leave blank
#   TTS       -> Edge
```

That is the entire local setup. Edge-TTS makes outbound WebSocket calls
to Microsoft, so if you need a strictly air-gapped pipeline, swap the
TTS backend for Piper (offline neural voices) or bring your own
pre-rendered track.

## CLI

Sleeplens ships a small CLI for headless rendering on a server.

```bash
# Render from a topic.
python run.py render --topic "the history of the steam engine" \
    --background-image ./assets/visuals/rainy-window.png \
    --output-stem steam-engine-30m --json

# Render from a pre-written script.
python run.py render --script ./lessons/greek-myths.txt

# List bundled provider presets.
python run.py providers
```

The JSON output is one line, easy to wire into CI.

## Bundled ambient library

The studio does **not** ship audio files. To populate the ambient
library, run the generator:

```bash
uv run python scripts/generate_ambient.py
```

This produces 14 procedurally-synthesised beds (rain, ocean, forest,
fire, wind, river, brown noise, pink noise, alpha binaural, alpha
pulse, lofi, night crickets, cafe murmur) into `assets/ambient/`,
each 60 seconds of stereo, designed to loop cleanly, and tagged with
the keywords the scanner looks for.

Why not commit them? See `assets/ambient/README.md`. The short
version: synthetic audio can still match third-party fingerprinting
systems, and shipping the generated files in a public repo would
expose downstream users to false-positive copyright claims on the
videos they produce.

## Repository layout

```
sleeplens/
├── src/sleeplens/          # library
│   ├── ai/                 # AI connector + script writer
│   ├── audio/              # TTS, ambient scanner, mixer
│   ├── config/             # paths + pydantic settings
│   ├── core/               # pipeline + retry + state
│   ├── gui/                # CustomTkinter dark window
│   ├── utils/              # logging + helpers
│   ├── video/              # timing + ffmpeg builder
│   └── visual/             # asset resolver + Pillow fallback
├── tests/                  # pytest suite (15 tests)
├── scripts/                # one-shot smoke render
├── assets/
│   ├── ambient/            # generated locally, not committed (see assets/ambient/README.md)
│   └── visuals/            # drop your backgrounds here
├── cache/                  # bundled ffmpeg, temp files
├── output/                 # final videos
├── docs/                   # preview frames + screenshots
├── run.py                  # quickstart launcher
├── pyproject.toml
├── requirements.txt         # pip-compatible pin, generated from uv.lock
├── uv.lock                  # authoritative dep lockfile
├── .env.example
├── .gitignore
├── LICENSE                 # MIT
├── CHANGELOG.md
└── README.md
```

## Testing

```bash
.venv\Scripts\python -m pytest tests/ -q
```

The suite covers timing math, ambient library scanning, keyword matching,
the visual fallback, the AI connector's retry behaviour, and a full
mini-render that exercises every stage of the pipeline end to end.

## Contributing

Issues and pull requests are welcome. Keep changes focused, add a test for
new behaviour, and follow the existing module boundaries. The pipeline
module is the only place that knows about the full flow; subsystems should
stay independently testable.

## License

MIT. See `LICENSE`.
