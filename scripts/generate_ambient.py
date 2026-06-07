"""Procedural ambient track generator.

Synthesises a small library of royalty-free ambient beds for Sleep Learning Engine.
No samples, no downloads, no copyright: every sound is built from
white noise and oscillators in numpy/scipy, then written to WAV
and re-encoded to Opus in an OGG container for compact distribution.

Each track is 60 seconds, 48 kHz stereo, normalised, and designed to
loop seamlessly. Filenames include the keywords the ambient scanner
expects (rain, ocean, lofi, alpha, ...).

Usage:
    uv run python scripts/generate_ambient.py
    uv run python scripts/generate_ambient.py --keep-wav
"""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SR = 48_000
DURATION = 60.0  # seconds. Small enough to be cheap, long enough to loop.
CHANNELS = 2


@dataclass
class Track:
    name: str
    generator: Callable[[np.ndarray], np.ndarray]


# ------------------------------------------------------------- helpers


def _fade_loop(samples: np.ndarray, fade_seconds: float = 0.5) -> np.ndarray:
    """Apply a tiny crossfade at the loop seam so playback is seamless."""
    fade = int(fade_seconds * SR)
    if fade * 2 >= samples.shape[0]:
        return samples
    # Linear crossfade: blend the last `fade` samples of the tail with the
    # first `fade` samples of the head, then drop the redundant tail.
    head = samples[:fade].copy()
    tail = samples[-fade:]
    fade_in = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    fade_out = 1.0 - fade_in
    blended = head * fade_in[:, None] + tail * fade_out[:, None]
    out = samples.copy()
    out[:fade] = blended
    out = out[:-fade]
    return out


def _normalize(samples: np.ndarray, peak: float = 0.85) -> np.ndarray:
    """Scale to a target peak so nothing clips when the bed is mixed."""
    p = float(np.max(np.abs(samples)))
    if p < 1e-9:
        return samples
    return samples * (peak / p)


def _stereo(mono: np.ndarray) -> np.ndarray:
    """Promote a mono signal to a slightly de-correlated stereo field."""
    if mono.ndim == 2:
        return mono
    rng = np.random.default_rng(seed=int(abs(mono[:1024].sum() * 1e3)) % (2**32))
    width = mono.shape[0]
    # Second channel is the same signal phase-shifted by a few milliseconds
    # plus a tiny uncorrelated noise floor for natural width.
    shift = int(0.012 * SR)
    right = np.concatenate([np.zeros(shift, dtype=mono.dtype), mono[:-shift]])
    wiggle = rng.normal(0.0, 0.003, size=width).astype(np.float32)
    right = right + wiggle
    return np.stack([mono.astype(np.float32), right.astype(np.float32)], axis=1)


