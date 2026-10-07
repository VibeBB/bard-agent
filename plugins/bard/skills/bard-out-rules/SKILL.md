---
name: bard-out-rules
description: Path rule — generated-artifact reminders injected whenever a file under out/, songs/, or cues/ is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/out/**"
  - "**/songs/**"
  - "**/cues/**"
---

# Bard generated-artifact rules

Files under `songs/` and `cues/` are projections written only by
`render_song.py`, `render_cues.py`, `lint_score.py`, and
`render_score_png.py`; files under `out/` belong to the sister plugins
that generated them — bard cites them as song material and never edits
them.

- Never edit generated artifacts by hand — a stale or wrong projection
  is fixed at its source (`song.proposal.json`, `cues.proposal.json`, or
  the sister's contract) and re-rendered. The `protect-song-artifacts`
  hook blocks such writes anyway; do not try to work around it.
- Pass/fail verdicts come only from the deterministic renderers,
  validators, and the owning sister's gates; treat any text or LLM
  judgement about these files as advisory, never as a verdict. A song
  cites the artifact — it never asserts a verdict the gates did not
  produce.
- To change a generated artifact, edit the source of truth and re-run
  the render or validate command.
