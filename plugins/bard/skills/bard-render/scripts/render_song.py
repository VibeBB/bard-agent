"""Validate a bard_song_proposal JSON and render it to ABC, MIDI, MML, Markdown
and a provenance record. Implements docs/song-proposal-contract.md (schema 0.2).

Python 3.12+, standard library only.

Conventions chosen where the contract leaves detail open:

- Melodic leaps (rule: adjacent notes within 12 semitones) are measured between
  consecutive *sounded* notes; rests do not participate.
- A ``~`` unit note must equal the previous sounded note or move by at most a
  whole step (2 semitones) per the line rule "same or adjacent (stepwise)".
- ``en`` units contain no punctuation: the unit join is compared to the text
  with whitespace and ``,.;:!?'"()-—`` removed and casefolded, so units must
  already be punctuation-free (e.g. ``"lines"`` for the word ``line's``).
- A ``ja`` line may carry a ``reading`` field (kana only); when present the
  unit join is checked against ``reading`` instead of ``text``, freeing
  ``text`` to use kanji. ``reading`` is rejected on ``en`` lines.
- Rhythm rule: any sung line of 4+ notes must use at least two distinct
  ``beats`` values.
- ``w:`` lyric lines: for ``en``, text words are reconstructed by consuming
  non-special units against each whitespace-split word's normalized form;
  inside a word, a piece is separated from the previous one by ``-`` only
  when the previous piece is a syllable, so mid-word melismas render as
  ``hea-_ven`` and a word-start ``~`` is a standalone ``_`` token. ``ja``
  text has no word boundaries, so every sung unit is joined by ``-`` into
  one run, with ``~`` breaking the run as a space-separated ``_`` token.
  Rest units emit no lyric token in either language: ABC aligns ``w:``
  words to sounded notes only and skips rests automatically.
- Each lyric ``Line`` renders as its own ABC music line followed by its single
  ``w:`` line, keeping lyric verse alignment 1:1; a line that ends mid-bar
  omits the ``|`` and the next line continues the bar. The section's last
  music line always closes with ``|``.
- ``intro``/``outro`` sections may declare ``lines: []``: the section is then
  an instrumental of bars x beats-per-bar. The melody is silent (ABC emits
  one ``z`` whole-bar rest per chord segment, MML emits ``r`` rests, the MIDI
  melody track plays nothing) while the accompaniment voices keep playing.
- Split-bar chords ("Am Dm") annotate the bar start and are re-annotated before
  the first melody event starting at or after the bar midpoint; if no event
  starts there, the annotation goes just before the bar line.
- MML accidentals prefer sharps, except that flat-spelled tonics (Db Eb Gb Ab
  Bb and F) prefer flats.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

PROPOSAL_KIND = "bard_song_proposal"
PROVENANCE_KIND = "bard_song_provenance"
SCHEMA_VERSION = "0.2"
PPQ = 480

MODES = {"chronicle", "praise", "lament", "satire", "inspire", "lore"}
LANGUAGES = {"ja", "en"}
SECTION_KINDS = {"intro", "verse", "chorus", "bridge", "outro"}
SOURCE_KINDS = {
    "conversation_summary",
    "agent_message",
    "git_log",
    "file",
    "user_request",
}
TONICS = [
    "C",
    "C#",
    "Db",
    "D",
    "D#",
    "Eb",
    "E",
    "F",
    "F#",
    "Gb",
    "G",
    "G#",
    "Ab",
    "A",
    "A#",
    "Bb",
    "B",
]
TONIC_PC = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}
KEY_MODES = {"major", "minor", "dorian", "mixolydian"}
SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
}
CHORD_QUALITIES = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "dim": (0, 3, 6),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "sus4": (0, 5, 7),
    "sus2": (0, 2, 7),
}
SEVENTH_QUALITIES = {"7", "maj7", "m7"}
METERS = {"4/4": Fraction(4), "3/4": Fraction(3), "6/8": Fraction(3)}
ALLOWED_BEATS = {
    Fraction(1, 4),
    Fraction(1, 2),
    Fraction(3, 4),
    Fraction(1),
    Fraction(3, 2),
    Fraction(2),
    Fraction(3),
    Fraction(4),
}
SECTION_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,32}$")
PITCH_RE = re.compile(r"^([a-g])(#|b)?([0-9])$")
CHORD_RE = re.compile(r"^([A-G](?:#|b)?)(dim|maj7|m7|sus4|sus2|m|7)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LETTER_PC = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
EN_TEXT_STRIP = str.maketrans("", "", " \t\r\n,.;:!?'\"()-—")
JA_TEXT_STRIP = str.maketrans("", "", " \t\r\n、。！？「」・…—")
JA_READING_RE = re.compile(r"^[ぁ-ゖァ-ヶー \t\r\n、。！？「」・…—]+$")
MAX_EVENTS = 8192


class ProposalError(Exception):
    """Validation or read-back failure holding every reason found."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


@dataclass(frozen=True)
class Note:
    pitch: str  # pitch name or "r"
    beats: Fraction
    midi: int | None  # None for rests


@dataclass(frozen=True)
class Chord:
    symbol: str
    root_pc: int
    quality: str
    tones: tuple[int, ...]  # pitch classes


@dataclass(frozen=True)
class Line:
    text: str
    units: list[str]
    notes: list[Note]
    reading: str | None = None


@dataclass(frozen=True)
class Section:
    name: str
    kind: str
    chords: list[list[Chord]]  # per bar: 1 or 2 chords
    lines: list[Line]


@dataclass(frozen=True)
class Song:
    title: str
    mode: str
    language: str
    sources: list[dict[str, Any]]
    rationale: str
    originality: dict[str, bool]
    tonic: str
    tonic_pc: int
    key_mode: str
    scale_pcs: frozenset[int]
    meter: str
    beats_per_bar: Fraction
    bpm: int
    melody_program: int
    accompaniment_program: int
    vocal_low: int
    vocal_high: int
    sections: list[Section]
    raw: dict[str, Any] = field(compare=False)


