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
EXPECTED_STOP_HOOKS = {"report-song-status"}


def _registered_tools() -> set[str]:
    """Import the builtin tool modules so their registrations exist."""
    import openhands.tools.preset.default  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
    from openhands.sdk.tool.registry import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        list_registered_tools,
    )

    openhands.tools.preset.default.register_default_tools(enable_browser=False)
    import openhands.tools.glob.definition  # noqa: F401  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.grep.definition  # noqa: F401  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.task.definition  # noqa: F401  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]

    return set(list_registered_tools())


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

    stop_hooks: set[str] = set()
    if plugin.hooks is not None:
        for group in plugin.hooks.stop:
            stop_hooks.update(h.name for h in group.hooks if h.name is not None)
    if stop_hooks != EXPECTED_STOP_HOOKS:
        reasons.append(
            f"stop hooks {sorted(stop_hooks)} != {sorted(EXPECTED_STOP_HOOKS)}"
        )

    registered = _registered_tools()
    min_examples = {"bard": 3, "bard-critic": 2}
    for agent in plugin.agents:
        for tool in agent.tools:
            if tool not in registered:
                reasons.append(f"agent {agent.name!r} tool {tool!r} not registered")
        want = min_examples.get(agent.name, 0)
        if len(agent.when_to_use_examples) < want:
            reasons.append(
                f"agent {agent.name!r} when_to_use_examples "
                f"{len(agent.when_to_use_examples)} < {want}"
            )
    for command in plugin.commands:
        for tool in command.allowed_tools:
            if tool not in registered:
                reasons.append(
                    f"command {command.name!r} allowed-tool {tool!r} not registered"
                )
    return reasons


def main() -> int:
    reasons = check_plugin(PLUGIN_DIR)
    if reasons:
        for r in reasons:
            print(r)
        return 1
    print(
        "plugin-load OK: agents={bard,bard-critic} "
        "skills={bard-render,bard-songcraft} commands={sing} "
        "stop-hooks={report-song-status}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
