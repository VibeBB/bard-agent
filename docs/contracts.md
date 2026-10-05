# Contracts

Every JSON shape bard reads or writes. Validators are fail-closed: unknown
keys, type mismatches and unreadable files are rejections, never skips.

## Song side

- **`song.proposal.json`** — canonical song truth (`bard_song_proposal`,
  schema 0.3; 0.2 accepted). Full contract:
  [song-proposal-contract.md](song-proposal-contract.md).
- **`song.provenance.json`** — `bard_song_provenance`: proposal sha256,
  per-output sha256 (`song.abc`, `song.mid`, `song.mml`, `song.md`,
  `song.contour.svg`), `sources`, `script_sha256`, `license`, `originality`,
  bpm/key/meter/bars/note_count, `generated_at`.
- **`score-review.json`** — `bard_score_review` envelope
  (`authority: none`, `tool: vision_review`, `stage: review`, `status`,
  `summary`, `artifacts`, `checked_at`) plus a typed `detail` block
  (`image_path`, `image_sha256`, `model`, `checklist: score_engraving`,
  `findings[{category,severity,note}]`). Summary must pass the shared
  impression rule (≥400 chars, ≥3 sentences) after the `inspected:` prefix is
  stripped. See ADR-0010 and [records-and-vision.md](records-and-vision.md).
- **`song.lint.json`** — lint output from `lint_score.py`.

## Cue side

- **`cues.proposal.json`** — `bard_cue_set` 0.1: product, device
  (`piezo|speaker`), sources, rationale, originality flags, cues[] with
  `id`, `purpose`, `bpm`, `program`, `loop`, `notes[{pitch,beats}]`.
  Contract: [cue-set-contract.md](cue-set-contract.md).
- **`cues.json`** — `bard_cue_manifest` (`system: bard`): per-cue id, purpose,
  ux_feedback, duration_ms, `tones[{freq_hz,start_ms,duration_ms}]`, mid/mml
  paths + sha256.
- **`cues.provenance.json`** — `bard_cue_provenance`: cue-set sha256, per-output
  sha256 (incl. `cues.timeline.svg`), sources, license.

## Records (VRP v1)

- **`observations/bard/decisions.jsonl`** — `{schema_version:1, kind:decision,
  plugin:bard, sequence, event_id, recorded_at, id, stage, question,
  principles[], options[{name,pros,cons}] (≥2), chosen, rationale (≥200),
  evidence[{path+sha256 | reference}], assumptions[], unknowns[], risks[],
  revisit_when, decided_by}`.
- **`impressions.jsonl`** — `kind:stage_impression` with `stage`,
  `artifacts[{path,sha256}]` (file or directory tree hash), `impression`
  (≥400 chars, ≥3 sentences).
- **`vision-reviews.jsonl`** — `kind:vision_review` with `image_path`/
  `image_sha256` and/or `source_event_id`, `model`, `checklist` (slug),
  `findings[]`, `impression`.
- **`vision-tool-events.jsonl` / `image-observations.jsonl`** — hook-written
  inputs to the vision-review requirement.
- **`records-status.json`** — last Stop-hook verdict (`pass`/`fail` +
  problems). `event_id` = sha256 of `{kind, sequence, **body}` with
  sorted keys; identical across siblings for identical bodies.

## `hooks/records-policy.json`

`{schema_version:1, plugin:bard, records_dir:"observations/bard",
artifact_globs:["songs/*/*","cues/*/*"], ignore_globs:["songs/*/score*.svg"],
max_stop_denials:2, record_hint}`.

## Liaison (SLP v2)

- **Request `*.ux-request.json`** — `{schema_version:2, system:"ux-creator",
  id slug == file stem, target_agent, stage ∈ requirements|design|
  manufacturing_handoff|build|evaluation|revision, risk low|high, purpose ≥20,
  rationale, requested_changes/expected_deliverables/acceptance (non-empty
  string lists), inputs[{path, sha256}], depends_on[], created_at ISO-8601
  with tz}`. High risk: `rationale` ≥20 chars and should cite a `jobs[].id`
  from a readable `*.ux.json` input (else warning, not rejection).
- **Response `*.ux-response.json`** — `{schema_version:2, system:"ux-creator",
  request (id), responder:"bard", status ∈ accepted|in_progress|done|
  rejected|deferred|needs_info, reason, input_hashes, artifacts[{path,
  sha256}], gate_verdicts[{gate, verdict}], decision_refs, impression_refs,
  questions_for_user[], responded_at}`.

Full liaison semantics: [sister-cooperation.md](sister-cooperation.md).
