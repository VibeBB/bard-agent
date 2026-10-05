"""Sister Liaison Protocol (SLP) v2 — bard side, stdlib mirror.

UX-creator writes ``<id>.ux-request.json`` files into the workspace; bard
answers with ``<id>.ux-response.json`` beside each request. This module is a
strict local mirror of the v2 shapes — it imports nothing from
UX-creator-agent.

Request v2 (strict, unknown keys rejected)::

    schema_version: 2, system: "ux-creator", id: slug (== file stem),
    target_agent: "bard", stage: <enum>, risk: low|high,
    purpose: str >= 20, rationale: str,
    requested_changes / expected_deliverables / acceptance: [str >= 1],
    inputs: [{path: workspace-relative, sha256: 64 lowercase hex}],
    depends_on: [request ids], created_at: ISO-8601 with timezone

Response v2 (strict)::

    schema_version: 2, system: "ux-creator", request: <id>,
    responder: "bard",
    status: accepted|in_progress|done|rejected|deferred|needs_info,
    reason: str (>= 20 chars unless accepted|in_progress),
    input_hashes: {path: sha256 seen when answering},
    artifacts: [{path, sha256}],
    gate_verdicts: [{gate, verdict: pass|fail|unknown}],
    decision_refs / impression_refs: [VRP event_id],
    questions_for_user: [str], responded_at: ISO-8601 with timezone

Python 3.12+, standard library only.

Usage through ``bard_cli.py``::

    python3 bard_cli.py ux-inbox [--root <workspace>]
    python3 bard_cli.py ux-respond --json <file|-> [--root <workspace>]
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

_RECORDS_PATH = (
    Path(__file__).resolve().parents[1] / "hooks" / "scripts" / "_records.py"
)
_spec = importlib.util.spec_from_file_location("_records", _RECORDS_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load _records.py from {_RECORDS_PATH}")
_records = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_records", _records)
_spec.loader.exec_module(_records)

TARGET: Final = "bard"
SCHEMA_VERSION: Final = 2
SYSTEM: Final = "ux-creator"
REQUEST_SUFFIX: Final = ".ux-request.json"
RESPONSE_SUFFIX: Final = ".ux-response.json"
MAX_DEPTH: Final = 4
SKIP_PARTS: Final = frozenset({".git", ".venv", "node_modules", "__pycache__"})
STAGES: Final = frozenset(
    {
        "requirements",
        "design",
        "manufacturing_handoff",
        "build",
        "evaluation",
        "revision",
    }
)
RISKS: Final = frozenset({"low", "high"})
STATUSES: Final = frozenset(
    {"accepted", "in_progress", "done", "rejected", "deferred", "needs_info"}
)
VERDICTS: Final = frozenset({"pass", "fail", "unknown"})
PURPOSE_MIN_CHARS: Final = 20
RATIONALE_MIN_CHARS: Final = 20
REASON_MIN_CHARS: Final = 20
FREE_REASON_STATUSES: Final = frozenset({"accepted", "in_progress"})
SOFT_REFUSE_STATUSES: Final = frozenset({"needs_info", "rejected", "deferred"})
SLUG_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
REQUEST_KEYS: Final = frozenset(
    {
        "schema_version",
        "system",
        "id",
        "target_agent",
        "stage",
        "risk",
        "purpose",
        "rationale",
        "requested_changes",
        "inputs",
        "expected_deliverables",
        "acceptance",
        "depends_on",
        "created_at",
    }
)
RESPONSE_KEYS: Final = frozenset(
    {
        "schema_version",
        "system",
        "request",
        "responder",
        "status",
        "reason",
        "input_hashes",
        "artifacts",
        "gate_verdicts",
        "decision_refs",
        "impression_refs",
        "questions_for_user",
        "responded_at",
    }
)
RESPOND_INPUT_KEYS: Final = frozenset(
    {
        "request",
        "status",
        "reason",
        "artifacts",
        "gate_verdicts",
        "decision_refs",
        "impression_refs",
        "questions_for_user",
    }
)
RECORDS_DIR: Final = Path("observations") / TARGET
JOB_ID_WARNING: Final = "job id citation not verifiable"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_str(value: Any, min_chars: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_chars


def _str_list_errors(value: Any, field: str, min_items: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < min_items:
        return [f"{field} must be a list with at least {min_items} string(s)"]
    if not all(_is_str(item) for item in value):
        return [f"{field} entries must be non-empty strings"]
    return []


def _workspace_path(value: Any, root: Path, field: str) -> tuple[Path, list[str]]:
    """Resolve a workspace-relative path; returns (path, errors)."""
    if not isinstance(value, str) or not value.strip():
        return root, [f"{field} must be a non-empty string"]
    raw = Path(value)
    if raw.is_absolute():
        return root, [f"{field} must be workspace-relative: {value}"]
    try:
        resolved = (root / raw).resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return root, [f"{field} escapes the workspace: {value}"]
    if resolved.is_symlink():
        return resolved, [f"{field} contains a symlink: {value}"]
    return resolved, []


def _ux_job_ids(path: Path) -> list[str]:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [
        job["id"] for job in jobs if isinstance(job, dict) and _is_str(job.get("id"))
    ]


def validate_request(
    data: Any, stem: str, root: Path
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Return (request, reasons, warnings); request is None when invalid."""
    reasons: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return None, ["request must be a JSON object"], warnings
    extra = sorted(set(data) - REQUEST_KEYS)
    if extra:
        reasons.append(f"unknown keys {extra}")
    if data.get("schema_version") != SCHEMA_VERSION:
        reasons.append(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("system") != SYSTEM:
        reasons.append(f"system must be {SYSTEM!r}")
    req_id = data.get("id")
    if not isinstance(req_id, str) or SLUG_RE.match(req_id) is None:
        reasons.append("id must be a lowercase slug")
        req_id = stem
    elif req_id != stem:
        reasons.append(f"id {req_id!r} must equal the file stem {stem!r}")
    if data.get("target_agent") != TARGET:
        reasons.append(f"target_agent must be {TARGET!r}")
    if data.get("stage") not in STAGES:
        reasons.append(f"stage must be one of {sorted(STAGES)}")
    risk = data.get("risk")
    if risk not in RISKS:
        reasons.append(f"risk must be one of {sorted(RISKS)}")
    if not _is_str(data.get("purpose"), PURPOSE_MIN_CHARS):
        reasons.append(f"purpose needs at least {PURPOSE_MIN_CHARS} characters")
    rationale = data.get("rationale")
    if not isinstance(rationale, str):
        reasons.append("rationale must be a string")
        rationale = ""
    if risk == "high" and len(rationale.strip()) < RATIONALE_MIN_CHARS:
        reasons.append(
            f"high-risk rationale needs at least {RATIONALE_MIN_CHARS} characters"
        )
    for field in ("requested_changes", "expected_deliverables", "acceptance"):
        reasons.extend(_str_list_errors(data.get(field), field))
    inputs_raw = data.get("inputs")
    inputs: list[dict[str, Any]] = []
    ux_inputs: list[Path] = []
    if not isinstance(inputs_raw, list):
        reasons.append("inputs must be a list")
    else:
        for i, item in enumerate(inputs_raw):
            where = f"inputs[{i}]"
            if not isinstance(item, dict):
                reasons.append(f"{where} must be an object")
                continue
            unknown = sorted(set(item) - {"path", "sha256"})
            if unknown:
                reasons.append(f"{where}: unknown keys {unknown}")
            path, path_errors = _workspace_path(item.get("path"), root, f"{where}.path")
            reasons.extend(path_errors)
            sha = item.get("sha256")
            if not isinstance(sha, str) or SHA256_RE.match(sha) is None:
                reasons.append(f"{where}.sha256 must be 64 lowercase hex digits")
            if path_errors or not isinstance(item.get("path"), str):
                continue
            inputs.append({"path": item["path"], "sha256": sha, "_path": path})
            if str(item["path"]).endswith(".ux.json"):
                ux_inputs.append(path)
    depends_raw = data.get("depends_on")
    if not isinstance(depends_raw, list):
        reasons.append("depends_on must be a list")
    else:
        for i, dep in enumerate(depends_raw):
            if not isinstance(dep, str) or SLUG_RE.match(dep) is None:
                reasons.append(f"depends_on[{i}] must be a request id slug")
            elif dep == req_id:
                reasons.append("depends_on may not name the request's own id")
    if _records.parse_time(data.get("created_at")) is None:
        reasons.append("created_at must be an ISO-8601 timestamp with a timezone")
    if risk == "high":
        cited = False
        readable = False
        for path in ux_inputs:
            ids = _ux_job_ids(path)
            if not ids:
                continue
            readable = True
            if any(job_id in rationale for job_id in ids):
                cited = True
        if not cited:
            warnings.append(JOB_ID_WARNING)
            if not readable:
                pass  # not verifiable: warning only
    request = {
        "id": req_id,
        "stage": data.get("stage"),
        "risk": risk,
        "purpose": data.get("purpose"),
        "inputs": inputs,
        "depends_on": [
            dep
            for dep in (depends_raw if isinstance(depends_raw, list) else [])
            if isinstance(dep, str)
        ],
        "raw": data,
    }
    return (None if reasons else request), reasons, warnings


def _request_stem(path: Path) -> str:
    return path.name[: -len(REQUEST_SUFFIX)]


def _response_path(request_path: Path) -> Path:
    return request_path.with_name(_request_stem(request_path) + RESPONSE_SUFFIX)


def _read_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"cannot read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"not JSON: {exc}"


def validate_response(data: Any) -> list[str]:
    """Reasons a *.ux-response.json fails the v2 shape (empty = valid)."""
    reasons: list[str] = []
    if not isinstance(data, dict):
        return ["response must be a JSON object"]
    extra = sorted(set(data) - RESPONSE_KEYS)
    if extra:
        reasons.append(f"unknown keys {extra}")
    if data.get("schema_version") != SCHEMA_VERSION:
        reasons.append(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("system") != SYSTEM:
        reasons.append(f"system must be {SYSTEM!r}")
    if not isinstance(data.get("request"), str):
        reasons.append("request must be the request id string")
    if data.get("responder") != TARGET:
        reasons.append(f"responder must be {TARGET!r}")
    if data.get("status") not in STATUSES:
        reasons.append(f"status must be one of {sorted(STATUSES)}")
    reason = data.get("reason")
    status = data.get("status")
    if not isinstance(reason, str):
        reasons.append("reason must be a string")
    elif status not in FREE_REASON_STATUSES and len(reason.strip()) < REASON_MIN_CHARS:
        reasons.append(f"reason needs at least {REASON_MIN_CHARS} characters")
    input_hashes = data.get("input_hashes")
    if not isinstance(input_hashes, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and SHA256_RE.match(v)
        for k, v in input_hashes.items()
    ):
        reasons.append("input_hashes must map paths to lowercase hex sha256")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        reasons.append("artifacts must be a list")
    else:
        for i, item in enumerate(artifacts):
            where = f"artifacts[{i}]"
            if not isinstance(item, dict) or sorted(set(item) - {"path", "sha256"}):
                reasons.append(f"{where} must be {{path, sha256}}")
                continue
            if not _is_str(item.get("path")):
                reasons.append(f"{where}.path must be a non-empty string")
            sha = item.get("sha256")
            if not isinstance(sha, str) or SHA256_RE.match(sha) is None:
                reasons.append(f"{where}.sha256 must be 64 lowercase hex digits")
    verdicts = data.get("gate_verdicts")
    if not isinstance(verdicts, list):
        reasons.append("gate_verdicts must be a list")
    else:
        for i, item in enumerate(verdicts):
            where = f"gate_verdicts[{i}]"
            if not isinstance(item, dict) or sorted(set(item) - {"gate", "verdict"}):
                reasons.append(f"{where} must be {{gate, verdict}}")
                continue
            if not _is_str(item.get("gate")):
                reasons.append(f"{where}.gate must be a non-empty string")
            if item.get("verdict") not in VERDICTS:
                reasons.append(f"{where}.verdict must be one of {sorted(VERDICTS)}")
    for field in ("decision_refs", "impression_refs", "questions_for_user"):
        if not isinstance(data.get(field), list):
            reasons.append(f"{field} must be a list")
    if _records.parse_time(data.get("responded_at")) is None:
        reasons.append("responded_at must be an ISO-8601 timestamp with a timezone")
    return reasons


def _iter_requests(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob(f"*{REQUEST_SUFFIX}"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) - 1 > MAX_DEPTH:
            continue
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.is_file():
            found.append(path)
    return sorted(found)


def _responded_ids(root: Path) -> set[str]:
    """Request ids that have a valid response file anywhere under root."""
    answered: set[str] = set()
    for path in sorted(root.rglob(f"*{RESPONSE_SUFFIX}")):
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        data, err = _read_json(path)
        if err is not None or not isinstance(data, dict):
            continue
        if validate_response(data):
            continue
        answered.add(str(data["request"]))
    return answered


def _inputs_stale(request: dict[str, Any]) -> bool:
    for entry in request["inputs"]:
        path = entry["_path"]
        if not path.is_file() or _sha256_file(path) != entry["sha256"]:
            return True
    return False


def _response_stale(request: dict[str, Any], response: dict[str, Any]) -> bool:
    input_hashes = response.get("input_hashes") or {}
    for entry in request["inputs"]:
        path = entry["_path"]
        current = _sha256_file(path) if path.is_file() else None
        if current is None or current != entry["sha256"]:
            return True
        if input_hashes.get(entry["path"]) != current:
            return True
    return False


def inbox(root: Path | None = None) -> dict[str, Any]:
    """Scan the workspace for bard liaison requests and classify them."""
    base = (root or Path.cwd()).resolve()
    requests: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    responded = _responded_ids(base)
    for path in _iter_requests(base):
        rel = path.relative_to(base).as_posix()
        data, err = _read_json(path)
        if err is not None:
            malformed.append({"path": rel, "reasons": [err]})
            continue
        if not isinstance(data, dict):
            malformed.append(
                {"path": rel, "reasons": ["request must be a JSON object"]}
            )
            continue
        if data.get("target_agent") != TARGET:
            continue  # addressed to a sister plugin — not ours
        request, reasons, warnings = validate_request(data, _request_stem(path), base)
        if request is None:
            malformed.append({"path": rel, "reasons": reasons})
            continue
        resp_path = _response_path(path)
        response: dict[str, Any] | None = None
        if resp_path.is_file():
            resp_data, resp_err = _read_json(resp_path)
            if resp_err is not None:
                malformed.append(
                    {
                        "path": resp_path.relative_to(base).as_posix(),
                        "reasons": [resp_err],
                    }
                )
            else:
                resp_reasons = validate_response(resp_data)
                if resp_reasons:
                    malformed.append(
                        {
                            "path": resp_path.relative_to(base).as_posix(),
                            "reasons": resp_reasons,
                        }
                    )
                else:
                    response = resp_data
        if response is not None:
            state = "stale" if _response_stale(request, response) else "answered"
        elif _inputs_stale(request):
            state = "stale"
        elif any(dep not in responded for dep in request["depends_on"]):
            state = "blocked"
        else:
            state = "new"
        requests.append(
            {
                "path": rel,
                "id": request["id"],
                "state": state,
                "stage": request["stage"],
                "risk": request["risk"],
                "purpose": request["purpose"],
                "warnings": warnings,
            }
        )
    return {
        "verdict": "pass",
        "root": str(base),
        "requests": requests,
        "malformed": malformed,
    }


def _known_event_ids(root: Path, filenames: list[str]) -> set[str]:
    ids: set[str] = set()
    for name in filenames:
        path = root / RECORDS_DIR / name
        if not path.is_file():
            continue
        records, _malformed = _records.load_jsonl(path)
        ids.update(str(record.get("event_id")) for record in records)
    return ids


def _load_request_file(
    value: Any, root: Path
) -> tuple[Path, dict[str, Any], list[str]]:
    """Resolve the request path from a respond input; returns path + request."""
    if not _is_str(value):
        raise ValueError("request must name the *.ux-request.json path")
    path, errors = _workspace_path(value, root, "request")
    if errors:
        raise ValueError("; ".join(errors))
    if not path.is_file():
        raise ValueError(f"request file not found: {value}")
    data, err = _read_json(path)
    if err is not None:
        raise ValueError(f"{value}: {err}")
    request, reasons, warnings = validate_request(data, _request_stem(path), root)
    if request is None:
        raise ValueError(f"{value} is not a valid bard request: " + "; ".join(reasons))
    assert request is not None
    return path, request, warnings


def respond(payload: Any, root: Path | None = None) -> dict[str, Any]:
    """Validate a respond input and write <stem>.ux-response.json."""
    base = (root or Path.cwd()).resolve()
    if not isinstance(payload, dict):
        raise ValueError("respond input must be a JSON object")
    extra = sorted(set(payload) - RESPOND_INPUT_KEYS)
    if extra:
        raise ValueError(f"unknown keys {extra}")
    req_path, request, _warnings = _load_request_file(payload.get("request"), base)
    status = payload.get("status")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    reason = payload.get("reason")
    if not isinstance(reason, str):
        reason = ""
    if status not in FREE_REASON_STATUSES and len(reason.strip()) < REASON_MIN_CHARS:
        raise ValueError(
            f"reason needs at least {REASON_MIN_CHARS} characters for status {status}"
        )
    artifacts_in = payload.get("artifacts", [])
    if not isinstance(artifacts_in, list):
        raise ValueError("artifacts must be a list of workspace-relative paths")
    verdicts_in = payload.get("gate_verdicts", [])
    if not isinstance(verdicts_in, list):
        raise ValueError("gate_verdicts must be a list of {gate, verdict}")
    gate_verdicts: list[dict[str, str]] = []
    for i, item in enumerate(verdicts_in):
        if not isinstance(item, dict) or set(item) - {"gate", "verdict"}:
            raise ValueError(f"gate_verdicts[{i}] must be {{gate, verdict}}")
        if item.get("verdict") not in VERDICTS or not _is_str(item.get("gate")):
            raise ValueError(
                f"gate_verdicts[{i}] verdict must be one of {sorted(VERDICTS)}"
            )
        gate_verdicts.append({"gate": item["gate"], "verdict": item["verdict"]})
    if status == "done":
        bad = [g for g in gate_verdicts if g["verdict"] != "pass"]
        if bad:
            names = ", ".join(f"{g['gate']}={g['verdict']}" for g in bad)
            raise ValueError(
                f"refusing done: gate verdict {names} is not pass; answer with "
                "status needs_info or rejected and a reason instead"
            )
    artifacts: list[dict[str, str]] = []
    for i, item in enumerate(artifacts_in):
        path, errors = _workspace_path(item, base, f"artifacts[{i}]")
        if errors:
            raise ValueError("; ".join(errors))
        if not path.is_file():
            raise ValueError(f"artifacts[{i}] does not exist: {item}")
        artifacts.append(
            {
                "path": path.relative_to(base).as_posix(),
                "sha256": _sha256_file(path),
            }
        )
    decision_refs = payload.get("decision_refs", [])
    impression_refs = payload.get("impression_refs", [])
    questions = payload.get("questions_for_user", [])
    for field, value in (
        ("decision_refs", decision_refs),
        ("impression_refs", impression_refs),
        ("questions_for_user", questions),
    ):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{field} must be a list of strings")
    if status == "done":
        if not artifacts:
            raise ValueError("status done requires at least one artifact")
        if not decision_refs:
            raise ValueError("status done requires at least one decision_ref")
        if not impression_refs:
            raise ValueError("status done requires at least one impression_ref")
    known_decisions = _known_event_ids(base, ["decisions.jsonl"])
    for ref in decision_refs:
        if ref not in known_decisions:
            raise ValueError(
                f"decision_ref {ref} is not an event_id in "
                f"{RECORDS_DIR.as_posix()}/decisions.jsonl"
            )
    known_impressions = _known_event_ids(
        base, ["impressions.jsonl", "vision-reviews.jsonl"]
    )
    for ref in impression_refs:
        if ref not in known_impressions:
            raise ValueError(
                f"impression_ref {ref} is not an event_id in "
                f"{RECORDS_DIR.as_posix()}/impressions.jsonl or vision-reviews.jsonl"
            )
    soft = status in SOFT_REFUSE_STATUSES
    input_hashes: dict[str, str] = {}
    for entry in request["inputs"]:
        path = entry["_path"]
        rel = entry["path"]
        if not path.is_file():
            if soft:
                continue
            raise ValueError(
                f"request input {rel} is missing; answer with needs_info, "
                "rejected or deferred to omit it"
            )
        input_hashes[rel] = _sha256_file(path)
    response = {
        "schema_version": SCHEMA_VERSION,
        "system": SYSTEM,
        "request": request["id"],
        "responder": TARGET,
        "status": status,
        "reason": reason.strip(),
        "input_hashes": input_hashes,
        "artifacts": artifacts,
        "gate_verdicts": gate_verdicts,
        "decision_refs": decision_refs,
        "impression_refs": impression_refs,
        "questions_for_user": questions,
        "responded_at": datetime.now(UTC).isoformat(),
    }
    out_path = _response_path(req_path)
    out_path.write_text(
        json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "verdict": "pass",
        "path": str(out_path),
        "response": response,
    }
