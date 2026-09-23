---
name: bard-songcraft
description: Decision tables for writing an original song about work in a workspace - song modes (chronicle, praise, lament, satire, inspire, lore), keys and modes, chord progressions, meter and rhythm, melody rules, lyric craft for English and Japanese, and the originality contract. Use before writing a bard song proposal.
version: 1.1.0
license: BSD-3-Clause
triggers:
  - song
  - ballad
  - lyrics
  - melody
  - jingle
  - chant
  - lament
  - bard
  - minstrel
  - 歌
  - 作詞
  - 作曲
  - 叙事詩
  - 吟遊詩人
---

# Bard songcraft

How to turn events in a workspace into an original, singable song. Every choice below feeds a
`bard_song_proposal` (see `../bard-render/SKILL.md`); the renderer enforces the mechanical rules
marked **(checked)**, you own the rest.

## 1. Pick the mode

| Mode | Sings about | Key / mode | Meter | Tempo | Form |
| --- | --- | --- | --- | --- | --- |
| `chronicle` | what happened, in order | Dorian or minor | 4/4 or 6/8 | 88..108 | strophic verses + one refrain line |
| `praise` | a success, release, merge | major or Mixolydian | 4/4 or 3/4 | 100..128 | verse-chorus |
| `lament` | something lost, a failure | minor or Dorian | 3/4 or 4/4 | 60..84 | 2-3 short strophic verses |
| `satire` | a bug, debt or absurd mechanism | Mixolydian or major | 6/8 or 4/4 | 108..140 | verse-chorus, chorus lands the joke |
| `inspire` | courage for the next step | major | 4/4 | 112..140 | chorus only, or verse + chorus |
| `lore` | how something works or came to be | Dorian or major | 4/4 | 84..104 | strophic, one fact per verse |

Default mode is `chronicle`. Default length: 8..24 bars per section, 2..4 sections, whole song
under 64 bars.

Work in stages and write each one down (`notes.md` facts with source tags → `story.md` arc,
form, refrain → `lyrics.md` with units → `plan.md` chords and rhythm palette →
`song.proposal.json`). Notes are written last, once per distinct melody: strophic verses
after the first reuse it through `melody_from` (§5). Writing the whole proposal in one pass
is the slowest and least reliable way to compose.

## 2. Scales

Degrees relative to the tonic (semitones). **(checked)**: every sung note must be in the scale.

| Mode | Semitones | Character |
| --- | --- | --- |
| `major` | 0 2 4 5 7 9 11 | bright, festive |
| `minor` | 0 2 3 5 7 8 10 (11 allowed as leading tone) | lament, reflection |
| `dorian` | 0 2 3 5 7 9 10 | medieval, the road, tales |
| `mixolydian` | 0 2 4 5 7 9 10 | rustic, dance, satire |

Tonic spellings: `C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B`. Prefer `D dorian`, `A minor`,
`G mixolydian`, `C major`, `E minor`, `G major` for a c4..e5 voice.

## 3. Chords

Chord symbol = root + quality (`""`, `m`, `dim`, `7`, `maj7`, `m7`, `sus4`, `sus2`). One chord per
bar, or two separated by a space for a half-bar split. **(checked)**: every chord root is in the
scale; the last chord of the song has the tonic as root.

| Mode | Diatonic triads | Progressions that work (one chord per bar) |
| --- | --- | --- |
| `major` | I ii iii IV V vi vii° | I V vi IV / I IV V I / vi IV I V / ii V I I |
| `minor` | i ii° III iv v VI VII | i VI III VII / i iv v i / i VII VI V |
| `dorian` | i ii III IV v vi° VII | i IV i IV / i VII IV i / i ii i VII |
| `mixolydian` | I ii iii° IV v vi VII | I VII IV I / I v IV I / I IV VII I |

Cadence: end on I (or i). The bar before the end takes V, IV or VII.

