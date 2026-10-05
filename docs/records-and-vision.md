# Records and vision

bard follows the VibeBB Record Protocol (VRP) v1 — the same append-only logs
every sibling keeps under `observations/<plugin>/`. Records are **creative
advisory evidence**: they explain choices and what the model saw; they never
gate, approve or reject work.

## Log files

`observations/bard/`: `decisions.jsonl`, `impressions.jsonl`,
`vision-reviews.jsonl`, plus the hook-written inputs
`vision-tool-events.jsonl`, `image-observations.jsonl`, `records-status.json`.
All are written only through `bard_cli.py record …` (or the hooks) — the
`protect-song-artifacts` pre-tool guard denies hand edits.

## What is recorded at each stage

Decisions for real choices — mode/key/meter/tempo, form, which tagged facts to
sing, prosody fixes, critic findings applied/declined; for cues: contour per
purpose, pitch band vs device, opening distinctiveness, loop. Each decision
names ≥2 options with pros/cons, ≥1 evidence ref bound by sha256 (or a named
standard reference), assumptions, unknowns, risks and a revisit trigger.

A **stage impression** (≥400 chars, ≥3 sentences: what was seen, what works,
one concern, how the maker/user reads it, next action) follows every stage
file, plus one directory impression for the whole output folder at the end.
`record status` runs before finishing.

## Vision points

The model views every rendered PNG and records a `vision_review` bound to the
image's sha256 (and to the vision-tool event via `source_event_id` when one
exists):

| Image | Produced by | Checklist |
| --- | --- | --- |
| `score.png` | `render_score_png.py --abc` + `validate_score_review.py --record` | `score-engraving` |
| `song.contour.png` | `render_song.py` → `--svg` rasterize | `melody-contour` |
| `cues.timeline.png` | `render_cues.py` → `--svg` rasterize | `cue-timeline` |

Sister images (e.g. a UX wireframe attached to a liaison request) are viewed
the same way and recorded under the same log when observed via `record
vision-review`.

## Stop-hook behavior

`require-records` (first `stop` hook, canonical across the family) refuses to
end a session that changed `artifact_globs` files without a fresh impression
covering their current bytes, owes a decision, or viewed an image/event with
no matching vision review. Bounded by `max_stop_denials` (2) so a model that
cannot comply still terminates; the verdict lands in `records-status.json`.
