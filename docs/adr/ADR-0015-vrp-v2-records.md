# ADR-0015: VRP v2 records and songs to sisters

Status: Accepted
Date: 2026-10-11

## Context

VRP v1 (ADR-0013) let a model append free prose that nobody had to answer:
logs could be edited or truncated unnoticed, the same concern could be
raised forever, a rejected idea could come back unchanged, one vision review
of a score was taken as seen, and bard had no way to hand a song to the
sister whose work it was about. wire-agent shipped VRP v2 as the family
reference; the user chose to port all of it to every plugin.

## Decision

- Copy the canonical v2 hooks (`_records.py`, `require_records.py`,
  `blind_guard.py`) byte-for-byte; `scripts/check_shared_hooks.py` pins the
  digests. `bard_records.py` stays a stdlib writer, but now imports the
  validators from the hook copy instead of re-implementing them, so the
  writer and the Stop hook cannot drift.
- Hash-chained logs, structured grounded impressions, near-duplicate
  refusal, read receipts, insight lifecycle, dispute no-re-raise,
  reconcile rounds and digest/search behave exactly as in wire (see
  `docs/records-and-vision.md`).
- `songs/*/score.png` is a dual-review image: the new `bard-blind-review`
  sub-agent records the blind round behind `blind-guard`, bard reconciles.
  The shared guard does not hide bard's own `score-review.json`, so the
  agent prompt forbids opening it; extending the shared pattern is a
  family-wide change for later.
- `record song-delivery` writes immutable, sha-pinned
  `liaison/<id>.bard-song.json`. It only cites sister `stage_impression`
  records and is never addressed to bard; bard refuses receipts for its own
  songs. A receipt therefore ends the exchange and cannot loop.
- `validate_score_review.py --record` requires `--vrp-json` because
  `score-review.json` does not carry facets, claims or lookback.

## Consequences

Records remain advisory: no gate, render or validator verdict reads them.
Existing v1 logs are archived as `<name>.v1.jsonl` on the first v2 write.
Callers that recorded impressions with the v1 shape now get a validation
error naming the missing v2 fields.