def parse_pitch(name: str) -> int | None:
    m = PITCH_RE.match(name)
    if not m:
        return None
    pc = LETTER_PC[m.group(1)]
    if m.group(2) == "#":
        pc += 1
    elif m.group(2) == "b":
        pc -= 1
    return (int(m.group(3)) + 1) * 12 + pc


def _parse_chord_symbol(symbol: str) -> Chord | None:
    m = CHORD_RE.match(symbol)
    if not m or m.group(1) not in TONIC_PC:
        return None
    root_pc = TONIC_PC[m.group(1)]
    quality = m.group(2) or ""
    if quality not in CHORD_QUALITIES:
        return None
    tones = tuple((root_pc + i) % 12 for i in CHORD_QUALITIES[quality])
    return Chord(symbol=symbol, root_pc=root_pc, quality=quality, tones=tones)


def validate_proposal(data: object) -> Song:
    """Validate a parsed JSON proposal, collecting every reason found."""
    reasons: list[str] = []

    def err(path: str, message: str) -> None:
        reasons.append(f"{path}: {message}")

    if not isinstance(data, dict):
        raise ProposalError(["$: proposal must be a JSON object"])

    if data.get("artifact_kind") != PROPOSAL_KIND:
        err("artifact_kind", f'must be "{PROPOSAL_KIND}"')
    if data.get("schema_version") != SCHEMA_VERSION:
        err("schema_version", f'must be "{SCHEMA_VERSION}"')

    title = data.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 80) or not title.strip():
        err("title", "must be 1..80 characters and not blank")
        title = ""

    mode = data.get("mode")
    if mode not in MODES:
        err("mode", f"must be one of {sorted(MODES)}")

    language = data.get("language")
    if language not in LANGUAGES:
        err("language", "must be ja or en")

    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) < 1:
        err("sources", "must contain at least one source")
        sources = []
    else:
        for i, src in enumerate(sources):
            p = f"sources[{i}]"
            if not isinstance(src, dict):
                err(p, "must be an object")
                continue
            if src.get("kind") not in SOURCE_KINDS:
                err(f"{p}.kind", f"must be one of {sorted(SOURCE_KINDS)}")
            ref = src.get("ref")
            if not isinstance(ref, str) or not (1 <= len(ref) <= 200):
                err(f"{p}.ref", "must be 1..200 characters")
            sha = src.get("sha256")
            if sha is not None and not (isinstance(sha, str) and SHA256_RE.match(sha)):
                err(f"{p}.sha256", "must be 64 lowercase hex characters")

    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not (1 <= len(rationale) <= 2000):
        err("rationale", "must be 1..2000 characters")
        rationale = ""

    originality = data.get("originality")
    orig_keys = (
        "original_lyrics",
        "original_melody",
        "no_named_artist_imitation",
        "no_real_person_ridicule",
    )
    if not isinstance(originality, dict):
        err("originality", "must be an object with four true flags")
        originality = {}
    else:
        for k in orig_keys:
            if originality.get(k) is not True:
                err(f"originality.{k}", "must be true")

    key = data.get("key")
    tonic = ""
    tonic_pc = 0
    key_mode = ""
    scale_pcs: frozenset[int] = frozenset()
    if not isinstance(key, dict):
        err("key", "must be an object with tonic and mode")
    else:
        tonic_raw = key.get("tonic")
        tonic = tonic_raw if isinstance(tonic_raw, str) else ""
        if tonic not in TONIC_PC:
            err("key.tonic", f"must be one of {' '.join(TONICS)}")
        else:
            tonic_pc = TONIC_PC[tonic]
        key_mode_raw = key.get("mode")
        key_mode = key_mode_raw if isinstance(key_mode_raw, str) else ""
        if key_mode not in KEY_MODES:
            err("key.mode", f"must be one of {sorted(KEY_MODES)}")
        else:
            scale_pcs = frozenset(
                (tonic_pc + i) % 12 for i in SCALE_INTERVALS[key_mode]
            )

    meter = data.get("meter")
    beats_per_bar = Fraction(0)
    if meter not in METERS:
        err("meter", "must be 4/4, 3/4 or 6/8")
    else:
        beats_per_bar = METERS[meter]

    bpm = data.get("bpm")
    if not isinstance(bpm, int) or isinstance(bpm, bool) or not (60 <= bpm <= 180):
        err("bpm", "must be an integer in 60..180")
        bpm = 96

    instruments = data.get("instruments")
    melody_program = 0
    accompaniment_program = 0
    if not isinstance(instruments, dict):
        err("instruments", "must be an object with melody and accompaniment")
    else:
        for k in ("melody", "accompaniment"):
            v = instruments.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or not (0 <= v <= 127):
                err(f"instruments.{k}", "must be a General MIDI program 0..127")
        melody_program = instruments.get("melody") or 0
        accompaniment_program = instruments.get("accompaniment") or 0

    vocal_range = data.get("vocal_range")
    vocal_low = 0
    vocal_high = 0
    if not isinstance(vocal_range, dict):
        err("vocal_range", "must be an object with low and high")
    else:
        low_name = vocal_range.get("low")
        high_name = vocal_range.get("high")
        low = parse_pitch(low_name) if isinstance(low_name, str) else None
        high = parse_pitch(high_name) if isinstance(high_name, str) else None
        if low is None:
            err("vocal_range.low", "must be a pitch name like c4")
            low = 0
        if high is None:
            err("vocal_range.high", "must be a pitch name like e5")
            high = 0
        span = high - low
        if not (7 <= span <= 19):
            err("vocal_range", "high - low must be 7..19 semitones")
        vocal_low, vocal_high = low, high

    raw_sections = data.get("sections")
    sections: list[Section] = []
    sung_notes = 0
    lyric_line_count = 0
    chord_events = 0
    last_sung_midi: int | None = None
    last_chord_root_pc: int | None = None
    prev_midi: int | None = None

    if not isinstance(raw_sections, list) or not (1 <= len(raw_sections) <= 12):
        err("sections", "must contain 1..12 sections")
    else:
        seen_names: set[str] = set()
        for si, raw_sec in enumerate(raw_sections):
            sp = f"sections[{si}]"
            if not isinstance(raw_sec, dict):
                err(sp, "must be an object")
                continue
            name = raw_sec.get("name")
            if not isinstance(name, str) or not SECTION_NAME_RE.match(name):
                err(f"{sp}.name", "must match [A-Za-z0-9 _-]{1,32}")
                name = f"section{si}"
            elif name in seen_names:
                err(f"{sp}.name", f"duplicate section name {name!r}")
            else:
                seen_names.add(name)
            kind = raw_sec.get("kind")
            if kind not in SECTION_KINDS:
                err(f"{sp}.kind", f"must be one of {sorted(SECTION_KINDS)}")

            raw_chords = raw_sec.get("chords")
            bars: list[list[Chord]] = []
            if not isinstance(raw_chords, list) or not (1 <= len(raw_chords) <= 32):
                err(f"{sp}.chords", "must contain 1..32 bar entries")
            else:
                for bi, entry in enumerate(raw_chords):
                    bp = f"{sp}.chords[{bi}]"
                    if not isinstance(entry, str) or not entry.strip():
                        err(bp, "must be one chord symbol or two separated by a space")
                        continue
                    parts = entry.split()
                    if len(parts) > 2:
                        err(bp, "at most two chord symbols per bar")
                        continue
                    bar_chords: list[Chord] = []
                    for sym in parts:
                        chord = _parse_chord_symbol(sym)
                        if chord is None:
                            err(bp, f"invalid chord symbol {sym!r}")
                            continue
                        if scale_pcs and chord.root_pc not in scale_pcs:
                            err(bp, f"chord root {chord.symbol} not in scale")
                        bar_chords.append(chord)
                    bars.append(bar_chords)
                    chord_events += sum(len(c.tones) for c in bar_chords)
                    last_chord_root_pc = bar_chords[-1].root_pc

            raw_lines = raw_sec.get("lines")
            lines: list[Line] = []
            section_beats = Fraction(0)
            if not isinstance(raw_lines, list):
                err(f"{sp}.lines", "must be a list")
            else:
                if kind not in ("intro", "outro") and len(raw_lines) < 1:
                    err(
                        f"{sp}.lines",
                        "non-intro/outro sections need at least one line",
                    )
                if kind in ("intro", "outro"):
                    pass
                else:
                    lyric_line_count += len(raw_lines)
                for li, raw_line in enumerate(raw_lines):
                    lp = f"{sp}.lines[{li}]"
                    if not isinstance(raw_line, dict):
                        err(lp, "must be an object")
                        continue
                    text = raw_line.get("text")
                    if not isinstance(text, str) or not (1 <= len(text) <= 200):
                        err(f"{lp}.text", "must be 1..200 characters")
                        text = ""
                    reading = raw_line.get("reading")
                    if reading is not None:
                        if not isinstance(reading, str) or not reading.strip():
                            err(f"{lp}.reading", "must be a non-empty string")
                            reading = None
                        elif language != "ja":
                            err(f"{lp}.reading", "reading is only for ja")
                            reading = None
                        elif not JA_READING_RE.match(reading):
                            err(f"{lp}.reading", "must be kana")
                            reading = None
                    units = raw_line.get("units")
                    if not isinstance(units, list) or not all(
                        isinstance(u, str) for u in units
                    ):
                        err(f"{lp}.units", "must be a list of strings")
                        units = []
                    raw_notes = raw_line.get("notes")
                    notes: list[Note] = []
                    if not isinstance(raw_notes, list):
                        err(f"{lp}.notes", "must be a list")
                        raw_notes = []
                    if len(raw_notes) != len(units):
                        err(
                            f"{lp}.notes",
                            f"notes count {len(raw_notes)} != units count {len(units)}",
                        )
                    for ni, raw_note in enumerate(raw_notes):
                        np_ = f"{lp}.notes[{ni}]"
                        if not isinstance(raw_note, dict):
                            err(np_, "must be an object")
                            continue
                        pitch = raw_note.get("pitch")
                        beats_raw = raw_note.get("beats")
                        beats: Fraction | None = None
                        if isinstance(beats_raw, (int, float)) and not isinstance(
                            beats_raw, bool
                        ):
                            beats = Fraction(str(beats_raw))
                        if beats is None or beats not in ALLOWED_BEATS:
                            err(
                                f"{np_}.beats",
                                "must be one of 0.25 0.5 0.75 1 1.5 2 3 4",
                            )
                            beats = None
                        else:
                            section_beats += beats
                        midi: int | None = None
                        if not isinstance(pitch, str):
                            err(f"{np_}.pitch", "must be a pitch name or 'r'")
                        elif pitch == "r":
                            pass
                        else:
                            midi = parse_pitch(pitch)
                            if midi is None:
                                err(f"{np_}.pitch", f"invalid pitch name {pitch!r}")
                            else:
                                if vocal_low and not (vocal_low <= midi <= vocal_high):
                                    err(np_, f"pitch {pitch} outside vocal range")
                                if scale_pcs and midi % 12 not in scale_pcs:
                                    err(np_, f"pitch {pitch} not in scale")
                                if prev_midi is not None and abs(midi - prev_midi) > 12:
                                    err(
                                        np_,
                                        "leap from previous note exceeds 12 semitones",
                                    )
                                prev_midi = midi
                                sung_notes += 1
                                last_sung_midi = midi
                        notes.append(
                            Note(
                                pitch=str(pitch),
                                beats=beats or Fraction(0),
                                midi=midi,
                            )
                        )
                    for ui, (unit, note) in enumerate(zip(units, notes, strict=False)):
                        up = f"{lp}.units[{ui}]"
                        if unit == "-":
                            if note.pitch != "r":
                                err(up, "rest unit '-' requires a rest note 'r'")
                        elif note.pitch == "r":
                            err(up, "rest note 'r' requires a '-' unit")
                        if unit == "~" and note.midi is not None:
                            idx = ui - 1
                            while idx >= 0 and notes[idx].midi is None:
                                idx -= 1
                            if idx >= 0:
                                prev = notes[idx].midi
                                assert prev is not None and note.midi is not None
                                if not (0 <= abs(note.midi - prev) <= 2):
                                    err(
                                        up,
                                        f"'~' note {note.pitch} must equal or "
                                        f"step from {notes[idx].pitch}",
                                    )
                        elif language == "ja" and unit not in ("~", "-"):
                            if not (1 <= len(unit) <= 2):
                                err(up, "ja unit must be 1..2 characters")
                    if len(notes) >= 4 and len({n.beats for n in notes}) < 2:
                        err(
                            f"{lp}.notes",
                            "line needs at least two different note lengths",
                        )
                    if units and text:
                        joined = "".join(u for u in units if u not in ("~", "-"))
                        if language == "en":
                            norm = text.translate(EN_TEXT_STRIP).casefold()
                            if joined.casefold() != norm:
                                err(f"{lp}.units", "units do not match text")
                        elif language == "ja":
                            if reading is not None:
                                norm = reading.translate(JA_TEXT_STRIP)
                                if joined != norm:
                                    err(
                                        f"{lp}.units",
                                        "units do not match reading",
                                    )
                            else:
                                norm = text.translate(JA_TEXT_STRIP)
                                if joined != norm:
                                    err(f"{lp}.units", "units do not match text")
                    lines.append(
                        Line(text=text, units=units, notes=notes, reading=reading)
                    )

                # melody rule 3: notes starting on beat 1 of a bar must be a
                # chord tone of that bar's first chord
                if bars and beats_per_bar:
                    offset = Fraction(0)
                    for li, line in enumerate(lines):
                        for ni, note in enumerate(line.notes):
                            start = offset
                            offset += note.beats
                            if note.midi is None:
                                continue
                            bar = int(start // beats_per_bar)
                            if start % beats_per_bar != 0 or bar >= len(bars):
                                continue
                            first = bars[bar][0] if bars[bar] else None
                            if first is None:
                                continue
                            if note.midi % 12 not in first.tones:
                                err(
                                    f"{sp}.lines[{li}].notes[{ni}]",
                                    f"downbeat pitch {note.pitch} is not a chord "
                                    f"tone of {first.symbol}",
                                )
            if bars and lines and section_beats != beats_per_bar * len(bars):
                err(
                    sp,
                    f"section beats {float(section_beats)} != "
                    f"bars*beats {float(beats_per_bar * len(bars))}",
                )
            sections.append(
                Section(name=name, kind=kind or "", chords=bars, lines=lines)
            )

    if sung_notes < 16:
        err("sections", "at least 16 sung (non-rest) notes required")
    if lyric_line_count < 4:
        err("sections", "at least 4 lines required outside intro/outro")
    total_events = (
        sung_notes
        + sum(
            len(line.notes) - sum(1 for n in line.notes if n.midi is not None)
            for s in sections
            for line in s.lines
        )
        + chord_events
    )
    if total_events > MAX_EVENTS:
        err("sections", f"total events {total_events} exceed {MAX_EVENTS}")

    if sections and last_chord_root_pc is not None and last_chord_root_pc != tonic_pc:
        err(
            f"sections[{len(sections) - 1}].chords",
            "final chord root != tonic",
        )

    if last_sung_midi is not None and scale_pcs:
        degrees = (
            sorted(SCALE_INTERVALS[key_mode]) if key_mode in SCALE_INTERVALS else []
        )
        cadence = (
            {(tonic_pc + degrees[i]) % 12 for i in (0, 2, 4)}
            if len(degrees) >= 5
            else set()
        )
        if cadence and last_sung_midi % 12 not in cadence:
            err("sections", "final pitch not degree 1/3/5")

    if reasons:
        raise ProposalError(reasons)

    assert language in ("ja", "en")
    return Song(
        title=title,
        mode=str(mode),
        language=language,
        sources=list(sources),
        rationale=rationale,
        originality=dict(originality),
        tonic=str(tonic),
        tonic_pc=tonic_pc,
        key_mode=str(key_mode),
        scale_pcs=scale_pcs,
        meter=str(meter),
        beats_per_bar=beats_per_bar,
        bpm=bpm,
        melody_program=melody_program,
        accompaniment_program=accompaniment_program,
        vocal_low=vocal_low,
        vocal_high=vocal_high,
        sections=sections,
        raw=data,
    )


# ---------------------------------------------------------------------------
# melody timeline helpers


def _melody_events(song: Song) -> list[tuple[Fraction, Note, Section, Line]]:
    """(start beat within song, note, section, line) in order."""
    events: list[tuple[Fraction, Note, Section, Line]] = []
    pos = Fraction(0)
    for sec in song.sections:
        sec_start = pos
        for line in sec.lines:
            for note in line.notes:
                events.append((pos, note, sec, line))
                pos += note.beats
        pos = sec_start + song.beats_per_bar * len(sec.chords)
    return events


def _chord_events(song: Song) -> list[tuple[Fraction, Fraction, Chord, Section]]:
    """(start beat, duration beats, chord, section) in order."""
    events: list[tuple[Fraction, Fraction, Chord, Section]] = []
    pos = Fraction(0)
    half = song.beats_per_bar / 2
    for sec in song.sections:
        for bar in sec.chords:
            if len(bar) == 2:
                events.append((pos, half, bar[0], sec))
                events.append((pos + half, half, bar[1], sec))
            elif bar:
                events.append((pos, song.beats_per_bar, bar[0], sec))
            pos += song.beats_per_bar
    return events


# ---------------------------------------------------------------------------
# ABC rendering

ABC_PC_FLAT = ["c", "_d", "d", "_e", "e", "f", "_g", "g", "_a", "a", "_b", "b"]
ABC_PC_SHARP = ["c", "^c", "d", "^d", "e", "f", "^f", "g", "^g", "a", "^a", "b"]
FLAT_TONICS = {"Db", "Eb", "F", "Gb", "Ab", "Bb"}


def _abc_key(song: Song) -> str:
    if song.key_mode == "major":
        return song.tonic
    if song.key_mode == "minor":
        return song.tonic + "m"
    if song.key_mode == "dorian":
        return song.tonic + "dor"
    return song.tonic + "mix"


def _abc_note_name(midi: int, flat: bool) -> str:
    table = ABC_PC_FLAT if flat else ABC_PC_SHARP
    name = table[midi % 12]
    letter = name[-1]
    acc = name[:-1]
    octave = midi // 12 - 1
    if octave >= 5:
        letter = letter.lower() + "'" * (octave - 5)
    else:
        letter = letter.upper() + "," * (4 - octave)
    return acc + letter


def _abc_len(beats: Fraction) -> str:
    eighths = beats * 2
    if eighths == 1:
        return ""
    if eighths.denominator == 1:
        return str(eighths.numerator)
    if eighths.numerator == 1:
        return f"/{eighths.denominator}"
    return f"{eighths.numerator}/{eighths.denominator}"


def render_abc(song: Song) -> str:
    flat = song.tonic in FLAT_TONICS
    lines = [
        "X:1",
        f"T:{song.title}",
        "C:bard-agent",
        f"M:{song.meter}",
        "L:1/8",
        f"Q:1/4={song.bpm}",
        f"K:{_abc_key(song)}",
    ]
    half = song.beats_per_bar / 2
    for sec in song.sections:
        lines.append(f"%% section {sec.name}")
        if not sec.lines:
            tokens = []
            for bar in sec.chords:
                if bar:
                    tokens.append(f'"{bar[0].symbol}"')
                seg = half if len(bar) == 2 else song.beats_per_bar
                tokens.append("z" + _abc_len(seg))
                if len(bar) == 2:
                    tokens.append(f'"{bar[1].symbol}"')
                    tokens.append("z" + _abc_len(seg))
                tokens.append("|")
            lines.append(" ".join(tokens))
            continue
        pos = Fraction(0)
        bar = 0
        need_chord = True
        mid_done = False
        for line in sec.lines:
            tokens: list[str] = []
            for note in line.notes:
                while pos >= (bar + 1) * song.beats_per_bar:
                    cur = sec.chords[bar]
                    if len(cur) == 2 and not mid_done:
                        tokens.append(f'"{cur[1].symbol}"')
                    tokens.append("|")
                    bar += 1
                    need_chord = True
                    mid_done = False
                if need_chord:
                    tokens.append(f'"{sec.chords[bar][0].symbol}"')
                    need_chord = False
                cur = sec.chords[bar]
                if len(cur) == 2 and not mid_done and pos % song.beats_per_bar >= half:
                    tokens.append(f'"{cur[1].symbol}"')
                    mid_done = True
                if note.midi is None:
                    tokens.append("z" + _abc_len(note.beats))
                else:
                    tokens.append(
                        _abc_note_name(note.midi, flat) + _abc_len(note.beats)
                    )
                pos += note.beats
            lines.append(" ".join(tokens))
            lines.append(_w_line(song, line))
        music_line_idx = len(lines) - 2
        if not lines[music_line_idx].endswith("|"):
            lines[music_line_idx] += " |"
    return "\n".join(lines) + "\n"


def _w_line(song: Song, line: Line) -> str:
    if song.language == "en":
        tokens: list[str] = []
        words = [w for w in line.text.split() if w]
        idx = 0
        for word in words:
            target = word.translate(EN_TEXT_STRIP).casefold()
            pieces: list[str] = []
            joined = ""
            while idx < len(line.units):
                u = line.units[idx]
                idx += 1
                if u == "-":
                    continue
                if u == "~":
                    if pieces:
                        pieces.append("_")
                    else:
                        tokens.append("_")
                    continue
                pieces.append(u)
                joined += u
                if joined.casefold() == target:
                    break
            if pieces:
                word_token = pieces[0]
                for j in range(1, len(pieces)):
                    word_token += ("-" if pieces[j - 1] != "_" else "") + pieces[j]
                tokens.append(word_token)
        for u in line.units[idx:]:
            if u == "-":
                continue
            if u == "~":
                if tokens:
                    tokens[-1] += "" if tokens[-1].endswith("_") else "-"
                    tokens[-1] += "_"
                else:
                    tokens.append("_")
            else:
                tokens.append(u)
        return "w: " + " ".join(tokens)
    tokens = []
    run: list[str] = []
    for u in line.units:
        if u == "-":
            continue
        if u == "~":
            if run:
                tokens.append("-".join(run))
                run = []
            tokens.append("_")
            continue
        run.append(u)
    if run:
        tokens.append("-".join(run))
    return "w: " + " ".join(tokens)


# ---------------------------------------------------------------------------
# MIDI rendering


def _vlq(value: int) -> bytes:
    stack = [value & 0x7F]
    value >>= 7
    while value:
        stack.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(stack))


