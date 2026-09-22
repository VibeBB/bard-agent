---
name: bard-render
description: Validate a bard_song_proposal JSON and render it deterministically to ABC notation, a Standard MIDI File, bard-mml text, a Markdown song sheet and a provenance record with a standard-library-only Python script. Use after writing a song proposal, or to check why a proposal was rejected.
version: 1.0.0
license: BSD-3-Clause
triggers:
  - render song
  - song.proposal.json
  - abc notation
  - midi
  - mml
  - bard-render
  - 歌を描画
  - ABC譜
---

# Bard render

`scripts/render_song.py` is the only writer of song artifacts. It reads one proposal, validates
it against `docs/song-proposal-contract.md` (schema 0.3; 0.2 still accepted), renders every
output in memory, reads each output back and compares it with the proposal, and only then
writes files. Any failure writes nothing and exits non-zero with every reason listed.
Python 3.12+, standard library only.

## Contract in one page

Start from a complete valid example and edit it: `examples/minimal.en.json` (English,
verse-chorus) or `examples/minimal.ja.json` (Japanese with `reading`, strophic
`melody_from`). Both render in CI. You do not need to read `render_song.py`.

```json
{
  "artifact_kind": "bard_song_proposal", "schema_version": "0.3",
  "title": "1..80 chars", "mode": "chronicle|praise|lament|satire|inspire|lore",
  "language": "ja|en",
  "sources": [{"kind": "conversation_summary|agent_message|git_log|file|user_request", "ref": "path or range"}],
  "rationale": "1..2000 chars; quote lyrics only verbatim",
  "originality": {"original_lyrics": true, "original_melody": true,
                  "no_named_artist_imitation": true, "no_real_person_ridicule": true},
  "key": {"tonic": "D", "mode": "major|minor|dorian|mixolydian"},
  "meter": "4/4|3/4|6/8", "bpm": 96,
  "instruments": {"melody": 74, "accompaniment": 24},
  "vocal_range": {"low": "c4", "high": "e5"},
  "sections": [
    {"name": "verse 1", "kind": "verse", "chords": ["Dm", "C", "Am Dm", "Dm"],
     "lines": [{"text": "...", "reading": "kana, ja only", "units": ["..."],
                "notes": [{"pitch": "d4", "beats": 0.5}]}]},
    {"name": "verse 2", "kind": "verse", "melody_from": "verse 1",
     "lines": [{"text": "...", "units": ["..."]}]}
  ]
}
```

- One note per unit; `-` unit ⇔ `r` pitch; `~` unit = melisma on the previous syllable, same or
  adjacent pitch. `beats` ∈ `0.25 0.5 0.75 1 1.5 2 3 4`; a section's notes sum to
  `bars × beats-per-bar` (`6/8` = 3 beats per bar).
- Section `name` `[A-Za-z0-9 _-]{1,32}`, unique; its first word (`intro verse chorus refrain
  bridge outro`) must agree with `kind` (`refrain` → `chorus`). `intro`/`outro` may have
  `lines: []` (instrumental).
- `melody_from: "<earlier section name>"` copies that section's `chords` and every line's
  `notes`; the copying section omits `chords` and `notes`, and must have the same number of
  lines, the same unit count per line, and `-` rests in the same positions. The source may
  not itself use `melody_from`.
- Mechanical melody rules: all pitches in `vocal_range` and in the scale; the note starting
  beat 1 of each bar is a tone of that bar's first chord; leaps ≤ 12 semitones; last sung note
  is degree 1/3/5 of the tonic; last chord root is the tonic; 16+ sung notes, 4+ lyric lines;
  a line of 4+ notes uses ≥ 2 different `beats` values.
- Lyric checks: `en` units joined == `text` minus spaces/punctuation (case-insensitive);
  `ja` units joined == `reading` if present else `text`; `reading` is kana only and `ja` only.

## Run

```bash
python3 "<bard plugin root>/skills/bard-render/scripts/render_song.py" \
    --proposal <out dir>/song.proposal.json --out-dir <out dir>
```

Options:

| Flag | Meaning |
| --- | --- |
| `--proposal PATH` | proposal JSON (required) |
| `--out-dir DIR` | output directory, created if missing (required) |
| `--check` | validate and render in memory, write nothing |
| `--json` | print the result as one JSON object instead of text |

Exit codes: `0` rendered (or `--check` passed), `2` proposal rejected (validation or read-back),
`3` I/O error. On success it prints the written paths and their sha256; on rejection it prints
one `reason` per line as `<path in proposal>: <message>`, e.g.
`sections[0].lines[1].notes[3]: downbeat pitch a4 is not a chord tone of C`.

