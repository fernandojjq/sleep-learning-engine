# Sleeplens

Turn a short topic into a multi-hour, sleep-friendly learning video. Sleeplens
generates calm narration, mixes in a soft ambient bed, paints a frame-accurate
progress bar, and writes a clean MP4 ready for YouTube, a podcast feed, or a
local media server. Zero platform lock-in, runs free or fully local.

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
- **Acoustic ambience mixer.** Drop royalty-free loops into
  `assets/ambient/`. The studio matches keywords from the script
  (rain, ocean, alpha, lofi, fire, brown noise, ...) and ducks the bed
  whenever the voice is active.
- **Frame-accurate progress bar.** A clean #00FF00 bar painted with the
  `geq` filter, advanced by the current frame number. No drift, no
  precomputation, works on multi-hour renders.
- **Dark, modern GUI.** CustomTkinter with a midnight palette, drag-and-drop
  asset slots, provider dropdown, real-time stage log, and a cancel
  button you can actually click.
- **Hardware-accelerated encoding.** Auto-detects NVENC, QuickSync, and
  AMF. Falls back to libx264 on machines without a discrete GPU.

## Quickstart

```bash
# 1. Get a free NVIDIA NIM key at https://build.nvidia.com
# 2. Clone, install, and launch.
git clone https://github.com/sleeplens/sleeplens.git
cd sleeplens
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# Optional: drop a ffmpeg build into cache/ if you do not have one on PATH.
# A working ffmpeg.exe is required for the encode step.

# 3. Set your key (or paste it in the GUI later).
cp .env.example .env
# edit .env and put your key in SLEEPLENS_API_KEY

# 4. Launch.
python run.py
```

A small first render takes about 30 seconds on a modern laptop. A 30 minute
narration takes about 4 minutes with NVENC, or 10 to 15 minutes with
libx264 at 720p.

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
│   ├── ambient/            # drop your loops here
│   └── visuals/            # drop your backgrounds here
├── cache/                  # bundled ffmpeg, temp files
├── output/                 # final videos
├── docs/                   # preview frames + screenshots
├── run.py                  # quickstart launcher
├── pyproject.toml
├── requirements.txt
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
