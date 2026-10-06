"""Accessibility and audibility checks of render_cues.py.

Boundaries follow the 3-value rule (just below, on, just above) for the
2.5 kHz fundamental limit (JIS S 0013 / ISO 24500 clause 4.3), the
listening-distance cap of ISO 24501 and the SPL margin.
"""

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_DIR = REPO_ROOT / "plugins" / "bard" / "skills" / "bard-render"
SCRIPT_PATH = RENDER_DIR / "scripts" / "render_cues.py"
EXAMPLE = RENDER_DIR / "examples" / "smart-kettle.cues.json"


@pytest.fixture(scope="module")
def m() -> Any:
    spec = importlib.util.spec_from_file_location("render_cues", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_cues"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def example() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _reasons(m: Any, data: dict[str, Any]) -> list[str]:
    with pytest.raises(m.ProposalError) as exc:
        m.validate_cue_set(data)
    return exc.value.reasons


def _flat(m: Any, data: dict[str, Any]) -> dict[str, Any]:
    """A response flat at 120 dB so SPL never limits a pitch test."""
    data = copy.deepcopy(data)
    data["transducer"]["response"] = [
        {"hz": 500, "spl_db": 120},
        {"hz": 5000, "spl_db": 120},
    ]
    return data


def test_example_passes_and_reports(m: Any, example: dict[str, Any]) -> None:
    cue_set = m.validate_cue_set(example)
    access = m.accessibility_report(cue_set)
    assert access["highest_fundamental_hz"] == pytest.approx(2093.0, abs=0.01)
    assert access["waivers"] == []
    audible = m.audibility_report(cue_set)
    assert audible["status"] == "pass"
    assert {row["id"] for row in audible["cues"]} == {c.id for c in cue_set.cues}
    for row in audible["cues"]:
        assert row["margin_db"] >= 5


def test_manifest_carries_both_reports(m: Any, example: dict[str, Any]) -> None:
    cue_set = m.validate_cue_set(example)
    manifest = json.loads(m.render_manifest(cue_set, m.render(cue_set)))
    assert manifest["accessibility"]["max_fundamental_hz"] == 2500.0
    assert manifest["audibility"]["status"] == "pass"
    assert manifest["authority"] == "none"


def test_audibility_unknown_without_transducer(m: Any, example: dict[str, Any]) -> None:
    del example["transducer"], example["listening"]
    cue_set = m.validate_cue_set(example)
    assert m.audibility_report(cue_set)["status"] == "unknown"
    assert "audibility: unknown" in m.render_markdown(cue_set)


@pytest.mark.parametrize(("pitch", "ok"), [("d#7", True), ("e7", False)])
def test_fundamental_limit_boundary(
    m: Any, example: dict[str, Any], pitch: str, ok: bool
) -> None:
    # d#7 = 2489.02 Hz (just below 2.5 kHz), e7 = 2637.02 Hz (just above).
    data = _flat(m, example)
    data["cues"][1]["notes"][1]["pitch"] = pitch
    if ok:
        m.validate_cue_set(data)
    else:
        assert any("above 2500 Hz" in r for r in _reasons(m, data))


def test_fundamental_limit_is_on_the_frequency(m: Any) -> None:
    assert m._freq_hz(99) < m.MAX_FUNDAMENTAL_HZ < m._freq_hz(100)


def test_reasoned_waiver_admits_high_pitch(m: Any, example: dict[str, Any]) -> None:
    data = _flat(m, example)
    data["cues"][1]["notes"][1]["pitch"] = "e7"
    reason = "Users are factory staff tested for high-frequency hearing yearly."
    data["accessibility_waivers"] = [{"check": "max_fundamental_hz", "reason": reason}]
    cue_set = m.validate_cue_set(data)
    assert m.accessibility_report(cue_set)["waivers"][0]["reason"] == reason
    assert "waiver max_fundamental_hz" in m.render_markdown(cue_set)


@pytest.mark.parametrize(
    ("waivers", "needle"),
    [
        ([{"check": "max_fundamental_hz", "reason": "short"}], "reason: 20..400"),
        ([{"check": "loop", "reason": "x" * 30}], "check: one of"),
        ([{"check": "max_fundamental_hz"}], "exactly check and reason"),
        ("all", "list of {check, reason}"),
        (
            [{"check": "max_fundamental_hz", "reason": "y" * 30}] * 2,
            "duplicate waiver",
        ),
    ],
)
def test_malformed_waivers_fail(
    m: Any, example: dict[str, Any], waivers: object, needle: str
) -> None:
    data = _flat(m, example)
    data["cues"][1]["notes"][1]["pitch"] = "e7"
    data["accessibility_waivers"] = waivers
    assert any(needle in r for r in _reasons(m, data))


def test_stale_waiver_fails(m: Any, example: dict[str, Any]) -> None:
    example["accessibility_waivers"] = [
        {"check": "max_fundamental_hz", "reason": "z" * 30}
    ]
    assert any("stale waiver" in r for r in _reasons(m, example))


def test_warning_must_loop(m: Any, example: dict[str, Any]) -> None:
    example["cues"][2]["loop"] = False
    assert any("must loop" in r for r in _reasons(m, example))


def test_error_may_be_one_shot(m: Any, example: dict[str, Any]) -> None:
    example["cues"][2]["purpose"] = "error"
    example["cues"][2]["loop"] = False
    m.validate_cue_set(example)


def test_loop_without_rest_fails(m: Any, example: dict[str, Any]) -> None:
    example["cues"][2]["notes"] = [{"pitch": "a6", "beats": 0.5}]
    assert any("without a rest" in r for r in _reasons(m, example))


def test_transducer_and_listening_come_together(
    m: Any, example: dict[str, Any]
) -> None:
    del example["listening"]
    assert any("both or neither" in r for r in _reasons(m, example))


def test_tone_outside_response_fails(m: Any, example: dict[str, Any]) -> None:
    example["transducer"]["response"][0]["hz"] = 1100
    assert any("outside the declared" in r for r in _reasons(m, example))


def _margin_case(example: dict[str, Any], need: float) -> dict[str, Any]:
    data = copy.deepcopy(example)
    data["transducer"]["response"] = [
        {"hz": 500, "spl_db": 70},
        {"hz": 5000, "spl_db": 70},
    ]
    data["transducer"]["distance_cm"] = 10
    data["listening"]["distance_m"] = 1.0
    data["listening"]["ambient_db"] = need - 5
    data["listening"]["min_margin_db"] = 5
    return data


@pytest.mark.parametrize(("need", "ok"), [(49.9, True), (50.0, True), (50.1, False)])
def test_spl_margin_boundary(
    m: Any, example: dict[str, Any], need: float, ok: bool
) -> None:
    # Flat 70 dB at 10 cm is 50 dB at 1 m (inverse square, -20 dB).
    data = _margin_case(example, need)
    if ok:
        m.validate_cue_set(data)
    else:
        assert any("below ambient" in r for r in _reasons(m, data))


@pytest.mark.parametrize(("distance", "ok"), [(3.9, True), (4.0, True), (4.1, False)])
def test_listening_distance_boundary(
    m: Any, example: dict[str, Any], distance: float, ok: bool
) -> None:
    data = _flat(m, example)
    data["listening"]["distance_m"] = distance
    if ok:
        m.validate_cue_set(data)
    else:
        assert any("listening.distance_m" in r for r in _reasons(m, data))


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda t: t.update(part=""), "transducer.part"),
        (lambda t: t.update(distance_cm=0), "transducer.distance_cm"),
        (lambda t: t.update(distance_cm=True), "transducer.distance_cm"),
        (lambda t: t.update(extra=1), "unknown keys"),
        (lambda t: t.update(response=[{"hz": 1000, "spl_db": 70}]), "2..32"),
        (lambda t: t["response"][1].update(hz=900), "strictly increase"),
        (lambda t: t["response"][1].update(hz=float("nan")), ".hz: 20..20000"),
        (lambda t: t["response"][1].update(spl_db=141), ".spl_db: 0..140"),
        (lambda t: t["response"][1].pop("spl_db"), "exactly hz and spl_db"),
    ],
)
def test_corrupt_transducer_fails(
    m: Any, example: dict[str, Any], mutate: Any, needle: str
) -> None:
    mutate(example["transducer"])
    assert any(needle in r for r in _reasons(m, example))


