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
EXPECTED_SKILLS = {"bard-proposal-rules", "bard-render", "bard-songcraft"}
EXPECTED_COMMANDS = {"sing"}
EXPECTED_SESSION_START_HOOKS: set[str] = set()
EXPECTED_USER_PROMPT_SUBMIT_HOOKS: set[str] = set()
EXPECTED_PRE_TOOL_USE_HOOKS = {"protect-song-artifacts"}
EXPECTED_STOP_HOOKS = {"report-song-status"}
EXPECTED_POST_TOOL_USE_HOOKS = {"record-image-observation", "record-vision-tool-event"}


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

    if plugin.hooks is not None:
        collected: dict[str, set[str]] = {
            "session_start": set(),
            "user_prompt_submit": set(),
            "pre_tool_use": set(),
            "stop": set(),
            "post_tool_use": set(),
        }
        for event_name in collected:
            groups = getattr(plugin.hooks, event_name, None) or []
            for group in groups:
                names = [h.name for h in group.hooks if h.name is not None]
                collected[event_name].update(names)
        expected_hooks = {
            "session_start": EXPECTED_SESSION_START_HOOKS,
            "user_prompt_submit": EXPECTED_USER_PROMPT_SUBMIT_HOOKS,
            "pre_tool_use": EXPECTED_PRE_TOOL_USE_HOOKS,
            "stop": EXPECTED_STOP_HOOKS,
            "post_tool_use": EXPECTED_POST_TOOL_USE_HOOKS,
        }
        for event_name, expected in expected_hooks.items():
            if collected[event_name] != expected:
                reasons.append(
                    f"{event_name} hooks "
                    f"{sorted(collected[event_name])} != {sorted(expected)}"
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
    all_hooks = (
        EXPECTED_SESSION_START_HOOKS
        | EXPECTED_USER_PROMPT_SUBMIT_HOOKS
        | EXPECTED_PRE_TOOL_USE_HOOKS
        | EXPECTED_STOP_HOOKS
        | EXPECTED_POST_TOOL_USE_HOOKS
    )
    plugin_summary = (
        f"agents={{{','.join(sorted(EXPECTED_AGENTS))}}} "
        f"skills={{{','.join(sorted(EXPECTED_SKILLS))}}} "
        f"commands={{{','.join(sorted(EXPECTED_COMMANDS))}}} "
        f"hooks={{{','.join(sorted(all_hooks))}}}"
    )
    print(f"plugin-load OK: {plugin_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
