from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

__all__ = [
    "TONICS",
    "TONIC_PC",
    "CHORD_QUALITIES",
    "PITCH_RE",
    "CHORD_RE",
    "LETTER_PC",
    "EN_TEXT_STRIP",
    "JA_TEXT_STRIP",
    "JA_READING_RE",
    "ProposalError",
    "Note",
    "Chord",
    "Line",
    "Section",
    "Song",
    "parse_pitch",
    "_parse_chord_symbol",
]

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

PITCH_RE = re.compile(r"^([a-g])(#|b)?([0-9])$")

CHORD_RE = re.compile(r"^([A-G](?:#|b)?)(dim|maj7|m7|sus4|sus2|m|7)?$")

LETTER_PC = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

EN_TEXT_STRIP = str.maketrans("", "", " \t\r\n,.;:!?'\"()-—")

JA_TEXT_STRIP = str.maketrans("", "", " \t\r\n、。！？「」・…—")

JA_READING_RE = re.compile(r"^[ぁ-ゖァ-ヶー \t\r\n、。！？「」・…—]+$")


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
