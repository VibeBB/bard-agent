# MCP and the CLI surface

**bard has no MCP server.** Its tools run on the host `python3` and are
invoked by the agent's terminal tool; adding an MCP server would give bard a
second, duplicate way to mutate the same append-only logs and projections.
Instead `plugins/bard/scripts/bard_cli.py` is the typed entry point and plays
the role wire fills with `wire_record_*` MCP tools.

## `bard_cli.py`

Exit codes: `0` ok · `2` rejected (reasons in JSON) · `3` I/O error.
All subcommands print one JSON object to stdout.

| Subcommand | Args | Reads | Writes |
| --- | --- | --- | --- |
| `record decision` | `--json <file|->` `[--root W]` | evidence paths (sha256/tree_sha256) | appends `observations/bard/decisions.jsonl` |
| `record impression` | `--json <file|->` `[--root W]` | artifact paths | appends `observations/bard/impressions.jsonl` |
| `record vision-review` | `--json <file|->` `[--root W]` | `image_path` bytes | appends `observations/bard/vision-reviews.jsonl` |
| `record status` | `[--root W]` | the three logs + `records-status.json` | — |
| `ux-inbox` | `[--root W]` | `**/*.ux-request.json` (depth ≤4, skips `.git`/`.venv`/`node_modules`), sibling `*.ux-response.json` | — |
| `ux-respond` | `--json <file|->` `[--root W]` | the named request, input/artifact files, record logs for refs | `<stem>.ux-response.json` beside the request (overwrite allowed) |

Validation is fail-closed: unknown keys are rejected, workspace escapes and
symlinks rejected, `done` requires ≥1 artifact + ≥1 `decision_ref` +
≥1 `impression_ref` and no non-pass gate verdict.

## Render/validate scripts (`skills/bard-render/scripts/`)

| Script | Args | Exit codes | Reads/writes |
| --- | --- | --- | --- |
| `render_song.py` | `--proposal P --out-dir D [--check] [--json]` | 0 ok · 2 reject · 3 I/O | reads `song.proposal.json`; writes `song.abc`, `song.mid`, `song.mml`, `song.md`, `song.contour.svg`, `song.provenance.json` (read-back checked; `--check` writes nothing) |
| `render_cues.py` | `--cues C --out-dir D [--check] [--json]` | 0 · 2 · 3 | reads `cues.proposal.json`; writes `cue-<id>.mid/.mml`, `cues.json`, `cues.md`, `cues.provenance.json`, `cues.timeline.svg` |
| `render_score_png.py` | `--abc A | --svg S` `[--out-dir D] [--json] [--prewarm]` | 0 rendered · 3 I/O · 4 docker/pin missing (skip) · 5 tool failed | `--abc` → `score.png` (+`score*.svg`); `--svg` → `<stem>.png`; all inside the pinned image |
| `validate_score_review.py` | `REVIEW [--json] [--record] [--root W]` | 0 ok · 1 problems | validates `score-review.json` (400-char/3-sentence summary); `--record` appends a VRP `vision_review` |
| `lint_score.py` | score lint for proposals | 0/2 | structure/prosody lint used by stage checks |

## Doctor

`hooks/scripts/bard_doctor.py` (also `/bard:doctor`): probes root resolution,
layout, `docker`, the image pin, and liaison inbox counts; always exits 0 with
`{"decision": "allow", "additionalContext": ...}`.