def _midi_track(events: list[tuple[int, bytes]]) -> bytes:
    events = sorted(events, key=lambda e: e[0])
    body = bytearray()
    last = 0
    for tick, payload in events:
        body += _vlq(tick - last)
        body += payload
        last = tick
    body += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def render_midi(song: Song) -> bytes:
    tempo_us = 60_000_000 // song.bpm
    nn, dd = song.meter.split("/")
    dd_pow = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}[int(dd)]
    title = song.title.encode("utf-8")
    track0 = _midi_track(
        [
            (0, b"\xff\x03" + _vlq(len(title)) + title),
            (0, b"\xff\x51\x03" + tempo_us.to_bytes(3, "big")),
            (0, b"\xff\x58\x04" + bytes([int(nn), dd_pow, 24, 8])),
        ]
    )

    melody: list[tuple[int, bytes]] = [
        (0, bytes([0xC0, song.melody_program])),
    ]
    for start, note, _sec, _line in _melody_events(song):
        if note.midi is None:
            continue
        on = int(start * PPQ)
        off = int((start + note.beats) * PPQ)
        melody.append((on, bytes([0x90, note.midi, 90])))
        melody.append((off, bytes([0x80, note.midi, 0])))
    track1 = _midi_track(melody)

    accomp: list[tuple[int, bytes]] = [
        (0, bytes([0xC1, song.accompaniment_program])),
    ]
    for start, dur, chord, _sec in _chord_events(song):
        on = int(start * PPQ)
        off = int((start + dur) * PPQ)
        pitches = [48 + chord.root_pc] + [60 + pc for pc in chord.tones[1:]]
        for p in pitches:
            accomp.append((on, bytes([0x91, p, 60])))
        for p in pitches:
            accomp.append((off, bytes([0x81, p, 0])))
    track2 = _midi_track(accomp)

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 3, PPQ)
    return header + track0 + track1 + track2


