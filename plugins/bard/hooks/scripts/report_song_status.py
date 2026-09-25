#!/usr/bin/env python3
"""Report song-artifact render and score-review status when an agent stops.

Reads the stop-hook event on stdin, scans `songs/*/song.proposal.json`
under the working directory, and reports each proposal as rendered (a
valid `song.provenance.json` exists next to it) or unrendered. Unrendered
proposals are surfaced so the agent states the render verdict explicitly
before finishing. It also scans for `score.png` images that lack a valid
sibling `score-review.json` — the score visual check is a required step,
so an image without a passing review record is surfaced as well.

Python standard library only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

PROPOSAL_NAME = "song.proposal.json"
PROVENANCE_NAME = "song.provenance.json"
PROVENANCE_KIND = "bard_song_provenance"
SCORE_PNG_NAME = "score.png"
REVIEW_NAME = "score-review.json"
SKIP_DIRECTORIES = {".git", ".venv", "node_modules"}
MAX_DEPTH = 4


def _load_review_validator() -> Any:
    """Import the skill's score-review validator; None when unavailable."""
    script = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "bard-render"
        / "scripts"
        / "validate_score_review.py"
    )
    if not script.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("validate_score_review", script)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - the hook degrades, never crashes
        return None
    return module.validate


_validate_review = _load_review_validator()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _score_review_problems(out_dir: Path) -> list[str] | None:
    """Problems with the score review in out_dir, or None when no score.png."""
    score = out_dir / SCORE_PNG_NAME
    if not score.is_file():
        return None
    review = out_dir / REVIEW_NAME
    if not review.is_file():
        return [f"{score}: no score-review.json (score vision review is required)"]
    try:
        record = json.loads(review.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{score}: unreadable score-review.json ({exc})"]
    if _validate_review is None:
        return []
    return [f"{score}: {problem}" for problem in _validate_review(record)]


def _is_rendered(out_dir: Path) -> bool:
    provenance = out_dir / PROVENANCE_NAME
    if not provenance.is_file():
        return False
    value = _read_json(provenance)
    if not isinstance(value, dict):
        raise ValueError(f"invalid provenance shape in {provenance}")
    if value.get("artifact_kind") != PROVENANCE_KIND:
        raise ValueError(f"unexpected artifact_kind in {provenance}")
    return True


def _find_proposals(root: Path) -> list[Path]:
    proposals: list[Path] = []
    search_root = root / "songs"
    if not search_root.is_dir():
        return proposals
    for path in search_root.rglob(PROPOSAL_NAME):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) > MAX_DEPTH:
            continue
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        if path.is_file():
            proposals.append(path)
    return sorted(proposals)


def main() -> int:
    try:
        event = json.load(sys.stdin)
        working_dir = Path(event.get("working_dir") or os.getcwd()).resolve()
        statuses: list[tuple[str, bool]] = []
        review_problems: list[str] = []
        for proposal in _find_proposals(working_dir):
            # Parse the proposal first so unreadable files fail closed.
            _read_json(proposal)
            statuses.append((str(proposal), _is_rendered(proposal.parent)))
            review_problems.extend(_score_review_problems(proposal.parent) or [])
        if statuses:
            lines = [
                f"{path}: rendered={str(rendered).lower()}"
                for path, rendered in statuses
            ]
            unrendered = [path for path, rendered in statuses if not rendered]
            if unrendered:
                lines.append(
                    "Before finishing, state the render verdict explicitly for: "
                    + ", ".join(unrendered)
                )
            if review_problems:
                lines.append("Score vision review required (never optional):")
                lines.extend(review_problems)
            context = "\n".join(lines)
        elif not working_dir.is_dir():
            context = (
                f"working_dir {working_dir} does not exist; "
                "cannot scan for song proposals."
            )
        elif not (working_dir / "songs").is_dir():
            context = f"No songs directory under {working_dir} (no songs written)."
        else:
            context = f"No song proposals found under {working_dir}/songs."
        print(json.dumps({"decision": "allow", "additionalContext": context}))
        return 0
    except Exception as exc:  # noqa: BLE001 - report and fail closed
        print(f"report_song_status: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
