"""Tests for the score-review.json validator (fail-closed contract)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "bard"
    / "skills"
    / "bard-render"
    / "scripts"
    / "validate_score_review.py"
)


@pytest.fixture(scope="session")
def validator() -> Any:
    spec = importlib.util.spec_from_file_location("validate_score_review", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_score_review"] = module
    spec.loader.exec_module(module)
    return module


LONG_SUMMARY = (
    "inspected: the eight-bar engraving reads cleanly, with chord labels "
    "placed above each measure and the melisma extender drawn after the "
    "final syllable. Lyric syllables sit under their notes without "
    "collisions, the bar lines are well formed, and the title block is "
    "legible; the only nit is a cramped chord label over bar three."
)


def _ok_record() -> dict[str, Any]:
    return {
        "artifact_kind": "bard_score_review",
        "authority": "none",
        "tool": "vision_review",
        "stage": "review",
        "status": "ok",
        "summary": LONG_SUMMARY,
        "artifacts": ["songs/x/score.png"],
        "detail": {
            "image_path": "songs/x/score.png",
            "image_sha256": "a" * 64,
            "model": "test-model",
            "checklist": "score_engraving",
            "findings": [
                {
                    "category": "cramped_chord_label",
                    "severity": "info",
                    "note": "bar 3 label crowds the staff",
                }
            ],
        },
        "checked_at": "2026-09-25T00:00:00+00:00",
    }


def test_valid_record_passes(validator: Any) -> None:
    assert validator.validate(_ok_record()) == []


def test_short_summary_rejected(validator: Any) -> None:
    record = _ok_record()
    record["summary"] = "inspected: looks fine."
    problems = validator.validate(record)
    assert any("240" in problem for problem in problems)


def test_single_sentence_summary_rejected(validator: Any) -> None:
    record = _ok_record()
    record["summary"] = "inspected: " + "the score is clean " * 30
    problems = validator.validate(record)
    assert any("two sentences" in problem for problem in problems)


def test_missing_prefix_rejected(validator: Any) -> None:
    record = _ok_record()
    record["summary"] = LONG_SUMMARY.removeprefix("inspected: ")
    problems = validator.validate(record)
    assert any("inspected:" in problem for problem in problems)


def test_ok_without_detail_rejected(validator: Any) -> None:
    record = _ok_record()
    del record["detail"]
    problems = validator.validate(record)
    assert any("detail" in problem for problem in problems)


def test_detail_rejected_for_not_applicable(validator: Any) -> None:
    record = _ok_record()
    record["status"] = "not_applicable"
    record["summary"] = "skipped: model not vision-capable"
    problems = validator.validate(record)
    assert any("detail must be omitted" in problem for problem in problems)


def test_not_applicable_without_detail_passes(validator: Any) -> None:
    record = _ok_record()
    record["status"] = "not_applicable"
    record["summary"] = "skipped: model not vision-capable"
    del record["detail"]
    assert validator.validate(record) == []


def test_bad_image_sha_rejected(validator: Any) -> None:
    record = _ok_record()
    record["detail"]["image_sha256"] = "zz"
    problems = validator.validate(record)
    assert any("image_sha256" in problem for problem in problems)


def test_bad_finding_category_rejected(validator: Any) -> None:
    record = _ok_record()
    record["detail"]["findings"][0]["category"] = "made_up"
    problems = validator.validate(record)
    assert any("category" in problem for problem in problems)


def test_cli_validates_file(validator: Any, tmp_path: Path) -> None:
    review = tmp_path / "score-review.json"
    review.write_text(json.dumps(_ok_record()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(review)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0

    review.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(review)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
