---
name: bard-proposal-rules
description: Path rule — proposal contract and originality reminders injected whenever a *.proposal.json file is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/*.proposal.json"
---

# Bard proposal file rules

- `song.proposal.json` follows the canonical contract in
  `docs/song-proposal-contract.md` (schema 0.3; 0.2 still accepted). Check the
  contract summary in `skills/bard-render/SKILL.md` before editing; do not
  read `render_song.py` to learn the contract.
- The proposal is rendered only when every `originality` declaration is
  `true`. Quoting or adapting existing lyrics or melodies, naming real
  artists as imitation targets, and mocking real people are prohibited.
- `skills/bard-render/scripts/render_song.py` is the only writer of song
  artifacts; ABC, MIDI, MML, the song sheet, and provenance are derived
  projections and are never hand-edited — fix the proposal and re-render.
- Validation is fail-closed: contract violations, parse failures, and
  read-back mismatches reject the proposal and partial output is not
  written.