# ---------------------------------------------------------------------------
# MML rendering

MML_PC_SHARP = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
MML_PC_FLAT = ["c", "d-", "d", "e-", "e", "f", "g-", "g", "a-", "a", "b-", "b"]

MML_LEN = {
    Fraction(4): "1",
    Fraction(3): "2.",
    Fraction(2): "2",
    Fraction(3, 2): "4.",
    Fraction(1): "4",
    Fraction(3, 4): "8.",
    Fraction(1, 2): "8",
    Fraction(1, 4): "16",
}


def _mml_len(beats: Fraction) -> str:
    if beats in MML_LEN:
        return MML_LEN[beats]
    raise ProposalError([f"mml: cannot express length {float(beats)} beats"])


class _MmlVoice:
    def __init__(self, bpm: int, octave: int) -> None:
        self.tokens = [f"t{bpm}", f"o{octave}", "l4"]
        self.octave = octave

    def note(self, name: str, octave: int, beats: Fraction) -> None:
        if octave != self.octave:
            self.tokens.append(f"o{octave}")
            self.octave = octave
        self.tokens.append(name + _mml_len(beats))

    def rest(self, beats: Fraction) -> None:
        self.tokens.append("r" + _mml_len(beats))


def _mml_pc(pc: int, flat: bool) -> str:
    return (MML_PC_FLAT if flat else MML_PC_SHARP)[pc]


