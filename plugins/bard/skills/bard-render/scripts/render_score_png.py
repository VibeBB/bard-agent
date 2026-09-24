#!/usr/bin/env python3
"""Render ``song.abc`` to ``score.png`` via abcm2ps (SVG) and rsvg-convert.

Optional post-render step for the bard plugin. ``render_song.py`` stays the
only deterministic writer of song artifacts; this script only translates its
``song.abc`` output into a score image through the same external tools the CI
workflows use (``abcm2ps -g`` then ``rsvg-convert``). It is advisory material
for human and vision review — the PNG is not part of the provenance output
set and nothing about it gates the song.

The SVG stage emits every character as a UTF-8 ``<text>`` element, so text is
never dropped at render time; font coverage is resolved by the rasterizer.
Non-Latin scripts such as Japanese still need a covering font installed on
the system (e.g. fonts-ipafont) — without one the glyphs appear as fallback
boxes instead of being silently removed. This is the same dependency CI
installs.

When the tools are not on ``PATH`` the script falls back to the digest-pinned
``bard-tools`` container image recorded in ``tools-image.json`` next to this
directory (overridable via ``BARD_TOOLS_IMAGE``): it pulls the image once and
runs the same abcm2ps + rsvg-convert pipeline inside the container with the
input and output directories bind-mounted, no network, and a read-only root
filesystem. Docker itself must be on ``PATH`` for the fallback to engage.

Python 3.12+, standard library only.

Usage::

    python3 render_score_png.py --abc songs/<slug>/song.abc [--out-dir DIR]
    python3 render_score_png.py --abc song.abc --json

Exit codes: ``0`` rendered; ``3`` input/output I/O error; ``4`` ``abcm2ps`` or
``rsvg-convert`` not on PATH and no usable docker fallback; ``5`` an external
tool failed or produced no PNG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_IO = 3
EXIT_NO_TOOLS = 4
EXIT_TOOL_FAILED = 5

# 150 dpi matches the resolution the previous PostScript + Ghostscript path
# used, keeping the score legible in ``file_editor view`` and CI artifacts.
RSVG_DPI = "150"

# Digest-pinned tools image for the docker fallback; populated by the
# publish-bard-images workflow's lock-update pull request.
PIN_PATH = Path(__file__).resolve().parents[1] / "tools-image.json"
IMAGE_ENV = "BARD_TOOLS_IMAGE"

PULL_TIMEOUT = 600
CONTAINER_CMD = (
    'abcm2ps -g "/in/$1" -O score.svg '
    '&& svg="$(ls score*.svg | sort | head -n 1)" '
    f'&& rsvg-convert -d {RSVG_DPI} -p {RSVG_DPI} "$svg" -o score.png'
)


@dataclass
class RenderError(Exception):
    message: str
    exit_code: int

    def __str__(self) -> str:
        return self.message


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], tool: str, timeout: int = 120) -> None:
    try:
        proc = subprocess.run(
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
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit code {proc.returncode}"
        raise RenderError(f"{tool}: {tail}", EXIT_TOOL_FAILED)


def _docker_ref() -> str | None:
    """Return the pinned ``image@digest`` fallback ref, or None when unset."""
    override = os.environ.get(IMAGE_ENV, "").strip()
    if override:
        return override
    if not PIN_PATH.is_file():
        return None
    try:
        data = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(
            f"cannot read docker fallback pin {PIN_PATH}: {exc}", EXIT_TOOL_FAILED
        ) from exc
    if not isinstance(data, dict):
        raise RenderError(
            f"docker fallback pin {PIN_PATH} is not a JSON object", EXIT_TOOL_FAILED
        )
    image = data.get("image")
    digest = data.get("digest")
    if not image or not digest:
        return None
    return f"{image}@{digest}"


def _render_host(abc_path: Path, out_dir: Path) -> None:
    _run(["abcm2ps", "-g", str(abc_path), "-O", str(out_dir / "score.svg")], "abcm2ps")


def _render_container(abc_path: Path, out_dir: Path, ref: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RenderError("docker not on PATH", EXIT_NO_TOOLS)
    try:
        _run([docker, "image", "inspect", ref], "docker image inspect")
    except RenderError:
        _run([docker, "pull", ref], "docker pull", timeout=PULL_TIMEOUT)
    cmd = [
        docker,
        "run",
        "--rm",
        "--network",
        "none",
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
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    cmd += [ref, "sh", "-c", CONTAINER_CMD, "sh", abc_path.name]
    _run(cmd, "docker run")


def render_score_png(abc_path: Path, out_dir: Path) -> dict[str, str]:
    """Render ``abc_path`` to ``out_dir/score.png``; return artifact details."""
    if not abc_path.is_file():
        raise RenderError(f"abc not found: {abc_path}", EXIT_IO)
    missing = [t for t in ("abcm2ps", "rsvg-convert") if shutil.which(t) is None]
    ref: str | None = None
    if missing:
        ref = _docker_ref()
        if ref is None:
            raise RenderError(
                "not on PATH: "
                + ", ".join(missing)
                + "; no pinned docker fallback image (score render skipped)",
                EXIT_NO_TOOLS,
            )
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RenderError(f"cannot create {out_dir}: {exc}", EXIT_IO) from exc

    png_path = out_dir / "score.png"
    # abcm2ps -g appends a per-tune index (score001.svg, score002.svg, ...);
    # the proposal contract emits a single tune, so the first file is the score.
    if ref is None:
        _render_host(abc_path, out_dir)
    else:
        _render_container(abc_path, out_dir, ref)
    svg_paths = sorted(out_dir.glob("score*.svg"))
    if not svg_paths:
        raise RenderError("abcm2ps produced no SVG output", EXIT_TOOL_FAILED)
    svg_path = svg_paths[0]
    if ref is None:
        _run(
            [
                "rsvg-convert",
                "-d",
                RSVG_DPI,
                "-p",
                RSVG_DPI,
                str(svg_path),
                "-o",
                str(png_path),
            ],
            "rsvg-convert",
        )

    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise RenderError("rsvg-convert produced no score.png", EXIT_TOOL_FAILED)
    result = {
        "abc": str(abc_path),
        "score_svg": str(svg_path),
        "score_png": str(png_path),
        "score_png_sha256": _sha256(png_path),
        "renderer": "docker" if ref is not None else "host",
    }
    if ref is not None:
        result["image"] = ref
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "Render song.abc to score.png").splitlines()[0]
    )
    parser.add_argument("--abc", required=True, type=Path, help="path to song.abc")
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
