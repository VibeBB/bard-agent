from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from song_model import (  # noqa: E402
    EN_TEXT_STRIP,
    JA_READING_RE,
    JA_TEXT_STRIP,
    TONIC_PC,
    TONICS,
    Chord,
    Line,
    Note,
    ProposalError,
    Section,
    Song,
    _parse_chord_symbol,
    parse_pitch,
)

PROPOSAL_KIND = "bard_song_proposal"

SCHEMA_VERSION = "0.3"

SCHEMA_VERSIONS_ACCEPTED = ("0.2", "0.3")

MODES = {"chronicle", "praise", "lament", "satire", "inspire", "lore"}

LANGUAGES = {"ja", "en"}

SECTION_KINDS = {"intro", "verse", "chorus", "bridge", "outro"}

SECTION_NAME_KIND = {
    "intro": "intro",
    "verse": "verse",
    "chorus": "chorus",
    "refrain": "chorus",
    "bridge": "bridge",
    "outro": "outro",
}

RATIONALE_QUOTE_RE = re.compile(
    r'(?:refrain|chorus|verse|サビ|リフレイン)\s*[「"“]([^」"”]{4,})[」"”]',
    re.IGNORECASE,
)

WS_RUN_RE = re.compile("[ 　]+")

SOURCE_KINDS = {
    "conversation_summary",
    "agent_message",
    "git_log",
    "file",
    "user_request",
}

KEY_MODES = {"major", "minor", "dorian", "mixolydian"}

SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
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

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MAX_EVENTS = 8192


@dataclass
class _Reasons:
    """Accumulates validation reasons as ``path: message`` strings."""

    reasons: list[str] = field(default_factory=list)

    def err(self, path: str, message: str) -> None:
        self.reasons.append(f"{path}: {message}")


@dataclass
class _Header:
    """Validated top-level proposal values shared with section checks."""

    schema_version: Any
    title: str
    mode: Any
    language: Any
    sources: list[Any]
    rationale: str
    originality: dict[str, Any]
    tonic: str
    tonic_pc: int
    key_mode: str
    scale_pcs: frozenset[int]
    meter: Any
    beats_per_bar: Fraction
    bpm: int
    melody_program: int
    accompaniment_program: int
    vocal_low: int
    vocal_high: int


@dataclass
class _Tally:
    """Running totals gathered while walking sections and lines."""

    sung_notes: int = 0
    lyric_line_count: int = 0
    chord_events: int = 0
    last_sung_midi: int | None = None
    last_chord_root_pc: int | None = None
    prev_midi: int | None = None

    def account_sung(self, midi: int, path: str, r: _Reasons) -> None:
        if self.prev_midi is not None and abs(midi - self.prev_midi) > 12:
            r.err(path, "leap from previous note exceeds 12 semitones")
        self.prev_midi = midi
        self.sung_notes += 1
        self.last_sung_midi = midi


def _validate_identity(data: dict[str, Any], r: _Reasons) -> tuple[Any, str, Any, Any]:
    if data.get("artifact_kind") != PROPOSAL_KIND:
        r.err("artifact_kind", f'must be "{PROPOSAL_KIND}"')
    schema_version = data.get("schema_version")
    if schema_version not in SCHEMA_VERSIONS_ACCEPTED:
        accepted = SCHEMA_VERSIONS_ACCEPTED
        r.err(
            "schema_version",
            f'must be "{accepted[0]}" or "{accepted[1]}"',
        )

    title = data.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 80) or not title.strip():
        r.err("title", "must be 1..80 characters and not blank")
        title = ""

    mode = data.get("mode")
    if mode not in MODES:
        r.err("mode", f"must be one of {sorted(MODES)}")

    language = data.get("language")
    if language not in LANGUAGES:
        r.err("language", "must be ja or en")

    return schema_version, title, mode, language


def _validate_sources(data: dict[str, Any], r: _Reasons) -> list[Any]:
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) < 1:
        r.err("sources", "must contain at least one source")
        return []
    for i, src in enumerate(sources):
        p = f"sources[{i}]"
        if not isinstance(src, dict):
            r.err(p, "must be an object")
            continue
        if src.get("kind") not in SOURCE_KINDS:
            r.err(f"{p}.kind", f"must be one of {sorted(SOURCE_KINDS)}")
        ref = src.get("ref")
        if not isinstance(ref, str) or not (1 <= len(ref) <= 200):
            r.err(f"{p}.ref", "must be 1..200 characters")
        sha = src.get("sha256")
        if sha is not None and not (isinstance(sha, str) and SHA256_RE.match(sha)):
            r.err(f"{p}.sha256", "must be 64 lowercase hex characters")
    return sources


