# Product cue set contract `bard_cue_set` 0.1

A cue set is the source of truth for a product's short functional sounds
(earcons): startup, completion, warning, and similar cues. It lives at
`cues/<slug>/cues.proposal.json` and is rendered by
`plugins/bard/skills/bard-render/scripts/render_cues.py`, which reuses the
MIDI and MML primitives of `render_song.py`. The validator judges the cue set
text only; it grants no pass/fail authority over the product, its UX contract,
or its firmware (ADR-0011). A complete, passing example is
`plugins/bard/skills/bard-render/examples/smart-kettle.cues.json`.

## Top level

Unknown keys are rejected at the top level and in each cue.

| Field | Rule |
| --- | --- |
| `artifact_kind` | fixed value `bard_cue_set` |
| `schema_version` | `"0.1"` |
| `product` | 1..80 characters, not whitespace-only |
| `device` | `piezo` (range `c5`..`c8`) or `speaker` (range `c3`..`c8`) |
| `sources` | at least one `{kind, ref[, sha256]}`; `kind` is `ux_request` / `conversation_summary` / `agent_message` / `git_log` / `file` / `user_request`; `ref` 1..200 characters; `sha256` 64 lowercase hex digits |
| `rationale` | 1..2000 characters |
| `originality` | exactly `original_melody` and `no_trademark_sound_imitation`, both `true` |
| `cues` | 1..16 entries |
| `transducer` | optional, declared together with `listening`: `part` 1..120 characters, `distance_cm` 1..100 (the datasheet measuring distance), `response` 2..32 `{hz, spl_db}` points from the datasheet curve, `hz` 20..20000 strictly increasing, `spl_db` 0..140 |
| `listening` | optional, declared together with `transducer`: exactly `distance_m` 0.1..4 (the ISO 24501 scope), `ambient_db` 0..120 (A-weighted interfering sound), `min_margin_db` 0..40, and `rationale` 20..400 characters naming where the numbers come from |
| `accessibility_waivers` | optional list of `{check, reason}`; `check` is `max_fundamental_hz`, `reason` 20..400 characters, one waiver per check |

## Cues

| Field | Rule |
| --- | --- |
| `id` | `[a-z][a-z0-9_]{0,31}`, unique in the set; names the output files |
| `purpose` | `startup` / `shutdown` / `completion` / `success` / `warning` / `error` / `notification` / `confirm` / `cancel` / `pairing` |
| `ux_feedback` | optional; the ux-creator `feedback` id this cue realises (1..64 of `[A-Za-z0-9_.-]`) |
| `bpm` | integer 60..240 (one beat is a quarter note) |
| `program` | optional General MIDI program 0..127 for the MIDI preview, default `80` (square lead) |
| `loop` | optional boolean, default `false`; only `warning` and `error` may loop |
| `notes` | 1..16 `{pitch, beats}`; `pitch` is a note name (`c6`, `f#6`, `bb5`) inside the device range or `r` (rest); `beats` is one of `0.125, 0.25, 0.375, 0.5, 0.75, 1, 1.5, 2` |

Rejection conditions beyond the field rules:

1. The first and last note are sounded (no leading or trailing rest).
2. Duration `sum(beats) × 60000 / bpm` is 50..3000 ms, and at most 300 ms for
   `confirm` and `cancel`.
3. No two cues are identical at real time (same pitches and same note
   durations in milliseconds).
4. A `warning` cue loops: JIS S 0013:2011 (the national text of ISO
   24500:2010) clause 4.2 keeps a warning sounding while its cause lasts.
   `error` may stay one-shot for invalid-operation feedback.
5. A looping cue contains at least one rest, so it repeats as an ON/OFF
   pattern rather than a drone (every warning pattern in JIS S 0013 table 3
   is ON/OFF).
6. No sounded fundamental exceeds 2500 Hz (JIS S 0013 clause 4.3; older
   listeners with age-related hearing loss lose high frequencies first)
   unless an `accessibility_waivers` entry for `max_fundamental_hz` gives the
   reason. A waiver with no cue above 2500 Hz is rejected as stale.
7. With `transducer` and `listening` declared, every sounded tone lies inside
   the response curve, and its estimated level at the listener — datasheet
   SPL interpolated linearly over log frequency, minus
   `20·log10(distance_m·100 / distance_cm)` for free-field inverse-square
   spreading — is at least `ambient_db + min_margin_db`.

ISO 24501:2010 gives the measuring method for signal and interfering sound
levels (Annexes A and B); `listening` records the result or an explicit
assumption. The estimate is a design screen; a measurement on the built
product supersedes it. A listening evaluation by an audio-capable AI agent
(advisory, never a verdict) is future work (see the family roadmap on
www.vibebb.org).

## Rendering

| Output | Contents |
| --- | --- |
| `cue-<id>.mid` | SMF format 1, 480 ticks per beat. Track 0: title (`<product> <id>`), tempo, 4/4. Track 1: the cue on channel 0 with `program`, velocity 100 |
| `cue-<id>.mml` | `bard-mml 0.1`: `;` header lines (product, cue, purpose, device, bpm, loop, license) and one `@melody` voice using the song tokens plus length `32` (0.125 beats) and `16.` (0.375 beats) |
| `cues.json` | `artifact_kind: bard_cue_manifest`, `system: bard`, `authority: none`, `product`, `device`, `artifacts` (the MIDI/MML file names), and per cue `id`, `purpose`, `ux_feedback`, `loop`, `bpm`, `program`, `duration_ms`, `mid`/`mml` `{path, sha256}`, `tones[]` of `{start_ms, duration_ms, midi, freq_hz}`, an `accessibility` report (`reference`, `max_fundamental_hz`, `highest_fundamental_hz`, `warnings_loop`, `waivers`), and an `audibility` report (`status: unknown` with a `reason` when no transducer is declared; otherwise `status: pass`, the transducer and listening values, the estimation `model`, and per cue `id`, `min_spl_db`, `margin_db` over ambient) (`midi: null`, `freq_hz: 0.0` for rests; frequencies in 12-TET with a4 = 440 Hz, rounded to 0.01 Hz; milliseconds rounded half up). Sorted keys, no timestamps |
| `cues.md` | one-page preview: a table of cues with purpose, UX feedback, duration, loop and note names, then an accessibility section (highest fundamental, waivers, audibility), `rationale` and `sources` |
| `cues.provenance.json` | `artifact_kind: bard_cue_provenance`, `authority: none`, generation time, cue-set path/sha256, sha256 of each output, `sources`, generating-script sha256, `license: BSD-3-Clause`, `originality`, `device`, cue count |

The same cue set produces byte-identical outputs except the provenance
timestamp. The `protect-song-artifacts` hook denies hand edits to every
output above.

## Read-back checks (fail-closed)

- MIDI: re-parse each `cue-<id>.mid` and confirm channel-0 note-on and
  note-off counts equal the cue's sounded notes.
- MML: re-parse each `cue-<id>.mml` and confirm the `@melody` note count and
  total length equal the cue.

If any check fails, nothing is written and the process exits `2`.

## ux-creator hand-off

ux-creator asks for cues with a `*.ux-request.json` whose `target_agent` is
`bard`. bard answers with `cues/<slug>/cues.json`; ux-creator records it with
`import --from bard`, which extracts each cue `id` so its interaction-content
gates can confirm that every sound cue in the UX contract names a rendered
bard cue.
