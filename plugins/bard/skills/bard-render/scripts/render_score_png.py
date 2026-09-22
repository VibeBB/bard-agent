#!/usr/bin/env python3
"""Render ``song.abc`` to ``score.png`` via abcm2ps and Ghostscript.

Optional post-render step for the bard plugin. ``render_song.py`` stays the
only deterministic writer of song artifacts; this script only translates its
``song.abc`` output into a score image through the same external tools the CI
workflows use (``abcm2ps`` then ``gs``). It is advisory material for human and
vision review — the PNG is not part of the provenance output set and nothing
about it gates the song.

Japanese titles and lyrics need a CJK font on the system (e.g. fonts-ipafont),
the same dependency CI installs.

Python 3.12+, standard library only.

Usage::

    python3 render_score_png.py --abc out/bard/<slug>/song.abc [--out-dir DIR]
    python3 render_score_png.py --abc song.abc --json

Exit codes: ``0`` rendered; ``3`` input/output I/O error; ``4`` ``abcm2ps`` or
``gs`` not on PATH; ``5`` an external tool failed or produced no PNG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_IO = 3
EXIT_NO_TOOLS = 4
EXIT_TOOL_FAILED = 5

GS_ARGS = (
    "-dSAFER",
    "-dBATCH",
    "-dNOPAUSE",
    "-sDEVICE=png16m",
    "-r150",
)


@dataclass
class RenderError(Exception):
    message: str
    exit_code: int

    def __str__(self) -> str:
        return self.message


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], tool: str) -> None:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except OSError as exc:
        raise RenderError(f"{tool}: failed to launch: {exc}", EXIT_TOOL_FAILED) from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"{tool}: timed out after 120s", EXIT_TOOL_FAILED) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit code {proc.returncode}"
        raise RenderError(f"{tool}: {tail}", EXIT_TOOL_FAILED)


def render_score_png(abc_path: Path, out_dir: Path) -> dict[str, str]:
    """Render ``abc_path`` to ``out_dir/score.png``; return artifact details."""
    if not abc_path.is_file():
        raise RenderError(f"abc not found: {abc_path}", EXIT_IO)
    missing = [t for t in ("abcm2ps", "gs") if shutil.which(t) is None]
    if missing:
        raise RenderError(
            "not on PATH: " + ", ".join(missing) + " (score render skipped)",
            EXIT_NO_TOOLS,
        )
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RenderError(f"cannot create {out_dir}: {exc}", EXIT_IO) from exc

    ps_path = out_dir / "score.ps"
    png_path = out_dir / "score.png"
    _run(["abcm2ps", str(abc_path), "-O", str(ps_path)], "abcm2ps")
    _run(["gs", *GS_ARGS, f"-sOutputFile={png_path}", str(ps_path)], "gs")

    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise RenderError("gs produced no score.png", EXIT_TOOL_FAILED)
    return {
        "abc": str(abc_path),
        "score_ps": str(ps_path),
        "score_png": str(png_path),
        "score_png_sha256": _sha256(png_path),
    }


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
