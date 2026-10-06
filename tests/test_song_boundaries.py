"""Boundary tests for the song-proposal validator.

Techniques follow docs/test-coverage.md: 3-value boundaries (below / on /
above) on the tempo, General MIDI program, vocal-range span and melodic
leap limits, plus type equivalence classes (bool is not an int).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest


def _reasons(render_module: Any, data: dict[str, Any]) -> list[str]:
    try:
        render_module.validate_proposal(data)
    except render_module.ProposalError as error:
        return list(error.reasons)
    return []


def _has(reasons: list[str], needle: str) -> bool:
    return any(needle in reason for reason in reasons)


@pytest.mark.parametrize(
    ("bpm", "ok"),
    [
        (59, False),
        (60, True),
        (61, True),
        (179, True),
        (180, True),
        (181, False),
        (True, False),
    ],
)
def test_bpm_three_value_boundary(
    render_module: Any, valid_en: dict[str, Any], bpm: Any, ok: bool
) -> None:
    data = copy.deepcopy(valid_en)
    data["bpm"] = bpm
    assert _has(_reasons(render_module, data), "60..180") is not ok


@pytest.mark.parametrize("role", ["melody", "accompaniment"])
@pytest.mark.parametrize(
    ("program", "ok"),
    [(-1, False), (0, True), (1, True), (126, True), (127, True), (128, False)],
)
def test_midi_program_three_value_boundary(
    render_module: Any, valid_en: dict[str, Any], role: str, program: int, ok: bool
) -> None:
    data = copy.deepcopy(valid_en)
    data["instruments"][role] = program
    assert _has(_reasons(render_module, data), f"instruments.{role}") is not ok


@pytest.mark.parametrize(
    ("low", "high", "ok"),
    [
        ("f4", "b4", False),  # 6 semitones
        ("e4", "b4", True),  # 7
        ("e4", "c5", True),  # 8
        ("b3", "f5", True),  # 18
        ("c4", "g5", True),  # 19
        ("b3", "g5", False),  # 20
    ],
)
def test_vocal_range_span_three_value_boundary(
    render_module: Any, valid_en: dict[str, Any], low: str, high: str, ok: bool
) -> None:
    data = copy.deepcopy(valid_en)
    data["vocal_range"] = {"low": low, "high": high}
    assert _has(_reasons(render_module, data), "7..19 semitones") is not ok


@pytest.mark.parametrize(("pitch", "ok"), [("d5", True), ("e5", True), ("f5", False)])
def test_melodic_leap_three_value_boundary(
    render_module: Any, valid_en: dict[str, Any], pitch: str, ok: bool
) -> None:
    # e4 -> d5 is 10, e4 -> e5 is 12 and e4 -> f5 is 13 semitones.
    data = copy.deepcopy(valid_en)
    data["vocal_range"] = {"low": "c4", "high": "g5"}
    notes = data["sections"][0]["lines"][0]["notes"]
    notes[1] = {"pitch": "e4", "beats": 0.5}
    notes[2] = {"pitch": pitch, "beats": 0.5}
    assert _has(_reasons(render_module, data), "exceeds 12 semitones") is not ok


def test_valid_fixture_has_no_reasons(
    render_module: Any, valid_en: dict[str, Any]
) -> None:
    assert _reasons(render_module, valid_en) == []


def test_empty_sources_are_rejected(
    render_module: Any, valid_en: dict[str, Any]
) -> None:
    data = copy.deepcopy(valid_en)
    data["sources"] = []
    assert any(reason.startswith("sources") for reason in _reasons(render_module, data))


@pytest.mark.parametrize(
    ("count", "ok"), [(0, False), (1, True), (12, True), (13, False)]
)
def test_section_count_boundary(
    render_module: Any, valid_en: dict[str, Any], count: int, ok: bool
) -> None:
    data = copy.deepcopy(valid_en)
    if count == 0:
        data["sections"] = []
    elif count == 13:
        extra = copy.deepcopy(data["sections"][0])
        data["sections"] = data["sections"] + [
            {**copy.deepcopy(extra), "name": f"extra {i}"} for i in range(11)
        ]
    elif count == 12:
        extra = copy.deepcopy(data["sections"][0])
        data["sections"] = [
            {**copy.deepcopy(extra), "name": f"extra {i}"} for i in range(10)
        ] + data["sections"]
    else:
        data["sections"] = data["sections"][-1:]
    assert len(data["sections"]) == count
    assert _has(_reasons(render_module, data), "1..12 sections") is not ok
