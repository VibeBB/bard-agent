# Research note: OpenHands SDK v1.49.6 feature evaluation for bard

Checked on: 2026-09-25 (PyPI openhands-sdk 1.49.6, released 2026-09-25;
openhands-tools 1.49.6; agent-canvas 1.24.0 carrying automation 1.15.1)

## Scope

bard consumes the SDK only as a plugin boundary (`plugins/bard`) plus the
`sdk-check` dependency group used by the `plugin-load` CI job. Features that
require runtime code (conversation orchestration, workspace management,
settings) are out of scope by design — the plugin declares behavior, the host
app executes it.

## v1.49.5 → v1.49.6 delta

| Change | bard relevance |
| --- | --- |
| Meta-profile routing: `llm/meta_profile_store.py`, `tool/builtins/classify_and_switch_llm.py`, agent-server `meta_profiles_router.py`, example `59_route_task_to_model.py` | operator-level — a meta-profile maps task classes to saved LLM profiles; it can point classes at the existing `vibebb-*` profiles |
| `verified_models.py`: adds `gpt-6-sol`, `gpt-6-luna`, `claude-opus-5-5`; drops `claude-opus-4-8` | none for the plugin — sub-agents resolve named profiles (`vibebb-author`/`vibebb-review`), never raw model strings. An operator profile still pointing at `claude-opus-4-8` is now "unverified" and Canvas 1.24.0 warns about it |
| `hooks/executor.py`: a non-string `decision` in hook JSON is treated as no decision | positive — hardens the `command` hooks (doctor, artifact guard, vision records, status report) against malformed output |
| `llm.py`: friendly error on an invalid API key; refresh the key and retry once on a 401 | positive — runtime resilience, no repo change |
| `mcp/oauth.py`, `mcp/utils.py`, agent-server `mcp_oauth_store.py`/`mcp_router.py`: OAuth token refresh fixes | none — bard exposes no MCP server and declares no OAuth MCP clients |
| agent-server Windows crash fix | n/a — the verification host is Linux |
| docs: system-before-user LLM message invariant | none — documentation only |

## Evaluated features

| Feature | Decision | Rationale |
| --- | --- | --- |
| Meta-profile routing (`ClassifyAndSwitchLLMTool`, `MetaProfileStore`, `meta_profiles_router`) | not adoptable at plugin boundary | Routing is a conversation-level builtin plus operator config under `~/.openhands/meta-profiles/` (or `$OH_PERSISTENCE_DIR/meta-profiles`); AgentDefinition frontmatter cannot pin a meta-profile per sub-agent. An operator may define a meta-profile whose classes resolve to `vibebb-author`/`vibebb-review`; a classifier miss fails loudly. No repo change. |
| New verified models (`gpt-6-sol`, `gpt-6-luna`, `claude-opus-5-5`) | no action | Model choice lives in operator-side `~/.openhands/profiles/`; the plugin pins no model names. |
| Non-string hook `decision` hardening | inherent | All bard hooks emit `decision` as a string; malformed JSON no longer crashes the decision parse — it simply records no decision. |
| LLM 401 refresh-and-retry / friendly invalid-key error | inherent | No repo change. |
| MCP OAuth token refresh | n/a | No MCP surface in this plugin. |
| AgentCanvas 1.23.0 → 1.24.0 (verification host) | host updated | The canvas now calls the agent-server runtime directly instead of `/api/cloud-proxy` (fixes 405 on verification confirm and compact-context), keeps MCP OAuth credentials on saves, and skips consent when tokens still work. Runtime-surface features (workspace-folder toggle, cloud read-only shared conversations) do not touch the plugin boundary. |

## Verification record

- `uv run python scripts/check_dependency_updates.py`: clean — no update
  candidates; only the recorded Python-3.14 deferrals remain.
- `uv run ruff check . && uv run ruff format --check .`, `uv run pyright`,
  `uv run pytest -q`: pass, including the updated
  `tests/test_dependency_check.py` pin assertions.
- Host AgentCanvas verified after the 1.24.0 update: `/ready`, `/health`,
  `/server_info`, `/api/automation/docs`, and `/canvas` all return 200, with
  agent-server/SDK/tools/workspace at 1.49.6.
