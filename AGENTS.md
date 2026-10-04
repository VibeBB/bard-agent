# Agent Work Contract

> Target: OpenHands Software Agent SDK v1.51.0, Python 3.12+

This document is the working contract for implementation, validation, and
documentation in this repository. The README is the product overview,
`docs/` contains specifications and operating policy, and `docs/adr/`
contains architectural decisions.
README (English first, followed by a Japanese section), docs, issues, PRs, commit messages, code comments, and identifiers are written in English. Existing Japanese documents under docs/ may stay Japanese until they are revised.

## Purpose

bard is a minstrel agent that writes songs about work in an OpenHands
workspace, conversations with the user, and conversations with other agents.
It is distributed as an OpenHands plugin (`plugins/bard`), and the parent
agent invokes it with the `task` tool (`subagent_type: bard`).

## Layout

```text
plugins/bard/
├── .plugin/plugin.json
├── agents/
│   ├── bard.md               # Minstrel that writes songs (task sub-agent)
│   ├── bard-critic.md        # Critic (no pass/fail authority)
│   └── bard-cue.md           # Product sound cues (earcons) for ux-creator / firmware
├── commands/sing.md          # /bard:sing — directs context collection and task invocation
├── commands/cue.md           # /bard:cue — product sound cue request and task invocation
├── hooks/                    # session_start doctor, pre_tool_use song-artifact guard,
│                             # post_tool_use vision records, stop hook reporting song
│                             # render status (stdlib only)
├── skills/
│   ├── bard-songcraft/       # Songwriting theory decision tables, modes, and copyright contract
│   ├── bard-cuecraft/        # Product sound cue purposes, device ranges, originality rules
│   ├── bard-render/          # Proposal JSON validation and ABC/MIDI/MML/lyrics/provenance rendering,
│   │                         # plus cue-set rendering (render_cues.py) (stdlib only)
│   └── bard-proposal-rules/  # Path-triggered rule on *.proposal.json (contract + originality reminders)
│       ├── SKILL.md
│       ├── scripts/
│       └── tests/
docs/
├── song-proposal-contract.md # Canonical proposal JSON contract
├── cue-set-contract.md       # Product sound cue set JSON contract
├── adr/
└── research/
docker/                       # bard-tools image (abcm2ps + rsvg-convert + IPA font), the
                              # render_score_png.py execution environment; see docker/README.md
scripts/                      # Release and image-lock helper scripts (stdlib Python / bash)
tests/                        # Plugin-asset consistency checks
```

## Invariants

- The proposal JSON (`docs/song-proposal-contract.md`) is the sole source of
  truth for a song. ABC, MIDI, and MML are derived deterministically from it.
  The same proposal produces byte-identical outputs.
- bard, the critic, and Skills do not judge whether work (code, design, or a
  PR) passes or fails. A song is an observation and must not feed judgments
  back into the work it describes. The critic returns observations only and
  does not rewrite the proposal.
- The validator judges proposal text only. Contract violations, parse failures,
  and read-back mismatches fail closed; partial output is not written.
- `bard-render` scripts use only the Python standard library. Do not couple
  imports to music libraries or import GPL/AGPL code. External tools such as
  FluidSynth and LilyPond are not adopted at this time.
- Quoting or adapting lyrics or melodies from existing songs, naming real
  artists as imitation targets, and mocking real people are prohibited. The
  proposal is rendered only when every `originality` declaration is `true`.
- Text-reading and text-writing paths must specify `encoding="utf-8"`.
- Never put API keys, tokens, or secrets in logs, inputs, or commits.
- Files containing externally sourced code must retain the original license
  notices and attribution. Do not add unrelated third-party copyright notices
  to original files.

## Plugin boundary

- Do not build custom tool, event, history, or executor infrastructure;
  delegate to the OpenHands SDK.
- Invoke sub-agents only with `task` (`TaskToolSet`). Do not use `delegate` or
  `workflow` (ADR-0001).
- A task sub-agent does not receive the parent's conversation history. The
  parent summarizes the subject in `context.md`, and bard reads the workspace
  (git log and files) itself (ADR-0001).
