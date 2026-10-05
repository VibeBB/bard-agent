from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import xml.sax.saxutils as _xml
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from song_model import (  # noqa: E402
    EN_TEXT_STRIP,
    Chord,
    Line,
    Note,
    ProposalError,
    Section,
    Song,
)
from song_validate import SCHEMA_VERSION  # noqa: E402

__all__ = [
    "PROVENANCE_KIND",
    "PPQ",
    "_CLASH_OFFSETS",
    "_melody_events",
    "_chord_events",
    "_melody_pcs_during",
    "_clashes",
    "_n_chord_voices",
    "_accompaniment_slots",
    "ABC_PC_FLAT",
    "ABC_PC_SHARP",
    "FLAT_TONICS",
    "_abc_key",
    "_abc_note_name",
    "_abc_len",
    "render_abc",
    "_w_line",
    "_vlq",
    "_midi_track",
    "render_midi",
    "MML_PC_SHARP",
    "MML_PC_FLAT",
    "MML_LEN",
    "_mml_len",
    "_MmlVoice",
    "_mml_pc",
    "render_mml",
    "render_markdown",
    "render_provenance",
    "render_contour_svg",
]

PROVENANCE_KIND = "bard_song_provenance"

PPQ = 480


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


_CLASH_OFFSETS = (1, 11)


def _melody_pcs_during(song: Song, start: Fraction, end: Fraction) -> set[int]:
    """Melody pitch classes sounding at any point of [start, end)."""
    pcs: set[int] = set()
    for n_start, note, _sec, _line in _melody_events(song):
        if note.midi is None:
            continue
        if n_start < end and n_start + note.beats > start:
            pcs.add(note.midi % 12)
    return pcs


def _clashes(pc: int, melody_pcs: set[int]) -> bool:
    return any((m - pc) % 12 in _CLASH_OFFSETS for m in melody_pcs)


def _n_chord_voices(song: Song) -> int:
    return max(
        3,
        max(
            (len(c.tones) for s in song.sections for bar in s.chords for c in bar),
            default=3,
        ),
    )


def _accompaniment_slots(
    song: Song,
) -> tuple[
    list[list[int | None]],
    list[dict[str, Any]],
]:
    """Per chord event, the pitch class each voice slot sounds (None = rest).

    Voice 0 is the bass; the rest are upper voices. When a chord tone would
    clash with the sounding melody (minor-9th / major-7th pitch-class
    offsets) or duplicate an already-assigned tone, the slot is re-voiced
    deterministically: substitute the first non-clashing, not-yet-used
    chord tone; drop the voice when no substitute works.
    """
    n_voices = _n_chord_voices(song)
    slots: list[list[int | None]] = []
    adjustments: list[dict[str, Any]] = []
    for start, dur, chord, sec in _chord_events(song):
        melody_pcs = _melody_pcs_during(song, start, start + dur)
        defaults: list[int | None] = [chord.root_pc, *chord.tones[1:]]
        defaults += [None] * (n_voices - len(defaults))
        event: list[int | None] = []
        used: set[int] = set()
        for vi, pc in enumerate(defaults):
            if pc is not None and (pc in used or _clashes(pc, melody_pcs)):
                substitute = next(
                    (
                        cand
                        for cand in chord.tones
                        if cand not in used and not _clashes(cand, melody_pcs)
                    ),
                    None,
                )
                adj: dict[str, Any] = {
                    "section": sec.name,
                    "beat": float(start),
                    "chord": chord.symbol,
                    "voice": vi + 1,
                    "from_pc": pc,
                }
                if substitute is None:
                    adj["action"] = "dropped"
                else:
                    adj["action"] = "substituted"
                    adj["to_pc"] = substitute
                adjustments.append(adj)
                pc = substitute
            event.append(pc)
            if pc is not None:
                used.add(pc)
        slots.append(event)
    return slots, adjustments


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
        # The default lyric spacing (14pt) lets adjacent word syllables touch
        # under dense rhythms; 20pt keeps word boundaries legible.
        "%%vocalspace 20pt",
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
    slots, _adjustments = _accompaniment_slots(song)
    for (start, dur, chord, _sec), event_slots in zip(
        _chord_events(song), slots, strict=True
    ):
        on = int(start * PPQ)
        off = int((start + dur) * PPQ)
        pitches = [
            (48 if vi == 0 else 60) + pc
            for vi, pc in enumerate(event_slots[: len(chord.tones)])
            if pc is not None
        ]
        for p in pitches:
            accomp.append((on, bytes([0x91, p, 60])))
        for p in pitches:
            accomp.append((off, bytes([0x81, p, 0])))
    track2 = _midi_track(accomp)

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 3, PPQ)
    return header + track0 + track1 + track2


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

    n_chord_voices = _n_chord_voices(song)
    slots, _adjustments = _accompaniment_slots(song)
    voice_events: list[list[tuple[Fraction, str | None, int, Fraction]]] = [
        [] for _ in range(n_chord_voices)
    ]
    for (start, dur, _chord, _sec), event_slots in zip(
        _chord_events(song), slots, strict=True
    ):
        for vi in range(n_chord_voices):
            pc = event_slots[vi] if vi < len(event_slots) else None
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


