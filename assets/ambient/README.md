# Ambient bed library

This directory is intentionally empty in the public repository.

The studio supports royalty-free ambient beds for the sleep-learning
mix, but the audio files are **not** shipped with the source tree.
Anyone who clones the repo can generate a personal copy locally with
the bundled script.

## Why no bundled audio?

Even fully synthesised audio can match fingerprints in third-party
content identification systems. Shipping the generated files in a
public repository would let anyone reuse the same fingerprint, which
risks false-positive copyright claims on videos produced with the
studio. Keeping the audio out of the public tree avoids that
exposure entirely.

## How to generate the beds

From the project root, with the studio's virtual environment active:

```bash
uv run python scripts/generate_ambient.py
```

The script writes 14 procedurally generated tracks (rain, ocean,
forest, fire, wind, river, brown noise, pink noise, alpha binaural,
alpha pulse, lofi, night crickets, cafe murmur) into this folder.
The studio's mixer reads them automatically the next time you render.

The script needs `numpy` and `scipy` (already in `requirements.txt`)
plus an ffmpeg binary (see the main README).

## Want different sounds?

Edit `scripts/generate_ambient.py` to add a new generator, change
seeds, or alter the loop length. The file is intentionally short
and well-commented; a Python file with `gen_*` functions and a
matching entry in the `TRACKS` tuple is all you need.

## Want a real sample?

Drop your own royalty-free loops here. The studio accepts `.mp3`,
`.wav`, `.ogg`, `.flac`, `.m4a`, and `.aac`. Use keywords in the
filename (rain, ocean, lofi, alpha, ...) so the ambient scanner
matches them to your script.