def _validate_rationale(data: dict[str, Any], r: _Reasons) -> str:
    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not (1 <= len(rationale) <= 2000):
        r.err("rationale", "must be 1..2000 characters")
        rationale = ""
    return rationale


def _validate_originality(data: dict[str, Any], r: _Reasons) -> dict[str, Any]:
    originality = data.get("originality")
    orig_keys = (
        "original_lyrics",
        "original_melody",
        "no_named_artist_imitation",
        "no_real_person_ridicule",
    )
    if not isinstance(originality, dict):
        r.err("originality", "must be an object with four true flags")
        return {}
    for k in orig_keys:
        if originality.get(k) is not True:
            r.err(f"originality.{k}", "must be true")
    return originality


def _validate_key(
    data: dict[str, Any], r: _Reasons
) -> tuple[str, int, str, frozenset[int]]:
    key = data.get("key")
    tonic = ""
    tonic_pc = 0
    key_mode = ""
    scale_pcs: frozenset[int] = frozenset()
    if not isinstance(key, dict):
        r.err("key", "must be an object with tonic and mode")
    else:
        tonic_raw = key.get("tonic")
        tonic = tonic_raw if isinstance(tonic_raw, str) else ""
        if tonic not in TONIC_PC:
            r.err("key.tonic", f"must be one of {' '.join(TONICS)}")
        else:
            tonic_pc = TONIC_PC[tonic]
        key_mode_raw = key.get("mode")
        key_mode = key_mode_raw if isinstance(key_mode_raw, str) else ""
        if key_mode not in KEY_MODES:
            r.err("key.mode", f"must be one of {sorted(KEY_MODES)}")
        else:
            scale_pcs = frozenset(
                (tonic_pc + i) % 12 for i in SCALE_INTERVALS[key_mode]
            )
    return tonic, tonic_pc, key_mode, scale_pcs


def _validate_meter_bpm_instruments(
    data: dict[str, Any], r: _Reasons
) -> tuple[Any, Fraction, int, int, int]:
    meter = data.get("meter")
    beats_per_bar = Fraction(0)
    if meter not in METERS:
        r.err("meter", "must be 4/4, 3/4 or 6/8")
    else:
        beats_per_bar = METERS[meter]

    bpm = data.get("bpm")
    if not isinstance(bpm, int) or isinstance(bpm, bool) or not (60 <= bpm <= 180):
        r.err("bpm", "must be an integer in 60..180")
        bpm = 96

    instruments = data.get("instruments")
    melody_program = 0
    accompaniment_program = 0
    if not isinstance(instruments, dict):
        r.err("instruments", "must be an object with melody and accompaniment")
    else:
        for k in ("melody", "accompaniment"):
            v = instruments.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or not (0 <= v <= 127):
                r.err(f"instruments.{k}", "must be a General MIDI program 0..127")
        melody_program = instruments.get("melody") or 0
        accompaniment_program = instruments.get("accompaniment") or 0
    return meter, beats_per_bar, bpm, melody_program, accompaniment_program


def _validate_vocal_range(data: dict[str, Any], r: _Reasons) -> tuple[int, int]:
    vocal_range = data.get("vocal_range")
    vocal_low = 0
    vocal_high = 0
    if not isinstance(vocal_range, dict):
        r.err("vocal_range", "must be an object with low and high")
    else:
        low_name = vocal_range.get("low")
        high_name = vocal_range.get("high")
        low = parse_pitch(low_name) if isinstance(low_name, str) else None
        high = parse_pitch(high_name) if isinstance(high_name, str) else None
        if low is None:
            r.err("vocal_range.low", "must be a pitch name like c4")
            low = 0
        if high is None:
            r.err("vocal_range.high", "must be a pitch name like e5")
            high = 0
        span = high - low
        if not (7 <= span <= 19):
            r.err("vocal_range", "high - low must be 7..19 semitones")
        vocal_low, vocal_high = low, high
    return vocal_low, vocal_high


