# OpenHands SDK v1.53.0 feature evaluation (bard-agent)

Scope: `openhands-sdk` and `openhands-tools` move from 1.52.0 to 1.53.0 (GitHub release 2026-10-05; both packages published on PyPI). The complete upstream range `v1.52.0..v1.53.0` (6 pull requests) was reviewed. No other component moved in this update.

Primary source: [OpenHands SDK v1.53.0 release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.53.0).

## SDK 1.52.0 -> 1.53.0

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| #5024 fix(skills): exclude installed packages from the user skills scan | adopted implicitly | SDK-internal fix in `openhands/sdk/skills/skill.py`: skills inside the managed installed-packages directory no longer leak into the user-skill merge. Lands with the pin; plugin skills and `Plugin.load` are unaffected (`check_plugin_load.py` passes on 1.53.0). |
| #5479 feat(agent-server): serve a manifest-declared SVG icon for canvas extensions | available, not adopted | New optional `icon` field on `CanvasExtensionManifest` (package-root-relative `.svg` path, containment-checked), served at `GET /canvas_extensions/installed/{name}/icon` with a CSP-sandboxed `FileResponse`. VibeBB plugins are AgentCanvas plugins (`.plugin/plugin.json`), not canvas extensions — nothing declares a canvas-extension entrypoint manifest. Revisit only if a repo ships a canvas extension. |
| #5476 fix(ci): pin the TypeScript client's Agent Server in the release PR | not applicable | Upstream release CI only. |
| #5512 fix(ci): read the unreleased Agent Server contract from source on release PRs | not applicable | Upstream release CI only. |
| #5513 docs: refresh AGENTS.md guidance | not applicable | Upstream documentation only. |
| #4782 chore: weekly test sweep removes low-value coverage | not applicable | Upstream test-suite housekeeping only. |
| fastmcp `>=3.2.0,<4`, pydantic `>=2.13.5`, pillow `>=12.3.0`, requires-python `>=3.12` unchanged | n/a | The `openhands-sdk`, `openhands-tools`, and `openhands-agent-server` pyproject.tomls differ from v1.52.0 only in `version = "1.53.0"` (verified by diffing the two tags); the dependency constraint surface is identical. |

## Compatibility deferrals

MCP 2.x remains deferred: installed `openhands-sdk` 1.53.0 metadata still requires `fastmcp>=3.2.0,<4`, which caps `mcp<2` (latest 2.3.0). `scripts/dependency_update_deferrals.json` has no mcp entry in this repo and stays empty. The `openhands-agent-server` image tag `1.53.0-python` is available upstream; no committed image lock is edited by this bump.
