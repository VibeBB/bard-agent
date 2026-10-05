# Hooks

`plugins/bard/hooks/hooks.json` plus per-agent `hooks:` frontmatter
(`agents/bard.md`, `bard-cue.md`; the critic gets no records hooks). Every
command resolves the plugin root with the 4-root chain (see
[architecture.md](architecture.md)); an unresolved root means advisory hooks
exit 0, while `protect-song-artifacts` exits 2.

## session_start

| Hook | Script | Behavior |
| --- | --- | --- |
| `bard-doctor` | `bard_doctor.py` | Advisory probe (root, layout, docker, pin, liaison inbox counts) → `additionalContext`; exit 0 |
| `ensure-llm-profiles` | `ensure_llm_profiles.py` | Canonical shared hook; clones the active LLM profile into `vibebb-*` slots so the vision tool has a profile; exit 0 |
| `require-records` | `require_records.py session-start` | Writes the per-session marker `observations/bard/.sessions/<id>.json`; exit 0 |

## pre_tool_use

| Hook | Matcher | Script | Behavior |
| --- | --- | --- | --- |
| `protect-song-artifacts` | `file_editor\|apply_patch\|terminal` | `protect_song_artifacts.py` | Denies hand edits/writes to render projections (`song.abc/.mid/.mml/.md`, `song.provenance.json`, `score.png`, `song.contour.*`, `cues.*`, `cue-*.{mid,mml}`, `*.ux-response.json`, VRP logs `decisions/impressions/vision-reviews/vision-tool-events/image-observations.jsonl`, `records-status.json`) → exit 2 + reason |
| `safety-rail` | `terminal` | `safety_rail.py` | Canonical shared hook; denies destructive shell commands (rm -rf /, git push to main, --amend, etc.) → exit 2 |

## post_tool_use

| Hook | Matcher | Script | Behavior |
| --- | --- | --- | --- |
| `record-vision-tool-event` | `inspect_image_with_vision` | `record_vision_tool_event.py` | Appends the vision call to `vision-tool-events.jsonl`; exit 0 |
| `record-image-observation` | `file_editor` | `record_image_observation.py` | Appends viewed/created image observations to `image-observations.jsonl`; exit 0 |

## stop (order matters)

1. `require-records` — `require_records.py stop`: refuses (exit 2, bounded by
   `max_stop_denials: 2`) while the session owes records: unreviewed vision
   events/images, changed `artifact_globs` files with no fresh impression, no
   decision. Writes `records-status.json` either way.
2. `report-song-status` — `report_song_status.py`: advisory render-status
   report (proposals without render, missing/failed `score-review.json`, cue
   sets without valid provenance, PNGs without a VRP review bound to the
   current sha256); exit 0.
