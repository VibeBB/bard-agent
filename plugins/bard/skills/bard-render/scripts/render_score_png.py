#!/usr/bin/env python3
"""Render ``song.abc`` to ``score.png`` inside the pinned bard-tools image.

Optional post-render step for the bard plugin. ``render_song.py`` stays the
only deterministic writer of song artifacts; this script only translates its
``song.abc`` output into a score image through ``abcm2ps -g`` then
``rsvg-convert``, always executed inside the digest-pinned ``bard-tools``
container image recorded in ``tools-image.json`` next to this directory
(overridable via ``BARD_TOOLS_IMAGE``). The image bundles the exact tool
versions and the IPA font covering Japanese lyrics, so the render never
depends on host packages: the script pulls the image once and runs the
pipeline with the input and output directories bind-mounted, no network, all
capabilities dropped, no-new-privileges, and a read-only root filesystem.
Docker itself must be on ``PATH``. The PNG is
advisory material for human and vision review — it is not part of the
provenance output set and nothing about it gates the song.

Launcher-side verification uses BARD_VERIFY_ATTESTATION=auto|require|off.
It verifies lock provenance before pulling; a local image is not re-verified
during rendering. ``--prewarm`` verifies the lock even when the image is local.

The SVG stage emits every character as a UTF-8 ``<text>`` element, so text is
never dropped at render time; the image ships fonts-ipafont so non-Latin
lyrics render instead of appearing as fallback boxes.

Python 3.12+, standard library only.

Usage::

    python3 render_score_png.py --prewarm
    python3 render_score_png.py --abc songs/<slug>/song.abc [--out-dir DIR]
    python3 render_score_png.py --abc song.abc --json
    python3 render_score_png.py --svg songs/<slug>/song.contour.svg [--out-dir DIR]

``--svg`` rasterizes any ``*.svg`` (e.g. ``song.contour.svg`` or
``cues.timeline.svg``) to ``<same stem>.png`` next to it inside the same
pinned image — rsvg-convert only, same docker hardening and exit codes.

Exit codes: ``0`` rendered; ``3`` input/output I/O error; ``4`` docker not on
PATH or no usable pinned image (score render skipped — not an error for the
song); ``5`` an external tool failed or produced no PNG.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

EXIT_IO = 3
EXIT_NO_TOOLS = 4
EXIT_TOOL_FAILED = 5

# 150 dpi matches the resolution the previous PostScript + Ghostscript path
# used, keeping the score legible in ``file_editor view`` and CI artifacts.
RSVG_DPI = "150"

# Digest-pinned tools image; populated by the publish-bard-images workflow's
# lock-update pull request.
PIN_PATH = Path(__file__).resolve().parents[1] / "tools-image.json"
IMAGE_ENV = "BARD_TOOLS_IMAGE"

PULL_TIMEOUT = 600
_ATTEST_TIMEOUT_S = 120
_GH_AUTH_TIMEOUT_S = 15
_DOCKER_INFO_TIMEOUT_S = 10
_VERIFY_ENV = "BARD_VERIFY_ATTESTATION"
_REPOSITORY = "VibeBB/bard-agent"
_PUBLISH_FILE = ".github/workflows/publish-bard-images.yml"
CONTAINER_CMD = (
    'abcm2ps -g "/in/$1" -O score.svg '
    '&& svg="$(ls score*.svg | sort | head -n 1)" '
    f'&& rsvg-convert -d {RSVG_DPI} -p {RSVG_DPI} "$svg" -o score.png'
)
CONTAINER_CMD_SVG = f'rsvg-convert -d {RSVG_DPI} -p {RSVG_DPI} "/in/$1" -o "/work/$2"'


class ImagePin(TypedDict):
    ref: str
    image: str | None
    digest: str | None
    attestation: str | None


@dataclass
class RenderError(Exception):
    message: str
    exit_code: int

    def __str__(self) -> str:
        return self.message


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], tool: str, timeout: int = 120) -> None:
    proc = _run_timed(cmd, tool, timeout)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit code {proc.returncode}"
        raise RenderError(f"{tool}: {tail}", EXIT_TOOL_FAILED)


def _run_timed(
    cmd: list[str], tool: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except OSError as exc:
        raise RenderError(f"{tool}: failed to launch: {exc}", EXIT_TOOL_FAILED) from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            f"{tool}: timed out after {timeout}s", EXIT_TOOL_FAILED
        ) from exc


def _attestation_mode() -> str:
    mode = os.environ.get(_VERIFY_ENV, "auto")
    if mode not in {"auto", "require", "off"}:
        raise ValueError(f"{_VERIFY_ENV} must be auto, require, or off (got {mode!r})")
    return mode


def _docker_pin() -> ImagePin | None:
    """Return the locked image metadata, or an override without lock context."""
    override = os.environ.get(IMAGE_ENV, "").strip()
    if override:
        return {
            "ref": override,
            "image": None,
            "digest": None,
            "attestation": None,
        }
    if not PIN_PATH.is_file():
        return None
    try:
        data = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(
            f"cannot read tools image pin {PIN_PATH}: {exc}", EXIT_TOOL_FAILED
        ) from exc
    if not isinstance(data, dict):
        raise RenderError(
            f"tools image pin {PIN_PATH} is not a JSON object", EXIT_TOOL_FAILED
        )
    image = data.get("image")
    digest = data.get("digest")
    if (
        not isinstance(image, str)
        or not image
        or not isinstance(digest, str)
        or not digest
    ):
        return None
    attestation = data.get("attestation")
    return {
        "ref": f"{image}@{digest}",
        "image": image,
        "digest": digest,
        "attestation": attestation if isinstance(attestation, str) else None,
    }


def _verify_attestation(pin: ImagePin, *, override: bool) -> None:
    mode = _attestation_mode()
    if mode == "off":
        return
    gh = shutil.which("gh")
    reason: str | None = None
    if override:
        reason = "tools image override has no lock attestation context"
    elif not pin["attestation"]:
        reason = "lock entry has no attestation"
    elif not pin["image"] or not pin["digest"]:
        reason = "lock entry has no digest"
    elif gh is None:
        reason = "gh is not on PATH"
    else:
        try:
            auth = _run_timed(
                [gh, "auth", "status"], "gh auth status", _GH_AUTH_TIMEOUT_S
            )
        except RenderError:
            reason = "gh auth status failed"
        else:
            if auth.returncode != 0:
                reason = "gh auth status failed"
    if reason is not None:
        if mode == "require":
            raise RuntimeError(f"attestation verification required but {reason}")
        print(
            f"render_score_png.py: attestation verification skipped: {reason}",
            file=sys.stderr,
        )
        return
    assert gh is not None
    assert pin["image"] is not None and pin["digest"] is not None
    try:
        result = _run_timed(
            [
                gh,
                "attestation",
                "verify",
                f"oci://{pin['image']}@{pin['digest']}",
                "--repo",
                _REPOSITORY,
                "--signer-workflow",
                f"{_REPOSITORY}/{_PUBLISH_FILE}",
            ],
            "gh attestation verify",
            _ATTEST_TIMEOUT_S,
        )
    except RenderError as exc:
        raise RuntimeError(str(exc)) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"attestation verification failed for {pin['image']}@{pin['digest']}"
        )


def _docker_info_security_options(docker: str) -> str | None:
    """Return `docker info` security options, or None when unavailable."""
    try:
        result = subprocess.run(
            [docker, "info", "-f", "{{json .SecurityOptions}}"],
            capture_output=True,
            text=True,
            timeout=_DOCKER_INFO_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _container_user(docker: str) -> str:
    """uid:gid to run the render container as.

    On rootless Docker the host uid maps to an unmapped subuid inside the
    container user namespace, so the /work bind-mount writes fail. There
    container root (0:0) maps back to the daemon's owner — the invoking
    user — so 0:0 keeps writes working without weakening isolation (the
    container stays read-only, network-less, and cap-dropped). On rootful
    Docker keep the host uid so artifacts stay user-owned.
    """
    if "name=rootless" in (_docker_info_security_options(docker) or ""):
        return "0:0"
    return f"{os.getuid()}:{os.getgid()}"


def _inside_conversation_container() -> bool:
    """True when running inside an OpenHands docker conversation runtime.

    The runtime injects ``OH_PERSISTENCE_DIR``/``OH_RUNTIME_LAUNCHED_PROFILE``
    into each ``agent-server-conversation-*`` container, which carries no
    docker client — the pinned bard-tools image then has nowhere to launch.
    ``OH_CONVERSATION_RUNTIME`` is not usable as the signal: the runtime
    sets it to ``local`` inside the container itself.
    """
    if os.environ.get("OH_PERSISTENCE_DIR") or os.environ.get(
        "OH_RUNTIME_LAUNCHED_PROFILE"
    ):
        return True
    with contextlib.suppress(OSError):
        return Path.home() == Path("/var/openhands/.openhands")
    return False


def _docker_missing() -> RenderError:
    detail = "docker not on PATH"
    if _inside_conversation_container():
        detail += (
            " — this appears to be an OpenHands docker conversation "
            "container, which cannot launch tool containers; set the "
            "conversation runtime to local (Agent Canvas -> Settings -> "
            "Application) and start a new conversation"
        )
    return RenderError(detail, EXIT_NO_TOOLS)


def _render_container(
    abc_path: Path, out_dir: Path, pin: ImagePin, *, override: bool
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise _docker_missing()
    ref = pin["ref"]
    try:
        _run([docker, "image", "inspect", ref], "docker image inspect")
    except RenderError:
        try:
            _verify_attestation(pin, override=override)
        except RuntimeError as exc:
            raise RenderError(str(exc), EXIT_TOOL_FAILED) from exc
        _run([docker, "pull", ref], "docker pull", timeout=PULL_TIMEOUT)
    cmd = [
        docker,
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "-e",
        "HOME=/tmp",
        "-v",
        f"{abc_path.resolve().parent}:/in:ro",
        "-v",
        f"{out_dir.resolve()}:/work",
        "-w",
        "/work",
    ]
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        cmd += ["--user", _container_user(docker)]
    cmd += [ref, "sh", "-c", CONTAINER_CMD, "sh", abc_path.name]
    _run(cmd, "docker run")


def _render_svg_container(
    svg_path: Path, out_dir: Path, out_name: str, pin: ImagePin, *, override: bool
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise _docker_missing()
    ref = pin["ref"]
    try:
        _run([docker, "image", "inspect", ref], "docker image inspect")
    except RenderError:
        try:
            _verify_attestation(pin, override=override)
        except RuntimeError as exc:
            raise RenderError(str(exc), EXIT_TOOL_FAILED) from exc
        _run([docker, "pull", ref], "docker pull", timeout=PULL_TIMEOUT)
    cmd = [
        docker,
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "-e",
        "HOME=/tmp",
        "-v",
        f"{svg_path.resolve().parent}:/in:ro",
        "-v",
        f"{out_dir.resolve()}:/work",
        "-w",
        "/work",
    ]
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        cmd += ["--user", _container_user(docker)]
    cmd += [ref, "sh", "-c", CONTAINER_CMD_SVG, "sh", svg_path.name, out_name]
    _run(cmd, "docker run")


def prewarm_tools_image() -> str:
    """Verify and pull the pinned tools image without rendering a score."""
    try:
        _attestation_mode()
    except ValueError as exc:
        raise RenderError(str(exc), 2) from exc
    pin = _docker_pin()
    if pin is None:
        raise RenderError(
            f"no pinned bard-tools image ({PIN_PATH} missing or digest unset)",
            EXIT_NO_TOOLS,
        )
    docker = shutil.which("docker")
    if docker is None:
        raise _docker_missing()
    override = bool(os.environ.get(IMAGE_ENV, "").strip())
    try:
        _verify_attestation(pin, override=override)
    except RuntimeError as exc:
        raise RenderError(str(exc), EXIT_TOOL_FAILED) from exc
    try:
        _run([docker, "image", "inspect", pin["ref"]], "docker image inspect")
    except RenderError:
        _run([docker, "pull", pin["ref"]], "docker pull", timeout=PULL_TIMEOUT)
    return pin["ref"]


def render_score_png(abc_path: Path, out_dir: Path) -> dict[str, str]:
    """Render ``abc_path`` to ``out_dir/score.png``; return artifact details."""
    try:
        _attestation_mode()
    except ValueError as exc:
        raise RenderError(str(exc), 2) from exc
    if not abc_path.is_file():
        raise RenderError(f"abc not found: {abc_path}", EXIT_IO)
    pin = _docker_pin()
    if pin is None:
        raise RenderError(
            f"no pinned bard-tools image ({PIN_PATH} missing or digest unset; "
            "score render skipped)",
            EXIT_NO_TOOLS,
        )
    ref = pin["ref"]
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RenderError(f"cannot create {out_dir}: {exc}", EXIT_IO) from exc

    png_path = out_dir / "score.png"
    # abcm2ps -g appends a per-tune index (score001.svg, score002.svg, ...);
    # the proposal contract emits a single tune, so the first file is the score.
    _render_container(
        abc_path, out_dir, pin, override=bool(os.environ.get(IMAGE_ENV, "").strip())
    )
    svg_paths = sorted(out_dir.glob("score*.svg"))
    if not svg_paths:
        raise RenderError("abcm2ps produced no SVG output", EXIT_TOOL_FAILED)
    svg_path = svg_paths[0]

    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise RenderError("rsvg-convert produced no score.png", EXIT_TOOL_FAILED)
    return {
        "abc": str(abc_path),
        "score_svg": str(svg_path),
        "score_png": str(png_path),
        "score_png_sha256": _sha256(png_path),
        "image": ref,
    }


def render_svg_png(svg_path: Path, out_dir: Path) -> dict[str, str]:
    """Rasterize ``svg_path`` to ``out_dir/<stem>.png`` in the pinned image."""
    try:
        _attestation_mode()
    except ValueError as exc:
        raise RenderError(str(exc), 2) from exc
    if not svg_path.is_file():
        raise RenderError(f"svg not found: {svg_path}", EXIT_IO)
    pin = _docker_pin()
    if pin is None:
        raise RenderError(
            f"no pinned bard-tools image ({PIN_PATH} missing or digest unset; "
            "svg rasterize skipped)",
            EXIT_NO_TOOLS,
        )
    ref = pin["ref"]
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RenderError(f"cannot create {out_dir}: {exc}", EXIT_IO) from exc
    png_name = svg_path.name[: -len(".svg")] + ".png"
    _render_svg_container(
        svg_path,
        out_dir,
        png_name,
        pin,
        override=bool(os.environ.get(IMAGE_ENV, "").strip()),
    )
    png_path = out_dir / png_name
    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise RenderError(f"rsvg-convert produced no {png_name}", EXIT_TOOL_FAILED)
    return {
        "svg": str(svg_path),
        "png": str(png_path),
        "png_sha256": _sha256(png_path),
        "image": ref,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "Render song.abc to score.png").splitlines()[0]
    )
    parser.add_argument(
        "--prewarm", action="store_true", help="verify and prewarm the pinned image"
    )
    parser.add_argument("--abc", type=Path, help="path to song.abc")
    parser.add_argument(
        "--svg",
        type=Path,
        help="rasterize an SVG (e.g. song.contour.svg) to <stem>.png",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="output directory (default: the .abc file's directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as one JSON object",
    )
    args = parser.parse_args(argv)

    if args.prewarm:
        if args.abc is not None or args.svg is not None:
            parser.error("--abc/--svg cannot be used with --prewarm")
        try:
            image = prewarm_tools_image()
        except RenderError as exc:
            if args.json:
                print(json.dumps({"ok": False, "reason": str(exc)}))
            else:
                print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code
        if args.json:
            print(json.dumps({"ok": True, "image": image}))
        else:
            print(f"prewarmed tools image: {image}")
        return 0
    if args.svg is not None:
        if args.abc is not None:
            parser.error("--svg cannot be combined with --abc")
        if args.svg.suffix != ".svg":
            parser.error("--svg expects a .svg file")
        out_dir = (
            args.out_dir if args.out_dir is not None else args.svg.resolve().parent
        )
        try:
            result = render_svg_png(args.svg, out_dir)
        except RenderError as exc:
            if args.json:
                print(json.dumps({"ok": False, "reason": str(exc)}))
            else:
                print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code
        if args.json:
            print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        else:
            print(f"{result['png']}")
            print(f"sha256: {result['png_sha256']}")
        return 0
    if args.abc is None:
        parser.error("--abc or --svg is required unless --prewarm is set")

    out_dir = args.out_dir if args.out_dir is not None else args.abc.resolve().parent
    try:
        result = render_score_png(args.abc, out_dir)
    except RenderError as exc:
        if args.json:
            print(json.dumps({"ok": False, "reason": str(exc)}))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    if args.json:
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    else:
        print(f"score.png: {result['score_png']}")
        print(f"sha256: {result['score_png_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
