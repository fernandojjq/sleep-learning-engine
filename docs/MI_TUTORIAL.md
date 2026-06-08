# My Sleep Learning Engine tutorial

This assumes you already have everything installed at
`D:\proyectos\Proyectos Github\sleeplens` (uv, venv, ffmpeg in
`cache/`, the ambient library, tests passing).

## What you actually do

You write a `.txt` file with the script (Spanish, English,
whatever language you want), feed it to the app, and you get
back an MP4. No API calls, no AI generation, nothing fancy.
**That is the whole tutorial.**

---

## Make a video (3 steps, ~2 min of setup + render)

### 1. Write the script

Open Notepad (or any text editor) and save the file somewhere,
for example `D:\proyectos\Proyectos Github\sleeplens\output\`.

Format: paragraphs separated by one blank line. Each paragraph
becomes one narrated block with a pause between blocks.

Example (`D:\proyectos\Proyectos Github\sleeplens\output\rome-history.txt`):

```
Welcome. Today we are going to walk through two thousand years
of history, slowly, letting each fact settle before moving on.

Rome started as a small settlement on the banks of the Tiber
river, around the year 753 BC. Its first inhabitants lived
from agriculture and herding.

Over time those shepherds learned to organize. They built
walls, chose kings, and learned to defend themselves from the
neighbouring peoples coming down from the mountains in search
of fertile land.

The Republic came in 509 BC, when the romans decided they no
longer wanted kings. In their place they created a network of
magistracies, annual consuls, and a Senate that represented
the oldest families.
```

Longer script = longer video. ~150 words per minute. **4500
words is about 30 minutes.**

### 2. Open the app

```powershell
cd "D:\proyectos\Proyectos Github\sleeplens"
uv run python -m sleep_learning_engine gui
```

Go to the **Topic** tab and in the field at the bottom
("Or load a script file") paste the path to your `.txt`, or
use the **Browse** button and pick the file.

Leave the big textarea on top empty (you do not want the AI to
generate anything; you already have the script).

### 3. Quick config, then click Render

Settings that actually matter:

| Tab | Field | Recommended value | Why |
| --- | ----- | ----------------- | --- |
| **Topic** | Pause between paragraphs | `1.8` s | Comfortable pause to absorb |
| **Topic** | Language | `en` | English |
| **Audio** | Voice (dropdown) | `Aria - warm, conversational female [top pick]` | The dropdown already has 46 curated voices |
| **Audio** | TTS Rate | `-10%` | Slower = calmer |
| **Audio** | TTS Pitch | `-2Hz` | A little lower |
| **Audio** | Ambient bed mode | `auto` | Matches by keyword (rain, ocean, lofi, etc.) |
| **Audio** | Bed volume | `0.18` | Ambient is there but does not cover the voice |
| **Audio** | Duck amount | `12` dB | Voice stays clear, ambient drops while you talk |
| **Render** | Output preset | `sleep_720p` or `sleep_1080p` for Full HD | Enough for YouTube and podcast |
| **Render** | Encoder | `auto` | NVENC if you have NVIDIA, otherwise libx264 |

Leave everything else at default. The defaults work.

**Click "Render video"** and wait. The progress bar shows which
step is running (script -> voice -> timing -> ambient -> mix ->
visual -> encode).

### 4. Done, grab the MP4

When it finishes, the sidebar shows where the file is, how long
it is, and the pipeline state. The file lives at:

```
D:\proyectos\Proyectos Github\sleeplens\output\sleep_learning_engine-1717729384.mp4
```

The filename is a timestamp. If you want a friendlier name,
rename it from Windows Explorer or from the terminal:

```powershell
Rename-Item "D:\proyectos\Proyectos Github\sleeplens\output\sleep_learning_engine-1717729384.mp4" "rome-history-30m.mp4"
```

### 4b. Sidebar buttons (top to bottom)

| Button | What it does |
| ------ | ------------ |
| **Render full video** | The whole flow: script -> voice -> ambient -> mix -> visual -> encode |
| **Generate script only** | Only generates the script and saves it as `.txt` in `output/`. Useful to iterate the text before spending 5 min on a full render |
| **Save settings (API key, model, etc.)** | Saves everything (API key, model, voice, ambient, output) to `.sleeplens.toml`. You do not need to render to save |
| **Cancel** | Becomes enabled during a render. Cancels cleanly (partial files get cleaned up) |

---

## Generate script only (to iterate faster)

If you want to try several versions of the same topic without
waiting for a full render each time, use **Generate script
only**. It saves the `.txt` in `output/` and tells you the path.
After that you can:

- Re-read and tweak it
- Load that `.txt` in the "Or load a script file" field on
  the Topic tab
- Render the video with the polished script

Typical time: 5-15 seconds per script iteration, vs 5-10 min
per full render.

---

## Shortcut: do not want to open the GUI

Everything works from the terminal too, no GUI needed:

```powershell
cd "D:\proyectos\Proyectos Github\sleeplens"

