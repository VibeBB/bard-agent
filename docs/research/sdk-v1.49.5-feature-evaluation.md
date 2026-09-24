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

## Named SDK feature review (2026-09-24)

Focused pass on the SDK's security / confirmation / secrets / stuck /
memory / model-routing surfaces. Sources: installed `openhands-sdk` and
`openhands-tools` 1.49.5 plus upstream `main` (`sdk/subagent/schema.py`,
`sdk/subagent/registry.py`, `sdk/conversation/impl/local_conversation.py`,
`sdk/conversation/secret_registry.py`, `sdk/security/`,
`sdk/llm/llm_profile_store.py`, `tools/task/manager.py`), and the
agent-server `conversation_service.py` / `conversation_router.py` on `main`.

| Feature | Where it lives | Decision | Rationale |
| --- | --- | --- | --- |
| `EnsembleSecurityAnalyzer` (`PatternSecurityAnalyzer` + `PolicyRailSecurityAnalyzer`, worst-case fusion) | `Conversation.state` / agent-server `POST /conversations/{id}/security_analyzer` | not adoptable at plugin boundary | `AgentDefinition` has no `security_analyzer` field; only the host app can attach an analyzer. Plugin-side substitute adopted instead: the `safety-rail` `pre_tool_use` hook denies a deterministic denylist on terminal commands. |
| `LLMSecurityAnalyzer` / `ToolShieldLLMSecurityAnalyzer` / `GraySwanAnalyzer` | same | not adoptable at plugin boundary | Same as above; all opt-in server-side analyzers. |
| `ConfirmRisky` (`permission_mode: confirm_risky`) | AgentDefinition frontmatter → conversation confirmation policy | n/a — `never_confirm` already declared | bard/bard-critic stay `never_confirm`: a creative sub-agent whose only write path is `out/bard/*` under the proposal contract has nothing to gate. Verified the choice is also what `confirm_risky` would do anyway — `task/manager.py` never attaches an analyzer to the child conversation, so every action is `UNKNOWN` and the policy auto-resumes (Finding A). |
| `SecretRegistry` (`/secrets` API, env injection) | conversation state; `${VAR}` expansion in `mcp_config` | contract documented | bard declares no MCP servers, so nothing consumes it today; the contract (`${VAR}`/`${VAR:-default}` resolving through `secret_registry.get_secret_value`, env injection into commands naming the key) is recorded in `docs/operations.md` for future tools. |
| `StuckDetector` | `Conversation(stuck_detection=True)` default | already effective | On by default in every `LocalConversation`, including task sub-agents. Thresholds are Conversation init params — not plugin-settable; `max_iteration_per_run` already bounds runs. |
| Persistent memory (`AgentContext(load_memory=True)`) | server-side `AgentContext` (Canvas "Settings > Agent Context") | not adoptable at plugin boundary | The sub-agent factory builds `AgentContext` without `load_memory`; frontmatter has no switch. Top-level conversation only — seeded via `.openhands/memory/MEMORY.md` (the earlier "Persistent Memory not adopted" row predates this review; the seed now ships the durable contract facts). |
| Model routing (`Router`/`MultimodalRouter`, `model:` frontmatter) | `Agent.llm` (server) / `LLMProfileStore` | **adopted via profile convention** | The Router itself is server-side. bard declares `model: vibebb-author`, bard-critic `model: vibebb-review` — operators create the matching profiles in `~/.openhands/profiles/` (contract in `docs/operations.md`); a missing profile hard-fails the spawn (Finding B). |
| `SwitchLLMTool` / agent profiles (`mcp_server_refs`, `secret_refs`) / critic | agent-server profile + Canvas settings | not adoptable at plugin boundary | Server-side scoping features; bard-critic already plays the critic role at L2. |
| `condenser:` frontmatter | AgentDefinition | not adopted | Sub-agents already get a summarizing condenser by default at factory time (`default_condenser`), so there is nothing to add; bard's 120-iteration ceiling already has summarizing coverage. |

### Finding A — `confirm_risky` is effectively auto-approved in sub-agents

`openhands-tools` `task/manager.py` (verified on 1.49.5 and upstream `main`)
builds the child `LocalConversation` and calls `_set_confirmation_policy`,
but never calls `set_security_analyzer` — `state.security_analyzer` stays
`None`. Every action therefore carries risk `UNKNOWN`;
`ConfirmRisky` defaults to `confirm_unknown=True`, which raises
`WAITING_FOR_CONFIRMATION` per action and is then auto-approved because the
task path wires no confirmation handler. Net effect: zero gating plus
status-transition noise. bard's existing `never_confirm` is unaffected —
recorded here because the other VibeBB plugins used `confirm_risky`.

### Finding B — `model:` fails hard when the profile is missing

`agent_definition_to_factory` calls `LLMProfileStore(base_dir).load(name)`
and raises `ValueError` for unknown names, killing the `task` call. Any
non-`inherit` `model:` must ship with a documented profile-name convention
(`~/.openhands/profiles/vibebb-author.json`, `vibebb-review.json`) that the
operator creates first.

## Verification record

- `uv run pytest -q`: pass (see PR checks).
- `uv run --group sdk-check python scripts/check_plugin_load.py`: OK — SDK
  v1.49.5 loads the plugin, including the new `bard-proposal-rules` skill and
  `hooks/hooks.json`.
- `uv run python scripts/check_dependency_updates.py`: all rows 一致/保留.
