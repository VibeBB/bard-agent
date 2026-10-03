# OpenHands SDK v1.51.0 feature evaluation (bard-agent)

Scope: `openhands-sdk` and `openhands-tools` move from 1.50.1 to 1.51.0 (PyPI upload 2026-10-02). The complete upstream range `v1.50.1..v1.51.0` (the 18 PRs listed in the release notes) was reviewed. uv moves from 0.12.21 to 0.12.22. `ruff` (0.16.10) and `anchore/sbom-action` (v0.24.3) were already current and required no change.

Primary sources: [OpenHands SDK v1.51.0 release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.51.0), [uv 0.12.22 release](https://github.com/astral-sh/uv/releases/tag/0.12.22).

## SDK 1.50.1 -> 1.51.0

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| #5151 `tools` is the only tool control (`enable_sub_agents` / `enable_switch_llm_tool` retired from profiles schema v3 and settings schema v8, deprecated input folded into `tools` until 1.56.0; `/api/tools/catalog` added) | adopted (doc update) | Determines whether `task` appears: it is now purely whether the profile's effective `tools` contains `task_tool_set`. A persisted legacy `tools: []` still migrates to the default set; `[]` in a current payload means a bare agent. The `ensure_llm_profiles` hook clones profiles verbatim, so old and new profile shapes both load via the migration. `docs/operations.md` and `commands/sing.md` updated. Follow-up: profile JSONs carrying the retired switches stop being accepted as input in 1.56.0. |
| #5358 `SubAgentScope`: `task` offers only sub-agents that fit the delegating agent's tools/MCP, and refuses others at start (profile-resolver only) | adopted (doc update) | With a profile that pins `tools` explicitly, `bard` is offered only when the parent tool set covers what `bard` declares (`terminal`, `file_editor`, `grep`, `glob`, `task_tracker`, `task_tool_set`); `bard`'s own `task_tool_set` inherits the scope for `bard-critic` (`terminal`, `grep`, `glob`). Recorded in `docs/operations.md` and `commands/sing.md`; no code change — the fallback path already covers a `task`-less conversation. |
| #5406 launch every agent through `resolve` + `finalize` (new `openhands.sdk.launch`, server-side) | not adopted | Agent-server launch pipeline refactor; plugins run in local conversations and do not build launch agents. `Plugin.load` is unaffected (verified by `check_plugin_load.py` under 1.51.0). |
| #5449 profile `persona` replaces the agent's persona sections only | not adopted | This repo ships no Agent Profiles; the bard agents carry their own prompt files. |
| #5450 loaded tools supply their system-prompt guidance (`ToolDefinition.prompt_guidance`, `ToolGuidanceSection`; `PromptContext.enable_browser` removed) | not adopted | The plugin ships no tool definitions and no custom `system_prompt`; the default prompt is byte-identical upstream. |
| #5332 `prompt_cache_key` resolved via the real provider for proxied models | inherent | Bug fix on the LLM request path; restores cache-shard routing for `openhands/`-proxied non-OpenAI models. No repo change. |
| #5274 OpenRouter becomes a verified provider | noted | Widens the provider choices a `vibebb-*` LLM profile can point at; no repo change required. |
| #5412 router classifier sends system+user messages for direct-routing | not applicable | Agent-server routing templates (`OpenHands Router Pro/Flash`); not used by this plugin. |
| #5417 `/switch_llm` resolves provider connections (dangling ref -> 422 before switching) | not applicable | Agent-server endpoint; plugins do not call it. |
| #5434 `ACPAgentSettings.llm` deprecated (removed 1.56.0); ACP agents keep their metrics LLM | not applicable | No ACP agents in this repo. |
| #1326 `get_env()` no longer auto-loads `.env` (host apps call `load_dotenv()`) | noted | The plugin reads settings via `~/.openhands` files and `os.environ`, never `.env`; hooks are spawned by the SDK host which owns `.env` loading. |
| #5419 pydantic 2.12.5 -> 2.13.5 | lock-only | Picked up through `uv.lock` (locked 2.13.5). |
| #5425, #5428 `@typescript-eslint/*` 8.70.1; #5302-adjacent client deps | not applicable | This repository does not use the SDK TypeScript client. |
| #4945, #5415 CI behavior-test / version-bump fixes; #5397 stress-test slot | not applicable | Upstream CI/test-only changes. |
| #5470 release v1.51.0 | not applicable | Release housekeeping. |

## uv 0.12.21 -> 0.12.22

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| CPython 3.10.22, 3.11.17, 3.12.15, 3.13.16, 3.14.8 added to managed builds | inherent | New patch releases available via `uv python install`; the repo's 3.12/3.13 matrix is unchanged. |
| Workspace-member default groups and dependency-group Python requirements recorded in lockfiles | not applicable | Single-project repo, not a uv workspace. |
| `UV_PYTHON_ARCH` selects interpreter architecture | not adopted | Host architecture is already correct; no cross-arch install needed. |
| `uv audit`/`uv tool audit` preview: `--no-default-groups`, offline error clarity | not adopted | Preview features unused; `uv audit` is not part of this repo's checks. |
| Relock verifies unchanged requirements against lockfile hashes; false entry-point warnings fix; `--offline` hidden from `uv publish` help; CLI message formatting | inherent | Correctness/UX fixes picked up with the pin. |
| Rust toolchain 1.97+/1.99 | not applicable | Building uv from source is not done here. |

## Compatibility deferrals

MCP 2.x remains deferred: installed `openhands-sdk` 1.51.0 metadata still requires `fastmcp>=3.2.0,<4`, which caps `mcp<2` (locked: fastmcp 3.4.7, mcp 1.30.0). `scripts/dependency_update_deferrals.json` has no mcp entry in this repo; the only deferral on file is the Python 3.14 entry, unchanged. The `openhands-agent-server` image tag `1.51.0-python` is available upstream; no committed image lock is edited by this bump.
