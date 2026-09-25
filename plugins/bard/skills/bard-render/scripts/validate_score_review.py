"""Validate a `score-review.json` record against the vision_review contract.

The score visual check is a required step: when `score.png` renders and the
model is vision-capable, `score-review.json` must exist with `status: "ok"`,
a typed `detail` block, and a `summary` that carries a substantive
multi-sentence reading of the image (not a one-line verdict). This script is
the deterministic check for that shape — fail-closed: any schema violation,
missing field, or thin summary is a rejection.

Python 3.12+, standard library only.

Usage:
    validate_score_review.py score-review.json [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SUMMARY_MIN_LENGTH = 240
_SENTENCE_MARKS = "。.!?"
_SUMMARY_PREFIX = {"ok": "inspected:", "not_applicable": "skipped:", "error": "error:"}
_IMAGE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATUSES = frozenset(_SUMMARY_PREFIX)
_FINDING_CATEGORIES = {
    "lyric_collision",
    "orphaned_syllable",
    "cramped_chord_label",
    "malformed_barline",
    "font_fallback_tofu",
    "other",
}
_SEVERITIES = {"error", "warning", "info"}


def _summary_is_prose(summary: str) -> str | None:
    """Return a problem string when the summary is not a substantive reading."""
    if len(summary) < SUMMARY_MIN_LENGTH:
        return (
            f"summary must be a substantive multi-sentence reading "
            f"(>= {SUMMARY_MIN_LENGTH} characters; got {len(summary)})"
        )
    if sum(summary.count(mark) for mark in _SENTENCE_MARKS) < 2:
        return "summary must contain at least two sentences"
    return None


def _validate_detail(detail: Any, problems: list[str]) -> None:
    if not isinstance(detail, dict):
        problems.append("status ok requires a detail object")
        return
    if not isinstance(detail.get("image_path"), str) or not detail["image_path"]:
        problems.append("detail.image_path must be a non-empty string")
    sha = detail.get("image_sha256")
    if not isinstance(sha, str) or not _IMAGE_SHA256.match(sha):
        problems.append("detail.image_sha256 must be 64 lowercase hex characters")
    if not isinstance(detail.get("model"), str) or not detail["model"]:
        problems.append("detail.model must be a non-empty string")
    if detail.get("checklist") != "score_engraving":
        problems.append("detail.checklist must be 'score_engraving'")
    findings = detail.get("findings")
    if not isinstance(findings, list):
        problems.append("detail.findings must be a list")
        return
    for index, finding in enumerate(findings):
        where = f"detail.findings[{index}]"
        if not isinstance(finding, dict):
            problems.append(f"{where} must be an object")
            continue
        if finding.get("category") not in _FINDING_CATEGORIES:
            problems.append(f"{where}.category is not a known category")
        if finding.get("severity") not in _SEVERITIES:
            problems.append(f"{where}.severity must be error|warning|info")
        if not isinstance(finding.get("note"), str) or not finding["note"].strip():
            problems.append(f"{where}.note must be a non-empty string")
        bbox = finding.get("bbox")
        if bbox is not None and not (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(isinstance(v, int | float) for v in bbox)
        ):
            problems.append(f"{where}.bbox must be normalized [x, y, w, h]")


def validate(record: Any) -> list[str]:
    """Return the list of contract violations; empty means the record is valid."""
    problems: list[str] = []
    if not isinstance(record, dict):
        return ["score-review.json must contain one JSON object"]
    if record.get("artifact_kind") != "bard_score_review":
        problems.append("artifact_kind must be 'bard_score_review'")
    if record.get("authority") != "none":
        problems.append("authority must be 'none'")
    if record.get("tool") != "vision_review":
        problems.append("tool must be 'vision_review'")
    if record.get("stage") != "review":
        problems.append("stage must be 'review'")
    status = record.get("status")
    if status not in _STATUSES:
        problems.append("status must be ok|error|not_applicable")
    checked_at = record.get("checked_at")
    if not isinstance(checked_at, str) or not checked_at.strip():
        problems.append("checked_at must be a non-empty ISO 8601 string")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list) or not all(
        isinstance(item, str) for item in artifacts
    ):
        problems.append("artifacts must be a list of strings")
    summary = record.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("summary must be a non-empty string")
    else:
        prefix = _SUMMARY_PREFIX.get(status) if isinstance(status, str) else None
        if prefix is not None and not summary.startswith(prefix):
            problems.append(f"summary for status {status} must start with '{prefix}'")
        if status == "ok":
            prose = _summary_is_prose(summary)
            if prose is not None:
                problems.append(prose)
    detail = record.get("detail")
    if status == "ok":
        _validate_detail(detail, problems)
    elif detail is not None:
        problems.append("detail must be omitted for not_applicable/error")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a score-review.json record against the vision_review contract."
        )
    )
    parser.add_argument("review", type=Path, help="path to score-review.json")
    parser.add_argument("--json", action="store_true", help="emit a JSON verdict")
    args = parser.parse_args()
    try:
        raw = args.review.read_text(encoding="utf-8")
    except OSError as exc:
        problems = [f"cannot read {args.review}: {exc}"]
        record: Any = None
    else:
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            record = None
            problems = [f"score-review.json is not valid JSON: {exc}"]
        else:
            problems = validate(record)
    if args.json:
        print(
            json.dumps(
                {"ok": not problems, "problems": problems},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif problems:
        for problem in problems:
            print(f"score-review: {problem}", file=sys.stderr)
    else:
        print("score-review: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
