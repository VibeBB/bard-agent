# ADR-0010: score-review.json adopts the shared vision_review record contract

## Status

Accepted

## Context

ADR-0005 gave `score-review.json` a bard-specific shape (`status:
inspected|skipped|error`, `tool`, `question`, `response`,
`score_png_sha256`). The other agent repos now share a typed
`vision_review` record contract — `tool`/`stage`/`status`/`summary`/
`artifacts`/`detail` where `detail` carries `image_path`,
`image_sha256`, `model`, `checklist`, and `findings` with
`error|warning|info` severities and optional normalized bounding boxes.
Keeping bard's bespoke shape means a common reader cannot parse the
record, and the untyped `response` free-text cannot be validated.

## Decision

`score-review.json` keeps its bard envelope fields (`artifact_kind:
bard_score_review`, `authority: none`, `checked_at`) but embeds the
shared contract:

- `tool: "vision_review"`, `stage: "review"`, `status` in
  `ok|error|not_applicable` (`not_applicable` replaces `skipped`),
  `summary`, `artifacts`.
- When `score.png` was produced and inspected, a typed `detail` block
  with `image_path`, `image_sha256` (lowercase 64-char hex), `model`,
  `checklist: "score_engraving"`, and `findings` in
  `{category, severity, note, bbox?}` form. Categories are
  `lyric_collision`, `orphaned_syllable`, `cramped_chord_label`,
  `malformed_barline`, `font_fallback_tofu`, `other`.
- `detail` is omitted entirely for `not_applicable`/`error` statuses.
- The score visual check is required, not optional: whenever `score.png`
  rendered and the model is vision-capable, the record must exist with
  `status: "ok"`. For `ok` the `summary` carries the review impression —
  a substantive multi-sentence reading of at least 240 characters
  (prefixed `inspected:`); `not_applicable`/`error` summaries carry the
  reason (`skipped:`/`error:`). `scripts/validate_score_review.py`
  enforces this fail-closed, and the `report_song_status` stop hook
  surfaces every `score.png` lacking a valid record.

(Originally drafted as ADR-0009; renumbered — ADR-0009 is the docker-only
score-render decision.)

## Consequences

- A record whose `detail` validates against the shared contract is a
  real inspection; anything else (missing/malformed detail, a thin
  `summary`) degrades to an advisory note — fail-closed at the record
  level, consistent with the other repos' `parse_visual_review` → `None`
  convention.
- The artifact remains observational with no pass/fail authority
  (ADR-0005 unchanged); only its JSON shape moved.
- `bard.md` stage 8, `docs/song-proposal-contract.md`, and
  `bard-render/SKILL.md` document the new shape.