@pytest.mark.parametrize(
    ("key", "value", "needle"),
    [
        ("ambient_db", -1, "ambient_db"),
        ("min_margin_db", 41, "min_margin_db"),
        ("rationale", "too short", "rationale"),
        ("extra", 1, "exactly"),
    ],
)
def test_corrupt_listening_fails(
    m: Any, example: dict[str, Any], key: str, value: object, needle: str
) -> None:
    example["listening"][key] = value
    assert any(needle in r for r in _reasons(m, example))


def test_non_object_blocks_fail(m: Any, example: dict[str, Any]) -> None:
    example["transducer"] = []
    example["listening"] = "kitchen"
    reasons = _reasons(m, example)
    assert any(r.startswith("transducer:") for r in reasons)
    assert any(r.startswith("listening:") for r in reasons)


@pytest.mark.parametrize("hz", [1000.0, 1046.5, 1234.5, 1500.0, 2093.0, 4000.0])
def test_interpolation_is_log_linear_and_bounded(
    m: Any, example: dict[str, Any], hz: float
) -> None:
    t = m.validate_cue_set(example).transducer
    level = m.spl_at(t, hz)
    lo = max(p for p in t.response if p[0] <= hz)
    hi = min(p for p in t.response if p[0] >= hz)
    assert min(lo[1], hi[1]) - 1e-9 <= level <= max(lo[1], hi[1]) + 1e-9
    if lo != hi:
        frac = (math.log(hz) - math.log(lo[0])) / (math.log(hi[0]) - math.log(lo[0]))
        assert level == pytest.approx(lo[1] + frac * (hi[1] - lo[1]))
    assert m.spl_at(t, 999.0) is None
    assert m.spl_at(t, 4000.1) is None
