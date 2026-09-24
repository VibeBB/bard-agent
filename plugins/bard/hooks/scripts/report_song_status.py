#!/usr/bin/env python3
"""Report song-artifact render status when an agent stops.

Reads the stop-hook event on stdin, scans `songs/*/song.proposal.json`
under the working directory, and reports each proposal as rendered (a
valid `song.provenance.json` exists next to it) or unrendered. Unrendered
proposals are surfaced so the agent states the render verdict explicitly
before finishing.

Python standard library only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROPOSAL_NAME = "song.proposal.json"
PROVENANCE_NAME = "song.provenance.json"
PROVENANCE_KIND = "bard_song_provenance"
SKIP_DIRECTORIES = {".git", ".venv", "node_modules"}
MAX_DEPTH = 4


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
        for proposal in _find_proposals(working_dir):
            # Parse the proposal first so unreadable files fail closed.
            _read_json(proposal)
            statuses.append((str(proposal), _is_rendered(proposal.parent)))
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
