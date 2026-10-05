"""Writers for the VibeBB Record Protocol (VRP) v1 — bard port.

bard has no ``src`` package and no MCP server, so the typed record writers
live here as a plugin script, standard library only. They mirror
``src/wire/records.py`` in the wire-agent repository: the same input fields
and strictness (unknown keys rejected), the same written record JSON shape
(``model_dump(exclude_none=True)`` equivalent), the same ``event_id``
identity construction, and the same workspace-path containment.

Every built record is re-validated with the stdlib mirror in
``hooks/scripts/_records.py`` before it is appended, so a line that would
fail the Stop hook is rejected at write time. Records are advisory evidence
(L2): they never change a deterministic gate verdict.

Usage through ``bard_cli.py``::

    python3 bard_cli.py record decision --json <file|-> [--root <workspace>]
    python3 bard_cli.py record impression --json <file|-> [--root <workspace>]
    python3 bard_cli.py record vision-review --json <file|-> [--root <workspace>]
    python3 bard_cli.py record status [--root <workspace>]
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

_HOOKS_SCRIPTS = Path(__file__).resolve().parents[1] / "hooks" / "scripts"


def _load_records_mirror() -> Any:
    """Import the shared stdlib VRP validator from hooks/scripts."""
    sys.path.insert(0, str(_HOOKS_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "_records", _HOOKS_SCRIPTS / "_records.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load _records.py from {_HOOKS_SCRIPTS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_records = _load_records_mirror()

PLUGIN: Final = "bard"
SCHEMA_VERSION: Final = 1
RECORDS_DIR: Final = Path("observations") / PLUGIN
IMPRESSION_MIN_CHARS: Final = 400
IMPRESSION_MIN_SENTENCES: Final = 3
RATIONALE_MIN_CHARS: Final = 200
PRINCIPLE_MIN_CHARS: Final = 12
QUESTION_MIN_CHARS: Final = 10
LOG_FILES: Final[dict[str, str]] = {
    "decision": "decisions.jsonl",
    "stage_impression": "impressions.jsonl",
    "vision_review": "vision-reviews.jsonl",
}
SKIP_PARTS: Final = frozenset(_records.SKIP_PARTS)
SEVERITIES: Final = frozenset(_records.SEVERITIES)
DECIDERS: Final = frozenset(_records.DECIDERS)
_SLUG_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")

sentence_count = _records.sentence_count
sha256_file = _records.sha256_file
tree_sha256 = _records.tree_sha256
impression_errors = _records.impression_errors
record_errors = _records.record_errors


def workspace_root() -> Path:
    return Path(os.environ.get("OPENHANDS_PROJECT_DIR") or Path.cwd()).resolve()


def workspace_path(value: str | Path, root: Path | None = None) -> Path:
    """Resolve a workspace-relative path, rejecting escapes and symlinks.

    Mirrors ``src/wire/workspace.py`` in wire-agent exactly.
    """
    base = (root or workspace_root()).resolve()
    candidate = Path(value)
    raw = candidate if candidate.is_absolute() else base / candidate
    try:
        relative = raw.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path is outside the workspace: {value}") from exc
    current = base
    for part in relative.parts:
        if part == "..":
            current = current.parent
            if current != base and base not in current.parents:
                raise ValueError(f"path is outside the workspace: {value}")
        elif part not in ("", "."):
            current = current / part
        if current.is_symlink():
            raise ValueError(f"workspace path contains a symlink: {value}")
    resolved = raw.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"path is outside the workspace: {value}")
    return resolved


def records_dir(root: Path | None = None) -> Path:
    return (root or workspace_root()) / RECORDS_DIR


# ---------------------------------------------------------------------------
# input validation (strict: unknown keys rejected, same limits as wire)


def _fail(message: str) -> None:
    raise ValueError(message)


def _need(cond: bool, message: str) -> None:
    if not cond:
        _fail(message)


def _is_str(value: Any, min_chars: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_chars


def _str_list(value: Any, min_items: int, min_chars: int, field: str) -> list[str]:
    _need(isinstance(value, list), f"{field} must be a list of strings")
    items = list(value)
    _need(len(items) >= min_items, f"{field} needs at least {min_items} item(s)")
    for item in items:
        _need(
            isinstance(item, str) and len(item.strip()) >= min_chars,
            f"{field} entries need at least {min_chars} character(s)",
        )
    return items


def _extra_keys(data: Mapping[str, Any], allowed: set[str]) -> list[str]:
    return sorted(set(data) - allowed)


def _impression_prose(value: Any) -> str:
    """Reject a terse status line where a long-form impression is required."""
    errors = impression_errors(value)
    if errors:
        _fail("; ".join(errors))
    return value.strip()


def _validate_option(raw: Any, index: int) -> dict[str, Any]:
    where = f"options[{index}]"
    _need(isinstance(raw, dict), f"{where} must be an object")
    option = dict(raw)
    _need(
        not _extra_keys(option, {"name", "pros", "cons"}),
        f"{where}: unknown keys {_extra_keys(option, {'name', 'pros', 'cons'})}",
    )
    name = option.get("name")
    _need(_is_str(name), f"{where}.name is required")
    pros = _str_list(option.get("pros"), 1, 1, f"{where}.pros")
    cons = _str_list(option.get("cons"), 1, 1, f"{where}.cons")
    return {"name": name, "pros": pros, "cons": cons}


def _validate_evidence_input(raw: Any, index: int) -> dict[str, Any]:
    where = f"evidence[{index}]"
    _need(isinstance(raw, dict), f"{where} must be an object")
    entry = dict(raw)
    _need(
        not _extra_keys(entry, {"path", "reference"}),
        f"{where}: unknown keys {_extra_keys(entry, {'path', 'reference'})}",
    )
    path = entry.get("path")
    reference = entry.get("reference")
    _need(
        path is not None or (isinstance(reference, str) and bool(reference.strip())),
        f"{where} needs a path (bound by sha256) or a reference",
    )
    return {"path": path, "reference": reference}


def _validate_finding(raw: Any, index: int) -> dict[str, Any]:
    where = f"findings[{index}]"
    _need(isinstance(raw, dict), f"{where} must be an object")
    finding = dict(raw)
    _need(
        not _extra_keys(finding, {"category", "severity", "note"}),
        f"{where}: unknown keys "
        f"{_extra_keys(finding, {'category', 'severity', 'note'})}",
    )
    _need(_is_str(finding.get("category")), f"{where}.category is required")
    _need(
        finding.get("severity") in SEVERITIES,
        f"{where}.severity must be one of {sorted(SEVERITIES)}",
    )
    _need(_is_str(finding.get("note")), f"{where}.note is required")
    return {
        "category": finding["category"],
        "severity": finding["severity"],
        "note": finding["note"],
    }


def _decision_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    allowed = {
        "id",
        "stage",
        "question",
        "principles",
        "options",
        "chosen",
        "rationale",
        "evidence",
        "assumptions",
        "unknowns",
        "risks",
        "revisit_when",
        "decided_by",
    }
    _need(not _extra_keys(data, allowed), f"unknown keys {_extra_keys(data, allowed)}")
    for key in ("id", "stage"):
        value = data.get(key)
        _need(
            isinstance(value, str) and _SLUG_RE.match(value) is not None,
            f"{key} must be a lowercase slug",
        )
    _need(
        _is_str(data.get("question"), QUESTION_MIN_CHARS),
        f"question must state the decision in at least {QUESTION_MIN_CHARS} chars",
    )
    principles = _str_list(data.get("principles"), 1, PRINCIPLE_MIN_CHARS, "principles")
    raw_options = data.get("options")
    _need(
        isinstance(raw_options, list) and len(raw_options) >= 2,
        "options must list at least two considered alternatives",
    )
    options = [
        _validate_option(item, i) for i, item in enumerate(cast(list[Any], raw_options))
    ]
    names = [o["name"] for o in options]
    _need(len(set(names)) == len(names), "option names must be unique")
    _need(data.get("chosen") in names, "chosen must name one of the options")
    _need(
        _is_str(data.get("rationale"), RATIONALE_MIN_CHARS),
        f"rationale must explain the choice in at least {RATIONALE_MIN_CHARS} chars",
    )
    raw_evidence = data.get("evidence")
    _need(
        isinstance(raw_evidence, list) and len(raw_evidence) >= 1,
        "evidence must cite at least one artifact (path) or reference",
    )
    evidence_in = [
        _validate_evidence_input(item, i)
        for i, item in enumerate(cast(list[Any], raw_evidence))
    ]
    assumptions = _str_list(data.get("assumptions", []), 0, 1, "assumptions")
    unknowns = _str_list(data.get("unknowns", []), 0, 1, "unknowns")
    risks = _str_list(data.get("risks"), 1, 1, "risks")
    _need(
        _is_str(data.get("revisit_when")),
        "revisit_when must name the observation that would reopen the decision",
    )
    decided_by = data.get("decided_by", "agent")
    _need(decided_by in DECIDERS, "decided_by must be 'agent' or 'user'")
    return {
        "id": data["id"],
        "stage": data["stage"],
        "question": data["question"],
        "principles": principles,
        "options": options,
        "chosen": data["chosen"],
        "rationale": data["rationale"],
        "evidence": evidence_in,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "risks": risks,
        "revisit_when": data["revisit_when"],
        "decided_by": decided_by,
    }


def _impression_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    allowed = {"stage", "artifacts", "impression"}
    _need(not _extra_keys(data, allowed), f"unknown keys {_extra_keys(data, allowed)}")
    stage = data.get("stage")
    _need(
        isinstance(stage, str) and _SLUG_RE.match(stage) is not None,
        "stage must be a lowercase slug",
    )
    artifacts = _str_list(data.get("artifacts"), 1, 1, "artifacts")
    impression = _impression_prose(data.get("impression"))
    return {"stage": stage, "artifacts_in": artifacts, "impression": impression}


def _vision_review_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    allowed = {
        "image_path",
        "source_event_id",
        "model",
        "checklist",
        "findings",
        "impression",
    }
    _need(not _extra_keys(data, allowed), f"unknown keys {_extra_keys(data, allowed)}")
    image_path = data.get("image_path")
    source_event_id = data.get("source_event_id")
    _need(
        image_path is not None or source_event_id is not None,
        "a vision review needs image_path or source_event_id",
    )
    _need(_is_str(data.get("model")), "model is required")
    checklist = data.get("checklist")
    _need(
        isinstance(checklist, str) and _SLUG_RE.match(checklist) is not None,
        "checklist must be a lowercase slug",
    )
    findings_in = data.get("findings", [])
    _need(isinstance(findings_in, list), "findings must be a list")
    findings = [_validate_finding(item, i) for i, item in enumerate(findings_in)]
    impression = _impression_prose(data.get("impression"))
    return {
        "image_path": image_path,
        "source_event_id": source_event_id,
        "model": data["model"],
        "checklist": checklist,
        "findings": findings,
        "impression": impression,
    }


# ---------------------------------------------------------------------------
# appending


def _relative(value: str, root: Path) -> tuple[str, Path]:
    path = workspace_path(value, root)
    if not path.exists():
        raise ValueError(f"artifact does not exist: {value}")
    relative = (
        path.relative_to(root.resolve()).as_posix() if path != root.resolve() else "."
    )
    return relative, path


def _append(kind: str, body: dict[str, Any], root: Path) -> dict[str, Any]:
    log = records_dir(root) / LOG_FILES[kind]
    log.parent.mkdir(parents=True, exist_ok=True)
    existing = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    sequence = len([line for line in existing if line.strip()]) + 1
    identity = {"kind": kind, "sequence": sequence, **body}
    event_id = hashlib.sha256(
        json.dumps(
            identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "plugin": PLUGIN,
        "sequence": sequence,
        "event_id": event_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        **body,
    }
    # model_dump(exclude_none=True) equivalent: drop None-valued top-level fields.
    validated = {k: v for k, v in record.items() if v is not None}
    errors = record_errors(kind, validated)
    if errors:
        _fail("record fails the shared validator: " + "; ".join(errors))
    with log.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(validated, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
    return {"verdict": "pass", "kind": kind, "path": str(log), "record": validated}


def record_decision(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _decision_body(payload)
    evidence: list[dict[str, Any]] = []
    for item in body["evidence"]:
        if item["path"] is not None:
            relative, path = _relative(str(item["path"]), base)
            evidence.append({"path": relative, "sha256": tree_sha256(path)})
        else:
            evidence.append({"reference": item["reference"]})
    body["evidence"] = evidence
    return _append("decision", body, base)


def record_impression(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _impression_body(payload)
    artifacts: list[dict[str, str]] = []
    for value in body.pop("artifacts_in"):
        relative, path = _relative(value, base)
        artifacts.append({"path": relative, "sha256": tree_sha256(path)})
    body["artifacts"] = artifacts
    return _append("stage_impression", body, base)


def record_vision_review(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _vision_review_body(payload)
    body["image_sha256"] = None
    if body["image_path"] is not None:
        relative, path = _relative(str(body["image_path"]), base)
        if not path.is_file():
            raise ValueError(f"image is not a file: {body['image_path']}")
        body["image_path"] = relative
        body["image_sha256"] = sha256_file(path)
    # Reorder to wire's field order for the identity hash (sort_keys makes
    # order irrelevant, but the written record keeps insertion order).
    ordered = {
        "image_path": body["image_path"],
        "image_sha256": body["image_sha256"],
        "source_event_id": body["source_event_id"],
        "model": body["model"],
        "checklist": body["checklist"],
        "findings": body["findings"],
        "impression": body["impression"],
    }
    return _append("vision_review", ordered, base)


RECORDERS = {
    "decision": record_decision,
    "impression": record_impression,
    "vision-review": record_vision_review,
}


def records_summary(root: Path | None = None) -> dict[str, Any]:
    """Counts per log plus the last Stop-hook verdict; informational only."""
    directory = records_dir(root)
    counts: dict[str, int] = {}
    for kind, filename in LOG_FILES.items():
        path = directory / filename
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        counts[kind] = len([line for line in lines if line.strip()])
    status_path = directory / "records-status.json"
    status: Any = None
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {
                "verdict": "fail",
                "problems": ["records-status.json is malformed"],
            }
    return {
        "verdict": "pass",
        "records_dir": str(directory),
        "counts": counts,
        "last_stop": status,
    }
