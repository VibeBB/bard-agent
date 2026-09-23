# Research note: OpenHands SDK v1.49.5 feature evaluation for bard

Checked on: 2026-09-23 (PyPI openhands-sdk 1.49.5, released 2026-09-23)

## Scope

bard consumes the SDK only as a plugin boundary (`plugins/bard`) plus the
`sdk-check` dependency group used by the `plugin-load` CI job. Features that
require runtime code (conversation orchestration, workspace management,
settings) are out of scope by design — the plugin declares behavior, the host
app executes it.

## v1.49.4 → v1.49.5 delta

| Change | bard relevance |
| --- | --- |
| `PreserveDataUrls` / `SkipSecretMasking` markers: image `data:` URLs in `Message.image_urls` and `browser_use` screenshot data are no longer secret-masked (`openhands/sdk/utils/masking.py`, `message.py`, tools wheel) | adopted (no code change) — keeps image data URLs intact through secret masking; relevant to any vision/image path the host runs for Stage 8 or user-attached images |
| `openhands/sdk/mcp/tool.py` mcp 2.x wire-key normalization (snake_case ↔ camelCase) | none — bard declares no MCP servers; forward-compat only (`fastmcp<4` still caps `mcp<2.0`, recorded in `scripts/dependency_update_deferrals.json`) |
| `model_features.py`: `gpt-6` family + `gpt-5.2-codex` entries | none — host model capability, outside the plugin boundary |
| `telemetry.py`: `UsageSnapshot` | none — runtime telemetry surface, outside the plugin boundary |

## Evaluated features

| Feature | Decision | Rationale |
| --- | --- | --- |
| `inspect_image_with_vision` (`VisionInspectTool`) | adopted for user-attached images only; documented accurately | The tool inspects images attached to the **latest user message** (`image_index`), auto-attached only when a saved vision-capable LLM profile exists. It cannot read workspace files, so Stage 8's `score.png` has no vision fallback when the conversation model is not vision-capable — the prompt now records that case as `status: "skipped"` instead of implying `file_editor view` still works. |
| `file_editor view` image display | unchanged | Advertised only when `llm.vision_is_active()`; Stage 8 already keys on this. |
| `paths:` skill rules (PathTrigger) | adopted | New `bard-proposal-rules` skill injects proposal-contract + originality reminders deterministically whenever a `*.proposal.json` file is touched. Keyword skills (`bard-songcraft`, `bard-render`) stay `triggers:`-based; the mechanisms are exclusive. |
| MCP `ToolAnnotations` | not applicable | bard ships no MCP server. |
| Prompt/agent-type hooks, Persistent Memory | not adopted | The `hooks/hooks.json` stop hook remains the only hook needed; session memory across runs is out of scope for a task sub-agent. |

## Verification record

- `uv run pytest -q`: pass (see PR checks).
- `uv run --group sdk-check python scripts/check_plugin_load.py`: OK — SDK
  v1.49.5 loads the plugin, including the new `bard-proposal-rules` skill and
  `hooks/hooks.json`.
- `uv run python scripts/check_dependency_updates.py`: all rows 一致/保留.