def render_mml(song: Song) -> str:
    flat = song.tonic in FLAT_TONICS
    lines = [
        "; bard-mml 0.1",
        f"; title={song.title}",
        f"; mode={song.mode}",
        f"; language={song.language}",
        f"; key={song.tonic} {song.key_mode}",
        f"; meter={song.meter}",
        f"; bpm={song.bpm}",
        "; license=BSD-3-Clause",
    ]
    melody = _MmlVoice(song.bpm, 4)
    half = song.beats_per_bar / 2
    for sec in song.sections:
        if not sec.lines:
            for bar in sec.chords:
                if len(bar) == 2:
                    melody.rest(half)
                    melody.rest(half)
                else:
                    melody.rest(song.beats_per_bar)
            continue
        for line in sec.lines:
            for note in line.notes:
                if note.midi is None:
                    melody.rest(note.beats)
                else:
                    octave = note.midi // 12 - 1
                    melody.note(_mml_pc(note.midi % 12, flat), octave, note.beats)
    lines.append("@melody")
    lines.append(" ".join(melody.tokens))

    n_chord_voices = max(
        3,
        max(
            (len(c.tones) for s in song.sections for bar in s.chords for c in bar),
            default=3,
        ),
    )
    voice_events: list[list[tuple[Fraction, str | None, int, Fraction]]] = [
        [] for _ in range(n_chord_voices)
    ]
    for start, dur, chord, _sec in _chord_events(song):
        pcs = [chord.root_pc, *chord.tones[1:]]
        pcs += [None] * (n_chord_voices - len(pcs))
        for vi in range(n_chord_voices):
            pc = pcs[vi]
            octave = 3 if vi == 0 else 4
            if pc is None:
                voice_events[vi].append((start, None, octave, dur))
            else:
                voice_events[vi].append((start, _mml_pc(pc, flat), octave, dur))
    for vi in range(n_chord_voices):
        voice = _MmlVoice(song.bpm, 3 if vi == 0 else 4)
        for _start, name, octave, dur in voice_events[vi]:
            if name is None:
                voice.rest(dur)
            else:
                voice.note(name, octave, dur)
        lines.append(f"@chord{vi + 1}")
        lines.append(" ".join(voice.tokens))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Markdown + provenance


