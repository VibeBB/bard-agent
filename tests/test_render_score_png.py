"""Tests for render_score_png.py (dockerized abcm2ps + rsvg-convert, advisory)."""

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
PIN_PATH = (
    REPO_ROOT / "plugins" / "bard" / "skills" / "bard-render" / "tools-image.json"
)


@pytest.fixture()
def score_module() -> Any:
    spec = importlib.util.spec_from_file_location("render_score_png", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_score_png"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# container render (the only render path)


def _which_docker_only(t: str) -> str | None:
    return "/usr/bin/docker" if t == "docker" else None


def _which_gh_and_docker(name: str) -> str | None:
    return f"/usr/bin/{name}" if name in {"docker", "gh"} else None


def _no_tools(_name: str) -> str | None:
    return None


def _unexpected_which(_name: str) -> str | None:
    pytest.fail("unexpected tool lookup")


def _pin_file(tmp_path: Path, digest: object = "sha256:" + "ab" * 32) -> Path:
    pin = tmp_path / "tools-image.json"
    pin.write_text(
        json.dumps(
            {
                "image": "ghcr.io/vibebb/bard-tools",
                "tag": "deadbeef-tools",
                "digest": digest,
                "attestation": "https://github.com/VibeBB/bard-agent/attestations/1",
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


def _unexpected_subprocess(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("unexpected subprocess call")


def test_missing_abc_is_io_error(score_module: Any, tmp_path: Path) -> None:
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(tmp_path / "nope.abc", tmp_path)
    assert err.value.exit_code == score_module.EXIT_IO


def test_container_render_returns_png_sha(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)
    result = score_module.render_score_png(abc, tmp_path)
    png = tmp_path / "score.png"
    assert result["score_png"] == str(png)
    assert result["score_png_sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()
    assert result["score_svg"] == str(tmp_path / "score001.svg")
    assert result["image"] == "ghcr.io/vibebb/bard-tools@sha256:" + "ab" * 32
    assert (tmp_path / "score001.svg").is_file()


def test_container_render_env_override(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setenv("BARD_TOOLS_IMAGE", "example.invalid/tools@sha256:" + "cd" * 32)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)
    result = score_module.render_score_png(abc, tmp_path)
    assert result["image"].startswith("example.invalid/tools@sha256:")


def test_no_pin_is_skip(
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


def test_missing_pin_file_is_skip(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", tmp_path / "no-pin.json")
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_NO_TOOLS


def test_missing_docker_is_skip(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _no_tools)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_NO_TOOLS
    assert "docker not on PATH" in str(err.value)


def test_container_pull_failure(
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


def test_container_run_failure(
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
            return subprocess.CompletedProcess(cmd, 0, "[]", "")
        return subprocess.CompletedProcess(cmd, 1, "", "syntax error")

    monkeypatch.setattr(score_module.subprocess, "run", fail)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_score_png(abc, tmp_path)
    assert err.value.exit_code == score_module.EXIT_TOOL_FAILED


def test_corrupt_pin(
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


def test_cli_json_ok(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)
    code = score_module.main(["--abc", str(abc), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert (
        payload["score_png_sha256"]
        == hashlib.sha256((tmp_path / "score.png").read_bytes()).hexdigest()
    )


def test_attestation_verification_uses_lock_signer(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "require")
    monkeypatch.setattr(score_module.shutil, "which", _which_gh_and_docker)
    commands: list[tuple[list[str], dict[str, Any]]] = []

    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append((cmd, kwargs))
        if cmd[0].endswith("/gh"):
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "not found")
        if cmd[1:2] == ["run"]:
            work = Path(next(a for a in cmd if a.endswith(":/work")).split(":")[0])
            (work / "score001.svg").write_bytes(b"<svg>fake</svg>")
            (work / "score.png").write_bytes(b"\x89PNG fake")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(score_module.subprocess, "run", run)
    pin = _pin_file(tmp_path)
    monkeypatch.setattr(score_module, "PIN_PATH", pin)
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")

    score_module.render_score_png(abc, tmp_path)

    verify_index = next(
        index
        for index, (command, _kwargs) in enumerate(commands)
        if command[1:3] == ["attestation", "verify"]
    )
    verify, verify_kwargs = commands[verify_index]
    assert verify == [
        "/usr/bin/gh",
        "attestation",
        "verify",
        "oci://ghcr.io/vibebb/bard-tools@sha256:" + "ab" * 32,
        "--repo",
        "VibeBB/bard-agent",
        "--signer-workflow",
        "VibeBB/bard-agent/.github/workflows/publish-bard-images.yml",
    ]
    auth_index = next(
        index
        for index, (command, _kwargs) in enumerate(commands)
        if command[1:3] == ["auth", "status"]
    )
    auth, auth_kwargs = commands[auth_index]
    assert auth == ["/usr/bin/gh", "auth", "status"]
    assert auth_kwargs["timeout"] == score_module._GH_AUTH_TIMEOUT_S
    assert verify_kwargs["timeout"] == score_module._ATTEST_TIMEOUT_S
    pull_index = next(
        index
        for index, (command, _kwargs) in enumerate(commands)
        if command[1:2] == ["pull"]
    )
    assert auth_index < verify_index < pull_index


def test_required_attestation_failure_prevents_pull(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "require")
    monkeypatch.setattr(
        score_module.shutil,
        "which",
        _which_docker_only,
    )
    commands: list[list[str]] = []

    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        if cmd[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "not found")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(score_module.subprocess, "run", run)
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")

    with pytest.raises(score_module.RenderError, match="gh is not on PATH"):
        score_module.render_score_png(abc, tmp_path)
    assert not any(command[1:2] == ["pull"] for command in commands)


def test_invalid_attestation_mode_exits_two(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "invalid")
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")

    assert score_module.main(["--abc", str(abc)]) == 2


def test_off_does_not_look_up_gh(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "off")
    monkeypatch.setattr(
        score_module,
        "PIN_PATH",
        _pin_file(tmp_path),
    )
    monkeypatch.setattr(
        score_module.shutil,
        "which",
        _unexpected_which,
    )
    monkeypatch.setattr(
        score_module.subprocess,
        "run",
        _unexpected_subprocess,
    )
    pin = score_module._docker_pin()
    assert pin is not None
    score_module._verify_attestation(pin, override=False)


def test_auto_skips_when_gh_is_missing(
    score_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "auto")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(
        score_module.subprocess,
        "run",
        _unexpected_subprocess,
    )
    pin = score_module._docker_pin()
    assert pin is not None
    score_module._verify_attestation(pin, override=False)
    assert "gh is not on PATH" in capsys.readouterr().err


def test_auto_skips_without_lock_attestation(
    score_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "auto")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    pin = score_module._docker_pin()
    assert pin is not None
    pin["attestation"] = None
    monkeypatch.setattr(score_module.shutil, "which", _which_gh_and_docker)
    monkeypatch.setattr(
        score_module.subprocess,
        "run",
        _unexpected_subprocess,
    )
    score_module._verify_attestation(pin, override=False)
    assert "lock entry has no attestation" in capsys.readouterr().err


def test_auto_skips_when_auth_fails(
    score_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "auto")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.setattr(score_module.shutil, "which", _which_gh_and_docker)

    def failed_auth(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(
        score_module.subprocess,
        "run",
        failed_auth,
    )
    pin = score_module._docker_pin()
    assert pin is not None
    score_module._verify_attestation(pin, override=False)
    assert "gh auth status failed" in capsys.readouterr().err


def test_auto_skips_image_override(
    score_module: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "auto")
    monkeypatch.setattr(score_module.shutil, "which", _which_gh_and_docker)
    monkeypatch.setattr(
        score_module.subprocess,
        "run",
        _unexpected_subprocess,
    )
    score_module._verify_attestation(
        {
            "ref": "ghcr.io/vibebb/bard-tools@sha256:" + "ab" * 32,
            "image": None,
            "digest": None,
            "attestation": None,
        },
        override=True,
    )
    assert "override has no lock attestation context" in capsys.readouterr().err


@pytest.mark.parametrize("missing_context", ["attestation", "gh"])
def test_require_errors_for_missing_context(
    score_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_context: str,
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "require")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    pin = score_module._docker_pin()
    assert pin is not None
    if missing_context == "attestation":
        pin["attestation"] = None

    def which(name: str) -> str | None:
        return None if missing_context == "gh" and name == "gh" else f"/usr/bin/{name}"

    monkeypatch.setattr(score_module.shutil, "which", which)
    with pytest.raises(RuntimeError, match="verification required"):
        score_module._verify_attestation(pin, override=False)


def test_attestation_timeout_prevents_pull(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "require")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.setattr(score_module.shutil, "which", _which_gh_and_docker)
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["attestation", "verify"]:
            raise subprocess.TimeoutExpired(command, score_module._ATTEST_TIMEOUT_S)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(score_module.subprocess, "run", run)
    with pytest.raises(score_module.RenderError, match="timed out"):
        score_module.prewarm_tools_image()
    assert not any(command[1:2] == ["pull"] for command in commands)


def test_prewarm_verifies_attestation_when_image_is_local(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "require")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_gh_and_docker)
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(score_module.subprocess, "run", run)

    image = score_module.prewarm_tools_image()

    verify = next(
        command for command in commands if command[1:3] == ["attestation", "verify"]
    )
    inspect = next(
        command for command in commands if command[1:3] == ["image", "inspect"]
    )
    assert commands.index(verify) < commands.index(inspect)
    assert image == "ghcr.io/vibebb/bard-tools@sha256:" + "ab" * 32
    assert not any(command[1:2] == ["pull"] for command in commands)


def test_normal_render_with_local_image_does_not_verify(
    score_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "require")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)

    score_module.render_score_png(abc, tmp_path)

    assert capsys.readouterr().err == ""


def test_prewarm_cli_succeeds(
    score_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setenv("BARD_VERIFY_ATTESTATION", "off")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_ok)

    assert score_module.main(["--prewarm", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "image": "ghcr.io/vibebb/bard-tools@sha256:" + "ab" * 32,
    }


def test_cli_json_no_pin(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", tmp_path / "no-pin.json")
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    code = score_module.main(["--abc", str(abc), "--json"])
    assert code == score_module.EXIT_NO_TOOLS
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# real render inside the pinned image (opt-in; needs docker)


def _tools_image() -> str | None:
    override = os.environ.get("BARD_TOOLS_IMAGE", "").strip()
    if override:
        return override
    try:
        data = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    image, digest = data.get("image"), data.get("digest")
    return f"{image}@{digest}" if image and digest else None


_DOCKER = shutil.which("docker")
_IMAGE = _tools_image()
requires_docker = pytest.mark.skipif(
    _DOCKER is None or _IMAGE is None,
    reason="docker or the pinned bard-tools image is unavailable",
)


@pytest.fixture()
def _require_docker() -> None:
    if os.environ.get("BARD_REQUIRE_DOCKER") == "1" and (
        _DOCKER is None or _IMAGE is None
    ):
        pytest.fail(
            "BARD_REQUIRE_DOCKER=1 is set but docker or the pinned "
            "bard-tools image is unavailable"
        )


@requires_docker
@pytest.mark.usefixtures("_require_docker")
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


@requires_docker
@pytest.mark.usefixtures("_require_docker")
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
# --svg mode (rsvg-convert only, same hardening)


def _fake_docker_run_svg(
    cmd: list[str], **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    assert cmd[0].endswith("docker")
    sub = cmd[1:]
    if sub[:3] == ["image", "inspect"]:
        return subprocess.CompletedProcess(cmd, 0, "[]", "")
    if sub[:2] == ["pull"]:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    if sub[0] == "run":
        work = Path(next(a for a in cmd if a.endswith(":/work")).split(":")[0])
        (work / "song.contour.png").write_bytes(b"\x89PNG fake")
    return subprocess.CompletedProcess(cmd, 0, "", "")


def test_svg_render_returns_png_sha(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svg = tmp_path / "song.contour.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_svg)
    result = score_module.render_svg_png(svg, tmp_path)
    png = tmp_path / "song.contour.png"
    assert result["png"] == str(png)
    assert result["png_sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()


def test_svg_missing_is_io_error(score_module: Any, tmp_path: Path) -> None:
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_svg_png(tmp_path / "nope.svg", tmp_path)
    assert err.value.exit_code == score_module.EXIT_IO


def test_svg_no_pin_is_skip(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svg = tmp_path / "song.contour.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path, digest=None))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _unexpected_subprocess)
    with pytest.raises(score_module.RenderError) as err:
        score_module.render_svg_png(svg, tmp_path)
    assert err.value.exit_code == score_module.EXIT_NO_TOOLS


def test_svg_cli_path(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svg = tmp_path / "song.contour.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)
    monkeypatch.setattr(score_module.subprocess, "run", _fake_docker_run_svg)
    assert score_module.main(["--svg", str(svg), "--out-dir", str(tmp_path)]) == 0
    assert (tmp_path / "song.contour.png").is_file()


@requires_docker
@pytest.mark.usefixtures("_require_docker")
def test_abcm2ps_svg_rasterize_real_render(tmp_path: Path) -> None:
    svg = tmp_path / "song.contour.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
        '<rect width="40" height="40" fill="#ffffff"/></svg>',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--svg", str(svg), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    png = tmp_path / "song.contour.png"
    assert payload["ok"] is True
    assert png.is_file() and png.read_bytes()[:4] == b"\x89PNG"


def test_container_user_rootless(
    score_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rootless daemons get 0:0; rootful/unreachable keep the host uid."""
    users: list[str] = []

    def run_rootless(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[1:4] == ["info", "-f", "{{json .SecurityOptions}}"]:
            out = '["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]'
            return subprocess.CompletedProcess(cmd, 0, out, "")
        return _fake_docker_run_ok(cmd, **kwargs)

    def run_plain(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_docker_run_ok(cmd, **kwargs)

    abc = tmp_path / "song.abc"
    abc.write_text("X:1\nT:t\nK:C\n", encoding="utf-8")
    monkeypatch.setattr(score_module, "PIN_PATH", _pin_file(tmp_path))
    monkeypatch.delenv("BARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(score_module.shutil, "which", _which_docker_only)

    def capture_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        proc = run_rootless(cmd, **kwargs)
        if cmd[1] == "run":
            users.append(cmd[cmd.index("--user") + 1])
        return proc

    monkeypatch.setattr(score_module.subprocess, "run", capture_run)
    score_module.render_score_png(abc, tmp_path)
    assert users == ["0:0"]

    users.clear()
    monkeypatch.setattr(score_module.subprocess, "run", capture_run)

    def capture_plain(
        cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        proc = run_plain(cmd, **kwargs)
        if cmd[1] == "run":
            users.append(cmd[cmd.index("--user") + 1])
        return proc

    monkeypatch.setattr(score_module.subprocess, "run", capture_plain)
    score_module.render_score_png(abc, tmp_path)
    assert users == [f"{os.getuid()}:{os.getgid()}"]
