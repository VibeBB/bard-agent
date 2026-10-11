# Records and vision

bard follows the VibeBB Record Protocol (VRP) v2 — the same chained,
append-only logs every sibling keeps under `observations/<plugin>/`; the
family specification is `wire-agent` `docs/records-protocol.md`. Records are
**creative advisory evidence**: they explain choices and what the model saw;
they never gate, approve or reject work.

## Log files

`observations/bard/`: `decisions.jsonl`, `impressions.jsonl`,
`vision-reviews.jsonl`, `reconciles.jsonl`, `insights.jsonl`, `reads.jsonl`
(and `song-receipts.jsonl`, which bard never writes: it refuses receipts for
its own songs), plus the hook-written inputs `vision-tool-events.jsonl`,
`image-observations.jsonl`, `records-status.json`. All are written only
through `bard_cli.py record …` (or the hooks) — the `protect-song-artifacts`
pre-tool guard denies hand edits. A log written entirely by VRP v1 is renamed
to `<name>.v1.jsonl` on the first v2 write.

Every line carries `schema_version` 2, `sequence`, `prev_event_id`,
`writer` and `event_id` (the sha256 of the canonical record). The writer
verifies the chain before appending and refuses a log that was edited,
truncated or reordered; readers report such a log under
`integrity_problems` and never resolve references into it.

## What is recorded at each stage

Decisions for real choices — mode/key/meter/tempo, form, which tagged facts to
sing, prosody fixes, critic findings applied/declined; for cues: contour per
purpose, pitch band vs device, opening distinctiveness, loop. Each decision
names ≥2 options with pros/cons, principles, ≥1 evidence ref bound by sha256,
assumptions, unknowns, risks and a revisit trigger.

A **stage impression** follows every stage file, plus one directory impression
for the whole output folder at the end:

- prose ≥400 characters and ≥3 sentences, refused when it is a near
  duplicate of an earlier impression of the same stage;
- `facets`: ≥2 `observed`, `works`, `concerns` (id, severity, `about`,
  anchor), `feelings.maker` / `feelings.user`, `next_actions`;
- ≥2 `claims`, each an exact token (`anchor`) of the cited text artifact
  (a lyric syllable, a `K:` line, a cue id), checked against the file bytes;
- `confidence`, `unknowns`, optional `insights` and `upstream` answers.

`record digest` lists open sister concerns and unanswered reads; answer each
one acted on in `upstream` (`adopted` / `deferred` / `disputed` / `noted`).
A disputed concern cannot be raised again while the artifact bytes are
unchanged, and a rejected insight is only re-proposed with `revisits` and a
reason. `record search` filters every sister log by text, kind, stage,
artifact or severity. `record status` runs before finishing.

## Vision points

The model views every rendered PNG and records a `vision_review` bound to the
image's sha256 (and to the vision-tool event via `source_event_id` when one
exists), with claims plus a `lookback` verdict per claim:

| Image | Produced by | Checklist | Blind second review |
| --- | --- | --- | --- |
| `score.png` | `render_score_png.py --abc` + `validate_score_review.py --record --vrp-json` | `score-engraving` | yes (`bard-blind-review`) |
| `song.contour.png` | `render_song.py` → `--svg` rasterize | `melody-contour` | no |
| `cues.timeline.png` | `render_cues.py` → `--svg` rasterize | `cue-timeline` | no |

`dual_review_globs` (`songs/*/score.png`) require a `blind` review by
`bard-blind-review`, whose `blind-guard` hook hides earlier reviews and
records, and a `record reconcile` of `[primary, blind]`; a split gets one
`tiebreak` round (at most 2 rounds) and stays `unknown` if unresolved.

## Songs to sisters

`record song-delivery` writes `liaison/<id>.bard-song.json`
(`kind: bard_song_delivery`, `schema_version` 1): the addressed sister
(`to`, never `bard`), `title`, `verse`, the song file pinned by sha256, the
sister `impression_refs` the song was made from, `reason` and `created_at`.
Each ref must resolve to a sister `stage_impression`; deliveries are never
overwritten. The sister answers with its own `song_receipt`; a receipt
never triggers another song, so the exchange cannot loop.

## Stop-hook behavior

`require-records` (first `stop` hook, canonical across the family) refuses to
end a session that changed `artifact_globs` files without a fresh impression
covering their current bytes, owes a decision, viewed an image/event with no
matching vision review, or owes a blind review / reconcile for a
`dual_review_globs` image. Bounded by `max_stop_denials` (2) so a model that
cannot comply still terminates; the verdict lands in `records-status.json`.