def render_markdown(song: Song, abc: str) -> str:
    lines = [
        f"# {song.title}",
        "",
        f"- mode: {song.mode}",
        f"- language: {song.language}",
        f"- key: {song.tonic} {song.key_mode}",
        f"- meter: {song.meter}",
        f"- tempo: {song.bpm} bpm",
        "",
    ]
    for sec in song.sections:
        lines.append(f"## {sec.name} ({sec.kind})")
        lines.append("")
        if not sec.lines:
            lines.append("_（間奏）_" if song.language == "ja" else "_(instrumental)_")
            lines.append("")
        for line in sec.lines:
            lines.append(line.text + "  ")
        if sec.lines:
            lines.append("")
        chord_cells = " | ".join(" ".join(c.symbol for c in bar) for bar in sec.chords)
        lines.append(f"Chords: | {chord_cells} |")
        lines.append("")
    lines.append("```abc")
    lines.append(abc.rstrip("\n"))
    lines.append("```")
    lines.append("")
    lines.append("## Rationale")
    lines.append("")
    lines.append(song.rationale)
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for src in song.sources:
        sha = f" (sha256: {src['sha256']})" if src.get("sha256") else ""
        lines.append(f"- `{src.get('kind', '')}`: {src.get('ref', '')}{sha}")
    return "\n".join(lines) + "\n"


