"""VibeBB Record Protocol (VRP) v2 writers for bard — standard library only.

The rules live in ``hooks/scripts/_records.py``, the family's canonical
stdlib module (byte-identical to wire-agent's ``_vrp.py``). Each writer
checks the payload shape, hashes the files it cites, re-runs the same
validators the Stop hook uses, and appends a chained line under
``observations/bard/``: ``prev_event_id`` links to the previous line and
``event_id`` is the sha256 of the line's canonical content.

Write-time checks need the workspace and are only done here: claims must
quote tokens found in the cited artifact, a new impression must not be a
near copy of an earlier one, upstream citations must resolve to intact
sister logs, a disputed concern cannot return on unchanged bytes, a
rejected insight needs ``revisits``, and review rounds are capped.

bard also writes song deliveries (``liaison/<id>.bard-song.json``). A
delivery may only cite impressions; receipts are never song material, so a
sister's receipt cannot start another song. Records are advisory evidence
and never change a gate verdict.
"""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

_HOOKS_SCRIPTS = Path(__file__).resolve().parents[1] / "hooks" / "scripts"


def _load_records_mirror() -> Any:
    """Import the shared stdlib VRP module from hooks/scripts."""
    sys.path.insert(0, str(_HOOKS_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "_records", _HOOKS_SCRIPTS / "_records.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load _records.py from {_HOOKS_SCRIPTS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_vrp = _load_records_mirror()

PLUGIN: Final = "bard"
SCHEMA_VERSION: Final = _vrp.SCHEMA_VERSION
RECORDS_DIR: Final = Path(_vrp.OBSERVATIONS_DIR) / PLUGIN
IMPRESSION_MIN_CHARS: Final = _vrp.IMPRESSION_MIN_CHARS
IMPRESSION_MIN_SENTENCES: Final = _vrp.IMPRESSION_MIN_SENTENCES
RATIONALE_MIN_CHARS: Final = _vrp.RATIONALE_MIN_CHARS
LOG_FILES: Final[dict[str, str]] = dict(_vrp.LOG_FILES)

sentence_count = _vrp.sentence_count
sha256_file = _vrp.sha256_file
tree_sha256 = _vrp.tree_sha256
impression_errors = _vrp.impression_errors
record_errors = _vrp.record_errors


def impression_is_prose(text: str) -> str:
    """Return ``text`` when it meets the impression prose rules, else raise."""
    errors = _vrp.impression_errors(text)
    if errors:
        raise ValueError("; ".join(errors))
    return text


_IMPRESSION_KEYS: Final = frozenset(
    {
        "impression",
        "facets",
        "claims",
        "insights",
        "upstream",
        "confidence",
        "unknowns",
        "delta",
    }
)
_ALLOWED: Final[dict[str, frozenset[str]]] = {
    "decision": frozenset(
        {
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
            "impression_refs",
            "insight_refs",
        }
    ),
    "stage_impression": _IMPRESSION_KEYS | {"stage", "artifacts"},
    "vision_review": _IMPRESSION_KEYS
    | {
        "image_path",
        "source_event_id",
        "model",
        "checklist",
        "reviewer",
        "findings",
        "lookback",
    },
    "insight_status": frozenset(
        {
            "insight",
            "status",
            "reason",
            "evidence",
            "gate_verdicts",
            "decision_refs",
            "revisit_when",
        }
    ),
    "review_reconcile": frozenset({"reviews"}),
    "song_receipt": frozenset({"delivery", "felt", "prompted_review", "follow_up"}),
    "upstream_read": frozenset({"artifact", "producer"}),
    "song_delivery": frozenset(
        {"id", "to", "title", "verse", "song", "impression_refs", "reason"}
    ),
}
_DEFAULTS: Final[dict[str, dict[str, Any]]] = {
    "decision": {
        "assumptions": [],
        "unknowns": [],
        "decided_by": "agent",
        "impression_refs": [],
        "insight_refs": [],
    },
    "stage_impression": {"insights": [], "upstream": [], "unknowns": []},
    "vision_review": {
        "insights": [],
        "upstream": [],
        "unknowns": [],
        "reviewer": "primary",
        "findings": [],
    },
    "insight_status": {"gate_verdicts": [], "decision_refs": []},
}


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


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        items = cast(dict[str, Any], value).items()
        return {k: _drop_none(v) for k, v in items if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in cast(list[Any], value)]
    return value


def _payload(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reject unknown keys, apply the documented defaults, drop nulls."""
    if not isinstance(payload, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("payload must be a JSON object")
    unknown = sorted(set(payload) - _ALLOWED[kind])
    if unknown:
        raise ValueError(f"unknown {kind} fields: {unknown}")
    body: dict[str, Any] = {**_DEFAULTS.get(kind, {}), **dict(payload)}
    facets = body.get("facets")
    if isinstance(facets, dict) and "concerns" not in facets:
        body["facets"] = {**cast(dict[str, Any], facets), "concerns": []}
    return cast(dict[str, Any], _drop_none(body))


def _strings(body: Mapping[str, Any], key: str) -> list[str]:
    value = body.get(key)
    if not isinstance(value, list) or not all(
        isinstance(v, str) for v in cast(list[Any], value)
    ):
        raise ValueError(f"{key} must be a list of strings")
    return cast(list[str], value)


def _text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _relative(value: str, root: Path) -> tuple[str, Path]:
    path = workspace_path(value, root)
    if not path.exists():
        raise ValueError(f"artifact does not exist: {value}")
    relative = (
        path.relative_to(root.resolve()).as_posix() if path != root.resolve() else "."
    )
    return relative, path


def _archive_legacy(log: Path) -> None:
    records, _ = _vrp.load_jsonl(log)
    if not _vrp.is_legacy(records):
        return
    index = 1
    target = log.with_name(f"{log.stem}.v1.jsonl")
    while target.exists():
        index += 1
        target = log.with_name(f"{log.stem}.v1-{index}.jsonl")
    log.rename(target)


def _append(kind: str, body: dict[str, Any], root: Path) -> dict[str, Any]:
    log = records_dir(root) / LOG_FILES[kind]
    log.parent.mkdir(parents=True, exist_ok=True)
    with (log.parent / ".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _archive_legacy(log)
        existing, problems = _vrp.verify_log(log, kind)
        if problems:
            raise ValueError(
                f"{log.name} fails integrity, refusing to append: {problems[0]}."
                " Move the"
                " file aside (it stays as evidence) to start a new chain."
            )
        now = datetime.now(UTC)
        last = _vrp.parse_time(existing[-1].get("recorded_at")) if existing else None
        if last is not None and now.timestamp() < last:
            raise ValueError(
                "system clock is behind the last record; refusing to append"
            )
        writer: dict[str, Any] = {"plugin": PLUGIN}
        for key, env in (("agent", "VRP_AGENT"), ("model", "VRP_MODEL")):
            if os.environ.get(env, "").strip():
                writer[key] = os.environ[env].strip()
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "plugin": PLUGIN,
            "sequence": len(existing) + 1,
            "prev_event_id": _vrp.chain_head(existing),
            "recorded_at": now.isoformat(),
            "writer": writer,
            **{key: value for key, value in body.items() if value is not None},
        }
        record["event_id"] = _vrp.compute_event_id(record)
        errors = _vrp.record_errors(kind, record)
        if errors:
            raise ValueError(f"invalid {kind}: " + "; ".join(errors))
        with log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    return {"verdict": "pass", "kind": kind, "path": str(log), "record": record}


def _workspace(
    base: Path,
) -> dict[str, tuple[dict[str, list[dict[str, Any]]], list[str]]]:
    return _vrp.plugin_logs(base)


def _own(
    workspace: dict[str, tuple[dict[str, list[dict[str, Any]]], list[str]]],
) -> dict[str, list[dict[str, Any]]]:
    logs, problems = workspace.get(PLUGIN, ({}, []))
    if problems:
        raise ValueError(f"{PLUGIN} records fail integrity: {problems[0]}")
    return logs


def _context_errors(
    kind: str, body: dict[str, Any], base: Path, artifacts: list[dict[str, str]]
) -> list[str]:
    workspace = _workspace(base)
    own = _own(workspace)
    draft = (
        {"kind": kind, **body, "artifacts": artifacts}
        if artifacts
        else {"kind": kind, **body}
    )
    errors = _vrp.grounding_errors(draft, base)
    errors += _vrp.novelty_errors(draft, own.get(kind, []))
    errors += _vrp.upstream_resolution_errors(draft, workspace)
    errors += _vrp.reraise_errors(draft, PLUGIN, workspace)
    errors += _vrp.rejected_insight_errors(draft, workspace)
    return errors


def _hash_evidence(items: Any, base: Path) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ValueError("evidence must cite at least one path or reference")
    evidence: list[dict[str, Any]] = []
    for item in cast(list[Any], items):
        if not isinstance(item, dict):
            raise ValueError("evidence entries must be objects")
        entry = cast(dict[str, Any], item)
        if set(entry) - {"path", "reference"}:
            raise ValueError(
                f"unknown evidence fields: {sorted(set(entry) - {'path', 'reference'})}"
            )
        if isinstance(entry.get("path"), str):
            relative, path = _relative(entry["path"], base)
            evidence.append({"path": relative, "sha256": tree_sha256(path)})
        elif isinstance(entry.get("reference"), str) and entry["reference"].strip():
            evidence.append({"reference": entry["reference"]})
        else:
            raise ValueError("evidence needs a path (bound by sha256) or a reference")
    return evidence


def _refs(body: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = body.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(v, dict) for v in cast(list[Any], value)
    ):
        raise ValueError(f"{key} must be a list of objects")
    return cast(list[dict[str, Any]], value)


def record_decision(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _payload("decision", payload)
    body["evidence"] = _hash_evidence(body.get("evidence"), base)
    workspace = _workspace(base)
    problems = [
        p
        for ref in _refs(body, "impression_refs")
        if (
            p := _vrp.resolve_ref(
                workspace, str(ref.get("system")), str(ref.get("event_id"))
            )[1]
        )
    ]
    for ref in _refs(body, "insight_refs"):
        target, problem = _vrp.resolve_ref(
            workspace, str(ref.get("system")), str(ref.get("event_id"))
        )
        ids = {
            str(i.get("id"))
            for i in cast(list[dict[str, Any]], (target or {}).get("insights") or [])
        }
        if problem or ref.get("insight_id") not in ids:
            problems.append(
                problem or f"insight {ref.get('insight_id')} is not in that impression"
            )
    if problems:
        raise ValueError("unresolved refs: " + "; ".join(problems))
    return _append("decision", body, base)


def record_impression(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _payload("stage_impression", payload)
    paths = _strings(body, "artifacts")
    if not paths:
        raise ValueError("artifacts must list at least one file or directory")
    artifacts: list[dict[str, str]] = []
    for value in paths:
        relative, path = _relative(value, base)
        artifacts.append({"path": relative, "sha256": tree_sha256(path)})
    body.pop("artifacts")
    errors = _vrp.impression_errors(body.get("impression"))
    errors += _context_errors("stage_impression", body, base, artifacts)
    if errors:
        raise ValueError("; ".join(errors))
    body["artifacts"] = artifacts
    return _append("stage_impression", body, base)


def record_vision_review(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _payload("vision_review", payload)
    image = body.get("image_path")
    if image is None and body.get("source_event_id") is None:
        raise ValueError("a vision review needs image_path or source_event_id")
    if body.get("reviewer") != "primary" and image is None:
        raise ValueError("blind and tiebreak reviews must bind image_path")
    if image is not None:
        relative, path = _relative(_text(body, "image_path"), base)
        if not path.is_file():
            raise ValueError(f"image is not a file: {image}")
        body["image_path"] = relative
        body["image_sha256"] = sha256_file(path)
    own = _own(_workspace(base))
    errors = _vrp.impression_errors(body.get("impression"))
    errors += _context_errors("vision_review", body, base, [])
    errors += _round_errors(str(body.get("reviewer")), body.get("image_sha256"), own)
    if errors:
        raise ValueError("; ".join(errors))
    return _append("vision_review", body, base)


def _round_errors(
    reviewer: str, digest: Any, own: dict[str, list[dict[str, Any]]]
) -> list[str]:
    """Blind needs a primary; a tiebreak needs a round-1 split; each happens once."""
    if reviewer == "primary":
        return []
    reviews = [
        r for r in own.get("vision_review", []) if r.get("image_sha256") == digest
    ]
    primaries = [r for r in reviews if r.get("reviewer") == "primary"]
    if not primaries:
        return [
            f"a {reviewer} review needs a primary review of the same image bytes first"
        ]
    primary = primaries[-1]
    after = _vrp.parse_time(primary.get("recorded_at")) or 0.0
    later = [
        r
        for r in reviews
        if r.get("reviewer") == reviewer
        and (_vrp.parse_time(r.get("recorded_at")) or 0.0) >= after
    ]
    if later:
        return [
            f"this image already has its {reviewer} review; reviews are not repeated"
        ]
    if reviewer == "tiebreak":
        splits = [
            c
            for c in own.get("review_reconcile", [])
            if primary.get("event_id") in cast(list[str], c.get("reviews") or [])
            and c.get("outcome") == "disagree"
        ]
        if not splits:
            return [
                "a tiebreak review is only allowed after a round-1 reconcile"
                " that disagrees"
            ]
    return []


def record_reconcile(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    request = _strings(_payload("review_reconcile", payload), "reviews")
    if not 2 <= len(request) <= 3:
        raise ValueError(
            "reviews must list [primary, blind] or [primary, blind, tiebreak]"
        )
    own = _own(_workspace(base))
    by_id = {str(r.get("event_id")): r for r in own.get("vision_review", [])}
    missing = [event for event in request if event not in by_id]
    if missing:
        raise ValueError(f"unknown vision review event ids: {missing}")
    reviews = [by_id[event] for event in request]
    roles = [str(r.get("reviewer")) for r in reviews]
    expected = ["primary", "blind", "tiebreak"][: len(reviews)]
    if roles != expected:
        raise ValueError(f"reviews must be ordered {expected}, got {roles}")
    digests = {r.get("image_sha256") for r in reviews}
    if len(digests) != 1 or None in digests:
        raise ValueError("reconciled reviews must bind the same image bytes")
    prior = [
        c
        for c in own.get("review_reconcile", [])
        if request[0] in cast(list[str], c.get("reviews") or [])
    ]
    result = _vrp.reconcile(reviews[0], reviews[1:])
    if any(int(c.get("round") or 0) >= result["round"] for c in prior):
        raise ValueError(
            f"round {result['round']} is already reconciled for this primary review"
        )
    if result["round"] == 2 and not any(c.get("outcome") == "disagree" for c in prior):
        raise ValueError("round 2 needs a round-1 reconcile that disagrees")
    body = {"image_sha256": digests.pop(), "reviews": list(request), **result}
    return _append("review_reconcile", body, base)


def record_insight(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    base = (root or workspace_root()).resolve()
    body = _payload("insight_status", payload)
    body["evidence"] = _hash_evidence(body.get("evidence"), base)
    errors = _vrp.insight_write_errors(body, _workspace(base))
    if errors:
        raise ValueError("; ".join(errors))
    return _append("insight_status", body, base)


def record_song_receipt(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    """Reject every receipt: bard never addresses a song to itself."""
    base = (root or workspace_root()).resolve()
    body = _payload("song_receipt", payload)
    relative, path = _relative(_text(body, "delivery"), base)
    if not relative.startswith(_vrp.LIAISON_DIR + "/") or not relative.endswith(
        _vrp.SONG_DELIVERY_SUFFIX
    ):
        raise ValueError(f"delivery must be liaison/<id>{_vrp.SONG_DELIVERY_SUFFIX}")
    doc: Any = json.loads(path.read_text(encoding="utf-8"))
    problems = _vrp.song_delivery_errors(doc)
    if problems:
        raise ValueError("song delivery is malformed: " + "; ".join(problems))
    song = cast(dict[str, Any], doc)
    if song.get("to") != PLUGIN:
        raise ValueError(f"this song is addressed to {song.get('to')}, not {PLUGIN}")
    raise ValueError("bard does not address songs to itself")  # pragma: no cover


def impressions_for_artifact(
    path: Path, producer: str, root: Path | None = None
) -> tuple[list[dict[str, str]], list[str]]:
    """(refs, unresolved) for a sister artifact: its explicit impression_refs plus
    every intact producer impression bound to exactly these bytes."""
    base = (root or workspace_root()).resolve()
    workspace = _workspace(base)
    refs: list[dict[str, str]] = []
    unresolved: list[str] = []
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        value = None
    explicit: list[Any] = []
    if isinstance(value, dict):
        doc = cast(dict[str, Any], value)
        provenance = doc.get("provenance")
        explicit = cast(list[Any], doc.get("impression_refs") or [])
        if isinstance(provenance, dict):
            explicit += cast(
                list[Any], cast(dict[str, Any], provenance).get("impression_refs") or []
            )
    for item in explicit:
        if not isinstance(item, dict):
            unresolved.append("malformed impression_ref")
            continue
        entry = cast(dict[str, Any], item)
        system, event = str(entry.get("system") or producer), str(entry.get("event_id"))
        _, problem = _vrp.resolve_ref(workspace, system, event)
        if problem:
            unresolved.append(problem)
        elif {"system": system, "event_id": event} not in refs:
            refs.append({"system": system, "event_id": event})
    logs, problems = workspace.get(producer, ({}, []))
    if problems:
        unresolved.append(f"{producer} records fail integrity: {problems[0]}")
    else:
        digest = sha256_file(path)
        for kind in _vrp.IMPRESSION_KINDS:
            for record in logs.get(kind, []):
                shas = [
                    str(a.get("sha256"))
                    for a in cast(list[dict[str, Any]], record.get("artifacts") or [])
                ]
                if digest in shas or record.get("image_sha256") == digest:
                    ref = {"system": producer, "event_id": str(record.get("event_id"))}
                    if ref not in refs:
                        refs.append(ref)
    if not refs and not unresolved:
        unresolved.append(f"no {producer} impression is bound to {path.name}")
    return refs, unresolved


def record_read(payload: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Record a sister artifact taken in, with the impressions that came with it."""
    base = (root or workspace_root()).resolve()
    body = _payload("upstream_read", payload)
    relative, path = _relative(_text(body, "artifact"), base)
    if not path.is_file():
        raise ValueError(f"artifact is not a file: {body['artifact']}")
    producer = _text(body, "producer")
    if not _vrp._slug(producer):  # pyright: ignore[reportPrivateUsage]
        raise ValueError("producer must be a plugin slug")
    refs, unresolved = impressions_for_artifact(path, producer, base)
    record = {
        "artifact": {"path": relative, "sha256": sha256_file(path)},
        "producer": producer,
        "refs": refs,
        "unresolved": unresolved,
    }
    return _append("upstream_read", record, base)


def deliver_song(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    """Write ``liaison/<id>.bard-song.json`` for one sister.

    The song must be a workspace file (bound by sha256) and every cited
    impression must resolve to an intact impression log. Receipts and read
    records cannot be cited, so no sister record can ask for another song.
    Deliveries are immutable: an existing id is never overwritten.
    """
    base = (root or workspace_root()).resolve()
    body = _payload("song_delivery", payload)
    relative, path = _relative(_text(body, "song"), base)
    if not path.is_file():
        raise ValueError(f"song is not a file: {body['song']}")
    workspace = _workspace(base)
    problems: list[str] = []
    for ref in _refs(body, "impression_refs"):
        system, event = str(ref.get("system")), str(ref.get("event_id"))
        target, problem = _vrp.resolve_ref(workspace, system, event)
        if problem:
            problems.append(problem)
        elif target is None or target.get("kind") not in _vrp.IMPRESSION_KINDS:
            problems.append(f"{system}:{event[:12]} is not an impression")
    if problems:
        raise ValueError("unresolved impression_refs: " + "; ".join(problems))
    doc = {
        "kind": "bard_song_delivery",
        "schema_version": 1,
        "id": body.get("id"),
        "system": PLUGIN,
        "to": body.get("to"),
        "title": body.get("title"),
        "verse": body.get("verse"),
        "song": {"path": relative, "sha256": sha256_file(path)},
        "impression_refs": _refs(body, "impression_refs"),
        "reason": body.get("reason"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    errors = _vrp.song_delivery_errors(doc)
    if errors:
        raise ValueError("invalid song delivery: " + "; ".join(errors))
    target = base / _vrp.LIAISON_DIR / f"{doc['id']}{_vrp.SONG_DELIVERY_SUFFIX}"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise ValueError(
            f"song delivery {target.name} already exists; deliveries are immutable"
        ) from exc
    return {
        "verdict": "pass",
        "kind": "song_delivery",
        "path": str(target),
        "delivery": doc,
    }


RECORDERS = {
    "decision": record_decision,
    "impression": record_impression,
    "vision-review": record_vision_review,
    "reconcile": record_reconcile,
    "insight": record_insight,
    "read": record_read,
    "song-delivery": deliver_song,
}


def records_summary(root: Path | None = None) -> dict[str, Any]:
    """Counts per log, chain heads, integrity and the last Stop-hook verdict."""
    directory = records_dir(root)
    counts: dict[str, int] = {}
    heads: dict[str, str] = {}
    integrity: list[str] = []
    for kind, filename in LOG_FILES.items():
        records, problems = _vrp.verify_log(directory / filename, kind)
        counts[kind] = len(records)
        heads[kind] = _vrp.chain_head(records)
        integrity += problems
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
        "verdict": "unknown" if integrity else "pass",
        "records_dir": str(directory),
        "counts": counts,
        "heads": heads,
        "integrity_problems": integrity,
        "last_stop": status,
    }


def records_digest(root: Path | None = None) -> dict[str, Any]:
    return _vrp.digest((root or workspace_root()).resolve())


def records_search(
    payload: Mapping[str, Any], root: Path | None = None
) -> dict[str, Any]:
    allowed = {
        "query",
        "system",
        "kind",
        "stage",
        "artifact",
        "severity",
        "open_only",
        "limit",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown search fields: {unknown}")
    return _vrp.search((root or workspace_root()).resolve(), **dict(payload))
