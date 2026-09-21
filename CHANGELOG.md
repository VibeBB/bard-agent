# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