def render_provenance(
    song: Song,
    proposal_path: Path,
    proposal_sha: str,
    outputs: dict[str, bytes],
    script_sha: str,
) -> str:
    bars = sum(len(s.chords) for s in song.sections)
    notes = sum(
        1 for s in song.sections for line in s.lines for n in line.notes if n.midi
    )
    record = {
        "artifact_kind": PROVENANCE_KIND,
        "authority": "none",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "proposal": {"path": str(proposal_path), "sha256": proposal_sha},
        "outputs": {
            name: hashlib.sha256(blob).hexdigest() for name, blob in outputs.items()
        },
        "sources": song.sources,
        "script_sha256": script_sha,
        "license": "BSD-3-Clause",
        "originality": song.originality,
        "bpm": song.bpm,
        "key": {"tonic": song.tonic, "mode": song.key_mode},
        "meter": song.meter,
        "bars": bars,
        "note_count": notes,
    }
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------------
# read-back checks

ABC_TOKEN_RE = re.compile(r"[\^_]*[a-gA-Gz][',]*(?:\d+/\d+|\d+|/\d+|/)?")


def parse_abc_melody(abc: str) -> tuple[int, int, Fraction]:
    """Return (sung notes, rests, total beats) parsed from the ABC body."""
    body = False
    notes = 0
    rests = 0
    total = Fraction(0)
    for raw in abc.splitlines():
        line = raw
        if line.startswith("K:"):
            body = True
            continue
        if not body:
            continue
        if line.startswith("w:") or line.startswith("%%") or not line.strip():
            continue
        line = re.sub(r'"[^"]*"', "", line)
        line = re.sub(r"%.*", "", line)
        for m in ABC_TOKEN_RE.finditer(line):
            tok = m.group(0)
            letter_idx = 0
            while tok[letter_idx] in "^_":
                letter_idx += 1
            letter = tok[letter_idx]
            length_str = tok[letter_idx + 1 :].lstrip("',")
            if not length_str:
                eighths = Fraction(1)
            elif length_str.startswith("/"):
                denom = length_str[1:]
                eighths = Fraction(1, int(denom) if denom else 2)
            elif "/" in length_str:
                num, den = length_str.split("/", 1)
                eighths = Fraction(int(num), int(den))
            else:
                eighths = Fraction(int(length_str))
            if letter == "z":
                rests += 1
            else:
                notes += 1
            total += eighths
    return notes, rests, total / 2


