"""Tests for scripts/update_tools_image_lock.py and measure_image_tools.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_SCRIPT = REPO_ROOT / "scripts" / "update_tools_image_lock.py"
MEASURE_SCRIPT = REPO_ROOT / "scripts" / "measure_image_tools.py"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def lock_module() -> Any:
    return _load(LOCK_SCRIPT, "update_tools_image_lock")


@pytest.fixture()
def measure_module() -> Any:
    return _load(MEASURE_SCRIPT, "measure_image_tools")


def _tools_json(tmp_path: Path) -> Path:
    path = tmp_path / "tools.json"
    path.write_text(
        json.dumps({"abcm2ps": "8.14.11", "rsvg-convert": "2.60.0"}),
        encoding="utf-8",
    )
    return path


def _run_lock(module: Any, tmp_path: Path, digest: str) -> int:
    pin = tmp_path / "tools-image.json"
    return module.main(
        [
            "--pin",
            str(pin),
            "--image",
            "ghcr.io/vibebb/bard-tools",
            "--tag",
            "deadbeef-tools",
            "--digest",
            digest,
            "--published-at",
            "2026-09-23T00:00:00Z",
            "--workflow-run",
            "https://github.com/VibeBB/bard-agent/actions/runs/1",
            "--tools-json",
            str(_tools_json(tmp_path)),
        ]
    )


def test_lock_writes_entry(lock_module: Any, tmp_path: Path) -> None:
    digest = "sha256:" + "ab" * 32
    assert _run_lock(lock_module, tmp_path, digest) == 0
    entry = json.loads((tmp_path / "tools-image.json").read_text(encoding="utf-8"))
    assert entry["image"] == "ghcr.io/vibebb/bard-tools"
    assert entry["digest"] == digest
    assert entry["tools"]["abcm2ps"] == "8.14.11"
    assert entry["dockerfile"] == "docker/bard-tools.Dockerfile"


def test_lock_rejects_bad_digest(lock_module: Any, tmp_path: Path) -> None:
    assert _run_lock(lock_module, tmp_path, "not-a-digest") == 1
    assert not (tmp_path / "tools-image.json").exists()


def test_lock_rejects_bad_tools_json(lock_module: Any, tmp_path: Path) -> None:
    bad = tmp_path / "tools.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    pin = tmp_path / "tools-image.json"
    code = lock_module.main(
        [
            "--pin",
            str(pin),
            "--image",
            "img",
            "--tag",
            "t",
            "--digest",
            "sha256:" + "ab" * 32,
            "--published-at",
            "now",
            "--workflow-run",
            "url",
            "--tools-json",
            str(bad),
        ]
    )
    assert code == 1


def test_measure_parses_probe_output(
    measure_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = "\n".join(
        [
            "abcm2ps=abcm2ps-8.14.11 (2020-12-05)",
            "abc2midi=4.68 February 18 2022 abc2midi",
            "rsvg-convert=rsvg-convert version 2.60.0",
            "fonts-ipafont=003001-4",
        ]
    )

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    monkeypatch.setattr(measure_module.subprocess, "run", fake_run)
    tools = measure_module.probe_image("img@sha256:" + "ab" * 32)
    assert tools == {
        "abcm2ps": "8.14.11",
        "abc2midi": "4.68",
        "rsvg-convert": "2.60.0",
        "fonts-ipafont": "003001-4",
    }


def test_measure_fails_on_probe_error(
    measure_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, "", "docker: error")

    monkeypatch.setattr(measure_module.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        measure_module.probe_image("img")
