# ADR-0011: Product sound cues as a separate bard_cue_set contract

## Status

Accepted

## Context

VibeBB products need short functional sounds — a startup chime, a
completion tone, a warning beep — and ux-creator owns the interaction
content that decides when they play. bard already renders MIDI and MML
deterministically from a canonical proposal, so product sounds should reuse
that pipeline instead of a second sound generator. The song contract
(`bard_song_proposal`) does not fit: it requires lyrics, at least four lines
and sixteen notes, a vocal range, and harmonic accompaniment, none of which a
100 ms buzzer tick has.

## Decision

- Add a separate contract, `bard_cue_set` 0.1 (`docs/cue-set-contract.md`),
  with purpose-typed monophonic cues, device pitch ranges (`piezo`,
  `speaker`), duration budgets, and a distinguishability rule.
- Add `render_cues.py` next to `render_song.py`. It loads `render_song` the
  same way `lint_score.py` does and reuses its pitch parser, SMF track
  writer, MML note spelling, and MIDI/MML read-back parsers. Standard
  library only, fail-closed, nothing written on rejection.
- Emit a `cues.json` manifest (`system: bard`) with firmware-ready tone
  tables so firmware can play cues on a PWM buzzer without a MIDI parser, and
  so ux-creator can import cue ids as provenance.
- Add a `bard-cue` sub-agent, a `/bard:cue` command, and a `bard-cuecraft`
  skill. Cue artifacts join the song artifacts under the
  `protect-song-artifacts` hook.
- Keep the originality policy of ADR-0003: cues must not quote or imitate
  existing startup chimes, notification tones, or sound logos.

## Consequences

- Songs and cues evolve independently; the song contract is unchanged.
- The manifest is the integration point with ux-creator and firmware; its
  shape is part of the contract and changes need a schema bump.
- A cue carries no authority over the product or UX design — like a song, it
  is an observation-grade artifact.
