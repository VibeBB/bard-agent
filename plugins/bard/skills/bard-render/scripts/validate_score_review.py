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
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve()
_HOOKS_SCRIPTS = _SCRIPTS.parents[3] / "hooks" / "scripts"
_PLUGIN_SCRIPTS = _SCRIPTS.parents[3] / "scripts"


def _import_script(name: str, directory: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, directory / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load {name} from {directory}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


_records = _import_script("_records", _HOOKS_SCRIPTS)

# The summary is a VRP long-form impression: >= 400 chars, >= 3 sentences.
SUMMARY_PREFIXES = {"ok": "inspected:", "not_applicable": "skipped:", "error": "error:"}
_SUMMARY_PREFIX = SUMMARY_PREFIXES
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
    """Return a problem string when the summary fails the impression rule."""
    errors = _records.impression_errors(summary)
    return "; ".join(errors) if errors else None


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
            # Validate the text after the `inspected:` prefix — the prefix is
            # an envelope marker, not part of the impression.
            prose = _summary_is_prose(summary.removeprefix(prefix or "").strip())
            if prose is not None:
                problems.append(prose)
    detail = record.get("detail")
    if status == "ok":
        _validate_detail(detail, problems)
    elif detail is not None:
        problems.append("detail must be omitted for not_applicable/error")
    return problems


def _source_event_for(root: Path, image_sha: str) -> str | None:
    """event_id of a vision tool event or image observation bound to image_sha."""
    directory = root / "observations" / "bard"
    for name in ("vision-tool-events.jsonl", "image-observations.jsonl"):
        records, _malformed = _records.load_jsonl(directory / name)
        for record in records:
            if record.get("image_sha256") == image_sha:
                event_id = record.get("event_id")
                if isinstance(event_id, str):
                    return event_id
    return None


def record_review(
    record: dict[str, Any], review_path: Path, root: Path
) -> dict[str, Any]:
    """Mirror a validated ok-review into vision-reviews.jsonl via bard_records."""
    bard_records = _import_script("bard_records", _PLUGIN_SCRIPTS)
    detail = record["detail"]
    image_sha = str(detail["image_sha256"])
    image_ref = str(detail["image_path"])
    image = Path(image_ref)
    if not image.is_absolute():
        # detail.image_path is workspace-relative; fall back to the review's
        # directory only when the workspace-relative path does not exist.
        candidate = (root.resolve() / image).resolve()
        image = (
            candidate if candidate.is_file() else (review_path.parent / image).resolve()
        )
    try:
        relative_image = image.relative_to(root.resolve()).as_posix()
    except ValueError:
        relative_image = image_ref
    payload: dict[str, Any] = {
        "model": detail["model"],
        "checklist": "score-engraving",
        "findings": [
            {
                "category": f.get("category", "other"),
                "severity": f.get("severity", "info"),
                "note": f.get("note", ""),
            }
            for f in detail.get("findings") or []
        ],
        "impression": str(record["summary"]).removeprefix("inspected:").strip(),
    }
    source = _source_event_for(root, image_sha)
    if source is not None:
        payload["source_event_id"] = source
    else:
        payload["image_path"] = relative_image
    payload["findings"].append(
        {
            "category": "artifacts",
            "severity": "info",
            "note": "covers song.abc engraving and score.png render",
        }
    )
    return bard_records.record_vision_review(payload, root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a score-review.json record against the vision_review contract."
        )
    )
    parser.add_argument("review", type=Path, help="path to score-review.json")
    parser.add_argument("--json", action="store_true", help="emit a JSON verdict")
    parser.add_argument(
        "--record",
        action="store_true",
        help="when the review validates with status ok, append the matching "
        "VRP vision review to observations/bard/vision-reviews.jsonl",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="workspace root for --record (default: OPENHANDS_PROJECT_DIR or cwd)",
    )
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
    recorded: dict[str, Any] | None = None
    if (
        not problems
        and args.record
        and isinstance(record, dict)
        and record.get("status") == "ok"
    ):
        root = args.root or Path.cwd()
        try:
            recorded = record_review(record, args.review, root)
        except (ValueError, OSError) as exc:
            problems = [f"record vision-review failed: {exc}"]
    if args.json:
        print(
            json.dumps(
                {"ok": not problems, "problems": problems, "recorded": recorded},
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