def _validate_header(data: dict[str, Any], r: _Reasons) -> _Header:
    schema_version, title, mode, language = _validate_identity(data, r)
    sources = _validate_sources(data, r)
    rationale = _validate_rationale(data, r)
    originality = _validate_originality(data, r)
    tonic, tonic_pc, key_mode, scale_pcs = _validate_key(data, r)
    meter, beats_per_bar, bpm, melody_program, accompaniment_program = (
        _validate_meter_bpm_instruments(data, r)
    )
    vocal_low, vocal_high = _validate_vocal_range(data, r)
    return _Header(
        schema_version=schema_version,
        title=title,
        mode=mode,
        language=language,
        sources=sources,
        rationale=rationale,
        originality=originality,
        tonic=tonic,
        tonic_pc=tonic_pc,
        key_mode=key_mode,
        scale_pcs=scale_pcs,
        meter=meter,
        beats_per_bar=beats_per_bar,
        bpm=bpm,
        melody_program=melody_program,
        accompaniment_program=accompaniment_program,
        vocal_low=vocal_low,
        vocal_high=vocal_high,
    )


def _resolve_melody_from(
    sp: str,
    raw_sec: dict[str, Any],
    hdr: _Header,
    earlier: dict[str, Section],
    copier_names: set[str],
    r: _Reasons,
) -> tuple[Any, Section | None]:
    melody_from = raw_sec.get("melody_from")
    src: Section | None = None
    if melody_from is not None:
        if hdr.schema_version != SCHEMA_VERSION:
            r.err(
                f"{sp}.melody_from",
                "melody_from requires schema_version 0.3",
            )
        elif not isinstance(melody_from, str) or melody_from not in earlier:
            r.err(
                f"{sp}.melody_from",
                f'references unknown/later section "{melody_from}"',
            )
        elif melody_from in copier_names:
            r.err(
                f"{sp}.melody_from",
                f'source "{melody_from}" uses melody_from',
            )
        else:
            src = earlier[melody_from]
        if "chords" in raw_sec:
            r.err(
                f"{sp}.chords",
                "melody_from section must omit chords",
            )
    return melody_from, src


def _validate_section_chords(
    sp: str,
    raw_sec: dict[str, Any],
    melody_from: Any,
    src: Section | None,
    hdr: _Header,
    tally: _Tally,
    r: _Reasons,
) -> list[list[Chord]]:
    raw_chords = raw_sec.get("chords")
    bars: list[list[Chord]] = []
    if melody_from is not None:
        if src is not None:
            bars = [list(bar) for bar in src.chords]
            tally.chord_events += sum(len(c.tones) for bar in bars for c in bar)
            if bars and bars[-1]:
                tally.last_chord_root_pc = bars[-1][-1].root_pc
    elif not isinstance(raw_chords, list) or not (1 <= len(raw_chords) <= 32):
        r.err(f"{sp}.chords", "must contain 1..32 bar entries")
    else:
        for bi, entry in enumerate(raw_chords):
            bp = f"{sp}.chords[{bi}]"
            if not isinstance(entry, str) or not entry.strip():
                r.err(bp, "must be one chord symbol or two separated by a space")
                continue
            parts = entry.split()
            if len(parts) > 2:
                r.err(bp, "at most two chord symbols per bar")
                continue
            bar_chords: list[Chord] = []
            for sym in parts:
                chord = _parse_chord_symbol(sym)
                if chord is None:
                    r.err(bp, f"invalid chord symbol {sym!r}")
                    continue
                if hdr.scale_pcs and chord.root_pc not in hdr.scale_pcs:
                    r.err(bp, f"chord root {chord.symbol} not in scale")
                bar_chords.append(chord)
            bars.append(bar_chords)
            tally.chord_events += sum(len(c.tones) for c in bar_chords)
            tally.last_chord_root_pc = bar_chords[-1].root_pc
    return bars


