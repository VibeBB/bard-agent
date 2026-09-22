"""Tests for render_score_png.py (abcm2ps + gs wrapper, optional advisory artifact)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "plugins"
    / "bard"
    / "skills"
    / "bard-render"
    / "scripts"
    / "render_score_png.py"
)


@pytest.fixture()
def score_module() -> Any:
    spec = importlib.util.spec_from_file_location("render_score_png", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_score_png"] = module
    spec.loader.exec_module(module)
    return module


def _fake_run_ok(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    # Emulate the external tools by writing their -O / -sOutputFile targets.
    output: str | None = None
    if cmd[0] == "abcm2ps":
        output = cmd[cmd.index("-O") + 1]
    elif cmd[0] == "gs":
        output = next(a.split("=", 1)[1] for a in cmd if a.startswith("-sOutputFile="))
    if output:
        Path(output).write_bytes(
            b"%!PS fake\n" if cmd[0] == "abcm2ps" else b"\x89PNG fake"
        )
    return subprocess.CompletedProcess(cmd, 0, "", "")


def _which_ok(t: str) -> str:
    return "/usr/bin/" + t


def test_missing_abc_is_io_error(score_module: Any, tmp_path: Path) -> None:
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(tmp_path / "nope.abc", tmp_path)
    assert err.value.exit_code == score_module.EXIT_IO


def test_missing_tools_reports_skip(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "song.abc").write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module.shutil, "which", lambda _t: None)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(tmp_path / "song.abc", tmp_path)
    assert err.value.exit_code == score_module.EXIT_NO_TOOLS
    assert "abcm2ps" in str(err.value)


def test_abcm2ps_failure(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "song.abc").write_text("X:1\nT:t\nK:C\n", encoding="utf-8")

    def fail(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, "", "syntax error")

    monkeypatch.setattr(score_module.shutil, "which", _which_ok)
    monkeypatch.setattr(score_module.subprocess, "run", fail)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(tmp_path / "song.abc", tmp_path)
    assert err.value.exit_code == score_module.EXIT_TOOL_FAILED


def test_happy_path_returns_png_sha(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module.shutil, "which", _which_ok)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_run_ok)
    result = score_module.render_score_png(abc, tmp_path)
    png = tmp_path / "score.png"
    assert result["score_png"] == str(png)
    assert result["score_png_sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()
    assert (tmp_path / "score.ps").is_file()


def test_cli_json_ok(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module.shutil, "which", _which_ok)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_run_ok)
    code = score_module.main(["--abc", str(abc), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert (
        payload["score_png_sha256"]
        == hashlib.sha256((tmp_path / "score.png").read_bytes()).hexdigest()
    )


def test_cli_json_missing_tools(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module.shutil, "which", lambda _t: None)
    code = score_module.main(["--abc", str(abc), "--json"])
    assert code == score_module.EXIT_NO_TOOLS
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


_ABCM2PS = shutil.which("abcm2ps")
_GS = shutil.which("gs")
requires_score_tools = pytest.mark.skipif(
    _ABCM2PS is None or _GS is None,
    reason="abcm2ps/gs not installed",
)


@pytest.fixture()
def _require_score_tools() -> None:
    if os.environ.get("BARD_REQUIRE_ABCM2PS") == "1" and (
        _ABCM2PS is None or _GS is None
    ):
        pytest.fail("BARD_REQUIRE_ABCM2PS=1 is set but abcm2ps/gs are not on PATH")


@requires_score_tools
@pytest.mark.usefixtures("_require_score_tools")
def test_abcm2ps_score_png_real_render(tmp_path: Path) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text(
        "X:1\nT:Real render\nC:bard-agent\nM:4/4\nL:1/8\nQ:1/4=96\nK:D\n"
        "%% section verse 1\nD2 D2 E2 F2|G2 F2 E2 D2|]\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--abc", str(abc), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    png = tmp_path / "score.png"
    assert payload["ok"] is True
    assert png.is_file() and png.stat().st_size > 0
    assert png.read_bytes()[:4] == b"\x89PNG"
