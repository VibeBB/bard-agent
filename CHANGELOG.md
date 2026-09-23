# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `pre_tool_use` hook `protect-song-artifacts` (ported from mechanical-agent's
  artifact guard): rejects `file_editor`/`apply_patch`/`terminal` writes to
  render projections (`song.abc`, `song.mid`, `song.mml`, `song.md`,
  `song.provenance.json`, `score.png`) — `render_song.py`/`render_score_png.py`
  remain the only writers.
- `post_tool_use` provenance hooks recording vision calls and image
  observations to `.openhands/bard/vision-tool-events.jsonl` and
  `.openhands/bard/image-observations.jsonl`; declared on the bard and
  bard-critic agent frontmatter as needed (plugin hooks do not propagate to
  task sub-agents).


### Fixed

- `scripts/check_plugin_load.py` now asserts every hook kind
  (`session_start`, `user_prompt_submit`, `pre_tool_use`, `stop`,
  `post_tool_use`) instead of only `stop`, matching the other agents'
  checkers.

### Changed

- Bumped `openhands-sdk` / `openhands-tools` pins to `1.49.5` (`sdk-check`
  group) and documented the feature evaluation in
  `docs/research/sdk-v1.49.5-feature-evaluation.md`.
- Stage 8 of `agents/bard.md` now states the vision path precisely: when the
  conversation model is not vision-capable, `file_editor view` does not
  display `score.png` and `inspect_image_with_vision` cannot substitute (it
  only covers user-attached images), so the check is recorded as skipped; a
  note covers inspecting user-attached images via `inspect_image_with_vision`.

### Added

- `skills/bard-proposal-rules`: path-triggered rule (`*.proposal.json`)
  injecting proposal-contract and originality reminders deterministically.

## [1.0.0] - 2026-09-21

Initial public release under VibeBB/bard-agent.

- Six songwriting modes: `chronicle`, `praise`, `lament`, `satire`, `inspire`,
  and `lore`.
- Japanese and English lyrics.
- Deterministic outputs: `song.md`, ABC, MIDI, MML, proposal JSON, and
  provenance JSON.
- Proposal contract schema 0.3 with `melody_from`.
- Fail-closed renderer implemented with Python's standard library only.
- `bard` and `bard-critic` task sub-agents with a fallback path when
  sub-agents are unavailable.
- Tag-based release workflow with verification and installation smoke tests.

[Unreleased]: https://github.com/VibeBB/bard-agent/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/VibeBB/bard-agent/releases/tag/v1.0.0