## Outputs

| File | Content |
| --- | --- |
| `song.abc` | ABC 2.1, `L:1/8`, chords as `"Dm"`, lyrics in `w:` lines |
| `song.mid` | SMF format 1, 480 ticks/beat; track 1 melody, track 2 block chords |
| `song.mml` | `bard-mml 0.1`: `;` header lines, `@melody` and `@chord1..@chordN` monophonic voices (N = max chord tones, at least 3) |
| `song.md` | Markdown song sheet for the Agent Canvas preview: lyric lines with hard breaks, one `Chords: | ... |` line per section, full ABC in a fence, rationale, sources |
| `song.provenance.json` | `artifact_kind: bard_song_provenance`, `authority: none`, sha256 of proposal, script and every output, copy of `sources` and `originality`, `license: BSD-3-Clause` |

Outputs are byte-for-byte deterministic for the same proposal, except the `generated_at`
timestamp in the provenance record.

## Optional: score.png for visual review

`scripts/render_score_png.py` turns `song.abc` into `score.png` through `abcm2ps` +
`gs` — the same commands CI uses. It is not a deterministic render output: it is
post-render advisory material for human and vision review, needs the two tools on
`PATH` (Japanese also needs a CJK font such as fonts-ipafont), and is never part of
the provenance output set.

```bash
python3 "<bard plugin root>/skills/bard-render/scripts/render_score_png.py" \
    --abc <out dir>/song.abc --json
```

Exit codes: `0` rendered; `3` I/O error; `4` `abcm2ps`/`gs` missing (skip — not an
error for the song); `5` a tool failed. `bard` stage 8 consumes this: a
vision-capable model inspects `score.png` via `file_editor view` and writes the
finding to `score-review.json` (`authority: none`).

`abcm2ps` cannot map CJK characters to its font encoding and drops them with
`warning: char XXXX not treated`, so Japanese kana/kanji may be missing from the
image even with a CJK font installed. The check covers staff layout, not CJK
lyric coverage — judge lyrics from `lyrics.md`.

## Fixing a rejected proposal

Read every reason before editing; fix the proposal JSON, not the outputs. The common ones:

| Reason | Fix |
| --- | --- |
| `units do not match text` / `units do not match reading` | re-split the line; `en` drops spaces and `,.;:!?'"()-—`, `ja` drops spaces and `、。！？「」・…—`; a `~` or `-` unit is skipped. With a kana `reading`, `ja` units join to the reading and `text` may carry kanji |
| `reading is only for ja` / `reading must be kana` | drop `reading` on `en`; write `ja` readings in kana only |
| `line needs at least two different note lengths` | vary the rhythm: mix `beats` values, end the line on a long note or a rest |
| `notes count != units count` | one note per unit; a rest note (`r`) needs a `-` unit |
| `section beats N != bars*beats M` | add or trim notes, or change the number of chords (bars) |
| `downbeat pitch X is not a chord tone of Y` | move the note or change the bar's chord |
| `pitch X not in scale` / `outside vocal range` | choose a scale tone inside `vocal_range` |
| `chord root X not in scale` | pick a diatonic chord (see `../bard-songcraft/SKILL.md` §3) |
| `final chord root != tonic` / `final pitch not degree 1/3/5` | end on the tonic chord and a chord tone |
| `originality.* must be true` | only set the flags after re-checking the song; do not set them to pass |
| `name "…" implies kind …` | section names starting `intro`/`verse`/`chorus`/`refrain`/`bridge`/`outro` must use the matching `kind` (`refrain` → `chorus`) |
| `quoted lyric "…" does not appear` | a lyric quoted in `rationale` after `refrain`/`chorus`/`verse`/`サビ`/`リフレイン` must match the final `text`/`title`; fix the quote after revising lyrics |
| `melody_from references unknown/later section` | point at a section that appears earlier in `sections` |
| `melody_from source uses melody_from` | copy from the section that holds the notes, not from another copy |
| `melody_from section must omit chords/notes` | remove `chords` from the section and `notes` from its lines |
| `line count N != source M` / `units count N != source M` / `rest positions differ` | rewrite the copying line to the source line's unit count and rest placement, or change the source |
| `schema_version must be 0.2 or 0.3` / `melody_from requires schema_version 0.3` | write `"schema_version": "0.3"` |

The renderer judges the proposal text only. Whether the song is good, and whether the work it
sings about succeeded, are outside its scope.

## Contract source of truth

`docs/song-proposal-contract.md` in the bard-agent repository. The script embeds the same rules
as code; when they disagree, the document wins and the script has a bug.
