# Research note: OpenHands SDK v1.49.4 feature evaluation for bard

Checked on: 2026-09-23 (PyPI openhands-sdk 1.49.4, released 2026-09-23)

## Scope

bard consumes the SDK only as a plugin boundary (`plugins/bard`) plus the
`sdk-check` dependency group used by the `plugin-load` CI job. Features that
require runtime code (conversation orchestration, workspace management,
settings) are out of scope by design — the plugin declares behavior, the host
app executes it.

## v1.49.3 → v1.49.4 delta

| Change | bard relevance |
| --- | --- |
| `LookupSecret` URLs resolved in-process (`openhands.sdk.secret.secrets`, #5026) | none — saved-secret resolution is server/agent runtime; bard declares no secrets |
| ACP `agent_settings` reset on active-profile deletion (#5206) | none — ACP is a serving layer outside the plugin boundary |
| `agent-client-protocol` constraint `>=0.12.1,<0.13.0`, `joserfc>=1.7.5` | none — transitive constraint changes only |
| `fastmcp>=3.2.0,<4` unchanged | none — bard declares no MCP servers |

## Evaluated features

| Feature | Decision | Rationale |
| --- | --- | --- |
| `LookupSecret` in-process resolution | not adopted | Runtime/agent-server surface; the plugin boundary (`agents/`, `commands/`, `hooks/`, `skills/`, `.plugin/plugin.json`) is unchanged. |
| ACP profile `agent_settings` reset | not adopted | ACP is out of scope; no plugin-asset impact. |

No new plugin-boundary features arrived in this delta; the plugin format,
AgentDefinition, skills, and hook surfaces used by bard are unchanged.

## Verification record

- `uv run pytest -q`: 117 passed, 2 skipped.
- `uv run --group sdk-check python scripts/check_plugin_load.py`: OK — SDK
  v1.49.4 loads the plugin including `hooks/hooks.json`; `stop` matcher
  exposes `report-song-status`.