- The `hooks/` stop hook is advisory (`decision: allow`) and reports each
  `songs/*/song.proposal.json` render status plus any `score.png` whose
  sibling `score-review.json` is missing or fails validation; unreadable
  proposal or provenance JSON fails closed. The `pre_tool_use` guard rejects writes to
  render projections (`song.abc`, `song.mid`, `song.mml`, `song.md`,
  `song.provenance.json`, `song.lint.json`, `score.png`); the `post_tool_use` hooks record
  vision calls and image observations to `observations/bard/*.jsonl`.
  The `session_start` `bard-doctor` hook is advisory too: it resolves the
  plugin root, probes for `docker` on `PATH` and the `tools-image.json` pin
  (docker runs the pinned render image), checks the plugin layout, and reports findings
  as context — it never blocks the session. Sub-agents do not inherit
  plugin hooks, so `agents/bard.md` and
  `agents/bard-critic.md` declare the guard (and bard the vision record) in
  their frontmatter.
- AgentDefinitions do not declare `skills:`; reference SKILL.md paths from the
  prompt. Resolve the plugin root in this order:
  `$BARD_PLUGIN_ROOT`,
  `$OPENHANDS_PROJECT_DIR/plugins/bard`,
  `$HOME/.agents/plugins/bard`,
  `$HOME/.openhands/plugins/installed/bard`.
- Shared hooks are canonical across the family; change all 9 copies together
  and update `EXPECTED` in `scripts/check_shared_hooks.py`.
  `intake_attachments.py` and `record_*` hooks are intentionally repo-specific.
- Skills use `triggers:` (`KeywordTrigger`). A `paths:` glob list makes a
  skill a path-triggered rule instead (deterministic injection when a matching
  file is touched); the two mechanisms are exclusive — keyword skills stay
  model-invocable, rules live in their own `skills/` entries.
- `plugins/bard/skills/bard-render/tools-image.json` pins the render image
  by digest and ships with the plugin install; it is rewritten only by
  the publish workflow's lock-update pull request. While no published digest
  exists the `digest` stays `null` and the render stays inert.

