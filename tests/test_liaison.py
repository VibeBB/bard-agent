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


def test_respond_refuses_refs_into_broken_chain(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    log = tmp_path / "observations" / "bard" / "decisions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"event_id": "f" * 64}) + "\n", encoding="utf-8")
    payload = _respond_payload(tmp_path)
    payload["decision_refs"] = ["f" * 64]
    payload["impression_refs"] = []
    payload["status"] = "accepted"
    payload["reason"] = ""
    with pytest.raises(ValueError, match="fails integrity"):
        liaison.respond(payload, root=tmp_path)


def test_records_heads_are_genesis_then_skip_a_broken_chain(
    liaison: Any, tmp_path: Path
) -> None:
    records = liaison._records
    heads, broken = liaison._records_heads(tmp_path)
    assert broken == []
    assert heads == dict.fromkeys(records.LOG_FILES, records.GENESIS)
    log = tmp_path / liaison.RECORDS_DIR / records.LOG_FILES["upstream_read"]
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        '{"schema_version": 2, "event_id": "' + "1" * 64 + '"}\n', encoding="utf-8"
    )
    heads, broken = liaison._records_heads(tmp_path)
    assert broken == ["upstream_read"]
    assert "upstream_read" not in heads


@pytest.fixture()
def cue_delivery(
    liaison: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Use real renderer and VRP writers; no acceptance checks are mocked."""
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    request_path = _write_request(tmp_path, "cue-pack", _request(tmp_path))
    render_path = REPO_ROOT / "plugins/bard/skills/bard-render/scripts/render_cues.py"
    spec = importlib.util.spec_from_file_location("delivery_renderer", render_path)
    assert spec is not None and spec.loader is not None
    renderer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = renderer
    spec.loader.exec_module(renderer)
    data = json.loads(
        (render_path.parent.parent / "examples/smart-kettle.cues.json").read_text(
            encoding="utf-8"
        )
    )
    data["sources"] = [
        {"kind": "ux_request", "ref": request_path.name, "sha256": _sha(request_path)}
    ]
    out = tmp_path / "cues"
    out.mkdir()
    proposal = out / "cues.proposal.json"
    proposal.write_text(json.dumps(data), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "delivery_records", REPO_ROOT / "plugins/bard/scripts/bard_records.py"
    )
    assert spec is not None and spec.loader is not None
    records = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(records)
    decision = records.record_decision(
        {
            "id": "cue-patterns",
            "stage": "design",
            "question": "Which cue patterns should the kettle expose?",
            "principles": ["distinct product feedback", "bounded cue durations"],
            "options": [
                {"name": "one-tone", "pros": ["simple"], "cons": ["ambiguous"]},
                {"name": "distinct", "pros": ["recognizable"], "cons": ["more notes"]},
            ],
            "chosen": "distinct",
            "rationale": (
                "Use distinct rising notes for completion and an interrupted warning "
                "pattern for overheat. This keeps confirmation short and makes the "
                "warning recognizable without depending on a high fundamental."
                " Hardware measurements must verify the physical sound pressure."
            ),
            "evidence": [{"path": "cues/cues.proposal.json"}],
            "risks": ["physical audibility still needs measurement"],
            "revisit_when": "listening measurements change",
        },
        root=tmp_path,
    )["record"]
    assert renderer.main(["--cues", str(proposal), "--out-dir", str(out)]) == 0
    impression = records.record_impression(
        {
            "stage": "export",
            "artifacts": ["cues/cues.proposal.json"],
            "impression": (
                "The smart-kettle proposal separates startup, completion, warning and "
                "confirmation into four named patterns for independent checking. "
                "The warning alternates notes with rests, while completion uses a "
                "rising interval, so the source structures are different. A firmware "
                "developer can read tone tables without parsing MIDI, although source "
                "inspection says nothing about physical sound pressure. The next "
                "step is readback and hardware listening measurement."
            ),
            "facets": {
                "observed": ["smart-kettle has four cues", "warning includes rests"],
                "works": ["tone tables expose timing"],
                "concerns": [
                    {
                        "id": "sound-level",
                        "text": "physical sound level is unmeasured",
                        "severity": "warning",
                        "about": "self",
                    }
                ],
                "feelings": {
                    "maker": "can consume the tone tables",
                    "user": "needs audible feedback",
                },
                "next_actions": ["measure the selected buzzer"],
            },
            "claims": [
                {
                    "text": "proposal names the product",
                    "anchor": "smart-kettle",
                    "artifact": "cues/cues.proposal.json",
                },
                {
                    "text": "startup includes this pitch",
                    "anchor": "c6",
                    "artifact": "cues/cues.proposal.json",
                },
            ],
            "confidence": "medium",
            "unknowns": ["hardware sound pressure"],
        },
        root=tmp_path,
    )["record"]
    return {
        **_respond_payload(tmp_path),
        "status": "done",
        "reason": "official product cues rendered and read back",
        "artifacts": ["cues/cues.provenance.json"],
        "gate_verdicts": [{"gate": "bard.cue_set_schema", "verdict": "pass"}],
        "decision_refs": [decision["event_id"]],
        "impression_refs": [impression["event_id"]],
    }


def test_done_binds_full_official_bundle(
    liaison: Any, tmp_path: Path, cue_delivery: dict[str, Any]
) -> None:
    results = [liaison.respond(cue_delivery, root=tmp_path) for _ in range(5)]
    artifacts = results[0]["response"]["artifacts"]
    expected = {
        p.relative_to(tmp_path).as_posix() for p in (tmp_path / "cues").iterdir()
    }
    assert {item["path"] for item in artifacts} == expected
    assert len([p for p in expected if p.endswith(".mid")]) == 4
    assert all(item["sha256"] == _sha(tmp_path / item["path"]) for item in artifacts)
    assert all(out["response"]["artifacts"] == artifacts for out in results)
    assert liaison.validate_response(results[0]["response"]) == []


@pytest.mark.parametrize("command", ["cue", "inbox"])
def test_shipped_cue_completion_example(
    liaison: Any, tmp_path: Path, cue_delivery: dict[str, Any], command: str
) -> None:
    text = (REPO_ROOT / f"plugins/bard/commands/{command}.md").read_text(
        encoding="utf-8"
    )
    example = text.split("<<'JSON'\n", 1)[1].split("\n   JSON", 1)[0]
    payload = json.loads(example.replace("cues/<slug>/", "cues/"))
    payload.update(
        request=cue_delivery["request"],
        reason=cue_delivery["reason"],
        decision_refs=cue_delivery["decision_refs"],
        impression_refs=cue_delivery["impression_refs"],
    )
    assert liaison.respond(payload, root=tmp_path)["response"]["status"] == "done"


@pytest.mark.parametrize(
    "mutation",
    [
        "invalid_schema",
        "missing_proof",
        "missing_output",
        "empty_midi",
        "forged_empty_midi",
        "changed_source",
        "changed_request",
        "changed_input",
        "script_hash",
        "outside_source",
        "symlink_output",
        "extra_midi",
        "midi_tempo",
        "mml_timing",
        "manifest_timing",
        "invalid_proof",
        "other_request",
        "missing_timestamp",
    ],
)
def test_done_rejects_bad_cue_evidence_without_overwriting_response(
    liaison: Any, tmp_path: Path, cue_delivery: dict[str, Any], mutation: str
) -> None:
    liaison.respond(cue_delivery, root=tmp_path)
    response_path = tmp_path / "cue-pack.ux-response.json"
    previous = response_path.read_bytes()
    proof_path = tmp_path / "cues/cues.provenance.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    source = tmp_path / "cues/cues.proposal.json"
    midi = tmp_path / "cues/cue-boot.mid"
    if mutation == "invalid_schema":
        data = json.loads(source.read_text(encoding="utf-8"))
        data["driver"] = "placeholder"
        source.write_text(json.dumps(data), encoding="utf-8")
    elif mutation == "missing_proof":
        cue_delivery["artifacts"] = ["brief.md"]
    elif mutation == "missing_output":
        midi.unlink()
    elif mutation in {"empty_midi", "forged_empty_midi"}:
        midi.write_bytes(
            bytes.fromhex("4d546864000000060000000100804d54726b0000000400ff2f00")
        )
        if mutation == "forged_empty_midi":
            proof["outputs"][midi.name] = _sha(midi)
    elif mutation == "changed_source":
        source.write_bytes(source.read_bytes() + b"\n")
    elif mutation == "changed_request":
        request = tmp_path / "cue-pack.ux-request.json"
        request.write_bytes(request.read_bytes() + b"\n")
    elif mutation == "changed_input":
        (tmp_path / "brief.md").write_text("changed requirements", encoding="utf-8")
    elif mutation == "script_hash":
        proof["script_sha256"] = "f" * 64
    elif mutation == "outside_source":
        proof["cue_set"]["path"] = "../outside.proposal.json"
    elif mutation == "symlink_output":
        external = tmp_path.parent / f"{tmp_path.name}-outside.mid"
        external.write_bytes(midi.read_bytes())
        midi.unlink()
        midi.symlink_to(external)
    elif mutation == "extra_midi":
        (tmp_path / "placeholder.mid").write_bytes(b"placeholder")
        cue_delivery["artifacts"].append("placeholder.mid")
    elif mutation == "midi_tempo":
        blob = bytearray(midi.read_bytes())
        tempo = blob.index(b"\xff\x51\x03") + 3
        blob[tempo] ^= 1
        midi.write_bytes(blob)
    elif mutation == "mml_timing":
        mml = tmp_path / "cues/cue-boot.mml"
        mml.write_text(
            mml.read_text(encoding="utf-8").replace("t180", "t181"), encoding="utf-8"
        )
    elif mutation == "manifest_timing":
        manifest_path = tmp_path / "cues/cues.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["cues"][0]["duration_ms"] += 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif mutation == "invalid_proof":
        proof_path.write_text("{broken", encoding="utf-8")
    elif mutation == "other_request":
        data = json.loads(source.read_text(encoding="utf-8"))
        data["sources"][0]["ref"] = "other.ux-request.json"
        source.write_text(json.dumps(data), encoding="utf-8")
    elif mutation == "missing_timestamp":
        proof.pop("generated_at")
    if mutation not in {"invalid_proof"}:
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(ValueError):
        liaison.respond(cue_delivery, root=tmp_path)
    assert response_path.read_bytes() == previous


def test_done_without_proof_writes_no_response(
    liaison: Any, tmp_path: Path, cue_delivery: dict[str, Any]
) -> None:
    cue_delivery["artifacts"] = ["brief.md"]
    with pytest.raises(ValueError, match="cues.provenance.json"):
        liaison.respond(cue_delivery, root=tmp_path)
    assert not (tmp_path / "cue-pack.ux-response.json").exists()


def test_in_progress_does_not_require_cue_bundle(liaison: Any, tmp_path: Path) -> None:
    _write_request(tmp_path, "cue-pack", _request(tmp_path))
    payload = {
        **_respond_payload(tmp_path),
        "status": "in_progress",
        "artifacts": ["brief.md"],
    }
    assert (
        liaison.respond(payload, root=tmp_path)["response"]["status"] == "in_progress"
    )
