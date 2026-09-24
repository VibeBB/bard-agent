"""Tests for the advisory score lint and clash-avoidance voicing."""

import dataclasses
import importlib.util
import json
import struct
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LINT_PATH = (
    REPO_ROOT
    / "plugins"
    / "bard"
    / "skills"
    / "bard-render"
    / "scripts"
    / "lint_score.py"
)
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def lint_module(render_module: Any) -> Any:
    spec = importlib.util.spec_from_file_location("lint_score", LINT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_score"] = module
    spec.loader.exec_module(module)
    return module


def _render(render_module: Any, fixture: str, out_dir: Path) -> None:
    assert (
        render_module.main(
            [
                "--proposal",
                str(FIXTURES / fixture),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )


def test_lint_emitted_midi_has_no_residual_clash(
    render_module: Any, tmp_path: Path
) -> None:
    out_dir = tmp_path / "out"
    _render(render_module, "valid_en.json", out_dir)
    data = json.loads((FIXTURES / "valid_en.json").read_text(encoding="utf-8"))
    song = render_module.validate_proposal(data)
    report = render_module.lint_song(
        song, (out_dir / "song.mid").read_bytes(), source="valid_en.json"
    )
    assert report["verdict"] == "pass"
    assert report["errors"] == 0
    assert report["notes_checked"] > 0
    assert not [f for f in report["findings"] if f["type"] == "residual_clash"]
    # the fixture's melody forces the deterministic re-voicing path
    assert report["voicing"]["substituted"] >= 1
    assert report["voicing"]["dropped"] >= 1


def test_lint_flags_crafted_residual_clash(render_module: Any) -> None:
    data = json.loads((FIXTURES / "valid_en.json").read_text(encoding="utf-8"))
    song = render_module.validate_proposal(data)
    midi = (
        b"MThd"
        + struct.pack(">IHHH", 6, 1, 3, render_module.PPQ)
        + render_module._midi_track([])
        # melody: C5 (72) sounding a whole bar
        + render_module._midi_track(
            [(0, bytes([0x90, 72, 90])), (1920, bytes([0x80, 72, 0]))]
        )
        # accompaniment: B4 (71) — a minor-9th offset under the melody
        + render_module._midi_track(
            [(0, bytes([0x91, 71, 60])), (1920, bytes([0x81, 71, 0]))]
        )
    )
    report = render_module.lint_song(song, midi, source="crafted.mid")
    clashes = [f for f in report["findings"] if f["type"] == "residual_clash"]
    assert len(clashes) == 1
    assert clashes[0]["severity"] == "warning"


def test_voicing_drops_voice_when_every_tone_clashes(
    render_module: Any, valid_en: dict[str, Any]
) -> None:
    song = render_module.validate_proposal(valid_en)
    chord = render_module._parse_chord_symbol("C")
    assert chord is not None
    # C#4, Eb4, Gb4: every tone of a C triad sits a semitone off the melody
    notes = [
        render_module.Note(pitch=p, beats=Fraction(1), midi=m)
        for p, m in (("cs4", 61), ("_e4", 63), ("_g4", 66))
    ]
    line = render_module.Line(text="x", units=["x"], notes=notes)
    section = render_module.Section(
        name="verse", kind="verse", chords=[[chord]], lines=[line]
    )
    patched = dataclasses.replace(song, sections=[section])
    slots, adjustments = render_module._accompaniment_slots(patched)
    assert slots == [[None, None, None]]
    assert len(adjustments) == 3
    assert all(a["action"] == "dropped" for a in adjustments)


def test_voicing_is_deterministic(render_module: Any, valid_en: dict[str, Any]) -> None:
    song = render_module.validate_proposal(valid_en)
    slots_a, adj_a = render_module._accompaniment_slots(song)
    slots_b, adj_b = render_module._accompaniment_slots(song)
    assert slots_a == slots_b
    assert adj_a == adj_b


def test_lint_script_writes_report(
    render_module: Any, lint_module: Any, tmp_path: Path
) -> None:
    out_dir = tmp_path / "out"
    _render(render_module, "valid_en.json", out_dir)
    lint_path = out_dir / "song.lint.json"
    assert (
        lint_module.main(
            [
                "--proposal",
                str(FIXTURES / "valid_en.json"),
                "--mid",
                str(out_dir / "song.mid"),
                "--out",
                str(lint_path),
            ]
        )
        == 0
    )
    report = json.loads(lint_path.read_text(encoding="utf-8"))
    assert report["artifact_kind"] == "score_lint"
    assert report["authority"] == "none"
    assert report["verdict"] == "pass"


def test_lint_script_fails_closed_on_bad_proposal(
    lint_module: Any, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.proposal.json"
    bad.write_text("not json {", encoding="utf-8")
    assert lint_module.main(["--proposal", str(bad)]) == 1
