"""Tests for the bard plugin stop hook scripts."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "plugins"
    / "bard"
    / "hooks"
    / "scripts"
    / "report_song_status.py"
)


def _write_proposal(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "artifact_kind": "bard_song_proposal",
                "schema_version": "0.3",
            }
        ),
        encoding="utf-8",
    )


def _write_provenance(out_dir: Path) -> None:
    (out_dir / "song.provenance.json").write_text(
        json.dumps(
            {
                "artifact_kind": "bard_song_provenance",
                "authority": "none",
            }
        ),
        encoding="utf-8",
    )


def _run_hook(working_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps({"working_dir": str(working_dir)}),
        text=True,
        capture_output=True,
        check=False,
    )


def test_report_song_status_rendered_and_unrendered(tmp_path: Path) -> None:
    rendered = tmp_path / "out" / "bard" / "done-ja"
    unrendered = tmp_path / "out" / "bard" / "pending-en"
    _write_proposal(rendered / "song.proposal.json")
    _write_provenance(rendered)
    _write_proposal(unrendered / "song.proposal.json")

    result = _run_hook(tmp_path)

    assert result.returncode == 0
    context = json.loads(result.stdout)["additionalContext"]
    assert "rendered=true" in context
    assert "rendered=false" in context
    assert "state the render verdict explicitly" in context
    assert str(unrendered / "song.proposal.json") in context


def test_report_song_status_none(tmp_path: Path) -> None:
    result = _run_hook(tmp_path)

    assert result.returncode == 0
    assert "No out/bard directory" in json.loads(result.stdout)["additionalContext"]


def test_report_song_status_empty_out_bard(tmp_path: Path) -> None:
    (tmp_path / "out" / "bard").mkdir(parents=True)

    result = _run_hook(tmp_path)

    assert result.returncode == 0
    assert "No song proposals found" in json.loads(result.stdout)["additionalContext"]


def test_report_song_status_missing_working_dir(tmp_path: Path) -> None:
    result = _run_hook(tmp_path / "nonexistent")

    assert result.returncode == 0
    assert "does not exist" in json.loads(result.stdout)["additionalContext"]


def test_report_song_status_malformed_proposal(tmp_path: Path) -> None:
    proposal = tmp_path / "out" / "bard" / "bad-ja" / "song.proposal.json"
    proposal.parent.mkdir(parents=True)
    proposal.write_text("{not-json", encoding="utf-8")

    result = _run_hook(tmp_path)

    assert result.returncode == 1
    assert "report_song_status:" in result.stderr


def test_report_song_status_malformed_provenance(tmp_path: Path) -> None:
    out_dir = tmp_path / "out" / "bard" / "odd-en"
    _write_proposal(out_dir / "song.proposal.json")
    (out_dir / "song.provenance.json").write_text(
        json.dumps({"artifact_kind": "something_else"}),
        encoding="utf-8",
    )

    result = _run_hook(tmp_path)

    assert result.returncode == 1
    assert "report_song_status:" in result.stderr
