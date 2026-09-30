from __future__ import annotations

import re
import struct
import sys
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from song_model import ProposalError, Song  # noqa: E402
from song_render import _CLASH_OFFSETS, PPQ, _accompaniment_slots  # noqa: E402

__all__ = [
    "ABC_TOKEN_RE",
    "parse_abc_melody",
    "_read_vlq",
    "_iter_midi_events",
    "parse_midi_counts",
    "_midi_note_spans",
    "score_lint_report",
    "lint_song",
    "MML_TOKEN_RE",
    "parse_mml",
    "_readback_check",
]

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


def _iter_midi_events(
    data: bytes, *, label: str
) -> Iterator[tuple[str, int, int, int, int]]:
    """Walk an SMF and yield (kind, channel, pitch, velocity, tick).

    kind is "on" (note-on, velocity > 0), "off" (note-off or zero-velocity
    note-on) or "track_end" (yielded once per track with the final tick;
    channel/pitch/velocity are 0)."""
    if len(data) < 14 or data[:4] != b"MThd":
        raise ProposalError([f"{label}: missing MThd header"])
    hlen = struct.unpack(">I", data[4:8])[0]
    fmt, ntrks = struct.unpack(">HH", data[8:12])
    if fmt != 1 or ntrks < 2:
        raise ProposalError([f"{label}: bad format {fmt} or track count {ntrks}"])
    pos = 8 + hlen
    for _ in range(ntrks):
        if pos + 8 > len(data) or data[pos : pos + 4] != b"MTrk":
            raise ProposalError([f"{label}: missing MTrk header"])
        tlen = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        if pos + 8 + tlen > len(data):
            raise ProposalError([f"{label}: truncated track data"])
        track = data[pos + 8 : pos + 8 + tlen]
        pos += 8 + tlen
        i = 0
        tick = 0
        running = 0
        while i < len(track):
            delta, i = _read_vlq(track, i)
            tick += delta
            if i >= len(track):
                raise ProposalError([f"{label}: truncated event"])
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
                    raise ProposalError([f"{label}: truncated meta event"])
                i += 1
                meta_len, i = _read_vlq(track, i)
                i += meta_len
                if i > len(track):
                    raise ProposalError([f"{label}: truncated meta payload"])
                continue
            if status in (0xF0, 0xF7):
                syx_len, i = _read_vlq(track, i)
                i += syx_len
                if i > len(track):
                    raise ProposalError([f"{label}: truncated sysex payload"])
                continue
            if kind in (0xC0, 0xD0):
                i += 1
                continue
            if i + 1 >= len(track):
                raise ProposalError([f"{label}: truncated note event"])
            if kind == 0x90:
                pitch, vel = track[i], track[i + 1]
                i += 2
                yield ("on" if vel > 0 else "off", ch, pitch, vel, tick)
                continue
            if kind == 0x80:
                pitch = track[i]
                vel = track[i + 1]
                i += 2
                yield ("off", ch, pitch, vel, tick)
                continue
            i += 2
        yield ("track_end", 0, 0, 0, tick)


def parse_midi_counts(data: bytes) -> dict[int, list[int]]:
    """Parse an SMF and return {channel: [note_on_count, note_off_count]}."""
    counts: dict[int, list[int]] = {}
    for kind, ch, _pitch, _vel, _tick in _iter_midi_events(data, label="readback.midi"):
        if kind == "on":
            counts.setdefault(ch, [0, 0])[0] += 1
        elif kind == "off":
            counts.setdefault(ch, [0, 0])[1] += 1
    return counts


def _midi_note_spans(data: bytes) -> dict[int, list[tuple[int, int, int]]]:
    """Parse an SMF and return {channel: [(start_tick, end_tick, pitch)]}."""
    spans: dict[int, list[tuple[int, int, int]]] = {}
    open_notes: dict[tuple[int, int], int] = {}
    for kind, ch, pitch, _vel, tick in _iter_midi_events(data, label="lint.midi"):
        if kind == "on":
            open_notes[(ch, pitch)] = tick
        elif kind == "off":
            start = open_notes.pop((ch, pitch), None)
            if start is not None:
                spans.setdefault(ch, []).append((start, tick, pitch))
        else:
            for (o_ch, o_pitch), start in open_notes.items():
                spans.setdefault(o_ch, []).append((start, tick, o_pitch))
            open_notes = {}
    return spans


def score_lint_report(
    source: str,
    *,
    verdict: str,
    errors: int,
    warnings: int,
    notes_checked: int,
    voicing: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the `song.lint.json` envelope shared by the pass and fail paths."""
    return {
        "artifact_kind": "score_lint",
        "authority": "none",
        "schema_version": "1.0",
        "kind": "score_lint",
        "source": source,
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
        "notes_checked": notes_checked,
        "voicing": voicing,
        "findings": findings,
    }


def lint_song(song: Song, midi: bytes, *, source: str) -> dict[str, Any]:
    """Advisory score lint: residual melody/accompaniment clashes on the
    emitted MIDI plus the deterministic re-voicing adjustments applied.

    Warnings never block a render; verdict fails only when the report
    itself cannot be produced (callers report that separately)."""
    spans = _midi_note_spans(midi)
    melody = spans.get(0, [])
    accomp = spans.get(1, [])
    findings: list[dict[str, Any]] = []
    for m_start, m_end, m_pitch in melody:
        for a_start, a_end, a_pitch in accomp:
            if (
                a_start < m_end
                and a_end > m_start
                and (m_pitch - a_pitch) % 12 in _CLASH_OFFSETS
            ):
                findings.append(
                    {
                        "type": "residual_clash",
                        "severity": "warning",
                        "description": (
                            f"melody pitch {m_pitch} vs accompaniment "
                            f"{a_pitch} at beat {m_start / PPQ:g}"
                        ),
                    }
                )
    _, adjustments = _accompaniment_slots(song)
    substitutions = [
        {
            "section": a["section"],
            "beat": a["beat"],
            "chord": a["chord"],
            "voice": a["voice"],
            "from_pc": a["from_pc"],
            "to_pc": a["to_pc"],
        }
        for a in adjustments
        if a["action"] == "substituted"
    ]
    for a in adjustments:
        if a["action"] == "dropped":
            findings.append(
                {
                    "type": "voice_dropped",
                    "severity": "warning",
                    "description": (
                        f"{a['section']} beat {a['beat']:g} chord {a['chord']}: "
                        f"voice {a['voice']} (pc {a['from_pc']}) dropped, "
                        "every chord tone clashed"
                    ),
                }
            )
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return score_lint_report(
        source,
        verdict="pass",
        errors=0,
        warnings=warnings,
        notes_checked=len(melody) + len(accomp),
        voicing={
            "substituted": len(substitutions),
            "dropped": len(adjustments) - len(substitutions),
            "substitutions": substitutions,
        },
        findings=findings,
    )


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
