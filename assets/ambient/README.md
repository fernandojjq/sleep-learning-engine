# Ambient bed library

## Status (June 2026)

**Contest-period exception.** The 97 procedurally generated ambient
tracks are bundled in this directory for the duration of the
**Minimax contest submission window** so judges can clone, install, and
render immediately. See `docs/CONTEST_NOTICE.md` for the full rationale
and `scripts/strip_ambient.py` for the post-contest cleanup.

## Original policy (will be restored after the contest)

Normally, the audio files in this directory are **not** shipped with
the source tree. Anyone who clones the repo can generate a personal
copy locally with the bundled script:

```bash
uv run python scripts/generate_ambient.py
```

The script writes 97 procedurally generated tracks (rain, ocean,
forest, fire, wind, river, brown noise, pink noise, alpha binaural,
alpha pulse, lofi, night crickets, cafe murmur, ...) into this folder.
The studio's mixer reads them automatically the next time you render.

## Why is the audio normally kept out of git?

Even fully synthesised audio can match fingerprints in third-party
content identification systems. Shipping the generated files in a
public repository would let anyone reuse the same fingerprint, which
risks false-positive copyright claims on videos produced with the
studio. Keeping the audio out of the public tree avoids that
exposure entirely.

For the contest, the user accepted that exposure in exchange for a
frictionless judge experience. Revert with `scripts/strip_ambient.py`
once the contest window closes.

## Want different sounds?

Edit `scripts/generate_ambient.py` to add a new generator, change
seeds, or alter the loop length. The file is intentionally short
and well-commented; a Python file with `gen_*` functions and a
matching entry in the `TRACKS` tuple is all you need.

## Want to add your own royalty-free loops?

Drop them here. The studio accepts `.mp3`, `.wav`, `.ogg`, `.flac`,
`.m4a`, and `.aac`. Use keywords in the filename (rain, ocean, lofi,
alpha, ...) so the ambient scanner matches them to your script.
