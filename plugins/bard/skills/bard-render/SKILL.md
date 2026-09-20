---
name: bard-render
description: Validate a bard_song_proposal JSON and render it deterministically to ABC notation, a Standard MIDI File, bard-mml text, a Markdown song sheet and a provenance record with a standard-library-only Python script. Use after writing a song proposal, or to check why a proposal was rejected.
version: 0.2.0
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
it against `docs/song-proposal-contract.md` (schema 0.2), renders every output in memory, reads
each output back and compares it with the proposal, and only then writes files. Any failure
writes nothing and exits non-zero with every reason listed. Python 3.12+, standard library only.

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

The renderer judges the proposal text only. Whether the song is good, and whether the work it
sings about succeeded, are outside its scope.

## Contract source of truth

`docs/song-proposal-contract.md` in the bard-agent repository. The script embeds the same rules
as code; when they disagree, the document wins and the script has a bug.
