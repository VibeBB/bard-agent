"""Load plugins/bard through the OpenHands SDK plugin loader and assert the
expected agents, skills, commands, and manifest version.

Exits 0 on success and prints a one-line summary; exits 1 listing every
mismatch. Intended for the `plugin-load` CI job; the `sdk-check`
dependency group provides openhands-sdk.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugins" / "bard"

EXPECTED_AGENTS = {"bard", "bard-critic"}
EXPECTED_SKILLS = {"bard-render", "bard-songcraft"}
EXPECTED_COMMANDS = {"sing"}


def check_plugin(plugin_dir: Path) -> list[str]:
    """Return a list of mismatch reasons (empty means OK)."""
    from openhands.sdk.plugin import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        Plugin,
    )

    reasons: list[str] = []
    try:
        plugin = Plugin.load(plugin_dir)
    except Exception as e:  # noqa: BLE001 - surface any loader failure
        return [f"Plugin.load failed: {e}"]

    manifest = json.loads(
        (plugin_dir / ".plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    if plugin.manifest.version != manifest.get("version"):
        reasons.append(
            f"manifest version {plugin.manifest.version!r} != "
            f"plugin.json {manifest.get('version')!r}"
        )

    agents = {a.name for a in plugin.agents}
    if agents != EXPECTED_AGENTS:
        reasons.append(f"agents {sorted(agents)} != {sorted(EXPECTED_AGENTS)}")

    skills = {s.name for s in plugin.skills}
    if skills != EXPECTED_SKILLS:
        reasons.append(f"skills {sorted(skills)} != {sorted(EXPECTED_SKILLS)}")

    commands = {c.name for c in plugin.commands}
    if commands != EXPECTED_COMMANDS:
        reasons.append(f"commands {sorted(commands)} != {sorted(EXPECTED_COMMANDS)}")
    return reasons


def main() -> int:
    reasons = check_plugin(PLUGIN_DIR)
    if reasons:
        for r in reasons:
            print(r)
        return 1
    print(
        "plugin-load OK: agents={bard,bard-critic} "
        "skills={bard-render,bard-songcraft} commands={sing}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
