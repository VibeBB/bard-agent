"""Emit an advisory `song.lint.json` for a rendered proposal.

The lint inspects the *emitted* MIDI for residual melody/accompaniment
clashes (minor-9th / major-7th pitch-class offsets) and reports the
deterministic re-voicing adjustments `render_song` applied. It is a
review aid only — never a gate, never a verdict on the proposal.

Python 3.12+, standard library only.

Usage:
    lint_score.py --proposal song.proposal.json [--mid song.mid]
                [--out song.lint.json] [--json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

# render_song.py lives next to this script but is not an installed package.
_RENDER_PATH = Path(__file__).resolve().with_name("render_song.py")
_spec = importlib.util.spec_from_file_location("render_song", _RENDER_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load render_song module from {_RENDER_PATH}")
render_song = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("render_song", render_song)
_spec.loader.exec_module(render_song)


def _report_error(source: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "artifact_kind": "score_lint",
        "authority": "none",
        "schema_version": "1.0",
        "kind": "score_lint",
        "source": source,
        "verdict": "fail",
        "errors": len(reasons),
        "warnings": 0,
        "notes_checked": 0,
        "voicing": {"substituted": 0, "dropped": 0, "substitutions": []},
        "findings": [
            {
                "type": "lint_error",
                "severity": "error",
                "description": reason,
            }
            for reason in reasons
        ],
    }


def run(proposal_path: Path, mid_path: Path | None) -> dict[str, Any]:
    source = proposal_path.name
    try:
        raw_text = proposal_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as e:
        return _report_error(source, [f"proposal: cannot read or parse JSON: {e}"])
    try:
        song = render_song.validate_proposal(data)
    except render_song.ProposalError as e:
        return _report_error(source, [f"proposal rejected: {r}" for r in e.reasons])
    if mid_path is None:
        default = proposal_path.parent / "song.mid"
        mid_path = default if default.is_file() else None
    if mid_path is None:
        midi = render_song.render_midi(song)
    else:
        try:
            midi = mid_path.read_bytes()
        except OSError as e:
            return _report_error(source, [f"midi: cannot read: {e}"])
    try:
        return render_song.lint_song(song, midi, source=source)
    except render_song.ProposalError as e:
        return _report_error(source, e.reasons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument(
        "--mid",
        type=Path,
        default=None,
        help="rendered song.mid to lint; defaults to song.mid next to the "
        "proposal, else the MIDI is re-rendered in memory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the report JSON here instead of stdout-only",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as one JSON object (default: findings lines)",
    )
    args = parser.parse_args(argv)

    report = run(args.proposal, args.mid)

    if args.out is not None:
        try:
            args.out.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            report = _report_error(report["source"], [f"lint: cannot write: {e}"])

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(
            f"score lint: {report['verdict']} "
            f"({report['errors']} errors, {report['warnings']} warnings, "
            f"{report['notes_checked']} notes checked)"
        )
        for f in report["findings"]:
            print(f"  {f['severity']}: {f['type']}: {f['description']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
