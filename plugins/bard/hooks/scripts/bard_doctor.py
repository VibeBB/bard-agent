#!/usr/bin/env python3
"""Diagnose the bard plugin install when a session starts.

Resolves the plugin root through the same env-var chain the hooks use
(`BARD_PLUGIN_ROOT`, `$OPENHANDS_PROJECT_DIR/plugins/bard`,
`~/.agents/plugins/bard`, `~/.openhands/plugins/installed/bard`), probes for
`docker` on `PATH` (the pinned `bard-tools` image renders `score.png`), reads
the image pin (`skills/bard-render/tools-image.json`), and checks the plugin
layout (`.plugin/plugin.json`, `agents/`, `skills/`). Findings are reported
as additional context; the hook is advisory and always exits 0, even when the
plugin root cannot be resolved or a probe itself fails.

Python standard library only.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT_ENV = "BARD_PLUGIN_ROOT"
PROJECT_ENV = "OPENHANDS_PROJECT_DIR"
SELF_PATH = Path("hooks") / "scripts" / "bard_doctor.py"
REQUIRED_PATHS = (".plugin/plugin.json", "agents", "skills")
PROBE_TOOLS = ("docker",)
PIN_REL = Path("skills") / "bard-render" / "tools-image.json"


def _candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    root = os.environ.get(ROOT_ENV)
    if root:
        candidates.append(Path(root).expanduser())
    project = os.environ.get(PROJECT_ENV) or "."
    candidates.append(Path(project).expanduser() / "plugins" / "bard")
    home = Path.home()
    candidates.append(home / ".agents" / "plugins" / "bard")
    candidates.append(home / ".openhands" / "plugins" / "installed" / "bard")
    return candidates


def _resolve_root() -> Path | None:
    """Resolve the plugin root exactly like the hooks.json command template."""
    for candidate in _candidate_roots():
        if (candidate / SELF_PATH).is_file():
            return candidate.resolve()
    return None


def _findings(root: Path | None) -> list[str]:
    lines: list[str] = []
    if root is None:
        lines.append(
            "plugin root unresolved; checked "
            + ", ".join(str(c) for c in _candidate_roots())
        )
    else:
        missing = [rel for rel in REQUIRED_PATHS if not (root / rel).exists()]
        if missing:
            lines.append(
                f"plugin layout incomplete at {root}: missing {', '.join(missing)}"
            )
        else:
            lines.append(f"plugin layout ok at {root}")
    found = {tool: shutil.which(tool) for tool in PROBE_TOOLS}
    lines.append(
        "tools: "
        + ", ".join(
            f"{tool}={'ok' if found[tool] else 'missing'}" for tool in PROBE_TOOLS
        )
    )
    pin_ok = False
    if root is not None:
        pin_path = root / PIN_REL
        try:
            pin = json.loads(pin_path.read_text(encoding="utf-8"))
            pin_ok = bool(pin.get("image") and pin.get("digest"))
        except (OSError, json.JSONDecodeError):
            pin_ok = False
    lines.append(f"bard-tools pin: {'ok' if pin_ok else 'missing or unpinned'}")
    if not (found["docker"] and pin_ok):
        lines.append(
            "score.png unavailable: needs docker on PATH and a pinned "
            "bard-tools digest in tools-image.json"
        )
    return lines


def main() -> int:
    try:
        context = "bard doctor: " + "; ".join(_findings(_resolve_root()))
    except Exception as exc:  # noqa: BLE001 - the doctor is advisory
        print(f"bard_doctor: {exc}", file=sys.stderr)
        context = "bard doctor: probe failed; see the hook stderr log"
    print(json.dumps({"decision": "allow", "additionalContext": context}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
