# Operations

Operational detail for maintainers and installers: the release process,
plugin update caveats, and verification recipes. For a product overview see
the [README](../README.md).

## SBOM attestations

`publish-bard-images.yml` generates and attests a package-level SPDX-2.3 SBOM
for the published digest, uploads the full Syft SBOM as a 90-day workflow-run
artifact, and records the attested SBOM URL as `sbom_attestation` in the image
lock. The attested SBOM omits file entries and relationships involving files
to stay below the 16 MiB limit. `locked-image-check.yml` verifies the
SBOM attestation when present; an absent URL warns and continues. It also
renders the shipped score example through `render_score_png.py` and uploads
the smoke output.

## Release process

Distribution uses git tags ([ADR-0004](adr/ADR-0004-ci-cd-release-by-tag.md)).
Run the `release` workflow manually with `workflow_dispatch`. Select a `bump`
input (`patch`/`minor`/`major`, defaulting to `patch`) or a `version` input
(an explicit `X.Y.Z` override). It runs only on `main` and proceeds as follows:

1. **bump-version** — `scripts/release_bump.sh` resolves the version via
   `scripts/bump_version.py`, which checks the versions in
   `plugins/bard/.plugin/plugin.json`, `pyproject.toml`, both `SKILL.md` files,
   and `uv.lock`, writes the new version, and checks that the `v<version>` tag
   does not already exist before committing to `main`. When the ruleset
   rejects the direct push, the script routes the bump through an
   auto-merged fallback pull request. The script is covered by
   `tests/test_release_bump.py` (stubbed `gh`, local git remotes).
   An explicit `version` equal to the current version skips the bump commit and
   releases the current `main` HEAD.
2. **verify** — runs the normal CI (lint, type checks, and tests) through the
   reusable workflow.
3. **install-smoke** — installs from the target SHA with `install_plugin` and
   checks the agent, skill, and command listings.
4. **release** — creates plugin and score-sample ZIP files, then creates the
   `v<version>` tag and Release with `gh release create`, attests the zips
   with a build-provenance attestation (`actions/attest-build-provenance`),
   and uploads the provenance bundle as
   `bard-v<version>-provenance.intoto.jsonl`. Verify a downloaded asset
   with:
   `gh attestation verify dist/bard-plugin-v<version>.zip --repo VibeBB/bard-agent --signer-workflow VibeBB/bard-agent/.github/workflows/release.yml`

If any step fails, neither a tag nor a Release is created.

## Tools image provenance

The `publish-bard-images.yml` workflow attaches a GitHub build-provenance
attestation to the published `bard-tools` image. Its attestation URL is stored
in `plugins/bard/skills/bard-render/tools-image.json` alongside the image
digest.

Dispatch the workflow with `dry_run=true` to rehearse a publish: the image is
built into the local daemon and the Trivy gates, SBOM generation, measurement,
and smoke checks still run, but nothing is pushed, promoted (`:latest`),
attested, locked, or dispatched, and no SARIF reaches code scanning. The run
summary lists every skipped step.

## Container hardening

Three layers were adopted after a comparative evaluation of Lynis,
`docker build --check`, Trivy, Grype, Dockle, and hadolint:

- **Dockerfile lint** (`dockerfile-lint` job in `ci.yml`): hadolint
  v2.15.1 via `hadolint-action` v3.5.0 plus `docker build --check`
  (BuildKit built-in). `.hadolint.yaml` allows only docker.io and
  ghcr.io registries and waives DL3008 (exact deb pins rot when Debian
  archives drop them; the build-time smoke checks inside the RUN verify
  the installed tools work).
- **Image scan on publish** (`publish-bard-images.yml`): Trivy v0.75.0
  via `trivy-action` v0.36.0 scans the pushed digest for
  CRITICAL/HIGH fixable vulnerabilities, secrets, and misconfiguration,
  gated (`exit-code 1`), with SARIF uploaded to code scanning
  (`category: trivy-bard-tools`) and a full JSON report as an artifact.
  The action is SHA-pinned and `version:` is explicit — the March 2026
  Trivy supply-chain compromise made both non-negotiable.