# The simplest case
uv run python -m sleep_learning_engine render --script "D:\proyectos\Proyectos Github\sleeplens\output\rome-history.txt"

# With a custom output name
uv run python -m sleep_learning_engine render --script .\output\rome-history.txt --output-stem rome-history

# With a custom background
uv run python -m sleep_learning_engine render --script .\output\rome-history.txt --background-image D:\backgrounds\rain.jpg --output-stem rome-history

# JSON output for logs / CI
uv run python -m sleep_learning_engine render --script .\output\rome-history.txt --json
```

The `--json` flag prints one line like this, useful if you want
to log how long it took:

```json
{"status": "ok", "output": "...\\rome-history.mp4", "duration_seconds": 1820.5, "word_count": 4520, "runtime": "30m 20s"}
```

---

## You want to change something between videos

| If you want to... | Go to | Touch |
| ----------------- | ----- | ----- |
| Different voice | Audio tab | Change the **Voice** dropdown (46 curated, in Spanish, English, etc.) |
| Custom voice (not in the dropdown) | Audio tab | Pick **Custom...** in the dropdown, type the id in the field next to it |
| Different ambient (rain -> ocean) | Audio tab | Change **Ambient bed mode** to `keyword` or `random` |
| No ambient (voice only) | Audio tab | **Ambient bed mode** = `disabled` |
| More pauses | Topic tab | Raise **Pause between paragraphs** to `2.5` or `3` |
| Longer video | Topic tab | Write a longer script |
| Background image / video | Visuals tab | Paste the path or drag the file |
| 1080p resolution | Render tab | **Output preset** = `sleep_1080p` |
| Audio-only MP3 | Render tab | **Output preset** = `audio_only` |
| Change the AI model | Provider tab | **Model** dropdown (curated per provider); or **Custom...** to type one |
| Edit the system prompt | Provider tab | Click **Show advanced**, edit the textbox. If you leave it empty, it uses the default |

---

## Voices in the dropdown (curated for sleep)

The **Voice** dropdown on the Audio tab has 46 curated Edge TTS
voices, organized by language:

| Language | Count | Top picks |
| -------- | ----- | --------- |
| English (US) | 8 | **Aria** (female, warm), **Brian** (male, deep) |
| English (UK) | 4 | **Ryan** (male, audiobook) |
| English (AU / CA / IN / IE) | 5 | Natasha, William, Clara, Neerja, Emily |
| Spanish (ES / MX / AR) | 5 | Elvira, Laura, Dalia, Jorge, Elena |
| French (FR / CA) | 3 | Denise, Henri, Sylvie |
| German | 2 | Katja, Conrad |
| Italian | 3 | Elsa, Diego, Isabella |
| Portuguese (BR / PT) | 3 | Francisca, Antonio, Raquel |
| Japanese | 2 | Nanami, Keita |
| Chinese (CN / HK / TW) | 4 | Xiaoxiao, Yunyang, HiuMaan, HsiaoChen |
| Other | 7 | Korean, Dutch, Polish, Russian, Turkish, etc. |

If you want a voice that is not in the list, pick **Custom...**
in the dropdown and type the id in the field next to it (e.g.
`en-US-MichelleNeural`).

### How to pick the best voice for your video

You already have 17 audio samples (10-17 seconds each) in
`output/voice-previews/`. Open that folder in Windows Explorer
and play the MP3s until you find one you like. The exact id is
in the filename; look it up in the dropdown.

If you want to regenerate them or try more:

```powershell
# Regenerate all of them
uv run python scripts/voice_preview.py

# Try a single voice
uv run python scripts/voice_preview.py --voice en-US-BrianNeural

