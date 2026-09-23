"""Tests for render_score_png.py (abcm2ps + rsvg-convert, advisory artifact)."""

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
    # Emulate the external tools: abcm2ps -g writes <stem>001.svg next to its
    # -O target, rsvg-convert writes its -o target.
    if cmd[0] == "abcm2ps":
        target = Path(cmd[cmd.index("-O") + 1])
        output = target.with_name(target.stem + "001" + target.suffix)
        output.write_bytes(b"<svg>fake</svg>")
    elif cmd[0] == "rsvg-convert":
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"\x89PNG fake")
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
    # No tools and no usable docker fallback: an absent pin file plus an
    # empty override keep the skip deterministic once the real pin carries
    # a digest.
    monkeypatch.setattr(score_module, "PIN_PATH", tmp_path / "no-pin.json")
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
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
    assert result["score_svg"] == str(tmp_path / "score001.svg")
    assert (tmp_path / "score001.svg").is_file()


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
_RSVG = shutil.which("rsvg-convert")
requires_score_tools = pytest.mark.skipif(
    _ABCM2PS is None or _RSVG is None,
    reason="abcm2ps/rsvg-convert not installed",
)


@pytest.fixture()
def _require_score_tools() -> None:
    if os.environ.get("BARD_REQUIRE_ABCM2PS") == "1" and (
        _ABCM2PS is None or _RSVG is None
    ):
        pytest.fail(
            "BARD_REQUIRE_ABCM2PS=1 is set but abcm2ps/rsvg-convert are not on PATH"
        )


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


@requires_score_tools
@pytest.mark.usefixtures("_require_score_tools")
def test_abcm2ps_score_png_real_render_cjk(tmp_path: Path) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text(
        "X:1\nT:夜のビルドの歌\nC:bard-agent\nM:4/4\nL:1/8\nQ:1/4=96\nK:D\n"
        "D2 D2 E2 F2|G2 F2 E2 D2|]\nw: さ-く-ら-の し-た-で-う-\n",
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


# ---------------------------------------------------------------------------
# docker fallback


def _which_docker_only(t: str) -> str | None:
    return "/usr/bin/docker" if t == "docker" else None


def _pin_file(tmp_path: Path, digest: object = "sha256:" + "ab" * 32) -> Path:
    pin = tmp_path / "tools-image.json"
    pin.write_text(
        json.dumps(
            {
                "image": "ghcr.io/vibebb/bard-tools",
                "tag": "deadbeef-tools",
                "digest": digest,
            }
        ),
        encoding="utf-8",
    )
    return pin


def _fake_docker_run_ok(
    cmd: list[str], **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    assert cmd[0].endswith("docker")
    sub = cmd[1:]
    if sub[:3] == ["image", "inspect"]:
        return subprocess.CompletedProcess(cmd, 0, "[]", "")
    if sub[:2] == ["pull"]:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    if sub[0] == "run":
        # Emulate the container: abcm2ps writes score001.svg into the /work
        # mount, rsvg-convert writes score.png.
        work = Path(next(a for a in cmd if a.endswith(":/work")).split(":")[0])
        (work / "score001.svg").write_bytes(b"<svg>fake</svg>")
        (work / "score.png").write_bytes(b"\x89PNG fake")
    return subprocess.CompletedProcess(cmd, 0, "", "")


def test_docker_fallback_renders(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)
    result = score_module.render_score_png(abc, tmp_path)
    assert result["renderer"] == "docker"
    assert result["image"] == "ghcr.io/vibebb/bard-tools@sha256:" + "ab" * 32
    assert (tmp_path / "score.png").is_file()


def test_docker_fallback_env_override(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setenv("BARD_TOOLS_IMAGE", "example.invalid/tools@sha256:" + "cd" * 32)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)
    result = score_module.render_score_png(abc, tmp_path)
    assert result["renderer"] == "docker"
    assert result["image"].startswith("example.invalid/tools@sha256:")


def test_docker_fallback_no_pin_is_skip(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path, digest=None))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_NO_TOOLS


def test_docker_fallback_missing_docker_is_skip(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", lambda _t: None)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_NO_TOOLS
    assert "docker not on PATH" in str(err.value)


def test_docker_fallback_pull_failure(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)

    def fail(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[0].endswith("docker")
        if cmd[1:4] == ["image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "not found")
        return subprocess.CompletedProcess(cmd, 1, "", "pull access denied")

    monkeypatch.setattr(score_module.subprocess, "run", fail)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_TOOL_FAILED
    assert "docker pull" in str(err.value)


def test_docker_fallback_corrupt_pin(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    pin = tmp_path / "tools-image.json"
    pin.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", pin)
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_TOOL_FAILED
