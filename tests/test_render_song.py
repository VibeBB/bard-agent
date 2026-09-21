"""Tests for render_song.py: golden fixtures, determinism, negative checks."""

import copy
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "plugins"
    / "bard"
    / "skills"
    / "bard-render"
    / "scripts"
    / "render_song.py"
)
FIXTURES = Path(__file__).resolve().parent / "fixtures"

EXPECTED_FILES = {
    "song.abc",
    "song.mid",
    "song.mml",
    "song.md",
    "song.provenance.json",
}


def _run(render_module: Any, proposal: Path, out_dir: Path, *extra: str) -> int:
    return render_module.main(
        ["--proposal", str(proposal), "--out-dir", str(out_dir), *extra]
    )


def _write_proposal(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "song.proposal.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# golden paths


@pytest.mark.parametrize("fixture", ["valid_en.json", "valid_ja.json"])
def test_valid_fixture_renders(
    render_module: Any, tmp_path: Path, fixture: str
) -> None:
    proposal = FIXTURES / fixture
    out_dir = tmp_path / "out"
    assert _run(render_module, proposal, out_dir) == 0
    assert {p.name for p in out_dir.iterdir()} == EXPECTED_FILES

    prov = json.loads((out_dir / "song.provenance.json").read_text(encoding="utf-8"))
    assert prov["artifact_kind"] == "bard_song_provenance"
    assert prov["authority"] == "none"
    assert prov["license"] == "BSD-3-Clause"
    assert (
        prov["proposal"]["sha256"] == hashlib.sha256(proposal.read_bytes()).hexdigest()
    )
    for name in ("song.abc", "song.mid", "song.mml", "song.md"):
        assert (
            prov["outputs"][name]
            == hashlib.sha256((out_dir / name).read_bytes()).hexdigest()
        )


@pytest.mark.parametrize("fixture", ["valid_en.json", "valid_ja.json"])
def test_render_is_deterministic(
    render_module: Any, tmp_path: Path, fixture: str
) -> None:
    proposal = FIXTURES / fixture
    first = tmp_path / "a"
    second = tmp_path / "b"
    assert _run(render_module, proposal, first) == 0
    assert _run(render_module, proposal, second) == 0
    for name in ("song.abc", "song.mid", "song.mml", "song.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    pa = json.loads((first / "song.provenance.json").read_text(encoding="utf-8"))
    pb = json.loads((second / "song.provenance.json").read_text(encoding="utf-8"))
    pa.pop("generated_at")
    pb.pop("generated_at")
    assert pa == pb


def test_check_writes_nothing(render_module: Any, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    assert _run(render_module, FIXTURES / "valid_en.json", out_dir, "--check") == 0
    assert not out_dir.exists() or not list(out_dir.iterdir())


def test_midi_structure(render_module: Any, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    assert _run(render_module, FIXTURES / "valid_en.json", out_dir) == 0
    data = (out_dir / "song.mid").read_bytes()
    assert data[:4] == b"MThd"
    fmt, ntrks = struct.unpack(">HH", data[8:12])
    assert fmt == 1 and ntrks == 3


@pytest.mark.parametrize("fixture", ["valid_en.json", "valid_ja.json"])
def test_abc_lyrics_align_per_music_line(
    render_module: Any, tmp_path: Path, fixture: str
) -> None:
    out_dir = tmp_path / "out"
    assert _run(render_module, FIXTURES / fixture, out_dir) == 0
    abc = (out_dir / "song.abc").read_text(encoding="utf-8")
    pending: str | None = None
    pairs: list[tuple[str, str]] = []
    for raw in abc.splitlines():
        if raw.startswith("w: "):
            assert pending is not None, "w: line without a music line"
            pairs.append((pending, raw[3:]))
            pending = None
        elif raw.startswith(("X:", "T:", "C:", "M:", "L:", "Q:", "K:", "%%")):
            continue
        elif raw.strip():
            pending = raw
    assert len(pairs) >= 4
    for music, lyric in pairs:
        assert "*" not in lyric
        # ABC w: tokens align to sounded notes only; rests are skipped
        notes = [
            t
            for t in re.sub(r'"[^"]*"', "", music).split()
            if t != "|" and not t.startswith("z")
        ]
        # w: pieces: each "_" is its own melisma token; "-" separates syllables
        n_lyric = len(
            [p for tok in lyric.split() for p in re.findall(r"_|[^_-]+", tok)]
        )
        assert len(notes) == n_lyric, (music, lyric)


def test_long_utf8_title_renders(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    data = copy.deepcopy(valid_ja)
    data["title"] = "夜の歌" * 20  # 60 chars, 180 UTF-8 bytes -> 2-byte VLQ
    proposal = _write_proposal(tmp_path, data)
    out_dir = tmp_path / "out"
    assert _run(render_module, proposal, out_dir) == 0
    counts = render_module.parse_midi_counts((out_dir / "song.mid").read_bytes())
    assert counts[0][0] == counts[0][1] > 0


# ---------------------------------------------------------------------------
# negative tests: one-field corruptions of the valid en fixture


def _reject(
    render_module: Any,
    tmp_path: Path,
    valid_en: dict[str, Any],
    mutate: Any,
    expected: str,
) -> None:
    data = copy.deepcopy(valid_en)
    mutate(data)
    proposal = _write_proposal(tmp_path, data)
    out_dir = tmp_path / "out"
    code = _run(render_module, proposal, out_dir)
    assert code == 2
    assert not out_dir.exists() or not list(out_dir.iterdir())
    try:
        render_module.validate_proposal(data)
    except render_module.ProposalError as e:
        assert any(expected in r for r in e.reasons), (
            f"missing {expected!r} in {e.reasons}"
        )
    else:
        raise AssertionError("corrupted proposal was accepted")


def test_reject_originality_false(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["originality"]["original_melody"] = False

    _reject(render_module, tmp_path, valid_en, m, "must be true")


def test_reject_chord_root_out_of_scale(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # D# is not in the D dorian scale
        d["sections"][0]["chords"][0] = "D#m"

    _reject(render_module, tmp_path, valid_en, m, "chord root D#m not in scale")


def test_reject_final_chord_not_tonic(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][1]["chords"][-1] = "Am"

    _reject(render_module, tmp_path, valid_en, m, "final chord root != tonic")


def test_reject_downbeat_non_chord_tone(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # index 8 starts bar 2 (chord C); f4 is not a C chord tone
        d["sections"][0]["lines"][0]["notes"][8] = {"pitch": "f4", "beats": 1}

    _reject(render_module, tmp_path, valid_en, m, "is not a chord tone of C")


def test_reject_leap_over_octave(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # d4 then g5 = +19 semitones; g5 also leaves range, leap triggers anyway
        d["vocal_range"] = {"low": "c4", "high": "g5"}
        d["sections"][0]["lines"][0]["notes"][2] = {"pitch": "g5", "beats": 0.5}

    _reject(render_module, tmp_path, valid_en, m, "exceeds 12 semitones")


def test_reject_leap_across_section_boundary(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # verse ends on d4; chorus opens with f5 (+15) on an F-chord downbeat
        d["vocal_range"] = {"low": "c4", "high": "g5"}
        d["sections"][1]["lines"][0]["notes"][0] = {"pitch": "f5", "beats": 0.5}

    _reject(render_module, tmp_path, valid_en, m, "exceeds 12 semitones")


def test_reject_pitch_out_of_range(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["notes"][0] = {"pitch": "d3", "beats": 0.5}

    _reject(render_module, tmp_path, valid_en, m, "outside vocal range")


def test_reject_pitch_out_of_scale(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # ab4 is not in D dorian; keep it a chord tone so only the scale rule fires
        d["sections"][0]["lines"][0]["notes"][0] = {"pitch": "f4", "beats": 0.5}
        d["sections"][0]["lines"][0]["notes"][1] = {"pitch": "f#4", "beats": 0.5}

    _reject(render_module, tmp_path, valid_en, m, "not in scale")


def test_reject_units_text_mismatch(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["units"][0] = "Ov"

    _reject(render_module, tmp_path, valid_en, m, "units do not match text")


def test_reject_notes_units_count_mismatch(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["notes"].append({"pitch": "d4", "beats": 1})

    _reject(render_module, tmp_path, valid_en, m, "notes count 12 != units count 11")


def test_reject_section_beats_mismatch(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["chords"].append("Dm")

    _reject(render_module, tmp_path, valid_en, m, "section beats")


def test_reject_bad_beats_value(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["notes"][0]["beats"] = 0.33

    _reject(render_module, tmp_path, valid_en, m, "must be one of")


def test_reject_bad_schema_version(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["schema_version"] = "0.1"

    _reject(render_module, tmp_path, valid_en, m, 'must be "0.2"')


def test_reject_ja_unit_too_long(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["units"] = [
            "さくら",
            "の",
            "下",
            "で",
            "歌",
            "を",
            "つむ",
            "ぐ",
        ]

    _reject(render_module, tmp_path, valid_ja, m, "ja unit must be 1..2 characters")


def test_reject_melisma_after_leap(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # "~" at units[4] follows b4; e5 is a leap of 7
        d["sections"][0]["lines"][1]["notes"][4] = {"pitch": "e5", "beats": 0.5}

    _reject(render_module, tmp_path, valid_ja, m, "'~' note e5")


def test_reject_rest_without_dash_unit(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["notes"][0] = {"pitch": "r", "beats": 0.5}

    _reject(render_module, tmp_path, valid_en, m, "rest note 'r' requires a '-' unit")


def test_reject_final_pitch_not_cadence(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][1]["lines"][1]["notes"][-1] = {"pitch": "b4", "beats": 3}

    _reject(render_module, tmp_path, valid_en, m, "final pitch not degree 1/3/5")


# ---------------------------------------------------------------------------
# read-back parser unit tests


def test_parse_abc_melody_counts(render_module: Any, valid_en: dict[str, Any]) -> None:
    song = render_module.validate_proposal(valid_en)
    abc = render_module.render_abc(song)
    notes, rests, beats = render_module.parse_abc_melody(abc)
    assert notes == 58
    assert rests == 0
    assert beats == Fraction(48)


def test_parse_midi_counts_roundtrip(
    render_module: Any, valid_en: dict[str, Any]
) -> None:
    song = render_module.validate_proposal(valid_en)
    counts = render_module.parse_midi_counts(render_module.render_midi(song))
    assert counts[0] == [58, 58]
    assert counts[1][0] == counts[1][1] > 0


def test_parse_midi_counts_rejects_corruption(
    render_module: Any, valid_en: dict[str, Any]
) -> None:
    song = render_module.validate_proposal(valid_en)
    blob = bytearray(render_module.render_midi(song))
    blob[0:4] = b"XXXX"
    with pytest.raises(render_module.ProposalError):
        render_module.parse_midi_counts(bytes(blob))
    blob2 = bytearray(render_module.render_midi(song))
    # truncate inside the melody track
    del blob2[-10:]
    with pytest.raises(render_module.ProposalError):
        render_module.parse_midi_counts(bytes(blob2))


def test_parse_mml_counts(render_module: Any, valid_ja: dict[str, Any]) -> None:
    song = render_module.validate_proposal(valid_ja)
    voices = render_module.parse_mml(render_module.render_mml(song))
    assert voices["melody"] == (44, Fraction(24))
    for i in range(1, 4):
        assert voices[f"chord{i}"][1] == Fraction(24)
    assert "chord4" not in voices


def test_parse_mml_fourth_voice_for_seventh_chord(
    render_module: Any, valid_ja: dict[str, Any]
) -> None:
    data = copy.deepcopy(valid_ja)
    data["sections"][0]["chords"][1] = "Fm7"
    song = render_module.validate_proposal(data)
    voices = render_module.parse_mml(render_module.render_mml(song))
    assert voices["chord4"][1] == Fraction(24)


def test_parse_mml_rejects_garbage(render_module: Any) -> None:
    with pytest.raises(render_module.ProposalError):
        render_module.parse_mml("@melody\n???")


# ---------------------------------------------------------------------------
# w: lyric token emission


@pytest.mark.parametrize(
    ("units", "text", "expected"),
    [
        (["hea", "~", "ven"], "heaven", "w: hea-_ven"),
        (["hea", "~", "~", "ven"], "heaven", "w: hea-__ven"),
        (["hea", "ven", "~"], "heaven", "w: hea-ven-_"),
        (["hea", "-", "ven"], "heaven", "w: hea-ven"),
        (["hea", "ven", "~", "up"], "heaven up", "w: hea-ven _ up"),
        (["up", "~", "hea", "ven"], "up heaven", "w: up _ hea-ven"),
    ],
)
def test_w_line_en_pieces(
    render_module: Any,
    valid_en: dict[str, Any],
    units: list[str],
    text: str,
    expected: str,
) -> None:
    song = render_module.validate_proposal(valid_en)
    line = render_module.Line(text=text, units=units, notes=[])
    assert render_module._w_line(song, line) == expected


# ---------------------------------------------------------------------------
# external ABC tools

_ABCM2PS = shutil.which("abcm2ps")
requires_abcm2ps = pytest.mark.skipif(
    _ABCM2PS is None and not os.environ.get("BARD_REQUIRE_ABCM2PS"),
    reason="abcm2ps not installed",
)


def _abcm2ps_or_fail(tmp_path: Path, abc_path: Path) -> None:
    if _ABCM2PS is None:
        pytest.fail("BARD_REQUIRE_ABCM2PS=1 is set but abcm2ps is not on PATH")
    proc = subprocess.run(
        ["abcm2ps", str(abc_path), "-O", str(tmp_path / "song.ps")],
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "words in lyric line" not in output
    # "char NNNN not treated" means glyphs were dropped from the PS output;
    # e.g. lyrics are lost when no CJK font (fonts-ipafont) is installed.
    assert "not treated" not in output, output


@requires_abcm2ps
@pytest.mark.parametrize("fixture", ["valid_en.json", "valid_ja.json"])
def test_abcm2ps_accepts_abc(render_module: Any, tmp_path: Path, fixture: str) -> None:
    out_dir = tmp_path / "out"
    assert _run(render_module, FIXTURES / fixture, out_dir) == 0
    _abcm2ps_or_fail(tmp_path, out_dir / "song.abc")


# ---------------------------------------------------------------------------
# instrumental intro/outro sections


def _with_instrumental_sections(data: dict[str, Any]) -> dict[str, Any]:
    d = copy.deepcopy(data)
    d["sections"] = [
        {"name": "intro", "kind": "intro", "chords": ["Dm"], "lines": []},
        *d["sections"],
        {"name": "outro", "kind": "outro", "chords": ["Dm", "Dm"], "lines": []},
    ]
    return d


def test_instrumental_intro_outro_renders(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    data = _with_instrumental_sections(valid_en)
    proposal = _write_proposal(tmp_path, data)
    out_dir = tmp_path / "out"
    assert _run(render_module, proposal, out_dir) == 0
    assert {p.name for p in out_dir.iterdir()} == EXPECTED_FILES

    abc = (out_dir / "song.abc").read_text(encoding="utf-8")
    assert '%% section intro\n"Dm" z8 |' in abc
    assert '%% section outro\n"Dm" z8 | "Dm" z8 |' in abc
    intro_w = abc.split("%% section intro")[1].split("%% section")[0]
    assert "w:" not in intro_w

    n, r, b = render_module.parse_abc_melody(abc)
    assert (n, r, b) == (58, 3, Fraction(60))
    counts = render_module.parse_midi_counts((out_dir / "song.mid").read_bytes())
    assert counts[0] == [58, 58]
    voices = render_module.parse_mml((out_dir / "song.mml").read_text(encoding="utf-8"))
    assert voices["melody"] == (58, Fraction(60))
    assert "(instrumental)" in (out_dir / "song.md").read_text(encoding="utf-8")


@requires_abcm2ps
def test_abcm2ps_accepts_instrumental(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    proposal = _write_proposal(tmp_path, _with_instrumental_sections(valid_en))
    out_dir = tmp_path / "out"
    assert _run(render_module, proposal, out_dir) == 0
    _abcm2ps_or_fail(tmp_path, out_dir / "song.abc")


def test_reject_empty_lines_on_verse(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"] = []

    _reject(render_module, tmp_path, valid_en, m, "need at least one line")


# ---------------------------------------------------------------------------
# schema 0.2: reading, rhythm variety, markdown shape


def test_reject_monotone_rhythm(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        for n in d["sections"][0]["lines"][0]["notes"]:
            n["beats"] = 1 if n["pitch"] != "r" else 1

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        m,
        "line needs at least two different note lengths",
    )


def test_reject_reading_on_en(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["reading"] = "あんだー"

    _reject(render_module, tmp_path, valid_en, m, "reading is only for ja")


def test_reject_reading_not_kana(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["reading"] = "桜の下で"

    _reject(render_module, tmp_path, valid_ja, m, "must be kana")


def test_reject_units_mismatch_reading(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["lines"][0]["reading"] = "よるのうた"

    _reject(render_module, tmp_path, valid_ja, m, "units do not match reading")


def test_song_md_hard_breaks_and_chord_line(render_module: Any, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    assert _run(render_module, FIXTURES / "valid_ja.json", out_dir) == 0
    md = (out_dir / "song.md").read_text(encoding="utf-8")
    assert "桜の下で歌を紡ぐ  \n夜の火を越えてゆく" in md
    assert "Chords: | Am | F | G | Am |" in md
    assert "| bar | chord |" not in md


def test_reject_section_name_implies_kind(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        # verse section renamed like a refrain while keeping kind=verse
        d["sections"][0]["name"] = "refrain 1"

    _reject(
        render_module,
        tmp_path,
        valid_en,
        m,
        'name "refrain 1" implies kind chorus',
    )


def test_refrain_name_with_chorus_kind_ok(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    data = copy.deepcopy(valid_en)
    data["sections"][1]["name"] = "refrain 1"
    proposal = _write_proposal(tmp_path, data)
    assert _run(render_module, proposal, tmp_path / "out") == 0


def test_reject_stale_rationale_quote(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["rationale"] = "サビ「存在しない歌詞」を繰り返す。"

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        m,
        "does not appear in the lyrics",
    )


def test_rationale_quote_matches_normalized(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    data = copy.deepcopy(valid_ja)
    # 「」 quote matching a line after whitespace normalization
    data["rationale"] = "サビ「明日はもう　青い」で締める。"
    # the line text itself carries a fullwidth space; both sides collapse
    data["sections"][1]["lines"][1]["text"] = "明日はもう　青い"
    proposal = _write_proposal(tmp_path, data)
    assert _run(render_module, proposal, tmp_path / "out") == 0


def test_rationale_quote_ascii_quotes(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    data = copy.deepcopy(valid_en)
    # ASCII quotes and collapsed double space still match the line text
    data["rationale"] = 'the chorus "Raise up  the bridge" repeats'
    proposal = _write_proposal(tmp_path, data)
    assert _run(render_module, proposal, tmp_path / "out") == 0


# ---------------------------------------------------------------------------
# schema 0.3: melody_from + shipped examples

EXAMPLES = REPO_ROOT / "plugins/bard/skills/bard-render/examples"


def _to_03(d: dict[str, Any]) -> dict[str, Any]:
    d["schema_version"] = "0.3"
    return d


@pytest.mark.parametrize("example", ["minimal.en.json", "minimal.ja.json"])
def test_shipped_example_renders_deterministic(
    render_module: Any, tmp_path: Path, example: str
) -> None:
    proposal = EXAMPLES / example
    out1, out2 = tmp_path / "a", tmp_path / "b"
    assert _run(render_module, proposal, out1) == 0
    assert _run(render_module, proposal, out2) == 0
    for name in EXPECTED_FILES - {"song.provenance.json"}:
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    p1 = json.loads((out1 / "song.provenance.json").read_bytes())
    p2 = json.loads((out2 / "song.provenance.json").read_bytes())
    p1.pop("generated_at")
    p2.pop("generated_at")
    assert p1 == p2
    assert p1["schema_version"] == "0.3"


def test_melody_from_copies_notes(render_module: Any, tmp_path: Path) -> None:
    proposal = EXAMPLES / "minimal.ja.json"
    out_dir = tmp_path / "out"
    assert _run(render_module, proposal, out_dir) == 0
    song = render_module.validate_proposal(
        json.loads(proposal.read_text(encoding="utf-8"))
    )
    verse1 = song.sections[0]
    for copier in song.sections[1:]:
        assert [n.pitch for ln in copier.lines for n in ln.notes] == [
            n.pitch for ln in verse1.lines for n in ln.notes
        ]
        assert copier.chords == verse1.chords
    abc = (out_dir / "song.abc").read_text(encoding="utf-8")
    assert "%% section verse 2" in abc
    assert "コミットを重ね朝を呼ぶ" in (out_dir / "song.md").read_text(encoding="utf-8")
    counts = render_module.parse_midi_counts((out_dir / "song.mid").read_bytes())
    assert counts[0][0] == counts[0][1] == 78


def _mf(d: dict[str, Any], mutate: Any) -> dict[str, Any]:
    _to_03(d)
    mutate(d)
    return d


def _copy_verse2(d: dict[str, Any]) -> dict[str, Any]:
    sec = d["sections"][0]
    return {
        "name": "verse 2",
        "kind": "verse",
        "melody_from": "verse 1",
        "lines": [{"text": ln["text"], "units": ln["units"]} for ln in sec["lines"]],
    }


def test_reject_melody_from_unknown_section(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        sec = _copy_verse2(d)
        sec["melody_from"] = "bridge 9"
        d["sections"].append(sec)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        'references unknown/later section "bridge 9"',
    )


def test_reject_melody_from_later_section(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"][0]["melody_from"] = "chorus"
        d["sections"][0].pop("chords")
        for line in d["sections"][0]["lines"]:
            line.pop("notes")

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        'references unknown/later section "chorus"',
    )


def test_reject_melody_from_chained(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        copier = _copy_verse2(d)
        copier["name"] = "verse 2"
        d["sections"].append(copier)
        chained = _copy_verse2(d)
        chained["name"] = "verse 3"
        chained["melody_from"] = "verse 2"
        d["sections"].append(chained)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        'source "verse 2" uses melody_from',
    )


def test_reject_melody_from_keeps_chords(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        sec = _copy_verse2(d)
        sec["chords"] = ["Am", "F", "G", "Am"]
        d["sections"].append(sec)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        "melody_from section must omit chords",
    )


def test_reject_melody_from_keeps_notes(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        sec = _copy_verse2(d)
        sec["lines"][0]["notes"] = [
            {"pitch": n["pitch"], "beats": n["beats"]}
            for n in d["sections"][0]["lines"][0]["notes"]
        ]
        d["sections"].append(sec)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        "melody_from section must omit notes",
    )


def test_reject_melody_from_line_count(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        sec = _copy_verse2(d)
        sec["lines"] = sec["lines"][:1]
        d["sections"].append(sec)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        "line count 1 != source 2",
    )


def test_reject_melody_from_units_count(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        sec = _copy_verse2(d)
        sec["lines"][0]["units"] = sec["lines"][0]["units"][:-1]
        d["sections"].append(sec)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        "units count",
    )


def test_reject_melody_from_rest_positions(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        sec = _copy_verse2(d)
        # source line 1 has a rest at units index 10 ("-"); move it
        src = d["sections"][0]["lines"][1]["units"]
        assert src[10] == "-"
        new_units = list(src)
        new_units[10] = "を"
        new_units[9] = "-"
        sec["lines"][1]["units"] = new_units
        d["sections"].append(sec)

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        lambda d: _mf(d, m),
        "rest positions differ from source",
    )


def test_reject_melody_from_under_02(
    render_module: Any, tmp_path: Path, valid_ja: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["sections"].append(_copy_verse2(d))

    _reject(
        render_module,
        tmp_path,
        valid_ja,
        m,
        "melody_from requires schema_version 0.3",
    )


def test_reject_schema_version_04(
    render_module: Any, tmp_path: Path, valid_en: dict[str, Any]
) -> None:
    def m(d: dict[str, Any]) -> None:
        d["schema_version"] = "0.4"

    _reject(
        render_module,
        tmp_path,
        valid_en,
        m,
        'must be "0.2" or "0.3"',
    )