# Try your own text
uv run python scripts/voice_preview.py --text "The story of jazz, told slowly and calmly."
```

### Fine-tuning per voice (top picks)

All samples are recorded with **rate `-10%`** and **pitch `-2Hz`**.
If you want to fine-tune more:

| Voice | Rate | Pitch | Why |
| ----- | ---- | ----- | --- |
| `en-US-AriaNeural` | `-10%` | `-2Hz` | Warm default |
| `en-US-BrianNeural` | `-8%` | `-3Hz` | Already deep, do not overdo it |
| `en-US-EmmaNeural` | `-15%` | `0Hz` | Already a whisper, no pitch down |
| `en-US-AndrewNeural` | `-12%` | `-2Hz` | Audiobook pace |
| `en-GB-RyanNeural` | `-10%` | `-2Hz` | Default |

---

## AI models (Provider tab)

The **Model** dropdown shows the most common models for the
selected provider. It only changes when you change the provider.

| Provider | Curated models |
| -------- | -------------- |
| NVIDIA NIM (default) | DeepSeek V4, DeepSeek R1, Llama 3.1 70B, Llama 3.1 8B, Mistral Large 2, Qwen 2.5 72B |
| OpenAI | GPT-4o mini, GPT-4o, GPT-4.1 mini, GPT-4.1, o1-mini, o1-preview |
| Anthropic (via proxy) | Claude Sonnet 4.5, Claude Opus 4, Claude Haiku 4 |
| Ollama (local) | Llama 3.1, Llama 3.2, Mistral, Qwen 2.5, Phi-3 |
| LM Studio (local) | local-model |
| Custom | Whatever you type |

If you want a model that is not in the list, pick **Custom...**
and type the id in the field next to it. Click **Load model
list from provider** to have the provider return its current
list and merge it with the curated one.

---

## System prompt (advanced)

By default the AI writes in a calm tone, second person, with
pauses between paragraphs. If you want to change the tone
(more formal, shorter, more poetic, in a different style):

1. **Provider** tab
2. Click **Show advanced (system prompt)**
3. Edit the textbox with your instructions

If you leave it empty, it uses the default. If you fill it in,
it overrides the default for that session (saved in
`.sleeplens.toml`).

---

## Troubleshooting express

**Render takes a long time**
- Normal for long videos. ~5-10 min per hour of video with NVENC.
- If you have NVIDIA, the Render tab should show NVENC
  automatically. Check the log.
- If you are on CPU (libx264), it can be 2-3x slower. That is
  fine.

**`Cannot load nvcuda.dll` or `Error opening encoder` in the log**
- Your ffmpeg was built with NVENC but you do not have the
  CUDA runtime installed. The app detects this automatically:
  if the encoder fails on the first frame, it falls back to
  `libx264` and finishes the render. The log should say
  `Encoder h264_nvenc failed at init ... Retrying with libx264.`
- If you want real GPU speed, install current NVIDIA drivers
  + the CUDA runtime. In the meantime leave the encoder
  selector at `auto` and the app handles it.

**`ffmpeg exited with code 4294967284` or `Cannot allocate memory`**
- Your machine ran out of RAM. The 1080p encode needs ~700 MB
  free and the `geq` filter (progress bar) adds another
  150 MB. On a machine with 8 GB total and Windows + browser
  open, there is no room.
- **Quick fix:** lower the resolution to 720p on the Render
  tab (4x less memory for the filter graph) and lower the
  libx264 preset to `ultrafast`. The encode finishes at the
  cost of a little quality but the video comes out complete.
- **Cloud fix:** run the render on Google Colab (free). Run
  `python -m sleep_learning_engine cloud` from the project
  folder and open the URL. The notebook has T4 GPU + 12.7 GB
  of RAM, and finishes the 1080p encode in 1-2 minutes with
  real NVENC.

**Voice sounds weird or too fast**
- Lower **TTS Rate** to `-15%` or `-20%`.
- Change **Voice** to another one. Try `es-ES-LauraNeural`
  or `es-AR-ElenaNeural`.

**Ambient does not show up**
- The bundled library (97 tracks, generated with Minimax Music
  2.6) ships with the repo for the Minimax contest window. If
  you cloned before the bundle or stripped it post-contest, drop
  your own royalty-free loops into `assets\ambient\`. The studio
  accepts `.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`, and `.aac`.
  Use keywords in the filename (rain, ocean, lofi, alpha, ...)
  so the ambient scanner routes them to the right script.
- To generate new beds with Minimax Music 2.6, use the
  [minimax audio](https://www.minimax.io/audio) web app or the
  API at `https://api.minimaxi.com/v1`. Drop the output files
  straight into `assets\ambient\`. No code change needed.
- If you want all tracks at the same volume (important: the
  mixer does duck/unduck, and a 6 dB level difference between
  tracks is audible and disruptive), normalise with:
  `uv run python scripts/normalize_ambient.py`. A 30-day backup
  of the originals is kept in `assets\ambient\.loudnorm-backup\`.

**I want the ambient to vary, not always the same track**
- By default, sleep_learning_engine builds a **shuffled
  no-repeat playlist** with the tracks that match the script
  keywords. Each track plays once before the full cycle
  repeats, so a 6-hour video is not the same track 360 times.
- If you want to force a behaviour (auto / keyword / random /
  disabled), change **Ambient bed mode** in the Audio tab.

**I want the detailed log of an error**
- It is at
  `D:\proyectos\Proyectos Github\sleeplens\logs\sleep_learning_engine.log`
  (rotates at 5 MB with 5 history files).

**I want to reset all settings to default**
- Delete
  `D:\proyectos\Proyectos Github\sleeplens\.sleeplens.toml`.
  The next time you open the app it starts clean.

---

## Your setup in one block

```
D:\proyectos\Proyectos Github\sleeplens\
  .venv\                <- venv managed by uv
  cache\ffmpeg.exe      <- ffmpeg binary
  assets\ambient\       <- procedural tracks (rain, lofi, etc.)
  output\               <- where your final MP4s land
  output\voice-previews <- voice samples to pick your favourite
  logs\                 <- rotated log for debug
  docs\USER_GUIDE.md    <- generic tutorial for new users
  docs\MI_TUTORIAL.md   <- this file
```

That is it. With this you can produce videos on autopilot.
The setup is done, only the content is missing.
