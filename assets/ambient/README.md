# Ambient bed library

This directory is yours. The studio's ambient mixer scans it on every
render and picks tracks by keyword (rain, ocean, lofi, alpha, space,
fire, wind, lofi, ...) so the bed matches the topic of the script.

## How to add your own tracks

Drop any royalty-free loop into this folder. The studio accepts
`.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`, and `.aac`. Use keywords in
the filename so the ambient scanner can match them to your script:

```
rain-soft.mp3            -> "rain" keyword
ocean-night-45min.mp3    -> "ocean" keyword
lofi-deep-focus.mp3      -> "lofi" keyword
space-ambient-1.mp3      -> "space" keyword
fireplace-gentle.mp3     -> "fire" keyword
```

The same scanner is used to build the playlist. With a mix of keyword
hits and unrelated tracks, the studio filters the library down to the
subset that matches the script and shuffles them with the
no-repetition playlist builder. A 6-hour video with 14 matching tracks
plays each track ~25 times spread evenly across the runtime, never
the same track back-to-back.

The 97 `.mp3` files in this directory were generated with
**Minimax Music 2.6** and are bundled for the
[Minimax contest submission window](docs/CONTEST_NOTICE.md) so the
judges can clone, install, and render without setup. They are not
required to render - the studio runs fine with an empty folder (the
voice plays solo) or with just your own tracks.

## Removing the bundled tracks

When the contest window closes, the bundled tracks are no longer
needed and can be removed. `scripts/strip_ambient.py` does this in
one command:

```bash
uv run python scripts/strip_ambient.py --dry-run    # preview
uv run python scripts/strip_ambient.py             # actual strip
```

After stripping, the folder is empty (or contains only your own
royalty-free tracks), and the studio runs the same way as a fresh
clone: scan the folder, match by keyword, mix with the voice.

## Want longer or more tracks?

Generate more with **Minimax Music 2.6** directly and drop the
output `.mp3` files into this folder. The studio picks them up on
the next render - no code change, no rebuild. Use descriptive
filenames so the keyword scanner can route them to the right script.

## Volume normalisation

If your tracks are at wildly different levels, run
`scripts/normalize_ambient.py` to bring them all to -23 LUFS (broadcast
standard) and -1.5 dBTP. The studio's mixer does ducking and unducking,
and a 6 dB level difference between tracks is audible and disruptive
when one track fades in over the voice.

```bash
uv run python scripts/normalize_ambient.py
```

A 30-day backup of the originals is kept in
`assets/ambient/.loudnorm-backup/`.