def _parse_note(
    np_: str,
    raw_note: Any,
    hdr: _Header,
    tally: _Tally,
    r: _Reasons,
) -> tuple[Note, Fraction] | None:
    """Return the parsed Note and the beats it contributes, or None."""
    if not isinstance(raw_note, dict):
        r.err(np_, "must be an object")
        return None
    pitch = raw_note.get("pitch")
    beats_raw = raw_note.get("beats")
    beats: Fraction | None = None
    if isinstance(beats_raw, (int, float)) and not isinstance(beats_raw, bool):
        beats = Fraction(str(beats_raw))
    contributed = Fraction(0)
    if beats is None or beats not in ALLOWED_BEATS:
        r.err(
            f"{np_}.beats",
            "must be one of 0.25 0.5 0.75 1 1.5 2 3 4",
        )
        beats = None
    else:
        contributed = beats
    midi: int | None = None
    if not isinstance(pitch, str):
        r.err(f"{np_}.pitch", "must be a pitch name or 'r'")
    elif pitch == "r":
        pass
    else:
        midi = parse_pitch(pitch)
        if midi is None:
            r.err(f"{np_}.pitch", f"invalid pitch name {pitch!r}")
        else:
            if hdr.vocal_low and not (hdr.vocal_low <= midi <= hdr.vocal_high):
                r.err(np_, f"pitch {pitch} outside vocal range")
            if hdr.scale_pcs and midi % 12 not in hdr.scale_pcs:
                r.err(np_, f"pitch {pitch} not in scale")
            tally.account_sung(midi, np_, r)
    return (
        Note(
            pitch=str(pitch),
            beats=beats or Fraction(0),
            midi=midi,
        ),
        contributed,
    )


def _validate_units(
    lp: str,
    units: list[str],
    notes: list[Note],
    language: Any,
    r: _Reasons,
) -> None:
    for ui, (unit, note) in enumerate(zip(units, notes, strict=False)):
        up = f"{lp}.units[{ui}]"
        if unit == "-":
            if note.pitch != "r":
                r.err(up, "rest unit '-' requires a rest note 'r'")
        elif note.pitch == "r":
            r.err(up, "rest note 'r' requires a '-' unit")
        if unit == "~" and note.midi is not None:
            idx = ui - 1
            while idx >= 0 and notes[idx].midi is None:
                idx -= 1
            if idx >= 0:
                prev = notes[idx].midi
                assert prev is not None and note.midi is not None
                if not (0 <= abs(note.midi - prev) <= 2):
                    r.err(
                        up,
                        f"'~' note {note.pitch} must equal or "
                        f"step from {notes[idx].pitch}",
                    )
        elif language == "ja" and unit not in ("~", "-"):
            if not (1 <= len(unit) <= 2):
                r.err(up, "ja unit must be 1..2 characters")


def _validate_units_match_text(
    lp: str,
    units: list[str],
    text: str,
    reading: str | None,
    language: Any,
    r: _Reasons,
) -> None:
    if units and text:
        joined = "".join(u for u in units if u not in ("~", "-"))
        if language == "en":
            norm = text.translate(EN_TEXT_STRIP).casefold()
            if joined.casefold() != norm:
                r.err(f"{lp}.units", "units do not match text")
        elif language == "ja":
            if reading is not None:
                norm = reading.translate(JA_TEXT_STRIP)
                if joined != norm:
                    r.err(
                        f"{lp}.units",
                        "units do not match reading",
                    )
            else:
                norm = text.translate(JA_TEXT_STRIP)
                if joined != norm:
                    r.err(f"{lp}.units", "units do not match text")


def _validate_line(
    lp: str,
    raw_line: Any,
    hdr: _Header,
    tally: _Tally,
    melody_from: Any,
    src_line: Line | None,
    r: _Reasons,
) -> tuple[Line, Fraction] | None:
    """Return the parsed Line and the beats it contributes, or None."""
    if not isinstance(raw_line, dict):
        r.err(lp, "must be an object")
        return None
    text = raw_line.get("text")
    if not isinstance(text, str) or not (1 <= len(text) <= 200):
        r.err(f"{lp}.text", "must be 1..200 characters")
        text = ""
    reading = raw_line.get("reading")
    if reading is not None:
        if not isinstance(reading, str) or not reading.strip():
            r.err(f"{lp}.reading", "must be a non-empty string")
            reading = None
        elif hdr.language != "ja":
            r.err(f"{lp}.reading", "reading is only for ja")
            reading = None
        elif not JA_READING_RE.match(reading):
            r.err(f"{lp}.reading", "must be kana")
            reading = None
    units = raw_line.get("units")
    if not isinstance(units, list) or not all(isinstance(u, str) for u in units):
        r.err(f"{lp}.units", "must be a list of strings")
        units = []
    raw_notes = raw_line.get("notes")
    notes: list[Note] = []
    line_beats = Fraction(0)
    if melody_from is not None:
        if "notes" in raw_line:
            r.err(
                f"{lp}.notes",
                "melody_from section must omit notes",
            )
        if src_line is not None:
            notes = list(src_line.notes)
            line_beats += sum(n.beats for n in notes)
            if len(units) != len(src_line.units):
                r.err(
                    f"{lp}.units",
                    f"units count {len(units)} != source {len(src_line.units)}",
                )
            elif [i for i, u in enumerate(units) if u == "-"] != [
                i for i, u in enumerate(src_line.units) if u == "-"
            ]:
                r.err(
                    f"{lp}.units",
                    "rest positions differ from source",
                )
        raw_notes = []
        for ni, note in enumerate(notes):
            if note.midi is None:
                continue
            tally.account_sung(note.midi, f"{lp}.notes[{ni}]", r)
    elif not isinstance(raw_notes, list):
        r.err(f"{lp}.notes", "must be a list")
        raw_notes = []
    elif len(raw_notes) != len(units):
        r.err(
            f"{lp}.notes",
            f"notes count {len(raw_notes)} != units count {len(units)}",
        )
    for ni, raw_note in enumerate(raw_notes):
        parsed = _parse_note(f"{lp}.notes[{ni}]", raw_note, hdr, tally, r)
        if parsed is None:
            continue
        note, note_beats = parsed
        line_beats += note_beats
        notes.append(note)
    _validate_units(lp, units, notes, hdr.language, r)
    if len(notes) >= 4 and len({n.beats for n in notes}) < 2:
        r.err(
            f"{lp}.notes",
            "line needs at least two different note lengths",
        )
    _validate_units_match_text(lp, units, text, reading, hdr.language, r)
    return Line(text=text, units=units, notes=notes, reading=reading), line_beats


