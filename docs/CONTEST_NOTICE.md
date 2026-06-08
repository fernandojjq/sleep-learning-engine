# Contest-period ambient bundle

**Status:** TEMPORARY exception. This is in the public tree only for the
duration of the Minimax contest submission window. Strip after the contest
with `scripts/strip_ambient.py`.

## Why are the audio files in the repo right now?

The project ships a `generate_ambient.py` script that creates the 97
ambient beds locally with `numpy` + `scipy`. In normal operation the
audio is generated on each user's machine and never enters the public
tree (see the rationale in `assets/ambient/README.md`).

For the contest submission we bundle the generated `.mp3` files so the
judges can clone, install, and render immediately without running the
ambient generator first. This is the path of least friction for an
external evaluator who has 10 minutes to look at the project.

## Risk

The `assets/ambient/README.md` (unchanged) explains why procedurally
generated audio can still match third-party content identification
systems. Keeping the files in the public tree during the contest
exposes the generated fingerprints to reuse. The user accepted this
risk for the duration of the contest only.

## How to remove the audio after the contest

```bash
# Dry run first: shows what would be removed.
uv run python scripts/strip_ambient.py --dry-run

# Actually remove the mp3s from the working tree and from git.
uv run python scripts/strip_ambient.py

# Restore the gitignore so future commits don't accidentally re-add them.
git checkout -- .gitignore assets/ambient/README.md
git add scripts/strip_ambient.py docs/CONTEST_NOTICE.md
git commit -m "Post-contest: remove bundled ambient, keep generator + README"
```

The strip is idempotent: running it twice is a no-op the second time.
