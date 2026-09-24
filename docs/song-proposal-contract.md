# Song proposal contract `bard_song_proposal` 0.3

(Current `schema_version` is `"0.3"`. `"0.2"` is also accepted but cannot use
`melody_from`.)

This is the contract between the song proposal JSON written by the bard
agent (LLM) and the `bard-render` Skill that validates and renders it. The
validator judges the proposal text only — it does not judge the artistic
quality of the song nor the pass/fail status of the work the song is about.
The proposal is the sole source of truth for a song; ABC, MIDI, and MML are
all derived from it deterministically.

## Top level

```json
{
  "artifact_kind": "bard_song_proposal",
  "schema_version": "0.3",
  "title": "The Dragon of the Red Pipeline",
  "mode": "chronicle",
  "language": "en",
  "sources": [
    {"kind": "conversation_summary", "ref": "songs/red-pipeline/context.md", "sha256": "..."},
    {"kind": "git_log", "ref": "HEAD~20..HEAD"}
  ],
  "rationale": "Why this key, mode, meter and imagery fit the story.",
  "originality": {
    "original_lyrics": true,
    "original_melody": true,
    "no_named_artist_imitation": true,
    "no_real_person_ridicule": true
  },
  "key": {"tonic": "D", "mode": "dorian"},
  "meter": "4/4",
  "bpm": 96,
  "instruments": {"melody": 74, "accompaniment": 24},
  "vocal_range": {"low": "c4", "high": "e5"},
  "sections": [ ... ]
}
```

| Field | Rule |
| --- | --- |
| `artifact_kind` | fixed value `bard_song_proposal` |
| `schema_version` | `0.2` or `0.3`; `melody_from` is `0.3` only |
| `title` | 1..80 characters, not whitespace-only |
| `mode` | `chronicle` / `praise` / `lament` / `satire` / `inspire` / `lore` |
| `language` | `ja` / `en` |
| `sources` | at least one entry. `kind` is `conversation_summary` / `agent_message` / `git_log` / `file` / `user_request`. `ref` is 1..200 characters. `sha256` is optional (64 hex digits) |
| `rationale` | 1..2000 characters |
| `originality` | all four booleans must be `true` (original lyrics, original melody, no imitation of named artists, no ridicule of real people) |
| `key.tonic` | `C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B` |
| `key.mode` | `major` / `minor` / `dorian` / `mixolydian` |
| `meter` | `4/4` / `3/4` / `6/8`. One beat is a quarter note (in 6/8, an eighth note counts as 0.5 beats and one bar = 3 beats) |
| `bpm` | integer in 60..180 |
| `instruments.melody`, `instruments.accompaniment` | General MIDI program 0..127 |
| `vocal_range.low`, `vocal_range.high` | note names (see below). `high - low` spans 7..19 semitones |
| `sections` | 1..12 entries |

## Sections

```json
{
  "name": "verse 1",
  "kind": "verse",
  "chords": ["Dm", "C", "Dm", "Am", "Dm", "C", "Am Dm", "Dm"],
  "lines": [
    {
      "text": "Under the red light of the pipeline's eye",
      "units": ["Un", "der", "the", "red", "light", "of", "the", "pipe", "line's", "eye"],
      "notes": [
        {"pitch": "d4", "beats": 0.5}, {"pitch": "e4", "beats": 0.5},
        {"pitch": "f4", "beats": 1}, {"pitch": "g4", "beats": 1},
        {"pitch": "a4", "beats": 1},
        {"pitch": "g4", "beats": 0.5}, {"pitch": "f4", "beats": 0.5},
        {"pitch": "e4", "beats": 1}, {"pitch": "d4", "beats": 1},
        {"pitch": "d4", "beats": 1}
      ]
    }
  ]
}
```

| Field | Rule |
| --- | --- |
| `name` | 1..32 characters, `[A-Za-z0-9 _-]`, unique across the song |
| `kind` | `intro` / `verse` / `chorus` / `bridge` / `outro`. If the first word of `name` (case-insensitive) is `intro` / `verse` / `chorus` / `refrain` / `bridge` / `outro`, `kind` must be the corresponding kind (`refrain` maps to `chorus`) |
| `chords` | one element per bar, 1..32 bars. Each element is one chord symbol or two separated by a space (two symbols split the bar in half) |
| `melody_from` | optional (schema 0.3 only). Names an earlier section whose `chords` and per-line `notes` are copied (see "Melody reuse") |
| `lines` | zero or more (`intro`/`outro` may be empty, all other kinds need at least one). An `intro`/`outro` with `lines: []` becomes an instrumental stretch of bar-count × beats-per-bar where the melody rests and only accompaniment sounds (ABC emits a `z` whole-bar rest per chord span, MML emits `r`, Markdown prints `_(instrumental)_` / `_（間奏）_`, and no `w:` line is emitted). When lines are present, the concatenated `beats` totals of each line's `notes` must **equal** the section's total beat count (bar count × beats per bar) |