CONTOUR_PX_PER_BEAT = 36
CONTOUR_BARS_PER_ROW = 8
CONTOUR_PX_PER_SEMITONE = 14
_CONTOUR_PAD_LEFT = 90
_CONTOUR_ROW_TOP = 26
_CONTOUR_LYRIC_H = 14
_CONTOUR_ROW_GAP = 30
_CONTOUR_HEADER_H = 40


def _esc(text: object) -> str:
    return _xml.escape(str(text), {'"': "&quot;"})


def render_contour_svg(song: Song) -> str:
    """Deterministic piano-roll SVG of the melody for vision review.

    x = beats (fixed px per beat, wrapped into rows of CONTOUR_BARS_PER_ROW
    bars), y = MIDI pitch. Every sounded note is a rectangle with its lyric
    unit under it; bar lines, section boundaries, chord symbols and the
    vocal range bounds are drawn in. No timestamps — the same proposal
    produces byte-identical SVG.
    """
    beats_per_bar = song.beats_per_bar
    events: list[tuple[Fraction, Note, Section, str]] = []
    pos = Fraction(0)
    for sec in song.sections:
        sec_start = pos
        for line in sec.lines:
            for unit, note in zip(line.units, line.notes, strict=True):
                events.append((pos, note, sec, unit))
                pos += note.beats
        pos = sec_start + beats_per_bar * len(sec.chords)
    total_beats = pos
    row_beats = beats_per_bar * CONTOUR_BARS_PER_ROW
    n_rows = max(1, math.ceil(total_beats / row_beats))
    sounded = [note.midi for _s, note, _sec, _u in events if note.midi is not None]
    low = min([song.vocal_low, *sounded], default=song.vocal_low)
    high = max([song.vocal_high, *sounded], default=song.vocal_high)
    pitch_h = (high - low + 1) * CONTOUR_PX_PER_SEMITONE
    row_inner = pitch_h + _CONTOUR_ROW_TOP + _CONTOUR_LYRIC_H
    row_h = row_inner + _CONTOUR_ROW_GAP
    width = int(row_beats * CONTOUR_PX_PER_BEAT) + _CONTOUR_PAD_LEFT + 10
    height = _CONTOUR_HEADER_H + n_rows * row_h + 8

    def row_of(beat: Fraction) -> int:
        return int(beat // row_beats)

    def x_of(beat: Fraction) -> float:
        offset = beat - row_of(beat) * row_beats
        return _CONTOUR_PAD_LEFT + float(offset) * CONTOUR_PX_PER_BEAT

    def y_of(midi: int, row: int) -> float:
        top = _CONTOUR_HEADER_H + row * row_h + _CONTOUR_ROW_TOP
        return top + (high - midi) * CONTOUR_PX_PER_SEMITONE

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}" font-family="sans-serif">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
        f'<text x="10" y="24" font-size="16">{_esc(song.title)} — '
        f"{_esc(song.mode)} · {_esc(song.tonic)} {_esc(song.key_mode)} · "
        f"{_esc(song.meter)} · {song.bpm} bpm</text>",
    ]
    for row in range(n_rows):
        row_top = _CONTOUR_HEADER_H + row * row_h + _CONTOUR_ROW_TOP
        lyric_y = row_top + pitch_h + _CONTOUR_LYRIC_H - 2
        # vocal range bounds (dashed)
        for bound, name in (
            (song.vocal_low, "vocal low"),
            (song.vocal_high, "vocal high"),
        ):
            y = y_of(bound, row) + CONTOUR_PX_PER_SEMITONE / 2
            parts.append(
                f'<line x1="{_CONTOUR_PAD_LEFT}" y1="{y:.1f}" '
                f'x2="{width - 10}" y2="{y:.1f}" stroke="#c00" '
                f'stroke-dasharray="4 3" stroke-width="1"/>'
            )
            if row == 0:
                parts.append(
                    f'<text x="4" y="{y + 3:.1f}" font-size="9" fill="#c00">'
                    f"{_esc(name)}</text>"
                )
        # bar lines
        first_bar = row * CONTOUR_BARS_PER_ROW
        total_bars = int(math.ceil(total_beats / beats_per_bar))
        for bar in range(
            first_bar, min(first_bar + CONTOUR_BARS_PER_ROW + 1, total_bars + 1)
        ):
            x = (
                _CONTOUR_PAD_LEFT
                + (bar - first_bar) * float(beats_per_bar) * CONTOUR_PX_PER_BEAT
            )
            if x > width - 10:
                continue
            parts.append(
                f'<line x1="{x:.1f}" y1="{row_top}" x2="{x:.1f}" '
                f'y2="{row_top + pitch_h}" stroke="#bbb" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{x + 2:.1f}" y="{row_top - 4}" font-size="8" '
                f'fill="#999">{bar + 1}</text>'
            )
        # chord symbols at each chord change inside this row
        for start, _dur, chord, _sec in _chord_events(song):
            if row_of(start) != row:
                continue
            x = x_of(start)
            parts.append(
                f'<text x="{x + 1:.1f}" y="{row_top - 14}" font-size="10" '
                f'fill="#06c">{_esc(chord.symbol)}</text>'
            )
        parts.append(
            f'<line x1="{_CONTOUR_PAD_LEFT}" y1="{lyric_y + 3}" '
            f'x2="{width - 10}" y2="{lyric_y + 3}" stroke="#eee"/>'
        )
    # section boundaries
    pos = Fraction(0)
    for sec in song.sections:
        row = row_of(pos)
        x = x_of(pos)
        row_top = _CONTOUR_HEADER_H + row * row_h + _CONTOUR_ROW_TOP
        parts.append(
            f'<line x1="{x:.1f}" y1="{row_top - 18}" x2="{x:.1f}" '
            f'y2="{row_top + pitch_h}" stroke="#333" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x + 3:.1f}" y="{row_top - 20}" font-size="10" '
            f'fill="#333" font-weight="bold">{_esc(sec.name)}</text>'
        )
        pos += beats_per_bar * len(sec.chords)
    # melody notes
    for start, note, _sec, unit in events:
        if note.midi is None:
            continue
        row = row_of(start)
        x = x_of(start)
        y = y_of(note.midi, row)
        w = max(2.0, float(note.beats) * CONTOUR_PX_PER_BEAT - 1)
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
            f'height="{CONTOUR_PX_PER_SEMITONE - 1}" fill="#336" '
            f'fill-opacity="0.85"/>'
        )
        lyric_y = (
            _CONTOUR_HEADER_H
            + row * row_h
            + _CONTOUR_ROW_TOP
            + pitch_h
            + _CONTOUR_LYRIC_H
            - 2
        )
        label = "" if unit in ("-", "~") else unit
        if label:
            parts.append(
                f'<text x="{x + 1:.1f}" y="{lyric_y}" font-size="9" '
                f'fill="#444">{_esc(label)}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


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
        "schema_version": song.raw.get("schema_version", SCHEMA_VERSION),
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
