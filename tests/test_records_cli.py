"""bard_cli.py record plumbing, Stop/session hooks, policy and doc drift guards.

The VRP v2 rules themselves are covered in tests/test_records.py.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "bard"
RECORDS_PATH = PLUGIN_ROOT / "scripts" / "bard_records.py"
CLI_PATH = PLUGIN_ROOT / "scripts" / "bard_cli.py"
REQUIRE_RECORDS = PLUGIN_ROOT / "hooks" / "scripts" / "require_records.py"
POLICY_PATH = PLUGIN_ROOT / "hooks" / "records-policy.json"

IMPRESSION = (
    "The verse reads settled while the refrain lifts the register, which is exactly "
    "the arc the context file asked for. One concern is that bar twelve leans on the "
    "same rhythm cell three times in a row, so the maker may hear a stall where a push "
    "was intended. Next pass should vary the pickup into the chorus before rendering, "
    "and the score image should be inspected again once the new stem directions land "
    "so the engraving impression stays honest about what the reader sees."
)

DECISION_PAYLOAD = {
    "id": "mode-choice",
    "stage": "compose",
    "question": "Which mode should the verse use?",
    "principles": ["Dorian reads as resolved-but-wistful in the songcraft table"],
    "options": [
        {
            "name": "dorian",
            "pros": ["matches wistful subject"],
            "cons": ["narrow color"],
        },
        {"name": "aeolian", "pros": ["safer"], "cons": ["too dark for the hook"]},
    ],
    "chosen": "dorian",
    "rationale": "Dorian keeps the verse wistful without collapsing into aeolian "
    "gloom; the songcraft table recommends it for retrospective subjects and the "
    "context file asks for exactly that register. " * 2,
    "evidence": [{"path": "songs/demo/song.md"}],
    "risks": ["chorus may need a borrowed chord"],
    "revisit_when": "the critic flags mode fit",
}

IMPRESSION_PAYLOAD = {
    "stage": "compose",
    "artifacts": ["songs/demo"],
    "impression": IMPRESSION,
}

VISION_PAYLOAD = {
    "image_path": "songs/demo/score.png",
    "source_event_id": "0" * 64,
    "model": "test-model",
    "checklist": "score-engraving",
    "findings": [{"category": "layout", "severity": "info", "note": "stems aligned"}],
    "impression": IMPRESSION,
}

# Wire's writer output on the identical payloads/bytes (record minus recorded_at).
EXPECTED_WIRE = {
    "decision": {
        "event_id": "e186904ba85cfee312281ebfe781819c0b3cd33a004b918e47d546699f739e32",
        "image": None,
    },
    "stage_impression": {
        "event_id": "db55c007ef5129beb82c206d8db42957ed657b7df6bb49c0025b61afd74f526d",
        "artifact_sha256": (
            "18f901437f17ae832547a12a68a12b8248cec0c85371031962b93f89a28bb0c9"
        ),
    },
    "vision_review": {
        "event_id": "1952bb6496c871ab15336599c03e697fd5b3343a3e11848e4ecad2e767cad59f",
        "image_sha256": (
            "796120837694d3f3f29259cfeb25091698c2a0aa87873658d840b4993ee889b3"
        ),
    },
}


@pytest.fixture()
def records_module() -> Any:
    spec = importlib.util.spec_from_file_location("bard_records", RECORDS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bard_records"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    song = tmp_path / "songs" / "demo"
    song.mkdir(parents=True)
    (song / "song.md").write_text("x", encoding="utf-8")
    (song / "score.png").write_bytes(b"PNG")
    return tmp_path


# ---------------------------------------------------------------------------
# writer: accept/reject and wire parity


# ---------------------------------------------------------------------------
# CLI surface


def _cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_rejects_bad_payload(workspace: Path) -> None:
    proc = _cli(
        "record",
        "impression",
        "--json",
        "-",
        "--root",
        str(workspace),
        stdin=json.dumps({"stage": "compose"}),
    )
    assert proc.returncode == 2


def test_cli_status(workspace: Path) -> None:
    proc = _cli("record", "status", "--root", str(workspace))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["counts"]["decision"] == 0


# ---------------------------------------------------------------------------
# require_records hook (subprocess, like test_hooks.py)


def _run_hook(
    phase: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    import os

    hook_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd)}
    if env:
        hook_env.update(env)
    return subprocess.run(
        [sys.executable, str(REQUIRE_RECORDS), phase],
        input=json.dumps({}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=hook_env,
        check=False,
    )


def test_session_start_creates_marker(tmp_path: Path) -> None:
    proc = _run_hook("session-start", tmp_path)
    assert proc.returncode == 0
    sessions = tmp_path / "observations" / "bard" / ".sessions"
    assert any(sessions.glob("*.json"))


def test_stop_blocks_missing_records(tmp_path: Path) -> None:
    _run_hook("session-start", tmp_path)
    (tmp_path / "songs" / "demo").mkdir(parents=True)
    (tmp_path / "songs" / "demo" / "song.md").write_text("x", encoding="utf-8")
    proc = _run_hook("stop", tmp_path)
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "deny"
    assert "stage_impression" in payload["reason"]
    assert "decision" in payload["reason"]


def test_stop_without_marker_allows(tmp_path: Path) -> None:
    proc = _run_hook("stop", tmp_path)
    assert proc.returncode == 0


def test_policy_file_shape() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert policy["plugin"] == "bard"
    assert "songs/*/*" in policy["artifact_globs"]
    assert "cues/*/*" in policy["artifact_globs"]
    assert policy["records_dir"] == "observations/bard"
    assert policy["max_stop_denials"] == 2


def test_shared_hook_digests() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    check = importlib.import_module("check_shared_hooks")
    for name in ("_records.py", "require_records.py"):
        assert (
            check._digest(PLUGIN_ROOT / "hooks" / "scripts" / name, "bard")
            == check.EXPECTED[name]
        )


# ---------------------------------------------------------------------------
# prompt/CLI drift guard: every documented bard_cli.py invocation must parse


def _documented_invocations() -> list[tuple[str, list[str]]]:
    """bard_cli.py argument lists quoted in plugin Markdown files."""
    found: list[tuple[str, list[str]]] = []
    import re
    import shlex

    for md in sorted(PLUGIN_ROOT.rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"bard_cli\.py\s+(.+)$", line)
            if match is None:
                continue
            tail = match.group(1)
            tail = re.split(r"<<|&&|\|\||;|#|`", tail)[0]
            try:
                tokens = shlex.split(tail)
            except ValueError:
                tokens = tail.split()
            # drop leading placeholders (e.g. "$p/scripts/" fragments)
            if tokens and tokens[0].startswith("$"):
                tokens = tokens[1:]
            if not tokens:
                continue
            # alternation a|b|c -> first alternative; placeholders -> "-"
            args: list[str] = []
            skip_next = False
            for token in tokens:
                if skip_next:
                    skip_next = False
                    continue
                if token in ("<file|->", "<file>", "<stem>", "<json>"):
                    args.append("-")
                elif token.startswith("<"):
                    # a bare placeholder in command position is a subcommand
                    args.append("decision" if args and args[-1] == "record" else "-")
                elif "|" in token and not token.startswith("-"):
                    args.append(token.split("|")[0])
                else:
                    args.append(token)
            found.append((f"{md.name}:{lineno}", args))
    return found


def test_documented_cli_invocations_parse() -> None:
    """Every `bard_cli.py ...` line in plugins/**/*.md must be valid syntax.

    Parsing is checked with `--help` (argparse exits 0 only when the
    preceding arguments are well formed), so nothing is executed.
    """
    invocations = _documented_invocations()
    assert invocations, "no bard_cli.py invocations found in plugin docs"
    bad: list[str] = []
    for where, args in invocations:
        proc = subprocess.run(
            [sys.executable, str(CLI_PATH), *args, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            bad.append(f"{where}: {args} -> exit {proc.returncode}")
    assert not bad, "\n".join(bad)
