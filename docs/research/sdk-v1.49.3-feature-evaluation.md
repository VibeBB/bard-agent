# Research note: OpenHands SDK v1.49.3 feature evaluation for bard

Checked on: 2026-09-22 (PyPI openhands-sdk 1.49.3, released 2026-09-21)

## Scope

bard consumes the SDK only as a plugin boundary (`plugins/bard`) plus the
`sdk-check` dependency group used by the `plugin-load` CI job. Features that
require runtime code (conversation orchestration, workspace management,
settings) are out of scope by design — the plugin declares behavior, the host
app executes it.

## v1.49.2 → v1.49.3 delta

| Change | bard relevance |
| --- | --- |
| MCP OAuth with inline credentials | none — bard declares no MCP servers |
| Responses API stream-delta `item_id` stamping | runtime internals — none |
| `RemoteWorkspace.load_skills_from_agent_server(base_context=)` | runtime API — none (skills load via `Plugin.load`/`AgentContext`) |
| `resolve_auto_skills()` on remote workspaces | runtime API — none |
| Verified models `deepseek-v4.1-flash`, `nemotron-3-nano-omni-30b-a3b-reasoning` | none — agents use `model: inherit` |
| agent-server Docker host-gateway fix | none |

## Evaluated features

| Feature | Decision | Rationale |
| --- | --- | --- |
| Plugin `hooks/` (stop hook) | **Adopted** | bard had no hooks. A `stop` hook reports each `out/bard/*/song.proposal.json` render status (provenance present = rendered) so the agent states the render verdict explicitly — mirrors the proven `report-design-status` pattern in `VibeBB/electrical-circuit-agent`. Advisory (`decision: allow`); malformed proposal/provenance JSON fails closed (exit 1). |
| `inspect_image_with_vision` (VisionInspectTool) | not adopted | Inspects only images attached to the latest user message; workspace artifacts such as rendered score PNGs are not reachable by the tool. |
| `PlanningFileEditorTool` | not adopted | Restricts edits to `.agents_tmp/PLAN.md`; bard writes real proposal/brief files under `out/bard/<slug>/`. |
| `DelegateTool`, `WorkflowToolSet` | not adopted | Already rejected by ADR-0001 (not exposed in Agent Canvas; workflow executes arbitrary Python outside the hook/security boundary). |
| MCP servers (`.mcp.json`, OAuth) | not adopted | bard needs no external services; adding MCP surface would widen the plugin boundary for zero benefit. |
| Plugin format migration to `AgentPluginsFormat` | not adopted | `plugins/bard` already loads through the SDK plugin loader (`Plugin.load`, verified by `plugin-load` CI); the layout matches what Agent Canvas installs today. |

## Verification record

- `uv run pytest -q`: 105 passed, 1 skipped.
- `uv run --group sdk-check python scripts/check_plugin_load.py`: OK — SDK v1.49.3 loads the plugin including `hooks/hooks.json`; `stop` matcher exposes `report-song-status`.