def _validate_downbeats(
    sp: str,
    bars: list[list[Chord]],
    lines: list[Line],
    beats_per_bar: Fraction,
    r: _Reasons,
) -> None:
    # melody rule 3: notes starting on beat 1 of a bar must be a
    # chord tone of that bar's first chord
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
                r.err(
                    f"{sp}.lines[{li}].notes[{ni}]",
                    f"downbeat pitch {note.pitch} is not a chord "
                    f"tone of {first.symbol}",
                )


def _validate_section(
    si: int,
    raw_sec: Any,
    hdr: _Header,
    tally: _Tally,
    earlier: dict[str, Section],
    seen_names: set[str],
    copier_names: set[str],
    r: _Reasons,
) -> Section | None:
    sp = f"sections[{si}]"
    if not isinstance(raw_sec, dict):
        r.err(sp, "must be an object")
        return None
    name = raw_sec.get("name")
    if not isinstance(name, str) or not SECTION_NAME_RE.match(name):
        r.err(f"{sp}.name", "must match [A-Za-z0-9 _-]{1,32}")
        name = f"section{si}"
    elif name in seen_names:
        r.err(f"{sp}.name", f"duplicate section name {name!r}")
    else:
        seen_names.add(name)
    kind = raw_sec.get("kind")
    if kind not in SECTION_KINDS:
        r.err(f"{sp}.kind", f"must be one of {sorted(SECTION_KINDS)}")
    first_word = name.split()[0].lower() if name.split() else ""
    implied = SECTION_NAME_KIND.get(first_word)
    if implied is not None and kind in SECTION_KINDS and kind != implied:
        r.err(f"{sp}.kind", f'name "{name}" implies kind {implied}')

    melody_from, src = _resolve_melody_from(sp, raw_sec, hdr, earlier, copier_names, r)
    bars = _validate_section_chords(sp, raw_sec, melody_from, src, hdr, tally, r)

    raw_lines = raw_sec.get("lines")
    lines: list[Line] = []
    section_beats = Fraction(0)
    if not isinstance(raw_lines, list):
        r.err(f"{sp}.lines", "must be a list")
    else:
        if kind not in ("intro", "outro") and len(raw_lines) < 1:
            r.err(
                f"{sp}.lines",
                "non-intro/outro sections need at least one line",
            )
        if kind in ("intro", "outro"):
            pass
        else:
            tally.lyric_line_count += len(raw_lines)
        if melody_from is not None and src is not None:
            if len(raw_lines) != len(src.lines):
                r.err(
                    f"{sp}.lines",
                    f"line count {len(raw_lines)} != source {len(src.lines)}",
                )
        for li, raw_line in enumerate(raw_lines):
            lp = f"{sp}.lines[{li}]"
            src_line = (
                src.lines[li] if src is not None and li < len(src.lines) else None
            )
            parsed = _validate_line(lp, raw_line, hdr, tally, melody_from, src_line, r)
            if parsed is None:
                continue
            line, line_beats = parsed
            section_beats += line_beats
            lines.append(line)
        if bars and hdr.beats_per_bar:
            _validate_downbeats(sp, bars, lines, hdr.beats_per_bar, r)
    if bars and lines and section_beats != hdr.beats_per_bar * len(bars):
        r.err(
            sp,
            f"section beats {float(section_beats)} != "
            f"bars*beats {float(hdr.beats_per_bar * len(bars))}",
        )
    section = Section(name=name, kind=kind or "", chords=bars, lines=lines)
    earlier[name] = section
    if melody_from is not None:
        copier_names.add(name)
    return section


