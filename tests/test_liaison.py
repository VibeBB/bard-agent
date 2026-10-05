"""Tests for bard_liaison.py (SLP v2 request/response mirror)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIAISON_PATH = REPO_ROOT / "plugins" / "bard" / "scripts" / "bard_liaison.py"


@pytest.fixture()
def liaison() -> Any:
    spec = importlib.util.spec_from_file_location("bard_liaison", LIAISON_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bard_liaison"] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request(root: Path, **over: Any) -> dict[str, Any]:
    input_file = root / "brief.md"
    input_file.write_text("the product brief", encoding="utf-8")
    req = {
        "schema_version": 2,
        "system": "ux-creator",
        "id": "cue-pack",
        "target_agent": "bard",
        "stage": "design",
        "risk": "low",
        "purpose": "Design a startup and completion cue pair for the kettle",
        "rationale": "the UX plan calls for sound feedback on every job",
        "requested_changes": ["two cues"],
        "inputs": [{"path": "brief.md", "sha256": _sha(input_file)}],
        "expected_deliverables": ["cues.json"],
        "acceptance": ["cues play on a piezo"],
        "depends_on": [],
        "created_at": "2026-10-01T12:00:00+00:00",
    }
    req.update(over)
    return req


def _write_request(root: Path, name: str, req: dict[str, Any]) -> Path:
    path = root / f"{name}.ux-request.json"
    path.write_text(json.dumps(req), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# request validation


def test_valid_request(liaison: Any, tmp_path: Path) -> None:
    req, reasons, _warnings = liaison.validate_request(
        _request(tmp_path), "cue-pack", tmp_path
    )
    assert req is not None
    assert reasons == []


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"schema_version": 1}, "schema_version"),
        ({"system": "other"}, "system"),
        ({"id": "Bad Slug!"}, "id"),
        ({"stage": "nope"}, "stage"),
        ({"risk": "medium"}, "risk"),
        ({"purpose": "too short"}, "purpose"),
        ({"requested_changes": []}, "requested_changes"),
        ({"expected_deliverables": []}, "expected_deliverables"),
        ({"acceptance": []}, "acceptance"),
        ({"created_at": "not a date"}, "created_at"),
        ({"depends_on": ["cue-pack"]}, "depends_on"),
    ],
)
def test_invalid_requests(
    liaison: Any, tmp_path: Path, override: dict[str, Any], match: str
) -> None:
    req, reasons, _w = liaison.validate_request(
        _request(tmp_path, **override), "cue-pack", tmp_path
    )
    assert req is None
    assert any(match in r for r in reasons)


def test_request_unknown_key_rejected(liaison: Any, tmp_path: Path) -> None:
    req, reasons, _w = liaison.validate_request(
        _request(tmp_path, extra_key=1), "cue-pack", tmp_path
    )
    assert req is None
    assert any("unknown" in r for r in reasons)


def test_request_input_bad_sha(liaison: Any, tmp_path: Path) -> None:
    req, reasons, _w = liaison.validate_request(
        _request(tmp_path, inputs=[{"path": "brief.md", "sha256": "zz"}]),
        "cue-pack",
        tmp_path,
    )
    assert req is None
    assert any("sha256" in r for r in reasons)


def test_request_input_escape(liaison: Any, tmp_path: Path) -> None:
    req, reasons, _w = liaison.validate_request(
        _request(tmp_path, inputs=[{"path": "../x", "sha256": "a" * 64}]),
        "cue-pack",
        tmp_path,
    )
    assert req is None
    assert any("workspace" in r or "escape" in r for r in reasons)


def test_high_risk_needs_rationale_and_job_id(liaison: Any, tmp_path: Path) -> None:
    ux = tmp_path / "plan.ux.json"
    ux.write_text(json.dumps({"jobs": [{"id": "jtbd-1"}]}), encoding="utf-8")
    base = _request(
        tmp_path,
        risk="high",
        rationale="this cue affects safety signaling on the product",
        inputs=[{"path": "plan.ux.json", "sha256": _sha(ux)}],
    )
    req, _r, warnings = liaison.validate_request(base, "cue-pack", tmp_path)
    assert req is not None
    assert liaison.JOB_ID_WARNING in warnings
    cited = dict(base)
    cited["rationale"] = "covers job jtbd-1 signaling feedback"
    req2, _, warnings2 = liaison.validate_request(cited, "cue-pack", tmp_path)
    assert req2 is not None
    assert warnings2 == []
    short = dict(base)
    short["rationale"] = "short"
    req3, reasons3, _ = liaison.validate_request(short, "cue-pack", tmp_path)
    assert req3 is None
    assert any("rationale" in r for r in reasons3)


# ---------------------------------------------------------------------------
# inbox states


def test_inbox_new(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    report = liaison.inbox(tmp_path)
    assert report["requests"][0]["state"] == "new"


def test_inbox_ignores_other_targets(liaison: Any, tmp_path: Path) -> None:
    req = _request(tmp_path, target_agent="mechanical")
    _write_request(tmp_path, "other", req)
    assert liaison.inbox(tmp_path)["requests"] == []


def test_inbox_malformed(liaison: Any, tmp_path: Path) -> None:
    (tmp_path / "bad.ux-request.json").write_text("{oops", encoding="utf-8")
    req = _request(tmp_path, stage="bogus")
    _write_request(tmp_path, "cue-pack", req)
    report = liaison.inbox(tmp_path)
    paths = {m["path"] for m in report["malformed"]}
    assert "bad.ux-request.json" in paths
    assert "cue-pack.ux-request.json" in paths


def test_inbox_blocked_by_dependency(liaison: Any, tmp_path: Path) -> None:
    req = _request(tmp_path, depends_on=["missing-dep"])
    _write_request(tmp_path, "cue-pack", req)
    report = liaison.inbox(tmp_path)
    assert report["requests"][0]["state"] == "blocked"


def test_inbox_stale_input_changed(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    (tmp_path / "brief.md").write_text("edited", encoding="utf-8")
    report = liaison.inbox(tmp_path)
    assert report["requests"][0]["state"] == "stale"


def test_inbox_answered_and_stale_response(liaison: Any, tmp_path: Path) -> None:
    path = _write_request(tmp_path, "cue-pack", _request(tmp_path))
    response = _write_response(
        tmp_path, "cue-pack", {"brief.md": _sha(tmp_path / "brief.md")}
    )
    report = liaison.inbox(tmp_path)
    assert report["requests"][0]["state"] == "answered"
    (tmp_path / "brief.md").write_text("edited", encoding="utf-8")
    report = liaison.inbox(tmp_path)
    assert report["requests"][0]["state"] == "stale"
    assert path.is_file() and response.is_file()


def test_inbox_malformed_response_counts_as_unanswered(
    liaison: Any, tmp_path: Path
) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    (tmp_path / "cue-pack.ux-response.json").write_text("{bad", encoding="utf-8")
    report = liaison.inbox(tmp_path)
    assert report["requests"][0]["state"] == "new"
    assert any(m["path"] == "cue-pack.ux-response.json" for m in report["malformed"])


def _write_response(root: Path, stem: str, input_hashes: dict[str, str]) -> Path:
    path = root / f"{stem}.ux-response.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "system": "ux-creator",
                "request": "cue-pack",
                "responder": "bard",
                "status": "done",
                "reason": "cues rendered and read back for the request",
                "input_hashes": input_hashes,
                "artifacts": [{"path": "brief.md", "sha256": _sha(root / "brief.md")}],
                "gate_verdicts": [{"gate": "cue-set-contract", "verdict": "pass"}],
                "decision_refs": ["d" * 64],
                "impression_refs": ["e" * 64],
                "questions_for_user": [],
                "responded_at": "2026-10-01T13:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# respond


def _respond_payload(tmp_path: Path) -> dict[str, Any]:
    return {
        "request": "cue-pack.ux-request.json",
        "status": "needs_info",
        "reason": "the acceptance criteria do not name a device family",
        "artifacts": [],
        "gate_verdicts": [],
        "decision_refs": [],
        "impression_refs": [],
        "questions_for_user": ["piezo or speaker?"],
    }


def test_respond_happy_path(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    out = liaison.respond(_respond_payload(tmp_path), root=tmp_path)
    response_path = tmp_path / "cue-pack.ux-response.json"
    assert response_path.is_file()
    written = json.loads(response_path.read_text(encoding="utf-8"))
    assert written["status"] == "needs_info"
    assert written["input_hashes"]["brief.md"] == _sha(tmp_path / "brief.md")
    assert out["verdict"] == "pass"


def test_respond_rejects_short_reason(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload["reason"] = "no"
    with pytest.raises(ValueError, match="reason"):
        liaison.respond(payload, root=tmp_path)


def test_respond_done_with_fail_verdict(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload.update(
        status="done",
        reason="claimed done but a gate failed",
        artifacts=["brief.md"],
        gate_verdicts=[{"gate": "readback", "verdict": "fail"}],
        decision_refs=["d" * 64],
        impression_refs=["e" * 64],
    )
    with pytest.raises(ValueError, match="needs_info or rejected"):
        liaison.respond(payload, root=tmp_path)


def test_respond_done_with_unknown_verdict(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload.update(
        status="done",
        reason="claimed done but a gate is unknown",
        artifacts=["brief.md"],
        gate_verdicts=[{"gate": "score-review", "verdict": "unknown"}],
        decision_refs=["d" * 64],
        impression_refs=["e" * 64],
    )
    with pytest.raises(ValueError, match="refusing done"):
        liaison.respond(payload, root=tmp_path)


def test_respond_done_requires_refs_and_artifact(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload.update(
        status="done",
        reason="claimed done without evidence paths",
        artifacts=["brief.md"],
    )
    with pytest.raises(ValueError, match="decision_ref"):
        liaison.respond(payload, root=tmp_path)
    payload["decision_refs"] = ["d" * 64]
    with pytest.raises(ValueError, match="impression_ref"):
        liaison.respond(payload, root=tmp_path)


def test_respond_ref_must_exist_in_log(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload["decision_refs"] = ["f" * 64]
    payload["impression_refs"] = []
    payload["status"] = "accepted"
    payload["reason"] = ""
    with pytest.raises(ValueError, match="decisions.jsonl"):
        liaison.respond(payload, root=tmp_path)


def test_respond_missing_artifact(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload["artifacts"] = ["nope/missing.json"]
    with pytest.raises(ValueError, match="does not exist"):
        liaison.respond(payload, root=tmp_path)


def test_respond_artifact_escape(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload["artifacts"] = ["../escape.json"]
    with pytest.raises(ValueError):
        liaison.respond(payload, root=tmp_path)


def test_respond_unknown_key(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = _respond_payload(tmp_path)
    payload["bogus"] = 1
    with pytest.raises(ValueError, match="unknown keys"):
        liaison.respond(payload, root=tmp_path)


def test_respond_accepts_bare_request_id(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = {**_respond_payload(tmp_path), "request": "cue-pack"}
    out = liaison.respond(payload, root=tmp_path)
    assert out["verdict"] == "pass"
    assert (tmp_path / "cue-pack.ux-response.json").is_file()


def test_respond_bare_id_without_request_file(liaison: Any, tmp_path: Path) -> None:
    payload = {**_respond_payload(tmp_path), "request": "missing-pack"}
    with pytest.raises(ValueError, match="no request file"):
        liaison.respond(payload, root=tmp_path)
