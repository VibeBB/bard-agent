"""Tests for the bard plugin hook scripts (stop + session_start doctor)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).parents[1] / "plugins" / "bard"
SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "report_song_status.py"
DOCTOR_SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "bard_doctor.py"


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
    rendered = tmp_path / "songs" / "done-ja"
    unrendered = tmp_path / "songs" / "pending-en"
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
    assert "No songs directory" in json.loads(result.stdout)["additionalContext"]


def test_report_song_status_empty_songs(tmp_path: Path) -> None:
    (tmp_path / "songs").mkdir(parents=True)

    result = _run_hook(tmp_path)

    assert result.returncode == 0
    assert "No song proposals found" in json.loads(result.stdout)["additionalContext"]


def test_report_song_status_missing_working_dir(tmp_path: Path) -> None:
    result = _run_hook(tmp_path / "nonexistent")

    assert result.returncode == 0
    assert "does not exist" in json.loads(result.stdout)["additionalContext"]


def test_report_song_status_malformed_proposal(tmp_path: Path) -> None:
    proposal = tmp_path / "songs" / "bad-ja" / "song.proposal.json"
    proposal.parent.mkdir(parents=True)
    proposal.write_text("{not-json", encoding="utf-8")

    result = _run_hook(tmp_path)

    assert result.returncode == 1
    assert "report_song_status:" in result.stderr


def test_report_song_status_malformed_provenance(tmp_path: Path) -> None:
    out_dir = tmp_path / "songs" / "odd-en"
    _write_proposal(out_dir / "song.proposal.json")
    (out_dir / "song.provenance.json").write_text(
        json.dumps({"artifact_kind": "something_else"}),
        encoding="utf-8",
    )

    result = _run_hook(tmp_path)

    assert result.returncode == 1
    assert "report_song_status:" in result.stderr


def _run_doctor(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DOCTOR_SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_bard_doctor_resolves_plugin_root(tmp_path: Path) -> None:
    env = {
        "BARD_PLUGIN_ROOT": str(PLUGIN_ROOT),
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
    }

    result = _run_doctor(env)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allow"
    assert "plugin layout ok" in payload["additionalContext"]
    assert str(PLUGIN_ROOT) in payload["additionalContext"]


def test_bard_doctor_unresolved_root_is_advisory(tmp_path: Path) -> None:
    env = {
        "OPENHANDS_PROJECT_DIR": str(tmp_path),
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
    }

    result = _run_doctor(env)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allow"
    assert "unresolved" in payload["additionalContext"]


SAFETY_RAIL_SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "safety_rail.py"


def _run_safety_rail(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SAFETY_RAIL_SCRIPT)],
        input=json.dumps({"tool_name": "terminal", "tool_input": {"command": command}}),
        text=True,
        capture_output=True,
        check=False,
    )


def test_safety_rail_denies_denylist() -> None:
    for command in (
        "rm -rf /",
        "rm -fr ~",
        "dd if=x of=/dev/sda",
        "mkfs.ext4 /dev/sda1",
        "shutdown now",
        "git push origin main",
        "git push --force origin feat",
        "git reset --hard",
        "git clean -fd",
        "git checkout -- plugins/bard/agents/bard.md",
        "git stash drop",
        "git add .",
        "git commit --amend",
        "git commit --no-verify",
    ):
        assert _run_safety_rail(command).returncode == 2, command


def test_safety_rail_allows_normal_commands() -> None:
    for command in (
        "rm -rf out/bard",
        "git push --force-with-lease origin feat",
        "git push origin feat",
        "git add plugins/bard/agents/bard.md docs",
        "git commit -m message",
        "python scripts/render.py",
        "echo hi > out.txt",
        "find . -name '*.proposal.json'",
    ):
        assert _run_safety_rail(command).returncode == 0, command


ENSURE_PROFILES_SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "ensure_llm_profiles.py"


def test_ensure_llm_profiles_provisions(tmp_path: Path) -> None:
    """The session_start hook clones active_profile into vibebb-* slots."""
    home = tmp_path / "home"
    profiles = home / ".openhands" / "profiles"
    profiles.mkdir(parents=True)
    (home / ".openhands" / "settings.json").write_text(
        json.dumps({"active_profile": "test-model"}), encoding="utf-8"
    )
    template = {"schema_version": 1, "model": "test-model", "auth_type": "api_key"}
    (profiles / "test-model.json").write_text(json.dumps(template), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ENSURE_PROFILES_SCRIPT)],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["missing"] == []
    for name in ("vibebb-author", "vibebb-review"):
        profile = json.loads((profiles / f"{name}.json").read_text(encoding="utf-8"))
        assert profile["model"] == "test-model"
    # Idempotent: a second run provisions nothing and still reports ok.
    proc2 = subprocess.run(
        [sys.executable, str(ENSURE_PROFILES_SCRIPT)],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert json.loads(proc2.stdout)["findings"] == []


def test_ensure_llm_profiles_tolerates_missing_settings(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(ENSURE_PROFILES_SCRIPT)],
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path / "nohome"), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["missing"] == ["vibebb-author", "vibebb-review"]


IMAGE_OBS_SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "record_image_observation.py"
VISION_EVENT_SCRIPT = PLUGIN_ROOT / "hooks" / "scripts" / "record_vision_tool_event.py"


def _write_score_png(out_dir: Path) -> None:
    (out_dir / "score.png").write_bytes(b"\x89PNG fake")


def _write_review(out_dir: Path, status: str = "ok") -> None:
    summary = (
        "inspected: the engraving reads cleanly; chord labels sit above "
        "each measure and syllables align under their notes without "
        "collisions anywhere. Bar lines are well formed and the title "
        "block is legible; only the bar-three label is a little cramped."
    )
    record: dict[str, Any] = {
        "artifact_kind": "bard_score_review",
        "authority": "none",
        "tool": "vision_review",
        "stage": "review",
        "status": status,
        "summary": summary if status == "ok" else f"{status}: reason",
        "artifacts": ["score.png"],
        "checked_at": "2026-09-25T00:00:00+00:00",
    }
    if status == "ok":
        record["detail"] = {
            "image_path": "score.png",
            "image_sha256": "a" * 64,
            "model": "test-model",
            "checklist": "score_engraving",
            "findings": [],
        }
    (out_dir / "score-review.json").write_text(json.dumps(record), encoding="utf-8")


def test_report_song_status_flags_unreviewed_score(tmp_path: Path) -> None:
    song = tmp_path / "songs" / "x"
    _write_proposal(song / "song.proposal.json")
    _write_provenance(song)
    _write_score_png(song)

    result = _run_hook(tmp_path)

    assert result.returncode == 0
    context = json.loads(result.stdout)["additionalContext"]
    assert "score-review.json" in context
    assert "required" in context


def test_report_song_status_flags_thin_review(tmp_path: Path) -> None:
    song = tmp_path / "songs" / "x"
    _write_proposal(song / "song.proposal.json")
    _write_provenance(song)
    _write_score_png(song)
    (song / "score-review.json").write_text(
        json.dumps({"artifact_kind": "bard_score_review", "status": "ok"}),
        encoding="utf-8",
    )

    result = _run_hook(tmp_path)

    context = json.loads(result.stdout)["additionalContext"]
    assert "score.png" in context


def test_report_song_status_clean_review_not_flagged(tmp_path: Path) -> None:
    song = tmp_path / "songs" / "x"
    _write_proposal(song / "song.proposal.json")
    _write_provenance(song)
    _write_score_png(song)
    _write_review(song)

    result = _run_hook(tmp_path)

    context = json.loads(result.stdout)["additionalContext"]
    assert "Score vision review required" not in context


def test_record_image_observation_records_actor(tmp_path: Path) -> None:
    image = tmp_path / "score.png"
    image.write_bytes(b"\x89PNG fake")
    events = tmp_path / "obs.jsonl"
    env = dict(os.environ, BARD_IMAGE_OBSERVATIONS=str(events))
    payload = {
        "tool_name": "file_editor",
        "tool_input": {"command": "view", "path": str(image)},
        "tool_response": {"ok": True},
        "working_dir": str(tmp_path),
        "session_id": "s1",
        "agent": "bard",
        "action_id": "act-9",
    }
    result = subprocess.run(
        [sys.executable, str(IMAGE_OBS_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    record = json.loads(events.read_text(encoding="utf-8").splitlines()[0])
    assert record["actor"]["agent"] == "bard"
    assert record["tool_call_id"] == "act-9"


def test_record_vision_tool_event_records_actor(tmp_path: Path) -> None:
    events = tmp_path / "obs.jsonl"
    env = dict(os.environ, BARD_VISION_TOOL_EVENTS=str(events))
    payload = {
        "tool_name": "inspect_image_with_vision",
        "tool_input": {"image_index": 0, "question": "describe"},
        "tool_response": {
            "answer": "a clean score",
            "profile_name": "vibebb-review",
            "model": "m1",
        },
        "working_dir": str(tmp_path),
        "session_id": "s1",
        "subagent_type": "bard-critic",
        "tool_call_id": "tc-4",
    }
    result = subprocess.run(
        [sys.executable, str(VISION_EVENT_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    record = json.loads(events.read_text(encoding="utf-8").splitlines()[0])
    assert record["actor"]["subagent_type"] == "bard-critic"
    assert record["tool_call_id"] == "tc-4"