## Verification

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q
```

For Markdown-only changes, `git diff --check` and a relative-link check are
sufficient. Contributor setup and pull-request guidance are also documented
in [CONTRIBUTING.md](CONTRIBUTING.md).

The validator must include negative tests that deliberately break the judged
input and confirm that the broken proposal is rejected.

## CI/CD

- `.github/workflows/ci.yml` runs on pushes to main, pull requests,
  `workflow_dispatch` (used by the publish workflow to gate the image-pin
  PR; accepts a `ref` input like `workflow_call`), and `workflow_call`.
  Pull-request jobs also run on `bot/` automation branches: required checks
  are read from the pull_request check suite, so skipping them there
  would leave the pin/bump PRs permanently blocked. It runs `verify` (Python 3.12/3.13 matrix:
  ruff, format, pyright, and pytest), `independent-check` (required
  score PNG generation inside the pinned image, gated on a cryptographic
  verification of the lock's provenance attestation via
  `BARD_VERIFY_ATTESTATION=require` + `render_score_png.py --prewarm`),
  `pin-script-guard` (runs `test_publish_image_pin_pr.py` on PRs that
  touch the pin-PR script, its tests, or the publish workflow), and
  `plugin-load` (checks
  `Plugin.load` with `openhands-sdk==1.51.0` from the `sdk-check` group).
- `.github/workflows/release.yml` is `workflow_dispatch` only. A `bump` input
  (defaulting to patch) or an explicit `version` input controls the release.
  A `dry_run` input rehearses the release: version arithmetic and tag checks
  run, and downstream verify/install-smoke/build jobs still execute, but
  nothing is committed, pushed, tagged, or released.
  The bump-version state machine lives in `scripts/release_bump.sh`
  (the workflow step is a thin wrapper) and is covered by
  `tests/test_release_bump.py`, which exercises it against a stubbed `gh`
  and local git remotes.
  A greater explicit version runs `scripts/bump_version.py`, updates
  plugin.json, pyproject.toml, both SKILL.md files, and uv.lock, and commits
  the changes to main — or, when the ruleset rejects the direct push, opens a
  version-bump pull request and auto-merges it with `gh pr merge --auto`
  using the same self-approve + dispatched checks flow as the publish
  workflow — checks that the `v<version>` tag does not exist, and then
  runs verify, install-smoke, and `gh release create`. An explicit version
  equal to the current version performs a consistency check, skips the bump
  commit and push, checks that the tag does not exist, and releases the current
  main HEAD. The release job renders the shipped sample scores through the
  pinned `bard-tools` image (no host ABC tools are installed), which also
  exercises the container path of `render_score_png.py`, and attests the
  plugin/samples zips with `actions/attest-build-provenance`, uploading
  the provenance bundle to the release.
- `.github/workflows/publish-bard-images.yml` builds and publishes the
  `ghcr.io/<owner>/bard-tools` score-render image on `workflow_dispatch` and
  on pushes to main that touch `docker/**` or the lock scripts (excluding
  `docker/README.md` and the pin file itself), then opens a pull request that
  updates the digest pin in `plugins/bard/skills/bard-render/tools-image.json`
  — the file the render script reads at render time. The workflow
  self-approves any approval-gated `pull_request` runs on the pin branch
  and waits for the pull_request check suites, which are what satisfy the
  required checks; `ci.yml` and `workflow-lint.yml` are dispatched on the
  pin branch only as a fallback when no pull_request run appears (the
  dispatched runs never satisfy required checks). It auto-merges the
  PR via `gh pr merge --auto` (the merge queue is not enabled) — no
  manual steps. After the merge lands it dispatches `ci.yml`, `locked-image-check.yml`, and
  `workflow-lint.yml` on main fire-and-forget; `main-ci-failure-issue.yml` turns a failed main
  run into a tracking issue.
  A `dry_run` dispatch input rehearses the publish: the image is built
  into the local daemon (`push: false`, `load: true`) and the Trivy gates,
  SBOM generation, measurement, and smoke checks still run against the
  local tag, but nothing is pushed to the registry, `:latest` is not
  promoted, no attestation is stored, the digest-lock PR is not opened,
  no post-merge workflow is dispatched, and no SARIF reaches code
  scanning.
- `.github/workflows/locked-image-check.yml` validates the render-image
  lock, verifies available provenance and SBOM attestations, renders the
  shipped score example through `render_score_png.py`, and retains smoke
  output.
- `.github/workflows/check-dependency-updates.yml` runs
  `scripts/check_dependency_updates.py` weekly and on `workflow_dispatch`,
  aggregating update candidates (PyPI direct/lock drift, uv pin, Python
  minor, GitHub Actions `uses:` pins including subpath actions, uvx tool
  pins, sha256-verified direct downloads in workflows such as the zizmor
  wheel and the actionlint tarball, `version:` tool inputs on pinned
  actions such as the aquasecurity trivy scans, Docker ARGs and base
  image, and `git clone --branch` pins inside workflows such as the pinned
  Lynis checkout in `container-audit.yml`) into the "Dependency update
  check report" Issue labeled
  `dependency-updates`; fetch failures are reported as unknown and keep the
  issue open until both outdated and unknown counts reach zero.
  Deferrals with reasons and re-check deadlines live in
  `scripts/dependency_update_deferrals.json`. When adding, removing, or
  moving a dependency, adding a new version ARG to a Dockerfile, or starting
  to use a new external source (other than PyPI, a different Git repository,
  apt/PPA, etc.), update the target definitions in
  `scripts/check_dependency_updates.py` and its tests in the same change, and
  run `uv run python scripts/check_dependency_updates.py` locally to confirm
  nothing is missing.
  When bumping a dependency to a newer version, review the complete
  changelog of every updated component (all releases between the pinned
  and target versions), evaluate each new feature or behavior change for
  use in this repository, adopt the useful ones in the same change, and
  record the evaluation — including reasons for non-adoption — in the PR
  or under `docs/research/`.
- `.github/workflows/main-ci-failure-issue.yml` watches completed main
  runs of CI, Container hardening audit, Digest lock PR sweep, Dependency
  update check, Locked image check, PR branch cleanup, Publish bard images,
  Release, Scorecard, and Workflow lint (`workflow_run`), and files or
  closes a `ci-main-failure` tracking issue on failure/success; queued
  reports are keyed per triggering run so completions are not evicted.
- `.github/workflows/workflow-lint.yml` runs actionlint (structural YAML
  checks) and zizmor on every pull request, on pushes to main that touch
  `.github/**`, on
  `workflow_dispatch` (used by the publish workflow to gate the image-pin
  PR), and weekly, and uploads the results to code scanning as SARIF.
  `zizmor` is a required status check, so the pull-request trigger must
  not be path-filtered. Zizmor runs from a sha256-verified wheel with
  `GH_TOKEN` online audits, `--offline` on `bot/update-image-digests-*`
  branches, and gates on the recorded SARIF results.
- CodeQL analysis runs under GitHub's default setup today. A
  repo-managed `codeql.yml` requires disabling default setup first —
  advanced-configuration SARIF uploads are rejected while it is enabled —
  so its adoption is deferred to a settings change plus a follow-up PR.
- `.github/workflows/digest-lock-sweep.yml` retries stalled digest-lock PR
  merges every 6 hours (the branch ruleset still gates them) and
  dispatches `ci.yml`/`locked-image-check.yml` on main after a merge or
  any recent lock merge that lacks a post-merge dispatch, since bot merges
  do not fire push events.
- `.github/workflows/cache-sweep.yml` deletes stale actions caches
  monthly: `trivy-db-*` keys outside the current ISO week, `cache-trivy-*`
  daily keys older than two days, and the unbounded buildx gha
  `buildkit-blob-*`/`index-buildkit-*` entries — keeping the repo under
  the 10 GB LRU-eviction cliff.
- `.github/workflows/container-audit.yml` scans the pinned image weekly:
  Trivy SARIF to code scanning plus a full JSON report, a Docker CIS
  compliance scan that retries once on an empty result set and fails
  loudly when it still produces no results, an
  informational Lynis audit (procps/iproute2 installed so process and
  network tests run; the 3.1.7 checkout is detached onto its pinned
  commit), and a hardening report issue with a week-over-week vulnerability
  delta plus failed-CIS-check and top-fixable-CVE tables; duplicate open
  report issues are closed so the canonical one keeps updating.
- Every `uses:` entry is pinned to a 40-character SHA with a `# vX.Y.Z`
  comment. Checkout uses `persist-credentials: false`, and every job has a
  `timeout-minutes` setting.
- `dependabot.yml` groups GitHub Actions updates and monitors them weekly with
  a seven-day cooldown; Dockerfile updates are also monitored weekly with a
  seven-day cooldown under `/docker`. The uv ecosystem is intentionally
  excluded (Dependabot's bundled uv cannot satisfy `[tool.uv] required-version`),
  so Python dependency updates stay covered by the weekly
  check-dependency-updates.yml report.

Digest-lock PRs use `scripts/publish_image_pin_pr.sh`: the publisher waits
for the lock PR's `pull_request` runs and dispatches `ci.yml` and
`workflow-lint.yml` on the lock branch only when none appear, then polls
the authoritative required-check set for up to 15 minutes. Non-required
failures do not block publishing; a concluded required-check failure or a PR
closed without merge fails the job. A PR merged externally triggers the
existing post-merge main workflows. If required checks are still pending at
the deadline, the publisher arms squash auto-merge with branch deletion and
exits successfully.

SPDX SBOM generation prefers registry pulls, uses runner temporary storage,
and disables file metadata. The attested SBOM is package-level SPDX 2.3;
file entries and relationships involving files are omitted to stay below
16 MiB. The full Syft SBOM is attached to the workflow run as a 90-day
artifact.

## Git

Write commit messages in English. Do not use `git add .`, amend commits,
`--no-verify`, force push, direct pushes to main, `reset --hard`, `clean -fd`,
`checkout -- file`, or `stash drop`. Do not commit generated `out/` files,
secrets, or environment files. Use `git mv` when renaming files.

Shared workflows are canonical across the family; change all 11 copies together and update `EXPECTED` in `scripts/check_shared_workflows.py`.
