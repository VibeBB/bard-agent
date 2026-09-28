---
name: bard-cuecraft
description: Decision tables for original product sound cues (earcons) - startup, shutdown, completion, success, warning, error, notification, confirm, cancel and pairing sounds for piezo buzzers and speakers, their contours, durations, pitch bands and the originality rules. Use before writing a bard_cue_set.
version: 1.1.0
license: BSD-3-Clause
triggers:
  - earcon
  - product sound
  - startup sound
  - completion sound
  - warning sound
  - beep
  - buzzer
  - chime
  - 起動音
  - 完了音
  - 警告音
  - 効果音
  - ブザー
---

# Bard cuecraft

How to design the short sounds a product plays. Every choice feeds a `bard_cue_set`
(`../bard-render/SKILL.md`); the renderer enforces the rules marked **(checked)**, you own the
rest.

## 1. Purpose table

| Purpose | Meaning for the listener | Contour | Typical length | Loop |
| --- | --- | --- | --- | --- |
| `startup` | the device is awake and ready | rising, 2..4 notes, ends on a stable degree | 300..1200 ms | no |
| `shutdown` | the device is going to sleep | the startup contour mirrored (falling) | 300..1200 ms | no |
| `completion` | the task the user started has finished | rising interval (4th/5th/octave), last note longest | 300..1000 ms | no |
| `success` | an action succeeded | short rising pair | 150..500 ms | no |
| `notification` | something needs a glance, not action | two notes, neutral interval, mid band | 200..700 ms | no |
| `warning` | attention needed soon | repeated single pitch with gaps, unresolved | 400..2000 ms | may loop **(checked)** |
| `error` | an action failed or a fault exists | falling or dissonant pair, low end of the band | 300..1500 ms | may loop **(checked)** |
| `confirm` | the press or touch registered | one very short high tick | 50..300 ms **(checked)** | no |
| `cancel` | the action was withdrawn | one short falling pair | 50..300 ms **(checked)** | no |
| `pairing` | a connection is being made / made | alternating two notes | 300..1500 ms | no |

Every cue is 50..3000 ms long **(checked)** and must start and end on a sounded note
**(checked)** — leading silence adds latency to the UX feedback budget.

## 2. Distinguishability

- No two cues in a set may sound identical at real time **(checked)**.
- Give each cue a different opening two notes and a different rhythm shape; contour alone is not
  enough on a piezo.
- Completion and success must never share a contour with warning or error.
- Keep one tempo family per product (e.g. 150–180 bpm) so the set sounds like one product.

## 3. Devices

| `device` | Range **(checked)** | Notes |
| --- | --- | --- |
| `piezo` | `c5`..`c8` (523–4186 Hz) | loudest near the element's resonance (often 2–4 kHz, see the part's datasheet); one pitch at a time; `program` is ignored by hardware |
| `speaker` | `c3`..`c8` | small speakers lose everything below ~`c4`; choose a General MIDI `program` for the MIDI preview |

Cues are monophonic: the firmware plays `cues.json` `tones[]` as a sequence of
`(freq_hz, start_ms, duration_ms)`, where `freq_hz: 0` is silence.

## 4. Accessibility

- Never rely on sound alone: the UX contract pairs every audio cue with a visual or haptic
  feedback. Mention the pairing in `rationale` when you know it.
- Warning and error cues use the upper-middle of the band (roughly 1–3 kHz), where
  age-related hearing loss matters least for alerts; do not park them at the top of the range.

## 5. Originality

`originality.original_melody` and `originality.no_trademark_sound_imitation` must both be
`true` **(checked)**. Do not quote or imitate well-known startup chimes, notification tones,
jingles or sound logos of any company or product, and do not name them as references. If asked
to "sound like" an existing product, write an original cue with the requested character
instead.