def _apply_lowpass(samples: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray:
    """Zero-phase low-pass via SOS. Operates on each channel."""
    sos = signal.butter(order, cutoff_hz, btype="low", fs=SR, output="sos")
    if samples.ndim == 1:
        return signal.sosfiltfilt(sos, samples).astype(np.float32)
    out = np.empty_like(samples, dtype=np.float32)
    for c in range(samples.shape[1]):
        out[:, c] = signal.sosfiltfilt(sos, samples[:, c]).astype(np.float32)
    return out


def _apply_highpass(samples: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray:
    sos = signal.butter(order, cutoff_hz, btype="high", fs=SR, output="sos")
    if samples.ndim == 1:
        return signal.sosfiltfilt(sos, samples).astype(np.float32)
    out = np.empty_like(samples, dtype=np.float32)
    for c in range(samples.shape[1]):
        out[:, c] = signal.sosfiltfilt(sos, samples[:, c]).astype(np.float32)
    return out


def _brown_noise(n: int, seed: int) -> np.ndarray:
    """Brown noise (integrated white noise). Used for ocean swells and wind."""
    rng = np.random.default_rng(seed=seed)
    out = np.cumsum(rng.normal(0.0, 0.02, size=n).astype(np.float32))
    out -= np.mean(out)
    return out.astype(np.float32)


def _pink_noise(n: int, seed: int) -> np.ndarray:
    """Voss-McCartney pink noise. Cheap, deterministic, sounds warm."""
    rng = np.random.default_rng(seed=seed)
    num_rows = 16
    array = rng.normal(0.0, 1.0, size=(num_rows, n)).astype(np.float32)
    out = np.zeros(n, dtype=np.float32)
    running_sum = np.zeros(n, dtype=np.float32)
    for r in range(num_rows):
        running_sum += array[r]
        out += running_sum
    out /= num_rows
    out -= np.mean(out)
    return out.astype(np.float32)


def _white_noise(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed=seed)
    return rng.normal(0.0, 0.5, size=n).astype(np.float32)


# ------------------------------------------------------------- generators


def gen_rain_gentle(mono: np.ndarray) -> np.ndarray:
    """Filtered white noise + sparse droplet hits."""
    base = _white_noise(mono.shape[0], seed=11)
    base = _apply_lowpass(base, 8_000)
    rng = np.random.default_rng(seed=12)
    # Sparse droplets: short exponentially-decaying pops above ~3 kHz.
    drops = np.zeros_like(base)
    n_drops = int(DURATION * 90)
    positions = rng.integers(0, mono.shape[0] - 2000, size=n_drops)
    for p in positions:
        length = rng.integers(150, 600)
        amp = rng.uniform(0.05, 0.15)
        envelope = np.exp(-np.arange(length, dtype=np.float32) / (length * 0.25))
        click = rng.normal(0.0, 1.0, length).astype(np.float32) * envelope * amp
        drops[p : p + length] += click
    drops = _apply_highpass(drops, 2_500)
    return base * 0.6 + drops * 0.9


def gen_rain_heavy(mono: np.ndarray) -> np.ndarray:
    base = _white_noise(mono.shape[0], seed=21)
    base = _apply_lowpass(base, 6_000)
    rng = np.random.default_rng(seed=22)
    drops = np.zeros_like(base)
    n_drops = int(DURATION * 320)
    for p in rng.integers(0, mono.shape[0] - 2000, size=n_drops):
        length = rng.integers(120, 500)
        amp = rng.uniform(0.04, 0.18)
        env = np.exp(-np.arange(length, dtype=np.float32) / (length * 0.2))
        click = rng.normal(0.0, 1.0, length).astype(np.float32) * env * amp
        drops[p : p + length] += click
    drops = _apply_highpass(drops, 2_000)
    # Distant thunder: very low rumble, very rare.
    thunder = np.zeros_like(base)
    for t in (8.0, 22.0, 41.0, 53.0):
        start = int(t * SR)
        length = int(2.5 * SR)
        rumble = _brown_noise(length, seed=int(t * 100))
        rumble = _apply_lowpass(rumble, 90)
        env = np.exp(-np.arange(length, dtype=np.float32) / (length * 0.35))
        thunder[start : start + length] += rumble * env * 0.6
    return base * 0.9 + drops * 0.7 + thunder * 0.7


def gen_ocean_waves(mono: np.ndarray) -> np.ndarray:
    """Slow LFO modulating filtered brown noise gives the wave illusion."""
    n = mono.shape[0]
    t = np.arange(n, dtype=np.float32) / SR
    swell = 0.5 + 0.5 * np.sin(2 * math.pi * t / 9.5 - math.pi / 2)  # 9.5 s period
    base = _brown_noise(n, seed=31)
    base = _apply_lowpass(base, 1_800)
    # Add a touch of high-frequency hiss for foam.
    hiss = _white_noise(n, seed=32) * 0.04
    hiss = _apply_highpass(hiss, 4_000)
    return base * swell * 1.4 + hiss * swell


def gen_forest_birds(mono: np.ndarray) -> np.ndarray:
    """Pink noise base + sparse bird chirps around 3 kHz."""
    n = mono.shape[0]
    base = _pink_noise(n, seed=41)
    base = _apply_lowpass(base, 2_500)
    base *= 0.4
    rng = np.random.default_rng(seed=42)
    chirps = np.zeros(n, dtype=np.float32)
    n_birds = 22
    for _ in range(n_birds):
        # Place birds so they fall within a 60s window and evenly spaced
        # to make the loop feel natural.
        t0 = rng.uniform(0.5, DURATION - 1.0)
        f0 = rng.uniform(2_200, 3_800)
        f1 = f0 + rng.uniform(-400, 600)
        length = int(rng.uniform(0.08, 0.35) * SR)
        start = int(t0 * SR)
        if start + length >= n:
            continue
        local_t = np.linspace(0, 1, length, dtype=np.float32)
        freq = f0 + (f1 - f0) * local_t
        phase = np.cumsum(2 * math.pi * freq / SR)
        env = np.exp(-((local_t - 0.5) ** 2) / 0.05)  # gaussian
        tone = np.sin(phase) * env * rng.uniform(0.18, 0.32)
        chirps[start : start + length] += tone
    return base + chirps


def gen_fire_crackle(mono: np.ndarray) -> np.ndarray:
    n = mono.shape[0]
    bed = _brown_noise(n, seed=51) * 0.7
    bed = _apply_lowpass(bed, 600)
    rng = np.random.default_rng(seed=52)
    crackle = np.zeros(n, dtype=np.float32)
    n_pops = int(DURATION * 60)
    for p in rng.integers(0, n - 1500, size=n_pops):
        length = rng.integers(40, 200)
        amp = rng.uniform(0.1, 0.4)
        env = np.exp(-np.arange(length, dtype=np.float32) / (length * 0.18))
        click = rng.normal(0.0, 1.0, length).astype(np.float32) * env * amp
        crackle[p : p + length] += click
    crackle = _apply_highpass(crackle, 1_500)
    return bed + crackle * 1.3


def gen_wind_breeze(mono: np.ndarray) -> np.ndarray:
    n = mono.shape[0]
    t = np.arange(n, dtype=np.float32) / SR
    gust = 0.4 + 0.6 * (0.5 + 0.5 * np.sin(2 * math.pi * t / 13.0 - math.pi / 2))
    gust = gust * (0.6 + 0.4 * (0.5 + 0.5 * np.sin(2 * math.pi * t / 4.3)))
    base = _brown_noise(n, seed=61)
    base = _apply_lowpass(base, 700)
    return base * gust * 1.6


def gen_brown_noise(mono: np.ndarray) -> np.ndarray:
    return _brown_noise(mono.shape[0], seed=71) * 0.9


def gen_pink_noise(mono: np.ndarray) -> np.ndarray:
    return _pink_noise(mono.shape[0], seed=72) * 0.7


def gen_alpha_binaural(mono: np.ndarray) -> np.ndarray:
    """Binaural beats at 8 Hz (alpha band). Carrier 200 Hz L / 208 Hz R.

    Headphones recommended for the binaural effect; otherwise it sounds
    like a soft pad.
    """
    n = mono.shape[0]
    t = np.arange(n, dtype=np.float32) / SR
    left = 0.18 * np.sin(2 * math.pi * 200.0 * t)
    right = 0.18 * np.sin(2 * math.pi * 208.0 * t)
    # Soft pink noise floor.
    bed = _pink_noise(n, seed=81) * 0.15
    bed = _apply_lowpass(bed, 800)
    return np.stack([left + bed, right + bed], axis=1)


def gen_alpha_pulse(mono: np.ndarray) -> np.ndarray:
    """Isochronic alpha tones: a 200 Hz carrier pulsed at 10 Hz."""
    n = mono.shape[0]
    t = np.arange(n, dtype=np.float32) / SR
    pulse = 0.5 + 0.5 * np.sin(2 * math.pi * 10.0 * t)
    pulse = np.power(pulse, 4.0)  # sharper on/off
    carrier = 0.2 * np.sin(2 * math.pi * 200.0 * t)
    return (carrier * pulse).astype(np.float32)


def gen_lofi_chill(mono: np.ndarray) -> np.ndarray:
    """Simple lo-fi bed: soft pad + slow kick + vinyl hiss."""
    n = mono.shape[0]
    t = np.arange(n, dtype=np.float32) / SR
    # Pad: a stack of softly detuned sine waves.
    pad = (
        0.05 * np.sin(2 * math.pi * 110.0 * t)
        + 0.04 * np.sin(2 * math.pi * 165.0 * t)
        + 0.03 * np.sin(2 * math.pi * 220.0 * t)
    )
    # Slow kick on a 1.6 s period (37.5 BPM), landing on 60/120s seams.
    kick = np.zeros(n, dtype=np.float32)
    beat_period = 1.6
    for i in range(int(DURATION / beat_period) + 1):
        t0 = i * beat_period
        if t0 >= DURATION:
            break
        start = int(t0 * SR)
        length = int(0.35 * SR)
        if start + length >= n:
            continue
        freq = 60.0 * np.exp(-np.arange(length, dtype=np.float32) / (length * 0.12))
        phase = np.cumsum(2 * math.pi * freq / SR)
        env = np.exp(-np.arange(length, dtype=np.float32) / (length * 0.18))
        kick[start : start + length] = np.sin(phase) * env * 0.35
    hiss = _apply_highpass(_white_noise(n, seed=91), 4_000) * 0.02
    return (pad + kick + hiss).astype(np.float32)


def gen_night_crickets(mono: np.ndarray) -> np.ndarray:
    n = mono.shape[0]
    bed = _brown_noise(n, seed=101) * 0.25
    bed = _apply_lowpass(bed, 300)
    rng = np.random.default_rng(seed=102)
    crickets = np.zeros(n, dtype=np.float32)
    n_crickets = int(DURATION * 7)
    for _ in range(n_crickets):
        t0 = rng.uniform(0.0, DURATION - 0.6)
        f0 = rng.uniform(3_500, 5_500)
        # 4-pulse chirp pattern.
        start = int(t0 * SR)
        pulse_period = int(0.045 * SR)
        pulse_length = int(0.012 * SR)
        for i in range(5):
            pos = start + i * pulse_period
            if pos + pulse_length >= n:
                break
            env = np.exp(-np.arange(pulse_length, dtype=np.float32) / (pulse_length * 0.2))
            tone = np.sin(2 * math.pi * f0 * np.arange(pulse_length, dtype=np.float32) / SR)
            crickets[pos : pos + pulse_length] += tone * env * 0.18
    crickets = _apply_highpass(crickets, 3_000)
    return bed + crickets


def gen_river_stream(mono: np.ndarray) -> np.ndarray:
    n = mono.shape[0]
    base = _pink_noise(n, seed=111)
    base = _apply_bandpass_like(base, low=400, high=5_000)
    # Subtle flow LFO.
    t = np.arange(n, dtype=np.float32) / SR
    lfo = 0.6 + 0.4 * (0.5 + 0.5 * np.sin(2 * math.pi * t / 7.0))
    return base * lfo * 1.3


def _apply_bandpass_like(samples: np.ndarray, low: float, high: float) -> np.ndarray:
    samples = _apply_highpass(samples, low)
    samples = _apply_lowpass(samples, high)
    return samples


def gen_cafe_murmur(mono: np.ndarray) -> np.ndarray:
    """Pink noise + mid-band emphasis + very slow modulation."""
    n = mono.shape[0]
    base = _pink_noise(n, seed=121)
    base = _apply_bandpass_like(base, low=250, high=2_500)
    t = np.arange(n, dtype=np.float32) / SR
    lfo = 0.7 + 0.3 * (0.5 + 0.5 * np.sin(2 * math.pi * t / 11.0))
    return base * lfo * 1.0


# ------------------------------------------------------------- driver


TRACKS: tuple[Track, ...] = (
    Track("rain-gentle-60s.wav", gen_rain_gentle),
    Track("rain-heavy-60s.wav", gen_rain_heavy),
    Track("ocean-waves-60s.wav", gen_ocean_waves),
    Track("forest-birds-60s.wav", gen_forest_birds),
    Track("fire-crackle-60s.wav", gen_fire_crackle),
    Track("wind-breeze-60s.wav", gen_wind_breeze),
    Track("river-stream-60s.wav", gen_river_stream),
    Track("brown-noise-60s.wav", gen_brown_noise),
    Track("pink-noise-60s.wav", gen_pink_noise),
    Track("alpha-binaural-8hz-60s.wav", gen_alpha_binaural),
    Track("alpha-pulse-10hz-60s.wav", gen_alpha_pulse),
    Track("lofi-chill-60s.wav", gen_lofi_chill),
    Track("night-crickets-60s.wav", gen_night_crickets),
    Track("cafe-murmur-60s.wav", gen_cafe_murmur),
)


def write_wav(path: Path, samples: np.ndarray) -> None:
    """Write a float32 stereo signal in [-1, 1] as a 16-bit PCM WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if samples.ndim == 1:
        samples = np.stack([samples, samples], axis=1)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32_767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def _encode_opus(wav_path: Path, ogg_path: Path, ffmpeg_bin: Path) -> None:
    """Re-encode a WAV file to Opus inside an OGG container."""
    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-i",
        str(wav_path),
        "-c:a",
        "libopus",
        "-b:a",
        "96k",
        "-ac",
        "2",
        "-ar",
        "48000",
        str(ogg_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log = result.stderr.strip().splitlines()[-1] if result.stderr else "unknown error"
        raise RuntimeError(f"ffmpeg failed for {wav_path.name}: {log}")


def _resolve_ffmpeg() -> Path | None:
    """Find an ffmpeg binary, or return None if unavailable."""
    bundled = ROOT / "cache" / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    if bundled.exists():
        return bundled
    on_path = shutil.which("ffmpeg")
    if on_path:
        return Path(on_path)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Keep the intermediate WAV files alongside the OGG output.",
    )
    parser.add_argument(
        "--ogg-only",
        action="store_true",
        help="Only emit the OGG files (requires ffmpeg on PATH or in cache/).",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="After generating, run scripts/normalize_ambient.py to bring every "
        "track to the same integrated loudness (EBU R128, default -23 LUFS). "
        "Recommended so the mixer does not jolt the listener awake when "
        "ducking between tracks of different volumes.",
    )
    args = parser.parse_args()

    out_dir = ROOT / "assets" / "ambient"
    out_dir.mkdir(parents=True, exist_ok=True)
    n_samples = int(DURATION * SR)
    mono_template = np.zeros(n_samples, dtype=np.float32)

    ffmpeg_bin = _resolve_ffmpeg()
    if ffmpeg_bin is None and not args.keep_wav:
        # Fall back to WAV-only output so the script still works.
        print("ffmpeg not found; emitting WAV files only. Re-run after installing ffmpeg for OGG.")
        args.keep_wav = True
        args.ogg_only = False

    for track in TRACKS:
        wav_path = out_dir / track.name
        ogg_path = wav_path.with_suffix(".ogg")
        raw = track.generator(mono_template)
        if raw.ndim == 1:
            raw = _stereo(raw)
        else:
            raw = raw.astype(np.float32, copy=False)
        raw = _fade_loop(raw, fade_seconds=0.4)
        raw = _normalize(raw, peak=0.85)
        write_wav(wav_path, raw)
        size_wav = wav_path.stat().st_size / (1024 * 1024)
        if ffmpeg_bin is not None:
            _encode_opus(wav_path, ogg_path, ffmpeg_bin)
            size_ogg = ogg_path.stat().st_size / (1024 * 1024)
            if not args.keep_wav:
                wav_path.unlink()
            print(f"  {track.name:32s}  WAV {size_wav:5.2f} MB -> OGG {size_ogg:5.2f} MB")
        else:
            print(f"  {track.name:32s}  WAV {size_wav:5.2f} MB")
    print(f"Done. {len(TRACKS)} tracks in {out_dir}")

    if args.normalize:
        # Chain into the loudness normaliser so the user gets
        # volume-matched tracks in one command. The script is
        # self-contained and lives next to this one in scripts/.
        import subprocess
        normaliser = Path(__file__).resolve().parent / "normalize_ambient.py"
        print(f"\nNormalising loudness via {normaliser.name} ...")
        result = subprocess.run(
            [sys.executable, str(normaliser), "--dir", str(out_dir)],
            capture_output=True, text=True,
        )
        # Forward the normaliser's output so the user sees the LUFS deltas.
        if result.stdout:
            print(result.stdout.rstrip())
        if result.returncode != 0:
            print(f"WARNING: normaliser exited with code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
