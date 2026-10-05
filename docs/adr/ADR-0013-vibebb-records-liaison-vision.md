# ADR-0013: VibeBB record protocol port, SLP v2 liaison CLI, and melody/cue projections

Status: Accepted
Date: 2026-10-05

## Context

VibeBB adopted the Record Protocol (VRP v1) — append-only decision,
impression and vision-review logs — first in wire-agent, and upgraded
sibling liaison to SLP v2 (typed `*.ux-request.json`/`*.ux-response.json`).
bard had none of this: no records, no vision projections a model could look
at (only `score.png`), no liaison handling, and a score-review summary rule
(240 chars / 2 sentences) weaker than the shared impression rule. bard also
has no `src/` package and no MCP server — everything is stdlib scripts on the
host plus the pinned `bard-tools` image.

## Decision

- **VRP by port, not dependency**: copy the canonical shared hooks
  (`_records.py`, `require_records.py`) byte-for-byte into
  `plugins/bard/hooks/scripts/` (digests pinned in
  `scripts/check_shared_hooks.py`), and reimplement the typed writers as
  stdlib `plugins/bard/scripts/bard_records.py` mirroring
  `src/wire/records.py` semantics exactly — including the `event_id`
  identity hash (`{"kind","sequence",**body}` incl. None fields, sorted
  keys). Parity is pinned by constants in `tests/test_records.py` generated
  from wire's writer on identical payloads.
- **CLI instead of MCP**: `bard_cli.py` exposes `record
  decision|impression|vision-review|status` and `ux-inbox`/`ux-respond`
  subcommands; prompts reference exact invocations and a test fails CI when
  documented invocations stop parsing.
- **Liaison without ux-creator imports**: `bard_liaison.py` is a strict
  stdlib mirror of the v2 request/response shapes with all refusal rules
  (`done` needs artifacts + decision/impression refs and no non-pass gates).
- **New deterministic projections**: `song.contour.svg` (piano-roll with
  sections, chords, vocal range, staggered lyric units) and
  `cues.timeline.svg` (one row per cue on a shared ms scale, 100 ms ticks)
  rendered inside the same code path as the other outputs, rasterized by
  `render_score_png.py --svg` in the pinned image only.
- **Score-review adopts the impression rule**: `summary` minus the
  `inspected:` prefix must pass `_records.impression_errors` (≥400 chars,
  ≥3 sentences); `--record` appends the bound VRP vision review.
- **Cue distinctiveness checked**: two cues sharing their first two sounded
  notes (pitch + beats) are rejected by `render_cues.py`.

## Consequences

- Sessions that touch `songs/*/*` or `cues/*/*` owe records before the stop
  hook lets the conversation end (bounded: `max_stop_denials` 2).
- `observations/bard/*.jsonl` and `*.ux-response.json` are write-protected
  against hand edits; all writes go through the CLI.
- `report_song_status.py` now also reports PNGs lacking a sha-bound vision
  review and cue sets lacking valid provenance.
- CI renders and rasterizes the new projections (`out/ci/cues/` in the
  `bard-samples` artifact).
- Drift risk: the shared hooks must be updated in lockstep with EXPECTED
  digests; writer parity is only as fresh as the pinned constants.
