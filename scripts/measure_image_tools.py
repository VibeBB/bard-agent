#!/usr/bin/env python3
"""Measure tool versions inside a published bard-tools image.

Runs ``<image-ref> sh -c '<probe>'`` via docker and writes a ``tools`` mapping
(tool name -> version string) as JSON for
``scripts/update_tools_image_lock.py``. Python standard library only.

Usage::

    python3 scripts/measure_image_tools.py --image-ref ghcr.io/x/bard-tools@sha256:... \
        --out out/tools.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# (tool name, command, regex with one capture group -> version string).
PROBES: list[tuple[str, str, str]] = [
    ("abcm2ps", "abcm2ps -V 2>&1 | head -1", r"abcm2ps-([0-9][0-9.]*)"),
    ("abc2midi", "abc2midi -v 2>&1 | head -1", r"^([0-9][0-9.]*)"),
    (
        "rsvg-convert",
        "rsvg-convert --version | head -1",
        r"rsvg-convert version ([0-9][0-9.]*)",
    ),
    (
        "fonts-ipafont",
        "dpkg-query -W -f='${Version}' fonts-ipafont",
        r"^([0-9][0-9a-zA-Z.:~-]*)$",
    ),
]


def probe_image(image_ref: str) -> dict[str, str]:
    # Each probe prints one ``name=$(...)`` line so shifted or missing output
    # cannot misassign a version to the wrong tool.
    script = " ; ".join(f'echo "{name}=$({cmd})"' for name, cmd, _ in PROBES)
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "-e",
            "HOME=/tmp",
            image_ref,
            "sh",
            "-c",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"image probe failed: {proc.stderr.strip()}")
    tools: dict[str, str] = {}
    for name, _cmd, pattern in PROBES:
        value = ""
        for line in proc.stdout.splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip()
                break
        match = re.search(pattern, value)
        tools[name] = match.group(1) if match else "unknown"
    return tools


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        tools = probe_image(args.image_ref)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"measure_image_tools: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tools, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(tools, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
