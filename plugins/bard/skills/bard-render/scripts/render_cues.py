"""Validate a bard_cue_set JSON and render product sound cues (earcons).

A cue set describes the short sounds a product plays — startup, completion,
warning and similar — as monophonic note sequences. Every output is derived
deterministically from the cue set, reusing the MIDI and MML primitives of
``render_song.py``. Implements docs/cue-set-contract.md (schema 0.1).

Python 3.12+, standard library only.

Outputs (per cue set directory):

- ``cue-<id>.mid``  SMF format 1, 480 ticks per beat, one note track
- ``cue-<id>.mml``  bard-mml 0.1, one ``@melody`` voice
- ``cues.json``     bard_cue_manifest: firmware-ready tone tables and file map
- ``cues.md``       one-page preview for the Agent Canvas Markdown panel
- ``cues.timeline.svg``  one-row-per-cue timeline for vision review
- ``cues.provenance.json``  hashes, sources, originality, script sha256

Usage:
    render_cues.py --cues cues/<slug>/cues.proposal.json --out-dir cues/<slug>
                   [--check] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import struct
import sys
import xml.sax.saxutils as _xml
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

# render_song.py lives next to this script but is not an installed package.
_RENDER_PATH = Path(__file__).resolve().with_name("render_song.py")
_spec = importlib.util.spec_from_file_location("render_song", _RENDER_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load render_song module from {_RENDER_PATH}")
render_song = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("render_song", render_song)
_spec.loader.exec_module(render_song)

CUE_SET_KIND = "bard_cue_set"
MANIFEST_KIND = "bard_cue_manifest"
PROVENANCE_KIND = "bard_cue_provenance"
SCHEMA_VERSION = "0.1"
PPQ = 480

PURPOSES = {
    "startup",
    "shutdown",
    "completion",
    "success",
    "warning",
    "error",
    "notification",
    "confirm",
    "cancel",
    "pairing",
}
LOOPABLE_PURPOSES = {"warning", "error"}
# JIS S 0013:2011 (the national text of ISO 24500:2010), clause 4.2: a warning
# keeps sounding while its cause lasts; clause 4.3: fundamentals should not
# exceed 2.5 kHz because age-related hearing loss hits high frequencies first.
ACCESSIBILITY_REFERENCE = "JIS S 0013:2011 / ISO 24500:2010"
MUST_LOOP_PURPOSES = {"warning"}
MAX_FUNDAMENTAL_HZ = 2500.0
WAIVABLE_CHECKS = {"max_fundamental_hz"}
# ISO 24501:2010 covers listening distances up to about 4 m.
MAX_LISTENING_M = 4.0
MAX_MS: dict[str, int] = {"confirm": 300, "cancel": 300}
DEFAULT_MAX_MS = 3000
MIN_MS = 50
SOURCE_KINDS = {
    "conversation_summary",
    "agent_message",
    "git_log",
    "file",
    "user_request",
    "ux_request",
}
DEVICES: dict[str, tuple[str, str]] = {
    "piezo": ("c5", "c8"),
    "speaker": ("c3", "c8"),
}
ALLOWED_BEATS = {
    Fraction(1, 8),
    Fraction(1, 4),
    Fraction(3, 8),
    Fraction(1, 2),
    Fraction(3, 4),
    Fraction(1),
    Fraction(3, 2),
    Fraction(2),
}
MML_LEN = {
    Fraction(2): "2",
    Fraction(3, 2): "4.",
    Fraction(1): "4",
    Fraction(3, 4): "8.",
    Fraction(1, 2): "8",
    Fraction(3, 8): "16.",
    Fraction(1, 4): "16",
    Fraction(1, 8): "32",
}
CUE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
REF_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_CUES = 16
MAX_NOTES = 16
TOP_KEYS = {
    "artifact_kind",
    "schema_version",
    "product",
    "device",
    "sources",
    "rationale",
    "originality",
    "cues",
    "transducer",
    "listening",
    "accessibility_waivers",
}
TRANSDUCER_KEYS = {"part", "distance_cm", "response"}
LISTENING_KEYS = {"distance_m", "ambient_db", "min_margin_db", "rationale"}
CUE_KEYS = {"id", "purpose", "ux_feedback", "bpm", "program", "loop", "notes"}
ORIGINALITY_KEYS = ("original_melody", "no_trademark_sound_imitation")

ProposalError = render_song.ProposalError


@dataclass(frozen=True)
class CueNote:
    midi: int | None
    beats: Fraction


@dataclass(frozen=True)
class Cue:
    id: str
    purpose: str
    ux_feedback: str | None
    bpm: int
    program: int
    loop: bool
    notes: tuple[CueNote, ...]

    @property
    def total_beats(self) -> Fraction:
        return sum((n.beats for n in self.notes), Fraction(0))

    def ms(self, beats: Fraction) -> Fraction:
        return beats * 60000 / self.bpm


@dataclass(frozen=True)
class Transducer:
    part: str
    distance_cm: float
    response: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Listening:
    distance_m: float
    ambient_db: float
    min_margin_db: float
    rationale: str


@dataclass(frozen=True)
class CueSet:
    product: str
    device: str
    sources: list[Any]
    rationale: str
    originality: dict[str, Any]
    cues: tuple[Cue, ...]
    transducer: Transducer | None = None
    listening: Listening | None = None
    waivers: tuple[tuple[str, str], ...] = ()


def _ms_int(value: Fraction) -> int:
    return int(value + Fraction(1, 2))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: object, lo: int, hi: int) -> bool:
    return isinstance(value, str) and lo <= len(value) <= hi and bool(value.strip())


def _number(value: object, lo: float, hi: float) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and lo <= value <= hi
    )


def _validate_transducer(raw: object, reasons: list[str]) -> Transducer | None:
    if not isinstance(raw, dict):
        reasons.append("transducer: object with part, distance_cm, response")
        return None
    t = cast(dict[str, Any], raw)
    before = len(reasons)
    unknown = set(t) - TRANSDUCER_KEYS
    if unknown:
        reasons.append(f"transducer: unknown keys {sorted(unknown)}")
    if not _text(t.get("part"), 1, 120):
        reasons.append("transducer.part: 1..120 characters")
    distance = t.get("distance_cm")
    if not _number(distance, 1, 100):
        reasons.append("transducer.distance_cm: 1..100 (datasheet measuring distance)")
    raw_response = t.get("response")
    points: list[tuple[float, float]] = []
    if not isinstance(raw_response, list) or not 2 <= len(raw_response) <= 32:
        reasons.append("transducer.response: 2..32 {hz, spl_db} points")
    else:
        for i, rp in enumerate(cast(list[object], raw_response)):
            where = f"transducer.response[{i}]"
            if not isinstance(rp, dict) or set(cast(dict[str, Any], rp)) != {
                "hz",
                "spl_db",
            }:
                reasons.append(f"{where}: object with exactly hz and spl_db")
                continue
            point = cast(dict[str, Any], rp)
            if not _number(point["hz"], 20, 20000):
                reasons.append(f"{where}.hz: 20..20000")
            elif not _number(point["spl_db"], 0, 140):
                reasons.append(f"{where}.spl_db: 0..140")
            elif points and point["hz"] <= points[-1][0]:
                reasons.append(f"{where}.hz: frequencies must strictly increase")
            else:
                points.append((float(point["hz"]), float(point["spl_db"])))
    if len(reasons) > before:
        return None
    return Transducer(
        part=cast(str, t["part"]),
        distance_cm=float(cast(float, distance)),
        response=tuple(points),
    )


def _validate_listening(raw: object, reasons: list[str]) -> Listening | None:
    if not isinstance(raw, dict):
        reasons.append(f"listening: object with {sorted(LISTENING_KEYS)}")
        return None
    lst = cast(dict[str, Any], raw)
    before = len(reasons)
    if set(lst) != LISTENING_KEYS:
        reasons.append(f"listening: exactly {sorted(LISTENING_KEYS)}")
        return None
    if not _number(lst["distance_m"], 0.1, MAX_LISTENING_M):
        reasons.append(f"listening.distance_m: 0.1..{MAX_LISTENING_M}")
    if not _number(lst["ambient_db"], 0, 120):
        reasons.append("listening.ambient_db: 0..120 (A-weighted interfering sound)")
    if not _number(lst["min_margin_db"], 0, 40):
        reasons.append("listening.min_margin_db: 0..40")
    if not _text(lst["rationale"], 20, 400):
        reasons.append(
            "listening.rationale: 20..400 characters (where the numbers come from)"
        )
    if len(reasons) > before:
        return None
    return Listening(
        distance_m=float(lst["distance_m"]),
        ambient_db=float(lst["ambient_db"]),
        min_margin_db=float(lst["min_margin_db"]),
        rationale=cast(str, lst["rationale"]),
    )


def _validate_waivers(raw: object, reasons: list[str]) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        reasons.append("accessibility_waivers: list of {check, reason}")
        return ()
    waivers: list[tuple[str, str]] = []
    for i, rw in enumerate(cast(list[object], raw)):
        where = f"accessibility_waivers[{i}]"
        if not isinstance(rw, dict) or set(cast(dict[str, Any], rw)) != {
            "check",
            "reason",
        }:
            reasons.append(f"{where}: object with exactly check and reason")
            continue
        w = cast(dict[str, Any], rw)
        if w["check"] not in WAIVABLE_CHECKS:
            reasons.append(f"{where}.check: one of {sorted(WAIVABLE_CHECKS)}")
        elif not _text(w["reason"], 20, 400):
            reasons.append(f"{where}.reason: 20..400 characters")
        elif any(w["check"] == c for c, _ in waivers):
            reasons.append(f"{where}: duplicate waiver for {w['check']}")
        else:
            waivers.append((w["check"], w["reason"]))
    return tuple(waivers)


def spl_at(transducer: Transducer, hz: float) -> float | None:
    """Datasheet SPL at ``hz``, interpolated linearly over log frequency."""
    points = transducer.response
    if not points[0][0] <= hz <= points[-1][0]:
        return None
    for (h0, s0), (h1, s1) in zip(points, points[1:], strict=False):
        if h0 <= hz <= h1:
            t = (math.log(hz) - math.log(h0)) / (math.log(h1) - math.log(h0))
            return s0 + t * (s1 - s0)
    return None  # pragma: no cover - the range check above makes this unreachable


def listener_spl(
    transducer: Transducer, listening: Listening, hz: float
) -> float | None:
    """Free-field inverse-square estimate at the listening distance."""
    at_source = spl_at(transducer, hz)
    if at_source is None:
        return None
    ratio = listening.distance_m * 100.0 / transducer.distance_cm
    return at_source - 20.0 * math.log10(ratio)


def _check_accessibility(
    cues: list[Cue],
    transducer: Transducer | None,
    listening: Listening | None,
    waivers: tuple[tuple[str, str], ...],
    reasons: list[str],
) -> None:
    waived = {check for check, _ in waivers}
    above = False
    for cue in cues:
        if cue.purpose in MUST_LOOP_PURPOSES and not cue.loop:
            reasons.append(
                f"cues: {cue.id} is a {cue.purpose} and must loop while its "
                "cause lasts "
                f"({ACCESSIBILITY_REFERENCE} 4.2)"
            )
        if cue.loop and all(n.midi is not None for n in cue.notes):
            reasons.append(
                f"cues: {cue.id} loops without a rest; a repeating signal needs an "
                "ON/OFF pattern so it reads as a signal, not a drone"
            )
        for note in cue.notes:
            if note.midi is None:
                continue
            hz = _freq_hz(note.midi)
            if hz > MAX_FUNDAMENTAL_HZ:
                above = True
                if "max_fundamental_hz" not in waived:
                    reasons.append(
                        f"cues: {cue.id} plays {hz} Hz above "
                        f"{MAX_FUNDAMENTAL_HZ:.0f} Hz, "
                        "hard to hear with age-related hearing loss "
                        f"({ACCESSIBILITY_REFERENCE} 4.3); "
                        "lower it or add a reasoned waiver"
                    )
            if transducer is None or listening is None:
                continue
            level = listener_spl(transducer, listening, hz)
            if level is None:
                reasons.append(
                    f"cues: {cue.id} plays {hz} Hz outside the declared "
                    "transducer response"
                )
            elif level + 1e-9 < listening.ambient_db + listening.min_margin_db:
                reasons.append(
                    f"cues: {cue.id} at {hz} Hz reaches {level:.1f} dB at "
                    f"{listening.distance_m} m, below ambient "
                    f"{listening.ambient_db} dB "
                    f"+ margin {listening.min_margin_db} dB"
                )
    if "max_fundamental_hz" in waived and not above:
        reasons.append(
            "accessibility_waivers: max_fundamental_hz is waived but no cue exceeds "
            f"{MAX_FUNDAMENTAL_HZ:.0f} Hz; remove the stale waiver"
        )


def _validate_sources(data: dict[str, Any], reasons: list[str]) -> list[Any]:
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        reasons.append("sources: at least one entry required")
        return []
    for i, src in enumerate(cast(list[object], sources)):
        if not isinstance(src, dict):
            reasons.append(f"sources[{i}]: must be an object")
            continue
        s = cast(dict[str, Any], src)
        unknown = set(s) - {"kind", "ref", "sha256"}
        if unknown:
            reasons.append(f"sources[{i}]: unknown keys {sorted(unknown)}")
        if s.get("kind") not in SOURCE_KINDS:
            reasons.append(f"sources[{i}].kind: one of {sorted(SOURCE_KINDS)}")
        if not _text(s.get("ref"), 1, 200):
            reasons.append(f"sources[{i}].ref: 1..200 characters")
        sha = s.get("sha256")
        if sha is not None and not (
            isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)
        ):
            reasons.append(f"sources[{i}].sha256: 64 lowercase hex digits")
    return cast(list[Any], sources)


def _validate_note(
    raw: object, where: str, low: int, high: int, reasons: list[str]
) -> CueNote | None:
    if not isinstance(raw, dict):
        reasons.append(f"{where}: must be an object")
        return None
    n = cast(dict[str, Any], raw)
    unknown = set(n) - {"pitch", "beats"}
    if unknown:
        reasons.append(f"{where}: unknown keys {sorted(unknown)}")
    beats_raw = n.get("beats")
    beats: Fraction | None = None
    if isinstance(beats_raw, int | float) and not isinstance(beats_raw, bool):
        candidate = Fraction(beats_raw).limit_denominator(64)
        if candidate in ALLOWED_BEATS:
            beats = candidate
    if beats is None:
        allowed = ", ".join(str(float(b)) for b in sorted(ALLOWED_BEATS))
        reasons.append(f"{where}.beats: one of {allowed}")
    pitch = n.get("pitch")
    midi: int | None = None
    if pitch != "r":
        midi = render_song.parse_pitch(pitch) if isinstance(pitch, str) else None
        if midi is None:
            reasons.append(f"{where}.pitch: note name like c6 or r")
        elif not low <= midi <= high:
            reasons.append(f"{where}.pitch: {pitch} outside the device range")
    if beats is None or (pitch != "r" and midi is None):
        return None
    return CueNote(midi=midi, beats=beats)


def _validate_cue(
    raw: object, i: int, low: int, high: int, reasons: list[str]
) -> Cue | None:
    where = f"cues[{i}]"
    if not isinstance(raw, dict):
        reasons.append(f"{where}: must be an object")
        return None
    c = cast(dict[str, Any], raw)
    before = len(reasons)
    unknown = set(c) - CUE_KEYS
    if unknown:
        reasons.append(f"{where}: unknown keys {sorted(unknown)}")
    cue_id = c.get("id")
    if not (isinstance(cue_id, str) and CUE_ID_RE.fullmatch(cue_id)):
        reasons.append(f"{where}.id: [a-z][a-z0-9_]{{0,31}}")
        cue_id = f"#{i}"
    purpose = c.get("purpose")
    if purpose not in PURPOSES:
        reasons.append(f"{where}.purpose: one of {sorted(PURPOSES)}")
        purpose = ""
    ux_feedback = c.get("ux_feedback")
    if ux_feedback is not None and not (
        isinstance(ux_feedback, str) and REF_ID_RE.fullmatch(ux_feedback)
    ):
        reasons.append(f"{where}.ux_feedback: 1..64 of [A-Za-z0-9_.-]")
    bpm = c.get("bpm")
    if not (_is_int(bpm) and 60 <= cast(int, bpm) <= 240):
        reasons.append(f"{where}.bpm: integer in 60..240")
        bpm = 120
    program = c.get("program", 80)
    if not (_is_int(program) and 0 <= cast(int, program) <= 127):
        reasons.append(f"{where}.program: General MIDI program 0..127")
        program = 80
    loop = c.get("loop", False)
    if not isinstance(loop, bool):
        reasons.append(f"{where}.loop: boolean")
        loop = False
    elif loop and purpose not in LOOPABLE_PURPOSES:
        reasons.append(f"{where}.loop: only {sorted(LOOPABLE_PURPOSES)} cues may loop")
    raw_notes = c.get("notes")
    notes: list[CueNote] = []
    if not isinstance(raw_notes, list) or not 1 <= len(raw_notes) <= MAX_NOTES:
        reasons.append(f"{where}.notes: 1..{MAX_NOTES} entries")
    else:
        for j, rn in enumerate(cast(list[object], raw_notes)):
            note = _validate_note(rn, f"{where}.notes[{j}]", low, high, reasons)
            if note is not None:
                notes.append(note)
    if len(reasons) > before:
        return None
    if notes[0].midi is None or notes[-1].midi is None:
        reasons.append(f"{where}.notes: must start and end with a sounded note")
    cue = Cue(
        id=cue_id,
        purpose=purpose,
        ux_feedback=cast(str | None, ux_feedback),
        bpm=cast(int, bpm),
        program=cast(int, program),
        loop=loop,
        notes=tuple(notes),
    )
    total_ms = cue.ms(cue.total_beats)
    max_ms = MAX_MS.get(cue.purpose, DEFAULT_MAX_MS)
    if not MIN_MS <= total_ms <= max_ms:
        reasons.append(
            f"{where}: duration {float(total_ms):.1f} ms outside "
            f"{MIN_MS}..{max_ms} ms for {cue.purpose}"
        )
    return cue if len(reasons) == before else None


def validate_cue_set(data: object) -> CueSet:
    reasons: list[str] = []
    if not isinstance(data, dict):
        raise ProposalError(["cue set: top level must be an object"])
    d = cast(dict[str, Any], data)
    unknown = set(d) - TOP_KEYS
    if unknown:
        reasons.append(f"cue set: unknown keys {sorted(unknown)}")
    if d.get("artifact_kind") != CUE_SET_KIND:
        reasons.append(f"artifact_kind: must be {CUE_SET_KIND}")
    if d.get("schema_version") != SCHEMA_VERSION:
        reasons.append(f"schema_version: must be {SCHEMA_VERSION}")
    product = d.get("product")
    if not _text(product, 1, 80):
        reasons.append("product: 1..80 characters")
    device = d.get("device")
    if device not in DEVICES:
        reasons.append(f"device: one of {sorted(DEVICES)}")
        device = "speaker"
    sources = _validate_sources(d, reasons)
    rationale = d.get("rationale")
    if not _text(rationale, 1, 2000):
        reasons.append("rationale: 1..2000 characters")
    originality = d.get("originality")
    if not isinstance(originality, dict):
        reasons.append(f"originality: object with {list(ORIGINALITY_KEYS)}")
        originality = {}
    else:
        orig = cast(dict[str, Any], originality)
        if set(orig) != set(ORIGINALITY_KEYS) or not all(
            orig[k] is True for k in ORIGINALITY_KEYS
        ):
            reasons.append(
                f"originality: {list(ORIGINALITY_KEYS)} must all be true "
                "(no quoted or imitated jingles, startup chimes or brand sounds)"
            )
    low_name, high_name = DEVICES[device]
    low = cast(int, render_song.parse_pitch(low_name))
    high = cast(int, render_song.parse_pitch(high_name))
    raw_cues = d.get("cues")
    cues: list[Cue] = []
    if not isinstance(raw_cues, list) or not 1 <= len(raw_cues) <= MAX_CUES:
        reasons.append(f"cues: 1..{MAX_CUES} entries")
    else:
        for i, rc in enumerate(cast(list[object], raw_cues)):
            cue = _validate_cue(rc, i, low, high, reasons)
            if cue is not None:
                cues.append(cue)
    seen_ids: dict[str, int] = {}
    seen_shapes: dict[tuple[tuple[int | None, Fraction], ...], str] = {}
    seen_openings: dict[tuple[tuple[int | None, Fraction], ...], str] = {}
    for cue in cues:
        if cue.id in seen_ids:
            reasons.append(f"cues: duplicate id {cue.id}")
        seen_ids[cue.id] = 1
        shape = tuple((n.midi, n.beats * 60 / cue.bpm) for n in cue.notes)
        other = seen_shapes.get(shape)
        if other is not None:
            reasons.append(
                f"cues: {cue.id} sounds identical to {other}; "
                "each cue must be distinguishable"
            )
        seen_shapes.setdefault(shape, cue.id)
        sounded = [n for n in cue.notes if n.midi is not None]
        opening = tuple((n.midi, n.beats) for n in sounded[:2])
        if len(opening) == 2:
            other_open = seen_openings.get(opening)
            if other_open is not None:
                reasons.append(
                    f"cues: {cue.id} opens with the same two sounded notes "
                    f"(pitch and beats) as {other_open}; "
                    "each cue needs a distinct opening"
                )
            seen_openings.setdefault(opening, cue.id)
    transducer = None
    listening = None
    if "transducer" in d or "listening" in d:
        if not ("transducer" in d and "listening" in d):
            reasons.append("transducer and listening: declare both or neither")
        transducer = _validate_transducer(d.get("transducer"), reasons)
        listening = _validate_listening(d.get("listening"), reasons)
    waivers = _validate_waivers(d.get("accessibility_waivers"), reasons)
    _check_accessibility(cues, transducer, listening, waivers, reasons)
    if reasons:
        raise ProposalError(reasons)
    return CueSet(
        product=cast(str, product),
        device=cast(str, device),
        sources=sources,
        rationale=cast(str, rationale),
        originality=cast(dict[str, Any], originality),
        cues=tuple(cues),
        transducer=transducer,
        listening=listening,
        waivers=waivers,
    )


# ---------------------------------------------------------------------------
# rendering


def render_cue_midi(cue_set: CueSet, cue: Cue) -> bytes:
    tempo_us = 60_000_000 // cue.bpm
    name = f"{cue_set.product} {cue.id}".encode()
    track0 = render_song._midi_track(
        [
            (0, b"\xff\x03" + render_song._vlq(len(name)) + name),
            (0, b"\xff\x51\x03" + tempo_us.to_bytes(3, "big")),
            (0, b"\xff\x58\x04" + bytes([4, 2, 24, 8])),
        ]
    )
    events: list[tuple[int, bytes]] = [(0, bytes([0xC0, cue.program]))]
    t = Fraction(0)
    for note in cue.notes:
        if note.midi is not None:
            events.append((int(t * PPQ), bytes([0x90, note.midi, 100])))
            events.append((int((t + note.beats) * PPQ), bytes([0x80, note.midi, 0])))
        t += note.beats
    track1 = render_song._midi_track(events)
    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, PPQ)
    return header + track0 + track1


def render_cue_mml(cue_set: CueSet, cue: Cue) -> str:
    tokens = [f"t{cue.bpm}", "o5", "l4"]
    octave = 5
    for note in cue.notes:
        length = MML_LEN[note.beats]
        if note.midi is None:
            tokens.append("r" + length)
            continue
        note_octave = note.midi // 12 - 1
        if note_octave != octave:
            tokens.append(f"o{note_octave}")
            octave = note_octave
        tokens.append(render_song.MML_PC_SHARP[note.midi % 12] + length)
    lines = [
        "; bard-mml 0.1",
        f"; product={cue_set.product}",
        f"; cue={cue.id}",
        f"; purpose={cue.purpose}",
        f"; device={cue_set.device}",
        f"; bpm={cue.bpm}",
        f"; loop={'true' if cue.loop else 'false'}",
        "; license=BSD-3-Clause",
        "@melody",
        " ".join(tokens),
    ]
    return "\n".join(lines) + "\n"


def _freq_hz(midi: int) -> float:
    return round(440.0 * 2 ** ((midi - 69) / 12), 2)


def cue_tones(cue: Cue) -> list[dict[str, Any]]:
    tones: list[dict[str, Any]] = []
    t = Fraction(0)
    for note in cue.notes:
        start = _ms_int(cue.ms(t))
        end = _ms_int(cue.ms(t + note.beats))
        tones.append(
            {
                "start_ms": start,
                "duration_ms": end - start,
                "midi": note.midi,
                "freq_hz": 0.0 if note.midi is None else _freq_hz(note.midi),
            }
        )
        t += note.beats
    return tones


def _sounded_hz(cue: Cue) -> list[float]:
    return [_freq_hz(n.midi) for n in cue.notes if n.midi is not None]


def accessibility_report(cue_set: CueSet) -> dict[str, Any]:
    return {
        "reference": ACCESSIBILITY_REFERENCE,
        "max_fundamental_hz": MAX_FUNDAMENTAL_HZ,
        "highest_fundamental_hz": max(max(_sounded_hz(c)) for c in cue_set.cues),
        "warnings_loop": True,
        "waivers": [{"check": c, "reason": r} for c, r in cue_set.waivers],
    }


def audibility_report(cue_set: CueSet) -> dict[str, Any]:
    transducer, listening = cue_set.transducer, cue_set.listening
    if transducer is None or listening is None:
        return {
            "status": "unknown",
            "reason": "no transducer response or listening condition declared",
        }
    rows: list[dict[str, Any]] = []
    for cue in cue_set.cues:
        levels = [
            cast(float, listener_spl(transducer, listening, hz))
            for hz in _sounded_hz(cue)
        ]
        lowest = min(levels)
        rows.append(
            {
                "id": cue.id,
                "min_spl_db": round(lowest, 1),
                "margin_db": round(lowest - listening.ambient_db, 1),
            }
        )
    return {
        "status": "pass",
        "part": transducer.part,
        "datasheet_distance_cm": transducer.distance_cm,
        "listening_distance_m": listening.distance_m,
        "ambient_db": listening.ambient_db,
        "min_margin_db": listening.min_margin_db,
        "model": "datasheet SPL, log-frequency interpolation, inverse-square distance",
        "cues": rows,
    }


def render_manifest(cue_set: CueSet, files: dict[str, bytes]) -> str:
    cues: list[dict[str, Any]] = []
    for cue in cue_set.cues:
        mid = f"cue-{cue.id}.mid"
        mml = f"cue-{cue.id}.mml"
        cues.append(
            {
                "id": cue.id,
                "purpose": cue.purpose,
                "ux_feedback": cue.ux_feedback,
                "loop": cue.loop,
                "bpm": cue.bpm,
                "program": cue.program,
                "duration_ms": _ms_int(cue.ms(cue.total_beats)),
                "mid": {"path": mid, "sha256": hashlib.sha256(files[mid]).hexdigest()},
                "mml": {"path": mml, "sha256": hashlib.sha256(files[mml]).hexdigest()},
                "tones": cue_tones(cue),
            }
        )
    record = {
        "artifact_kind": MANIFEST_KIND,
        "schema_version": SCHEMA_VERSION,
        "system": "bard",
        "authority": "none",
        "product": cue_set.product,
        "device": cue_set.device,
        "cues": cues,
        "artifacts": sorted(files),
        "accessibility": accessibility_report(cue_set),
        "audibility": audibility_report(cue_set),
    }
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_markdown(cue_set: CueSet) -> str:
    lines = [
        f"# {cue_set.product} — product sound cues",
        "",
        f"- device: {cue_set.device}",
        f"- cues: {len(cue_set.cues)}",
        "",
        "| Cue | Purpose | UX feedback | Duration | Loop | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cue in cue_set.cues:
        names = " ".join(
            "r"
            if n.midi is None
            else render_song.MML_PC_SHARP[n.midi % 12] + str(n.midi // 12 - 1)
            for n in cue.notes
        )
        lines.append(
            f"| `{cue.id}` | {cue.purpose} | {cue.ux_feedback or '—'} | "
            f"{_ms_int(cue.ms(cue.total_beats))} ms | "
            f"{'yes' if cue.loop else 'no'} | {names} |"
        )
    access = accessibility_report(cue_set)
    lines += [
        "",
        "## Accessibility",
        "",
        f"- reference: {access['reference']}",
        f"- highest fundamental: {access['highest_fundamental_hz']} Hz "
        f"(limit {access['max_fundamental_hz']:.0f} Hz)",
        "- warning cues loop with an ON/OFF pattern",
    ]
    lines += [f"- waiver {c}: {r}" for c, r in cue_set.waivers]
    audible = audibility_report(cue_set)
    if audible["status"] == "unknown":
        lines.append(f"- audibility: unknown — {audible['reason']}")
    else:
        lines.append(
            f"- audibility ({audible['part']}, {audible['listening_distance_m']} m, "
            f"ambient {audible['ambient_db']} dB): "
            + ", ".join(f"{r['id']} {r['min_spl_db']} dB" for r in audible["cues"])
        )
    lines += ["", "## Rationale", "", cue_set.rationale, "", "## Sources", ""]
    for src in cue_set.sources:
        lines.append(f"- {src['kind']}: {src['ref']}")
    return "\n".join(lines) + "\n"


TIMELINE_ROW_H = 46
_TIMELINE_LABEL_W = 220
_TIMELINE_PAD = 10
_TIMELINE_HEADER_H = 24
_TIMELINE_MS_PX = 0.28


def _xml_esc(text: object) -> str:
    return _xml.escape(str(text), {'"': "&quot;"})


def _opening_interval(cue: Cue) -> str:
    sounded = [n.midi for n in cue.notes if n.midi is not None]
    if len(sounded) < 2:
        return "single note"
    delta = sounded[1] - sounded[0]
    if delta == 0:
        return "unison"
    direction = "+" if delta > 0 else "-"
    return f"{direction}{abs(delta)} semitones"


def render_timeline_svg(cue_set: CueSet) -> str:
    """Deterministic timeline SVG: one row per cue, shared millisecond scale.

    Every tone from ``cue_tones`` is a rectangle (rests are gaps) whose height
    encodes pitch within the cue's row; the row label carries id, purpose,
    duration, loop and the opening interval. No timestamps — the same cue set
    produces byte-identical SVG.
    """
    durations = [_ms_int(cue.ms(cue.total_beats)) for cue in cue_set.cues]
    max_ms = max(durations, default=1) or 1
    width = int(
        _TIMELINE_LABEL_W + math.ceil(max_ms * _TIMELINE_MS_PX) + _TIMELINE_PAD * 2
    )
    height = _TIMELINE_HEADER_H + len(cue_set.cues) * TIMELINE_ROW_H + _TIMELINE_PAD
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}" font-family="sans-serif">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
        f'<text x="10" y="16" font-size="13">{_xml_esc(cue_set.product)} — '
        f"{_xml_esc(cue_set.device)} cue timeline (ms)</text>",
    ]
    track_x = _TIMELINE_LABEL_W
    track_w = width - _TIMELINE_LABEL_W - _TIMELINE_PAD
    for i, cue in enumerate(cue_set.cues):
        top = _TIMELINE_HEADER_H + i * TIMELINE_ROW_H
        parts.append(
            f'<rect x="{track_x}" y="{top + 4}" width="{track_w}" '
            f'height="{TIMELINE_ROW_H - 8}" fill="#f6f6f6" '
            f'stroke="#ddd"/>'
        )
        duration = durations[i]
        loop_mark = " ↻" if cue.loop else ""
        parts.append(
            f'<text x="8" y="{top + 18}" font-size="10" fill="#333">'
            f"{_xml_esc(cue.id)} · {_xml_esc(cue.purpose)}{loop_mark}</text>"
        )
        parts.append(
            f'<text x="8" y="{top + 32}" font-size="9" fill="#777">'
            f"{duration} ms · {_xml_esc(_opening_interval(cue))}</text>"
        )
        tones = cue_tones(cue)
        midis = [t["midi"] for t in tones if t["midi"] is not None]
        lo = min(midis, default=0)
        hi = max(midis, default=0)
        span = max(1, hi - lo)
        inner_h = TIMELINE_ROW_H - 20
        for tone in tones:
            x = track_x + int(tone["start_ms"] / max_ms * track_w)
            w = max(2, int(tone["duration_ms"] / max_ms * track_w))
            if tone["midi"] is None:
                continue
            frac = (tone["midi"] - lo) / span
            y = top + 8 + int((1 - frac) * inner_h)
            h = max(3, inner_h // 3)
            parts.append(
                f'<rect x="{x}" y="{min(y, top + TIMELINE_ROW_H - 10)}" '
                f'width="{w}" height="{h}" fill="#336" fill-opacity="0.85"/>'
            )
    # millisecond ruler: minor ticks every 100 ms, labels every 500 ms
    ruler_y = _TIMELINE_HEADER_H - 4
    for ms in range(0, max_ms + 1, 100):
        if ms % 500 == 0:
            continue
        x = track_x + int(ms / max_ms * track_w)
        parts.append(
            f'<line x1="{x}" y1="{_TIMELINE_HEADER_H}" x2="{x}" '
            f'y2="{_TIMELINE_HEADER_H + 5}" stroke="#ccc"/>'
        )
    for ms in range(0, max_ms + 1, 500):
        x = track_x + int(ms / max_ms * track_w)
        parts.append(
            f'<text x="{x}" y="{ruler_y}" font-size="8" fill="#999">{ms}</text>'
        )
        parts.append(
            f'<line x1="{x}" y1="{_TIMELINE_HEADER_H}" x2="{x}" '
            f'y2="{height - _TIMELINE_PAD}" stroke="#eee"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render(cue_set: CueSet) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for cue in cue_set.cues:
        files[f"cue-{cue.id}.mid"] = render_cue_midi(cue_set, cue)
        files[f"cue-{cue.id}.mml"] = render_cue_mml(cue_set, cue).encode("utf-8")
    files["cues.timeline.svg"] = render_timeline_svg(cue_set).encode("utf-8")
    outputs = dict(files)
    outputs["cues.json"] = render_manifest(cue_set, files).encode("utf-8")
    outputs["cues.md"] = render_markdown(cue_set).encode("utf-8")
    return outputs


def readback_check(cue_set: CueSet, outputs: dict[str, bytes]) -> list[str]:
    reasons: list[str] = []
    for cue in cue_set.cues:
        sounded = sum(1 for n in cue.notes if n.midi is not None)
        counts = render_song.parse_midi_counts(outputs[f"cue-{cue.id}.mid"])
        ons, offs = counts.get(0, [0, 0])
        if ons != sounded or offs != sounded:
            reasons.append(
                f"readback.midi: {cue.id} note-on {ons} note-off {offs} != {sounded}"
            )
        voices = render_song.parse_mml(outputs[f"cue-{cue.id}.mml"].decode("utf-8"))
        melody = voices.get("melody")
        if melody != (sounded, cue.total_beats):
            reasons.append(f"readback.mml: {cue.id} voice {melody} mismatch")
    return reasons


def render_provenance(
    cue_set: CueSet,
    cues_path: Path,
    cues_sha: str,
    outputs: dict[str, bytes],
    script_sha: str,
) -> str:
    record = {
        "artifact_kind": PROVENANCE_KIND,
        "schema_version": SCHEMA_VERSION,
        "authority": "none",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cue_set": {"path": str(cues_path), "sha256": cues_sha},
        "outputs": {
            name: hashlib.sha256(blob).hexdigest()
            for name, blob in sorted(outputs.items())
        },
        "sources": cue_set.sources,
        "script_sha256": script_sha,
        "vision_points": render_song.vision_points(outputs),
        "license": "BSD-3-Clause",
        "originality": cue_set.originality,
        "device": cue_set.device,
        "cue_count": len(cue_set.cues),
    }
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


def _emit(as_json: bool, payload: dict[str, Any], lines: list[str]) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cues", required=True, type=Path)
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
    cues_path: Path = args.cues
    out_dir: Path = args.out_dir

    try:
        raw_text = cues_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as e:
        reasons = [f"cue set: cannot read or parse JSON: {e}"]
        _emit(args.json, {"status": "error", "reasons": reasons}, reasons)
        return 3 if isinstance(e, OSError) else 2
    cues_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    try:
        cue_set = validate_cue_set(data)
        outputs = render(cue_set)
        readback = readback_check(cue_set, outputs)
        if readback:
            raise ProposalError(readback)
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        prov = render_provenance(cue_set, cues_path, cues_sha, outputs, script_sha)
        outputs["cues.provenance.json"] = prov.encode("utf-8")
    except ProposalError as e:
        _emit(args.json, {"status": "rejected", "reasons": e.reasons}, e.reasons)
        return 2

    if args.check:
        _emit(
            args.json,
            {"status": "ok", "check": True, "cues_sha256": cues_sha},
            ["check ok"],
        )
        return 0

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}
        for name, blob in outputs.items():
            (out_dir / name).write_bytes(blob)
            written[name] = hashlib.sha256(blob).hexdigest()
    except OSError as e:
        reasons = [f"io: {e}"]
        _emit(args.json, {"status": "error", "reasons": reasons}, reasons)
        return 3

    _emit(
        args.json,
        {"status": "ok", "files": written},
        [f"{out_dir / name}: {sha}" for name, sha in written.items()],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