- **Weekly audit** (`container-audit.yml`, Mondays 03:42 UTC): pulls the
  pinned digest from `plugins/bard/skills/bard-render/tools-image.json`,
  re-scans with a fresh vulnerability DB (new CVEs against the frozen
  image), runs the Docker CIS compliance report, runs an informational
  in-image Lynis 3.1.7 audit, aggregates `container-hardening.json`
  (artifact), and edits/creates a "Container hardening report" issue.
  The issue closes automatically when fixable HIGH/CRITICAL findings
  reach zero. The Lynis Hardening Index is recorded as a trend metric
  only — its denominator shifts with container-skipped tests, so it
  never gates.

Not adopted, with reasons: `lynis audit dockerfile` (~6 greps, frozen
since 2018, subset of hadolint, hardening index always 1);
Dockle (v0.4.15 stale; its CIS-derived checks are covered by Trivy's
`--compliance docker-cis` report); Grype (equivalent for the SBOM path,
kept as fallback); checkov (redundant third linter); `cisofy/lynis`
Docker image (does not exist — Lynis runs from a pinned git clone);
non-root USER enforcement and HEALTHCHECK enforcement (CI tools images —
deferred policy decisions).

Changelog evaluation for the adopted pins is in the introducing PR.
Suppressions: `.hadolint.yaml` waivers above; `.trivyignore` holds
time-boxed finding IDs — entries must carry an `exp:` date and a
rationale line here when added.

The pinned `debian:13-slim` base digest keeps shipping the debs it was
built with, so the Dockerfile upgrades the packages Trivy flagged at
publish (libpcre2-8-0, libssl3t64, openssl-provider-legacy) via a
targeted `apt-get install --only-upgrade` layer rather than waiving them.
It also appends `UMASK 027` to `/etc/login.defs` (Lynis AUTH-9328): the
image has no interactive users, so files created at runtime stay
group-readable only. Because the tightened umask makes Lynis write its
report and log 0640 root-owned, the audit step `chmod 644`s both files
so the runner-side grep can read the index.

The weekly audit runs Lynis with the committed
`docker/lynis-container.prf` profile, which skips tests that are
inapplicable inside a container (kernel/systemd/mounts/storage/network/
PAM/accounting are governed by runtime flags, not the image filesystem).
The profile raises the Hardening Index and reduces the suggestion list
to image-actionable items; remaining suggestions are fixed in the
Dockerfile or silenced only with a documented reason.

The `git clone --depth 1 --branch 3.1.7` pin of `CISOfy/lynis` in
`container-audit.yml` is tracked by `scripts/check_dependency_updates.py`
as a `git-clone` surface (compared against the upstream repo's highest
semver tag), so a new Lynis release surfaces in the weekly dependency
report. The checker also covers subpath `uses:` actions such as
`github/codeql-action/upload-sarif` (tracked under the owning repo's
tags), the sha256-verified downloads in `workflow-lint.yml` (the zizmor
wheel against PyPI and the actionlint tarball against `rhysd/actionlint`
releases), and the trivy `version:` inputs on the aquasecurity
`trivy-action`/`setup-trivy` pins (against `aquasecurity/trivy` releases). The Python-version surface covers every
workflow's `python-version:` inputs and quoted `"3.x"` pins, the
`.python-version` dotfile, and any `uv python install`/`uv venv
--python`/`python3.x` pins inside the Dockerfiles.

`render_score_png.py` applies the runtime-hardening flags the container
profile defers to: `--network none`, `--user uid:gid`,
`--cap-drop ALL`, `--security-opt no-new-privileges`, plus a
`--read-only` root filesystem with a `/tmp` tmpfs for the tools' scratch
space.

### CIS baseline

The Trivy CIS compliance scan reports `DS-0002` (image runs as root) and
`DS-0026` (no `HEALTHCHECK`) on every tools image. Both are waived with
`exp:` entries in `.trivyignore`: these are CI build/tool containers, not
deployed services — workflows that need a non-root UID already run the
image with `docker run --user`, and batch tooling has no health endpoint
to probe. The waivers renew or get re-fixed by Dockerfile changes when
they lapse.

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