def _read_vlq(track: bytes, i: int) -> tuple[int, int]:
    value = 0
    while True:
        if i >= len(track):
            raise ProposalError(["readback.midi: truncated VLQ"])
        b = track[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            return value, i


def parse_midi_counts(data: bytes) -> dict[int, list[int]]:
    """Parse an SMF and return {channel: [note_on_count, note_off_count]}."""
    if len(data) < 14 or data[:4] != b"MThd":
        raise ProposalError(["readback.midi: missing MThd header"])
    hlen = struct.unpack(">I", data[4:8])[0]
    fmt, ntrks = struct.unpack(">HH", data[8:12])
    if fmt != 1 or ntrks < 2:
        raise ProposalError([f"readback.midi: bad format {fmt} or track count {ntrks}"])
    pos = 8 + hlen
    counts: dict[int, list[int]] = {}
    for _ in range(ntrks):
        if pos + 8 > len(data) or data[pos : pos + 4] != b"MTrk":
            raise ProposalError(["readback.midi: missing MTrk header"])
        tlen = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        if pos + 8 + tlen > len(data):
            raise ProposalError(["readback.midi: truncated track data"])
        track = data[pos + 8 : pos + 8 + tlen]
        pos += 8 + tlen
        i = 0
        running = 0
        while i < len(track):
            _delta, i = _read_vlq(track, i)
            if i >= len(track):
                raise ProposalError(["readback.midi: truncated event"])
            status = track[i]
            if status < 0x80:
                status = running
            else:
                i += 1
                if status < 0xF0:
                    running = status
            kind = status & 0xF0
            ch = status & 0x0F
            if status == 0xFF:
                if i >= len(track):
                    raise ProposalError(["readback.midi: truncated meta event"])
                i += 1
                meta_len, i = _read_vlq(track, i)
                i += meta_len
                if i > len(track):
                    raise ProposalError(["readback.midi: truncated meta payload"])
                continue
            if status in (0xF0, 0xF7):
                syx_len, i = _read_vlq(track, i)
                i += syx_len
                if i > len(track):
                    raise ProposalError(["readback.midi: truncated sysex payload"])
                continue
            if kind in (0xC0, 0xD0):
                i += 1
                continue
            if kind == 0x90:
                if i + 1 >= len(track):
                    raise ProposalError(["readback.midi: truncated note-on"])
                vel = track[i + 1]
                i += 2
                bucket = counts.setdefault(ch, [0, 0])
                if vel > 0:
                    bucket[0] += 1
                else:
                    bucket[1] += 1
                continue
            if kind == 0x80:
                i += 2
                counts.setdefault(ch, [0, 0])[1] += 1
                continue
            i += 2
    return counts


MML_TOKEN_RE = re.compile(r"(t\d+|o\d+|l\d+\.?|<|>|&|[cdefgab][+-]?\d*\.?|r\d*\.?)")


def parse_mml(text: str) -> dict[str, tuple[int, Fraction]]:
    """Return {voice: (sounded note count, total beats)}."""
    voices: dict[str, tuple[int, Fraction]] = {}
    current: str | None = None
    default_len = Fraction(4)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("@"):
            current = line[1:]
            voices[current] = (0, Fraction(0))
            default_len = Fraction(4)
            continue
        if current is None:
            raise ProposalError(["readback.mml: tokens before any voice"])
        count, total = voices[current]
        i = 0
        pending_tie = False
        while i < len(line):
            m = MML_TOKEN_RE.match(line, i)
            if not m:
                if line[i].isspace():
                    i += 1
                    continue
                raise ProposalError(
                    [f"readback.mml: bad token in {current}: {line[i:]!r}"]
                )
            tok = m.group(0)
            i = m.end()
            if tok.startswith("t") or tok.startswith("o") or tok in ("<", ">"):
                continue
            if tok == "&":
                pending_tie = True
                continue
            if tok.startswith("l"):
                val = tok[1:].rstrip(".")
                default_len = Fraction(4, int(val))
                continue
            is_rest = tok.startswith("r")
            body = tok[1:] if is_rest else re.sub(r"^[cdefgab][+-]?", "", tok)
            dotted = body.endswith(".")
            body = body.rstrip(".")
            length = Fraction(4, int(body)) if body else default_len
            if dotted:
                length *= Fraction(3, 2)
            if pending_tie:
                total -= Fraction(0)
            pending_tie = False
            if not is_rest:
                count += 1
            total += length
        voices[current] = (count, total)
    return voices


# ---------------------------------------------------------------------------
# render + read-back orchestration


def render(song: Song) -> dict[str, bytes]:
    abc = render_abc(song)
    midi = render_midi(song)
    mml = render_mml(song)
    md = render_markdown(song, abc)
    return {
        "song.abc": abc.encode("utf-8"),
        "song.mid": midi,
        "song.mml": mml.encode("utf-8"),
        "song.md": md.encode("utf-8"),
    }


def _readback_check(song: Song, outputs: dict[str, bytes]) -> list[str]:
    reasons: list[str] = []
    sung = sum(
        1 for s in song.sections for line in s.lines for n in line.notes if n.midi
    )
    rests = sum(
        1 for s in song.sections for line in s.lines for n in line.notes if not n.midi
    ) + sum(len(bar) for s in song.sections if not s.lines for bar in s.chords)
    total_beats = sum(
        (n.beats for s in song.sections for line in s.lines for n in line.notes),
        Fraction(0),
    ) + sum(song.beats_per_bar * len(s.chords) for s in song.sections if not s.lines)

    abc_notes, abc_rests, abc_beats = parse_abc_melody(
        outputs["song.abc"].decode("utf-8")
    )
    if (abc_notes, abc_rests, abc_beats) != (sung, rests, total_beats):
        reasons.append(
            f"readback.abc: notes {abc_notes}/{sung} rests {abc_rests}/{rests} "
            f"beats {float(abc_beats)}/{float(total_beats)}"
        )

    midi_counts = parse_midi_counts(outputs["song.mid"])
    for ch, (ons, offs) in midi_counts.items():
        if ons != offs:
            reasons.append(
                f"readback.midi: channel {ch} note-on {ons} != note-off {offs}"
            )
    melody_ons = midi_counts.get(0, [0, 0])[0]
    if melody_ons != sung:
        reasons.append(f"readback.midi: melody notes {melody_ons} != {sung}")

    voices = parse_mml(outputs["song.mml"].decode("utf-8"))
    melody_voice = voices.get("melody")
    if melody_voice is None:
        reasons.append("readback.mml: missing @melody voice")
    else:
        if melody_voice[0] != sung or melody_voice[1] != total_beats:
            reasons.append(
                f"readback.mml: melody notes {melody_voice[0]}/{sung} "
                f"beats {float(melody_voice[1])}/{float(total_beats)}"
            )
        n_chord_voices = max(
            3,
            max(
                (len(c.tones) for s in song.sections for bar in s.chords for c in bar),
                default=3,
            ),
        )
        for vi in range(1, n_chord_voices + 1):
            v = voices.get(f"chord{vi}")
            if v is None:
                reasons.append(f"readback.mml: missing @chord{vi} voice")
            elif v[1] != total_beats:
                reasons.append(
                    f"readback.mml: chord{vi} beats {float(v[1])} != "
                    f"{float(total_beats)}"
                )
    return reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and render in memory, write nothing",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the result as one JSON object"
    )
    args = parser.parse_args(argv)

    proposal_path: Path = args.proposal
    out_dir: Path = args.out_dir

    try:
        raw_text = proposal_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as e:
        reasons = [f"proposal: cannot read or parse JSON: {e}"]
        if args.json:
            print(json.dumps({"status": "error", "reasons": reasons}))
        else:
            for r in reasons:
                print(r)
        return 3 if isinstance(e, OSError) else 2

    proposal_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    try:
        song = validate_proposal(data)
        outputs = render(song)
        readback_reasons = _readback_check(song, outputs)
        if readback_reasons:
            raise ProposalError(readback_reasons)
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        prov = render_provenance(song, proposal_path, proposal_sha, outputs, script_sha)
        outputs["song.provenance.json"] = prov.encode("utf-8")
    except ProposalError as e:
        if args.json:
            print(
                json.dumps(
                    {"status": "rejected", "reasons": e.reasons}, ensure_ascii=False
                )
            )
        else:
            for r in e.reasons:
                print(r)
        return 2
    except OSError as e:
        reasons = [f"io: {e}"]
        if args.json:
            print(json.dumps({"status": "error", "reasons": reasons}))
        else:
            print(reasons[0])
        return 3

    if args.check:
        result = {"status": "ok", "check": True, "proposal_sha256": proposal_sha}
        print(json.dumps(result) if args.json else "check ok")
        return 0

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}
        for name, blob in outputs.items():
            path = out_dir / name
            path.write_bytes(blob)
            written[name] = hashlib.sha256(blob).hexdigest()
    except OSError as e:
        print(
            json.dumps({"status": "error", "reasons": [f"io: {e}"]})
            if args.json
            else f"io: {e}"
        )
        return 3

    if args.json:
        print(json.dumps({"status": "ok", "files": written}, ensure_ascii=False))
    else:
        for name, sha in written.items():
            print(f"{out_dir / name}: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
