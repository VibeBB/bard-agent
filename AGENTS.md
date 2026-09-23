# Agent Work Contract

> Target: OpenHands Software Agent SDK v1.49.4, Python 3.12+

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
│   └── bard-critic.md        # Critic (no pass/fail authority)
├── commands/sing.md          # /bard:sing — directs context collection and task invocation
├── hooks/                    # stop hook reporting song render status (stdlib only)
├── skills/
│   ├── bard-songcraft/       # Songwriting theory decision tables, modes, and copyright contract
│   └── bard-render/          # Proposal JSON validation and ABC/MIDI/MML/lyrics/provenance rendering (stdlib only)
│       ├── SKILL.md
│       ├── scripts/
│       └── tests/
docs/
├── song-proposal-contract.md # Canonical proposal JSON contract
├── adr/
└── research/
docker/                       # bard-tools image (abcm2ps + rsvg-convert + IPA font) for the
                              # render_score_png.py docker fallback; see docker/README.md
scripts/                      # Release and image-lock helper scripts (stdlib only)
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
  `out/bard/*/song.proposal.json` render status; unreadable proposal or
  provenance JSON fails closed.
- AgentDefinitions do not declare `skills:`; reference SKILL.md paths from the
  prompt. Resolve the plugin root in this order:
  `$BARD_PLUGIN_ROOT`,
  `$OPENHANDS_PROJECT_DIR/plugins/bard`,
  `$HOME/.openhands/plugins/installed/bard`.
- Skills use `triggers:` (`KeywordTrigger`).
- `plugins/bard/skills/bard-render/tools-image.json` pins the docker fallback
  image by digest and ships with the plugin install; it is rewritten only by
  the publish workflow's lock-update pull request. While no published digest
  exists the `digest` stays `null` and the fallback stays inert.

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

- `.github/workflows/ci.yml` runs on pushes to main, pull requests, merge
  groups, `workflow_dispatch` (used by the publish workflow to gate the
  image-pin PR), and `workflow_call`. It runs `verify` (Python 3.12/3.13 matrix:
  ruff, format, pyright, and pytest), `independent-check` (required
  `abcm2ps`/`rsvg-convert` and score PNG generation), and `plugin-load` (checks
  `Plugin.load` with `openhands-sdk==1.49.4` from the `sdk-check` group).
- `.github/workflows/release.yml` is `workflow_dispatch` only. A `bump` input
  (defaulting to patch) or an explicit `version` input controls the release.
  A greater explicit version runs `scripts/bump_version.py`, updates
  plugin.json, pyproject.toml, both SKILL.md files, and uv.lock, and commits
  the changes to main — or, when the ruleset rejects the direct push, opens a
  version-bump pull request and merges it through the merge queue using the
  same self-approve + dispatched checks + `enqueuePullRequest` flow as the
  publish workflow — checks that the `v<version>` tag does not exist, and then
  runs verify, install-smoke, and `gh release create`. An explicit version
  equal to the current version performs a consistency check, skips the bump
  commit and push, checks that the tag does not exist, and releases the current
  main HEAD. The release job renders the shipped sample scores through the
  pinned `bard-tools` image (no host ABC tools are installed), which also
  exercises the docker fallback path of `render_score_png.py`.
- `.github/workflows/publish-bard-images.yml` builds and publishes the
  `ghcr.io/<owner>/bard-tools` score-render image on `workflow_dispatch` and
  on pushes to main that touch `docker/**` or the lock scripts (excluding
  `docker/README.md` and the pin file itself), then opens a pull request that
  updates the digest pin in `plugins/bard/skills/bard-render/tools-image.json`
  — the file the docker fallback reads at render time. The workflow
  self-approves any approval-gated `pull_request` runs on the pin branch,
  dispatches `ci.yml` and `workflow-lint.yml` there for the required
  checks, and enqueues the PR into the merge queue via `gh pr merge
  --auto` — no manual steps.
- `.github/workflows/workflow-lint.yml` runs zizmor on every pull request,
  on merge groups, on pushes to main that touch `.github/**`, on
  `workflow_dispatch` (used by the publish workflow to gate the image-pin
  PR), and weekly, and uploads the results to code scanning as SARIF.
  `zizmor` is a required status check, so the pull-request trigger must
  not be path-filtered.
- Every `uses:` entry is pinned to a 40-character SHA with a `# vX.Y.Z`
  comment. Checkout uses `persist-credentials: false`, and every job has a
  `timeout-minutes` setting.
- `dependabot.yml` monitors GitHub Actions and uv weekly (`uv` has a seven-day
  cooldown).

## Git

Write commit messages in English. Do not use `git add .`, amend commits,
`--no-verify`, force push, direct pushes to main, `reset --hard`, `clean -fd`,
`checkout -- file`, or `stash drop`. Do not commit generated `out/` files,
secrets, or environment files. Use `git mv` when renaming files.