In SDK 1.51.0 (#5151), `enable_sub_agents` and `enable_switch_llm_tool` are
retired as stored fields and `tools` is the only tool control: `task` appears
exactly when the profile's effective `tools` contains `task_tool_set`. The
retired switches are still accepted as deprecated input (folded into `tools`,
removal announced for 1.56.0), and a persisted legacy `tools: []` still
migrates to the standard set — only `[]` written by a current-version payload
means a bare agent. Also, when a profile pins `tools` explicitly, `task`
offers only the sub-agents that fit the parent's tool set and refuses others
at start (#5358): `bard` needs `terminal`, `file_editor`, `grep`, `glob`,
`task_tracker` and `task_tool_set`, and `bard`'s nested delegation to
`bard-critic` (`terminal`, `grep`, `glob`) inherits the same scope. A profile
that lists `task_tool_set` but omits those tools leaves `task` present while
`bard` is not offered — the same symptom the fallback path already covers.

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
  profile raises `ValueError` at task spawn, so the `session_start` hook
  `hooks/scripts/ensure_llm_profiles.py` clones the conversation's
  `active_profile` into `vibebb-author.json`/`vibebb-review.json` when
  they are absent — edit those files afterwards to route the authoring
  or review lane at a different model. To fall back to the conversation
  model, set `model: inherit` locally.
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

## Launcher-side verification

`BARD_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or `off`.
The renderer verifies the lock entry with `gh attestation verify` immediately
before pulling. `render_score_png.py --prewarm` verifies even when the pinned
image is already local. In `auto`, an image override, missing attestation,
missing `gh`, or failed `gh auth status` prints one note and skips verification; once
verification starts, failure or timeout stops the pull. `require` treats the
skip conditions as errors, while `off` never verifies. A locally present
image is not re-verified during ordinary rendering.

## Local verification

pytest selects subsets directly for a faster local check — `-k <expr>`, a
test path, or `-n 0` to disable the default `-n auto` workers:

```bash
uv run pytest -q tests/test_render_score_png.py
uv run pytest -q -k abc
uv run pytest -q -n 0
```

Run the full `uv run pytest -q` before submitting.

## CI runner network auditing

CI and image-publishing jobs use `step-security/harden-runner` in audit-only mode. It observes network egress without blocking requests; per-run insights are available in the GitHub Actions job summary.

## Digest-lock PR verification

The publisher waits briefly for the lock PR's own `pull_request` runs, which are the only runs that satisfy required checks; it dispatches `ci.yml` and `workflow-lint.yml` on the lock branch only when none appear. It then polls the authoritative required-check set for up to 15 minutes. Non-required failures do not block publishing; a concluded required-check failure or a PR closed without merge fails the job. A PR merged externally triggers the existing post-merge main workflows without waiting for their results. If required checks remain pending at the deadline, the publisher arms squash auto-merge with branch deletion and exits successfully so branch protection can complete the merge. Bot merges do not fire push events, so `digest-lock-sweep.yml` dispatches `ci.yml` and `locked-image-check.yml` on main after any sweep merge or recent lock merge that lacks a post-merge dispatch.

SPDX generation prefers the GHCR registry source, writes temporary data under
the runner's temporary directory, and disables file metadata. The publisher
removes file entries and relationships involving files to produce the
package-level SPDX-2.3 SBOM. A guard reports disk space and the attested SBOM
size after transformation and fails above 16 MiB; the full Syft SBOM is
uploaded as a 90-day workflow-run artifact.

## Repository settings

Two repository settings must be managed manually in the GitHub UI; the
workflows assume these values:

- **Code scanning > CodeQL analysis**: keep GitHub *default setup*
  enabled. A repo-managed `codeql.yml` cannot coexist with it — code
  scanning rejects the advanced configuration's SARIF upload outright
  ("cannot be processed when the default setup is enabled", observed on
  PR #110) — so the versioned-file adoption waits on disabling default
  setup first (Settings → Advanced Security → CodeQL analysis → stop
  using default setup).
- **Dependency graph**: keep enabled; `dependency-review.yml` fails with
  "not supported on this repository" when it is off.

## Settings-level posture (recorded decisions)

The following live in repository Settings rather than code; they are
intentional for the solo-maintainer bot-merge workflow and are recorded
here so audits do not re-flag them:

- Branch protection does not require approving reviews, code owners, or
  "apply to administrators": every merge is performed by automation
  (digest-lock, version-bump, and Devin PRs), so required approvers would
  only add friction to a pipeline that already gates on the required-check
  set. OpenSSF Scorecard reports this as Branch-Protection 3 and
  Code-Review 0; that is the recorded trade-off, not an oversight.
- The Dependency graph must stay enabled for `dependency-review.yml` to
  evaluate pull requests.
- `release.yml` is dispatch-only; run it once with `dry_run=true` before
  the first real release to rehearse bump, verify, and install-smoke
  without creating a GitHub release.
