# Operations

Operational detail for maintainers and installers: the release process,
plugin update caveats, and verification recipes. For a product overview see
the [README](../README.md).

## Release process

Distribution uses git tags ([ADR-0004](adr/ADR-0004-ci-cd-release-by-tag.md)).
Run the `release` workflow manually with `workflow_dispatch`. Select a `bump`
input (`patch`/`minor`/`major`, defaulting to `patch`) or a `version` input
(an explicit `X.Y.Z` override). It runs only on `main` and proceeds as follows:

1. **bump-version** — `scripts/bump_version.py` checks the versions in
   `plugins/bard/.plugin/plugin.json`, `pyproject.toml`, both `SKILL.md` files,
   and `uv.lock`, writes the new version, and checks that the `v<version>` tag
   does not already exist before committing to `main`.
   An explicit `version` equal to the current version skips the bump commit and
   releases the current `main` HEAD.
2. **verify** — runs the normal CI (lint, type checks, and tests) through the
   reusable workflow.
3. **install-smoke** — installs from the target SHA with `install_plugin` and
   checks the agent, skill, and command listings.
4. **release** — creates plugin and score-sample ZIP files, then creates the
   `v<version>` tag and Release with `gh release create`.

If any step fails, neither a tag nor a Release is created.

## Updating the plugin

Agent Canvas caches a plugin repository per source string. Because the refspec
fetches tags only, specifying a new ref with the same source string can leave an
old `resolved_ref` in place. A workaround confirmed with 1.46.0 is to
uninstall the plugin, then add it again using a source with different casing
(for example, `github:VIBEBB/bard-agent`) or the full URL
`https://github.com/VibeBB/bard-agent.git`. Confirm that the plugin details'
`resolved_ref` matches the new tag's SHA.

Reinstalling with `force: true` can still use the old cache
(`~/.openhands/cache/extensions/bard-agent-*`), leaving `resolved_ref`
unchanged; this was confirmed with 1.46.0. The reliable procedure is
"uninstall → delete the cache directory above and its `.lock` file → install".
After installation, confirm that the installed-plugin API's `resolved_ref`
matches the intended commit.

## If sub-agents do not activate

With 1.46.0, there are cases where enabling "sub-agents" in the agent profile
still leaves `task` unavailable in the conversation (the settings API continues
to return `enable_sub_agents=false`). In that case `/bard:sing` uses its
fallback path and says so in the `実行経路:` line at the end of the response.
The fallback took approximately 34 minutes in one real-world run.

The environment verified in practice was OpenHands 1.46.0, which is separate
from the target SDK version 1.49.4. A conversation with `task_tool_set`
explicitly listed in the profile's `tools` showed the `task` path (nested
bard → bard-critic sub-agents) in its events. However, even when `task` is
available, the model sometimes handles the work in the parent conversation
(one of twelve songs in testing), so check the `/bard:sing` trailing
`実行経路:` line and the conversation events. A critic sub-agent LLM response
often takes 20–70 minutes or fails with a provider timeout; an
`llm.timeout` of at least 600 seconds is recommended.

Note: in SDK 1.49.4, `AgentSettings.create_agent` adds TaskToolSet through
`enable_sub_agents` only when the profile's `tools` is `None` (unspecified)
(source: `openhands-sdk/openhands/sdk/settings/model.py`). If `tools` is
explicitly set in the profile, `task` does not appear even when the setting is
ON. Either leave `tools` unspecified or explicitly add `task_tool_set`. Whether
1.46.0 behaves identically was not verified.

## Checking installation status via the API

Installation status can also be checked through the API (an
`X-Session-API-Key` is required). When `resolved_ref` matches the tag's commit
SHA, the intended version is installed.

```bash
curl -sS -H "X-Session-API-Key: $KEY" http://127.0.0.1:8000/api/plugins/installed
```

## OpenHands runtime surfaces

Runtime policy surfaces that the plugin declares but the host executes:

- `permission_mode: never_confirm` on bard and bard-critic — correct for a
  read-only creative sub-agent whose only write path is `out/bard/*` under
  the proposal contract. (For completeness: the SDK's task path never
  attaches a `security_analyzer` to the child conversation, so
  `confirm_risky` would see every action as `UNKNOWN` and auto-resume
  anyway — zero gating either way.)
- `model:` resolves through `LLMProfileStore` (`~/.openhands/profiles/`):
  `vibebb-author` for bard, `vibebb-review` for bard-critic. A missing
  profile raises `ValueError` at task spawn — create the profiles (canvas
  LLM settings or `LLMProfileStore.save`) before invoking the agents. To
  fall back to the conversation model, set `model: inherit` locally.
- Secrets: bard declares no MCP servers; if one is added later,
  `${VAR}` / `${VAR:-default}` in `mcp_config` expands through the
  conversation `SecretRegistry` before env, and registry values reach
  bash commands that name the key.
- The `safety-rail` `pre_tool_use` hook (`hooks/scripts/safety_rail.py`)
  denies a deterministic denylist on terminal commands: root/home `rm
  -rf`, block-device writes, power commands, and the git operations the
  work contract bans. Advisory depth, not a security analyzer — it passes
  everything it does not positively recognize.
- `.openhands/memory/MEMORY.md` seeds the project-tier persistent memory
  loaded when the host enables `AgentContext(load_memory)` (canvas
  "Settings > Agent Context"). The agent maintains the index; keep the
  seed to durable facts only.
- `StuckDetector` is on by default for every conversation including task
  sub-agents; `max_iteration_per_run` remains the repo-side bound.