Example in D dorian: `Dm C Dm Am | Dm C Am Dm` (roots D C D A / D C A D, all in the scale).

## 4. Meter and rhythm

One beat is a quarter note; `6/8` counts three beats of two eighths. Note lengths in beats:
`0.25 0.5 0.75 1 1.5 2 3 4`. **(checked)**: the notes of a section fill exactly
`bars × beats-per-bar`. **(checked)**: a line of 4+ notes must use at least two
different note lengths — a bar of four quarter notes is a rejection, not a ballad.
End each line on a long note (>=1.5 beats) or a rest, and put a `-` rest unit
between lines so the singer breathes.

| Meter | Beats per bar | Feel | Typical bar patterns (beats) |
| --- | --- | --- | --- |
| `4/4` | 4 | ballad, march | `1 1 1 1`, `1 0.5 0.5 1 1`, `0.5 0.5 1 0.5 0.5 1` |
| `3/4` | 3 | waltz, lament | `1 1 1`, `2 1`, `1.5 0.5 1` |
| `6/8` | 3 | jig, travel, satire | `0.5 0.5 0.5 0.5 0.5 0.5`, `1 0.5 1 0.5`, `1.5 1.5` |

Strong beats: 1 and 3 in `4/4`; 1 in `3/4`; 1 and (2.5) in `6/8`.

### Rhythm palette

Before writing notes, pick 3..5 bar patterns from the table for the song and name them
(`P1`..`P5`) in `plan.md`. Then assign one pattern per lyric line so that:

- no two adjacent lines share a pattern;
- the chorus/refrain uses a pattern no verse line uses;
- each line still ends on a note of >=1.5 beats or a rest, and each bar sums to its beats.

The renderer only checks the two-lengths rule; the palette is what keeps a 7-mora line
from becoming `1 1 1 1 1 1 2` eight times in a row, which is what happens without it.

## 5. Melody

- Vocal range default `c4..e5`; keep verses low, lift the chorus. **(checked)**: range 7..19
  semitones, all notes inside it.
- Mostly stepwise; leaps of a 3rd..5th on strong beats; **(checked)** no leap larger than an
  octave.
- **(checked)**: the note that starts beat 1 of each bar is a chord tone of that bar's first
  chord (rests are fine). Put passing tones on weak beats.
- Phrases of 2 or 4 bars; end each phrase on a long note or a rest.
- Contour inside a section: A A' B A'' — line 2 and line 4 vary line 1 by a step or two,
  line 3 climbs or falls away. Never three identical lines in one section.
- The chorus peak sits at least a 3rd above the verse peak and opens on a chord tone.
- Prefer a verse + chorus form over three identical verses; let the refrain line
  recur with the same words each time. A recurring refrain section is
  `kind: chorus` (name it `refrain N` or `chorus N`); verse sections stay
  `kind: verse` — the renderer checks name/kind agreement **(checked)**.
- Repeat the verse melody for every verse (strophic); vary only the words. Write the notes
  once: later verses declare `"melody_from": "verse 1"` and omit `chords` and every line's
  `notes`; the renderer copies both. **(checked)**: each line of the copying section has the
  same number of units as the source line, with `-` rests in the same positions.
- **(checked)**: the last sung note is the tonic, or the 3rd or 5th above it.
- Melisma: a held or stepwise-moving syllable is written as extra notes whose unit is `~`.

## 6. Lyrics

| Language | One unit is | Stress | Rhyme | Shape |
| --- | --- | --- | --- | --- |
| `en` | a syllable | stressed syllables on strong beats | AABB, ABAB or ABCB; near-rhyme is fine | 4-line stanzas, 8..10 syllables per line |
| `ja` | a mora (拗音・長音・促音 stay with the previous character) | word boundaries at phrase breaks; long vowels and the line-final mora get the longer notes | not required; keep one grammatical ending per section (〜た / 〜ぬ / 〜う) | 7-5, 8-6 or 5-7-5 mora shapes, or 4 lines of 8..12 morae; no 体言止め on 3+ consecutive lines |

