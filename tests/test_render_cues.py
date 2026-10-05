"""Tests for render_cues.py: golden example, determinism, negative checks."""

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_DIR = REPO_ROOT / "plugins" / "bard" / "skills" / "bard-render"
SCRIPT_PATH = RENDER_DIR / "scripts" / "render_cues.py"
EXAMPLE = RENDER_DIR / "examples" / "smart-kettle.cues.json"
HOOKS_DIR = REPO_ROOT / "plugins" / "bard" / "hooks" / "scripts"
HOOK = HOOKS_DIR / "protect_song_artifacts.py"


@pytest.fixture(scope="module")
def cues_module() -> Any:
    spec = importlib.util.spec_from_file_location("render_cues", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_cues"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def example() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _run(module: Any, path: Path, out_dir: Path, *extra: str) -> int:
    return module.main(["--cues", str(path), "--out-dir", str(out_dir), *extra])


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "cues.proposal.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _reasons(module: Any, data: dict[str, Any]) -> list[str]:
    with pytest.raises(module.ProposalError) as exc:
        module.validate_cue_set(data)
    return exc.value.reasons


def test_example_renders(cues_module: Any, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert _run(cues_module, EXAMPLE, out) == 0
    names = {p.name for p in out.iterdir()}
    cue_ids = ["boot", "done", "overheat", "press"]
    expected = {"cues.json", "cues.md", "cues.provenance.json", "cues.timeline.svg"}
    expected |= {f"cue-{i}.{ext}" for i in cue_ids for ext in ("mid", "mml")}
    assert names == expected

    manifest = json.loads((out / "cues.json").read_text(encoding="utf-8"))
    assert manifest["artifact_kind"] == "bard_cue_manifest"
    assert manifest["system"] == "bard"
    assert manifest["authority"] == "none"
    assert [c["id"] for c in manifest["cues"]] == cue_ids
    done = manifest["cues"][1]
    assert done["ux_feedback"] == "beep_done"
    assert done["duration_ms"] == 600
    assert [t["freq_hz"] for t in done["tones"]] == [1567.98, 2093.0]
    assert sum(t["duration_ms"] for t in done["tones"]) == done["duration_ms"]
    for cue in manifest["cues"]:
        for kind in ("mid", "mml"):
            blob = (out / cue[kind]["path"]).read_bytes()
            assert cue[kind]["sha256"] == hashlib.sha256(blob).hexdigest()

    prov = json.loads((out / "cues.provenance.json").read_text(encoding="utf-8"))
    assert prov["artifact_kind"] == "bard_cue_provenance"
    assert prov["license"] == "BSD-3-Clause"
    assert prov["cue_set"]["sha256"] == hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()
    assert (out / "cue-done.mml").read_text(encoding="utf-8").splitlines()[-1] == (
        "t150 o5 l4 o6 g8 o7 c4"
    )


def test_render_is_deterministic(cues_module: Any, tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    assert _run(cues_module, EXAMPLE, a) == 0
    assert _run(cues_module, EXAMPLE, b) == 0
    for path in a.iterdir():
        if path.name == "cues.provenance.json":
            continue
        assert path.read_bytes() == (b / path.name).read_bytes(), path.name


def test_midi_and_mml_read_back(cues_module: Any, example: dict[str, Any]) -> None:
    cue_set = cues_module.validate_cue_set(example)
    outputs = cues_module.render(cue_set)
    assert cues_module.readback_check(cue_set, outputs) == []
    counts = cues_module.render_song.parse_midi_counts(outputs["cue-overheat.mid"])
    assert counts[0] == [3, 3]


def test_check_writes_nothing(cues_module: Any, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert _run(cues_module, EXAMPLE, out, "--check") == 0
    assert not out.exists()


def test_rejection_writes_nothing(
    cues_module: Any, tmp_path: Path, example: dict[str, Any]
) -> None:
    example["originality"]["no_trademark_sound_imitation"] = False
    out = tmp_path / "out"
    assert _run(cues_module, _write(tmp_path, example), out) == 2
    assert not out.exists()


def _mutate(example: dict[str, Any], key: str) -> dict[str, Any]:
    data = copy.deepcopy(example)
    cues = data["cues"]
    if key == "unknown_top":
        data["extra"] = 1
    elif key == "purpose":
        cues[0]["purpose"] = "fanfare"
    elif key == "range":
        cues[0]["notes"][0]["pitch"] = "c4"
    elif key == "beats":
        cues[0]["notes"][0]["beats"] = 0.3
    elif key == "leading_rest":
        cues[0]["notes"].insert(0, {"pitch": "r", "beats": 0.25})
    elif key == "confirm_too_long":
        cues[3]["notes"][0]["beats"] = 1
    elif key == "too_short":
        cues[3]["notes"][0]["beats"] = 0.125
    elif key == "loop_not_allowed":
        cues[1]["loop"] = True
    elif key == "duplicate_id":
        cues[1]["id"] = "boot"
    elif key == "identical":
        cues[1] = {**copy.deepcopy(cues[0]), "id": "boot_again"}
    elif key == "bpm":
        cues[0]["bpm"] = 300
    elif key == "source_kind":
        data["sources"][0]["kind"] = "rumour"
    elif key == "ux_feedback":
        cues[1]["ux_feedback"] = "beep done!"
    return data


@pytest.mark.parametrize(
    ("key", "fragment"),
    [
        ("unknown_top", "unknown keys"),
        ("purpose", "purpose"),
        ("range", "device range"),
        ("beats", "beats"),
        ("leading_rest", "start and end"),
        ("confirm_too_long", "0..300 ms"),
        ("too_short", "outside 50"),
        ("loop_not_allowed", "may loop"),
        ("duplicate_id", "duplicate id"),
        ("identical", "sounds identical"),
        ("bpm", "bpm"),
        ("source_kind", "sources[0].kind"),
        ("ux_feedback", "ux_feedback"),
    ],
)
def test_negative(
    cues_module: Any, example: dict[str, Any], key: str, fragment: str
) -> None:
    reasons = _reasons(cues_module, _mutate(example, key))
    assert any(fragment in r for r in reasons), reasons


def test_speaker_allows_low_range(cues_module: Any, example: dict[str, Any]) -> None:
    example["device"] = "speaker"
    example["cues"][0]["notes"][0]["pitch"] = "c4"
    cues_module.validate_cue_set(example)


@pytest.mark.parametrize(
    ("path", "denied"),
    [
        ("cues/kettle/cues.json", True),
        ("cues/kettle/cue-boot.mid", True),
        ("cues/kettle/cue-boot.mml", True),
        ("cues/kettle/cues.provenance.json", True),
        ("cues/kettle/cues.proposal.json", False),
        ("cues/kettle/brief.md", False),
        ("cues/kettle/cues.timeline.svg", True),
        ("cues/kettle/cues.timeline.png", True),
    ],
)
def test_protect_hook_covers_cue_artifacts(path: str, denied: bool) -> None:
    spec = importlib.util.spec_from_file_location("protect_song_artifacts", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = {
        "tool_name": "file_editor",
        "tool_input": {"command": "create", "path": path, "file_text": "{}"},
    }
    assert module._is_artifact_write(payload) is denied


def test_cues_sharing_opening_notes_rejected(
    cues_module: Any, example: dict[str, Any]
) -> None:
    cue_set = json.loads(json.dumps(example))
    dupe = json.loads(json.dumps(cue_set["cues"][0]))
    dupe["id"] = "boot2"
    dupe["purpose"] = "completion"
    dupe["notes"] = [
        dict(cue_set["cues"][0]["notes"][0]),
        dict(cue_set["cues"][0]["notes"][1]),
        dict(cue_set["cues"][1]["notes"][-1]),
    ]
    cue_set["cues"].append(dupe)
    reasons = _reasons(cues_module, cue_set)
    assert any("opening" in reason for reason in reasons), reasons


def test_timeline_svg_written(cues_module: Any, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert _run(cues_module, EXAMPLE, out) == 0
    svg = (out / "cues.timeline.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") or "<svg" in svg
    prov = json.loads((out / "cues.provenance.json").read_text(encoding="utf-8"))
    assert (
        prov["outputs"]["cues.timeline.svg"]
        == hashlib.sha256((out / "cues.timeline.svg").read_bytes()).hexdigest()
    )