### Chord symbols

`<root><quality>`. `root` uses the same notation set as `key.tonic`;
`quality` is empty (major triad) / `m` / `dim` / `7` / `maj7` / `m7` /
`sus4` / `sus2`. A chord's root must belong to the key's scale (borrowed
chords are not allowed in 0.2). The root of the last chord of the last
section must be `key.tonic`.

### Lines

| Field | Rule |
| --- | --- |
| `text` | 1..200 characters |
| `units` | the sung-unit sequence: syllables for `en`, morae for `ja`. `~` extends the previous unit (melisma); `-` marks a rest position |
| `reading` | optional (`ja` only). A reading in hiragana, katakana, `ー`, whitespace, and punctuation. When present, the `units` consistency check runs against `reading` instead of `text`, so `text` may contain kanji. Not allowed for `en` |
| `notes` | same count as `units`. `pitch` is a note name or `r` (rest). `beats` is one of `0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4` |

`units`/`text` consistency (deterministic check):

- `en`: the units excluding `~` and `-` are concatenated and must equal
  `text` with whitespace and `,.;:!?'"()-—` removed, ignoring case.
- `ja`: taken from `reading` when present, otherwise `text`, after removing
  whitespace and punctuation (`、。！？「」・…—`). Mora segmentation is the
  proposer's responsibility, but each unit is 1..2 characters (attach
  yōon, long vowels, and geminate markers to the preceding character).
  Lyrics containing kanji go in `text` with their kana in `reading`.

`notes[i].pitch == "r"` ⇔ `units[i] == "-"`. A note whose `units[i]` is `~`
must be the same pitch as the previous note or stepwise-adjacent to it.

### Melody reuse (melody_from)

For strophic repetition (same melody with different lyrics), a section may
declare `melody_from: "<earlier section name>"`.

- `schema_version` must be `"0.3"` (rejected under `0.2`).
- The target must be a `name` that appears **earlier** in `sections`; an
  unknown or later name fails.
- The target itself must not use `melody_from` (no chaining).
- The copying section must omit the `chords` key, and every line must omit
  the `notes` key.
- The copying section must have the same line count, per-line `units`
  counts, and `-` (rest) positions as its target.
- All normal checks apply to the copied `chords`/`notes` (beat totals,
  downbeat harmony, range, leaps, cadence, etc.).

### Note names

`[a-g](#|b)?[0-9]` (e.g. `d4`, `f#4`, `bb3`). MIDI number: `c4 = 60`.

## Melody rules (rejection conditions)

1. Every non-rest note is within `vocal_range.low..high`.
2. Every non-rest note belongs to the key's scale; `minor` also allows the
   leading tone (raised 7th).
3. A melody note starting on beat 1 of a bar must be a chord tone of that
   bar's (first-half) chord (rests are allowed).
4. The leap between adjacent notes is at most a perfect octave (12
   semitones).
5. The final melody note of the song is scale degree 1, 3, or 5 of
   `key.tonic`.
6. At least 16 non-rest notes and at least 4 lines (excluding
   `intro`/`outro`).
7. Total event count (melody notes + chord notes) is at most 8192.
8. Each line with 4 or more notes uses at least two distinct `beats`
   values.
9. In `rationale`, any quotation (inside `「」`, `"`, or `“”`, four or more
   characters) following `refrain` / `chorus` / `verse` / `サビ` /
   `リフレイン` must — after whitespace normalization — partially match a
   line's `text` or the `title` (detects stale lyric quotes after
   revision).
10. `melody_from` follows every rule in "Melody reuse".

## Rendering