**(checked)**: the units of a line, joined, equal the line's text with spaces and punctuation
removed (case-insensitive for `en`). For `ja`, write the lyrics with kanji in `text`
and put a kana-only `reading` on the line — the units then join to `reading` instead
(units stay in kana either way). Rests are `-` units on `r` notes.

Craft:

- Make it concrete: a red log, the terminal at midnight, the test that vanished. One abstract
  noun per line at most.
- `en`: mark stressed syllables in `lyrics.md` (`'pipe line's 'eye`) and put them on the
  strong beats; a stressed syllable on a weak half-beat is the most common prosody fault.
- Every line traces to a tagged fact in `notes.md` or is imagery about one. A line that
  states an event, number or outcome with no tag is a grounding fault, not poetic licence.
- Turn tools into figures: CI is a watchman with a red flag, a flaky test is a will-o'-wisp,
  a merge is a bridge finished, a rollback is the road back.
- The refrain starts with the same words every time.
- Keep the timeline honest: sing only events that the context or the workspace supports.
  Invent imagery, never facts.
- Replace personal names with roles: the user, the wandering reviewer, the night watch, the
  other agent.

## 7. Instruments (General MIDI, 0-based)

| Voice | Program |
| --- | --- |
| lute / guitar | 24 |
| harp | 46 |
| recorder | 74 |
| pan flute | 75 |
| dulcimer | 15 |
| fiddle | 40 |
| choir (melody stand-in) | 52 |

Default: melody 74 (recorder), accompaniment 24 (nylon guitar). Lament: melody 40, accompaniment
46. Satire: melody 75, accompaniment 15.

## 8. Originality contract

Set all four `originality` flags to `true` only when every statement holds; the renderer refuses
the proposal otherwise **(checked)**, and the critic flags suspected resemblance.

- Lyrics and melody are your own. No quoting, adapting or parodying existing songs, no
  traditional tunes, no "in the style of <artist>".
- No ridicule of a real person, team, company or product. Satire targets code, bugs and
  mechanisms.
- If asked to use an existing song, decline and offer an original in the same spirit.

## 9. Worked example (English, chronicle, D dorian, 4/4, 96 bpm)

```text
Section "verse 1", chords: Dm C Dm Am Dm C Am Dm (8 bars)
Line: "Under the red light of the pipeline's eye"
units: Un der the red light of the pipe line's eye  (10 syllables)
notes: d4 .5 | e4 .5 | f4 1 | g4 1 | a4 1 | g4 .5 | f4 .5 | e4 1 | d4 1 | d4 1   (8 beats = 2 bars)
```

Beat 1 of bar 1 is `d4` over `Dm` (chord tone); beat 1 of bar 2 is `a4` over `C`... check the
table: `a4` is not in C major triad, so either move the line so `g4` lands on the downbeat or
change bar 2 to `Am`. The renderer would reject the first version; this is the kind of fix it
asks for.

### Worked example (Japanese, chronicle, A minor, 3/4, 90 bpm)

Kanji goes in `text`, kana in `reading`, morae in `units`. Thirteen morae over two
bars with varied beats and a breath rest:

```text
Section "verse 1", chords: Am F G Am (4 bars)
Line: text 桜の下で歌を紡ぐ / reading さくらのしたでうたをつむぐ
units: さ く ら の し た で う た を つ む ぐ  (13 morae)
notes: a4 .5 | b4 .5 | c5 .5 | b4 .5 | a4 .25 | g4 .25 | a4 .5 | f4 .5 | g4 .5 | f4 .25 | e4 .25 | d4 .5 | e4 1   (6 beats = 2 bars)
```

The downbeat of bar 2 lands on `f4` over `F` (chord tone), the line ends on a
long note, and the rhythm mixes `.25`, `.5` and `1` — both new checks pass.
Follow the line with a `-` rest unit at the start of the next line when the
singer should breathe.
