# Development

## Setup

```bash
uv sync                          # project venv (Python 3.12+)
```

## Verify

```bash
uv run ruff check . && uv run ruff format --check .
uv run pyright
env -u BASH_ENV -u "BASH_FUNC_gh%%" uv run python scripts/structural_coverage.py run
uv run python scripts/check_shared_hooks.py
uv run python scripts/check_shared_workflows.py
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
uvx zizmor@1.30.1 .github/workflows && actionlint -oneline
```

The `BASH_ENV`/`BASH_FUNC_gh%%` unsets are needed because the Devin `gh`
function breaks the stub-`gh` tests. `structural_coverage.py run` wraps pytest and
gates C0, C1, decision, C2, MC/DC and boundary floors from `pyproject.toml`
([test-coverage.md](test-coverage.md)).

Docker-dependent tests are opt-in: `BARD_REQUIRE_DOCKER=1 uv run pytest -q -k
abcm2ps -rs` runs the real in-image renders (needs docker + the pinned
`bard-tools` image).

## CI required checks

`verify (3.12)` / `verify (3.13)` (ruff, format, pyright, pytest),
`independent-check` (real `abcm2ps` render in the pinned image, attestation
verification, contour/cue rasterize into the `bard-samples` artifact),
`plugin-load` (`openhands-sdk` plugin load), `zizmor`.

## Shared hooks and workflows

`hooks/scripts/{_records.py, require_records.py, ensure_llm_profiles.py,
ensure_agent_profiles.py, safety_rail.py, _provenance.py}` are canonical
across the VibeBB family —
change all copies together and update `EXPECTED` in
`scripts/check_shared_hooks.py` (normalized-AST sha256). The shared workflows
follow `scripts/check_shared_workflows.py` the same way.

## Version bump

`scripts/bump_version.py` updates `plugins/bard/.plugin/plugin.json`,
`pyproject.toml`, the three SKILL.md files (`bard-render`, `bard-songcraft`,
`bard-cuecraft`), and `uv.lock`. See [operations.md](operations.md) for the
release workflow.