| Output | Contents |
| --- | --- |
| `song.abc` | ABC 2.1. `X:1`, `T:`, `C:bard-agent`, `M:`, `L:1/8`, `Q:1/4=<bpm>`, `K:<tonic><mode shorthand>` (`Ddor`, `Gmix`, `Am`, `C`). Chords in `"Dm"` form; lyrics as `w:` lines (`en` syllables joined with `-`, `~` as `_`, rests excluded — in ABC, rests do not participate in lyric alignment). A `%% section <name>` comment and a blank line per section |
| `song.mid` | SMF format 1, 480 ticks per beat. Track 0: tempo, meter, title. Track 1: melody (channel 0, `instruments.melody`). Track 2: accompaniment (channel 1, `instruments.accompaniment`). The accompaniment holds root (3rd octave) + 3rd + 5th (4th octave) per chord change, adding the 7th for seventh-family chords. When a chord tone would form a minor-9th or major-7th clash with the sounding melody, the voice is deterministically re-voiced: the first non-clashing, not-yet-used chord tone is substituted; the voice rests when every chord tone clashes |
| `song.mml` | `bard-mml 0.1`. Header comment lines starting with `;` (title, mode, language, key, meter, bpm, license); voices `@melody` and `@chord1`..`@chordN`, each monophonic (N is the song's maximum chord tone count, at least 3; `@chord4` appears when seventh chords exist). Tokens: `t<bpm>`, `o<oct>`, `l<len>`, note names (`c d e f g a b`, `+`/`-`), `r`, `&` (tie), `<`/`>` (octave). Lengths 1,2,4,8,16 with dots `.`: 0.75 beats is `8.`, 1.5 beats `4.`, 3 beats `2.`. Chord voices share the same clash-avoidance re-voicing as the MIDI accompaniment (`@chord1` is the bass at octave 3, the rest at octave 4); a dropped voice emits `r` |
| `song.md` | A one-page sheet for the Agent Canvas inline Markdown preview: title, mode, language, key/meter/tempo, per-section lyrics (`text` lines with two trailing spaces as hard breaks) and compact chord lines (`Chords: | Dm | C | ... |`, split bars as `Am Dm`), the full `song.abc` in an `abc` code fence, then `rationale` and `sources` |
| `song.provenance.json` | `authority: none`, `artifact_kind: bard_song_provenance`, generation time (UTC ISO 8601), proposal path/sha256, sha256 of each output, a copy of `sources`, the sha256 of the generating script, `license: BSD-3-Clause`, a copy of `originality`, `bpm`/`key`/`meter`/bar count/note count |

All text outputs use `encoding="utf-8"` with `\n` newlines.

### Optional advisory artifacts (not render outputs)

| Output | Contents |
| --- | --- |
| `score.png` | A score image rendered by `scripts/render_score_png.py` from `song.abc` via `abcm2ps` (`-g`, SVG) + `rsvg-convert`. A post-artifact for human review and vision inspection; part of neither the deterministic render outputs nor the read-back checks. Skipped when `abcm2ps`/`rsvg-convert` are absent. The SVG path emits every character as a UTF-8 `<text>` element so no glyphs are dropped at render time (ADR-0007). Non-Latin scripts such as Japanese need a suitable font (e.g. fonts-ipafont); without one, glyphs render as substitute boxes rather than disappearing. Lyric content is judged on `lyrics.md` |
| `score-review.json` | `artifact_kind: bard_score_review`, `authority: none`. Observations from a vision-capable model viewing `score.png` through `file_editor view` (`status: inspected\|skipped\|error`, the tool used, the question asked, a summary of findings, the score.png sha256, and inspection time). An observational record with no pass/fail authority over the proposal |
| `song.lint.json` | `artifact_kind: score_lint`, `authority: none`. Advisory report emitted by `scripts/lint_score.py`: residual melody/accompaniment clash findings parsed from the emitted `song.mid`, the deterministic re-voicing substitutions and drops applied per chord event, and note counts checked. A review aid with no pass/fail authority; `verdict: fail` means only that the lint itself could not run |

## Read-back checks (fail-closed)

- MIDI: re-parse our own output and confirm that note-on and note-off
  counts match per channel and that the melody note count matches the
  proposal.
- ABC: re-parse the note tokens of the generated body and confirm that the
  melody note count, rest count, and total beats match the proposal.
- MML: re-parse the generated text and confirm that `@melody`'s note count
  and total length match the proposal and that each chord voice's total
  length matches the melody's.

If any check fails, **nothing is written**; the reasons are listed and the
process exits non-zero.
