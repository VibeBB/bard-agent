#!/usr/bin/env python3
"""Update the bard-tools image pin used by the docker render fallback.

Rewrites ``plugins/bard/skills/bard-render/tools-image.json`` with the newly
published image's tag/digest plus provenance metadata (publish timestamp,
workflow run URL, Dockerfile path, measured tool versions). Invoked by the
publish-bard-images workflow on the lock-update branch. Standard library only.

Usage::

    python3 scripts/update_tools_image_lock.py \
        --pin plugins/bard/skills/bard-render/tools-image.json \
        --image ghcr.io/vibebb/bard-tools \
        --tag <sha>-tools \
        --digest sha256:... \
        --published-at 2026-09-23T00:00:00Z \
        --workflow-run https://github.com/.../actions/runs/... \
        --dockerfile docker/bard-tools.Dockerfile \
        --tools-json out/tools.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--pin", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--workflow-run", required=True)
    parser.add_argument("--dockerfile", default="docker/bard-tools.Dockerfile")
    parser.add_argument("--tools-json", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.digest.startswith("sha256:") or len(args.digest) != 71:
        print(f"invalid digest: {args.digest}", file=sys.stderr)
        return 1
    try:
        tools = json.loads(args.tools_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read tools json: {exc}", file=sys.stderr)
        return 1
    if not isinstance(tools, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in tools.items()
    ):
        print("tools json must be a string->string object", file=sys.stderr)
        return 1

    entry = {
        "image": args.image,
        "tag": args.tag,
        "digest": args.digest,
        "published_at": args.published_at,
        "workflow_run": args.workflow_run,
        "dockerfile": args.dockerfile,
        "tools": tools,
    }
    args.pin.parent.mkdir(parents=True, exist_ok=True)
    args.pin.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    print(f"updated {args.pin}: {args.image}@{args.digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