def _validate_song_totals(
    hdr: _Header,
    sections: list[Section],
    tally: _Tally,
    r: _Reasons,
) -> None:
    if tally.sung_notes < 16:
        r.err("sections", "at least 16 sung (non-rest) notes required")
    if tally.lyric_line_count < 4:
        r.err("sections", "at least 4 lines required outside intro/outro")
    total_events = (
        tally.sung_notes
        + sum(
            len(line.notes) - sum(1 for n in line.notes if n.midi is not None)
            for s in sections
            for line in s.lines
        )
        + tally.chord_events
    )
    if total_events > MAX_EVENTS:
        r.err("sections", f"total events {total_events} exceed {MAX_EVENTS}")

    if (
        sections
        and tally.last_chord_root_pc is not None
        and tally.last_chord_root_pc != hdr.tonic_pc
    ):
        r.err(
            f"sections[{len(sections) - 1}].chords",
            "final chord root != tonic",
        )

    if tally.last_sung_midi is not None and hdr.scale_pcs:
        degrees = (
            sorted(SCALE_INTERVALS[hdr.key_mode])
            if hdr.key_mode in SCALE_INTERVALS
            else []
        )
        cadence = (
            {(hdr.tonic_pc + degrees[i]) % 12 for i in (0, 2, 4)}
            if len(degrees) >= 5
            else set()
        )
        if cadence and tally.last_sung_midi % 12 not in cadence:
            r.err("sections", "final pitch not degree 1/3/5")

    if hdr.rationale:
        corpus = [WS_RUN_RE.sub(" ", line.text) for s in sections for line in s.lines]
        corpus.append(WS_RUN_RE.sub(" ", hdr.title))
        for m in RATIONALE_QUOTE_RE.finditer(hdr.rationale):
            quote = WS_RUN_RE.sub(" ", m.group(1)).strip()
            if quote and not any(quote in c for c in corpus):
                r.err(
                    "rationale",
                    f'quoted lyric "{quote}" does not appear in the lyrics',
                )


def validate_proposal(data: object) -> Song:
    """Validate a parsed JSON proposal, collecting every reason found."""
    if not isinstance(data, dict):
        raise ProposalError(["$: proposal must be a JSON object"])

    r = _Reasons()
    hdr = _validate_header(data, r)

    raw_sections = data.get("sections")
    sections: list[Section] = []
    tally = _Tally()

    if not isinstance(raw_sections, list) or not (1 <= len(raw_sections) <= 12):
        r.err("sections", "must contain 1..12 sections")
    else:
        seen_names: set[str] = set()
        earlier: dict[str, Section] = {}
        copier_names: set[str] = set()
        for si, raw_sec in enumerate(raw_sections):
            section = _validate_section(
                si, raw_sec, hdr, tally, earlier, seen_names, copier_names, r
            )
            if section is not None:
                sections.append(section)

    _validate_song_totals(hdr, sections, tally, r)

    if r.reasons:
        raise ProposalError(r.reasons)

    assert hdr.language in ("ja", "en")
    return Song(
        title=hdr.title,
        mode=str(hdr.mode),
        language=hdr.language,
        sources=list(hdr.sources),
        rationale=hdr.rationale,
        originality=dict(hdr.originality),
        tonic=str(hdr.tonic),
        tonic_pc=hdr.tonic_pc,
        key_mode=str(hdr.key_mode),
        scale_pcs=hdr.scale_pcs,
        meter=str(hdr.meter),
        beats_per_bar=hdr.beats_per_bar,
        bpm=hdr.bpm,
        melody_program=hdr.melody_program,
        accompaniment_program=hdr.accompaniment_program,
        vocal_low=hdr.vocal_low,
        vocal_high=hdr.vocal_high,
        sections=sections,
        raw=data,
    )
