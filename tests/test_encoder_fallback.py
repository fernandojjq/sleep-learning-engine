"""Regression tests for hardware-encoder fallback.

The user hit a real bug: ``ffmpeg -encoders`` lists ``h264_nvenc`` on
systems where the CUDA runtime is not installed, so the old
``pick_hardware`` would happily pick NVENC and only fail 5 minutes
later when the actual encode started. The fix runs a one-frame
canary and skips encoders that cannot be initialised.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sleep_learning_engine.video import builder  # noqa: E402
from sleep_learning_engine.video.builder import HardwareChoice, pick_hardware  # noqa: E402


class _FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _patch_probe(monkeypatch, encoder_list: str) -> None:
    """Make ``ffmpeg -encoders`` return a controlled list and the canary
    route through the same fake so the tests never shell out."""

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        # The first call is the encoder probe, everything after is a canary.
        if any(arg == "-encoders" for arg in cmd):
            return _FakeCompleted(stdout=encoder_list)
        # Canary: pretend libx264 always works so the auto path can
        # complete without actually invoking ffmpeg.
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(builder.subprocess, "run", fake_run)


def test_pick_hardware_skips_nvenc_when_canary_fails(monkeypatch) -> None:
    """The exact failure mode the user hit: NVENC is listed but unusable."""

    _patch_probe(monkeypatch, "h264_nvenc h264_qsv h264_amf h264_libopenh264")

    def fake_verify(binary, encoder):  # type: ignore[no-untyped-def]
        # NVENC fails (no CUDA), everything else works.
        return encoder != "h264_nvenc"

    monkeypatch.setattr(builder, "_verify_encoder_works", fake_verify)

    chosen = pick_hardware("auto", Path("fake-ffmpeg"))
    assert chosen.encoder != "h264_nvenc", (
        "NVENC was picked even though its canary encode failed"
    )
    assert chosen.encoder == "h264_qsv"


def test_pick_hardware_picks_nvenc_with_p4_vbr_flags_when_canary_passes(
    monkeypatch,
) -> None:
    """When the canary passes for NVENC, auto must select it AND carry
    the p4 / vbr / 4M rate-control flags. This is the regression for
    the Colab Pro T4 case: the canary used to be 128x128 and the
    driver rejected it for being below the 145 px NVENC H.264 minimum
    (FFmpeg trac #9251), so auto fell through to libx264 and the
    6:55 video took 10-15 min instead of 1-2 min.
    """

    _patch_probe(monkeypatch, "h264_nvenc h264_qsv h264_amf")

    def fake_verify(binary, encoder):  # type: ignore[no-untyped-def]
        return True  # every HW encoder passes the canary

    monkeypatch.setattr(builder, "_verify_encoder_works", fake_verify)

    chosen = pick_hardware("auto", Path("fake-ffmpeg"))
    assert chosen.encoder == "h264_nvenc", (
        f"Expected h264_nvenc when its canary passes, got {chosen.encoder!r}"
    )
    # The NVENC preset must carry p4 / vbr / 4M so the encode uses
    # the GPU's dedicated chip and stays under the 4 Mbps target
    # for 720p/1080p sleep content.
    flags = list(chosen.extra_flags)
    assert "-preset" in flags and "p4" in flags, (
        f"NVENC preset missing p4 quality knob: {flags}"
    )
    assert "-rc" in flags and "vbr" in flags, (
        f"NVENC preset missing vbr rate-control: {flags}"
    )
    assert "-b:v" in flags and "4M" in flags, (
        f"NVENC preset missing 4M target bitrate: {flags}"
    )


def test_pick_hardware_falls_all_the_way_to_libx264(monkeypatch) -> None:
    """If every HW encoder is broken, libx264 is the safe floor."""

    _patch_probe(monkeypatch, "h264_nvenc h264_qsv h264_amf")

    def fake_verify(binary, encoder):  # type: ignore[no-untyped-def]
        return False  # every HW encoder is broken

    monkeypatch.setattr(builder, "_verify_encoder_works", fake_verify)

    chosen = pick_hardware("auto", Path("fake-ffmpeg"))
    assert chosen.encoder == "libx264"


def test_pick_hardware_explicit_nvenc_keeps_user_choice(monkeypatch) -> None:
    """Explicit choice is preserved even if the canary would fail.

    The canary is only consulted for the auto path. If the user picked
    'nvenc' on purpose (knowing they have CUDA), respect that choice
    and do not silently swap encoders.
    """

    def fake_verify(binary, encoder):  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(builder, "_verify_encoder_works", fake_verify)

    chosen = pick_hardware("nvenc", Path("fake-ffmpeg"))
    assert chosen.encoder == "h264_nvenc"


def test_pick_hardware_unknown_choice_falls_back_to_libx264() -> None:
    chosen = pick_hardware("definitely-not-a-real-encoder", Path("fake-ffmpeg"))
    assert chosen.encoder == "libx264"


@pytest.mark.parametrize("encoder", ["h264_nvenc", "h264_qsv", "h264_amf", "libx264"])
def test_hardware_choice_extra_flags_are_present(encoder: str) -> None:
    """Every preset must carry its required flags, otherwise the
    eventual encode command will be malformed."""
    lookup = {
        "h264_nvenc": "nvenc",
        "h264_qsv": "qsv",
        "h264_amf": "amf",
        "libx264": "libx264",
    }
    chosen = pick_hardware(lookup[encoder], Path("fake-ffmpeg"))
    assert chosen.encoder == encoder
    assert len(chosen.extra_flags) >= 2, (
        f"{encoder} preset must include at least rate-control + quality flags"
    )
