# Contributing to bard-agent

Thank you for your interest in contributing to bard-agent.

## Setup

Use [uv](https://docs.astral.sh/uv/) with Python 3.12 or newer:

```bash
uv sync
```

Optional: the score-render tests run `abcm2ps`/`rsvg-convert` inside the
pinned `bard-tools` image, so they need docker and a resolvable image pin
(`tools-image.json`); otherwise they are skipped. `BARD_REQUIRE_DOCKER=1`
fails instead of skipping. The image bundles fonts-ipafont for Japanese
lyrics.

## Checks

Run the full check suite before opening a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

For a Markdown-only change, `git diff --check` and a check of relative links
are sufficient — `uv run python scripts/verify_docs.py` runs both the link
check and the ADR-index check that CI enforces. The documentation map (specs,
ADRs, research) lives in [docs/README.md](docs/README.md).

## Project invariants

The repository's working contract is [AGENTS.md](AGENTS.md). In particular,
the proposal JSON is the sole source of truth for generated music, rendering
must fail closed, generated outputs must be deterministic, and the renderer
must remain standard-library-only. Do not introduce existing-song quotations
or adaptations, imitation of real artists, or mockery of real people.

## Pull requests

1. Fork the repository and create a focused branch from `main`.
2. Keep each pull request small and focused on one change.
3. Add or update tests and documentation when behavior or contracts require it.
4. Ensure CI is green before requesting review.
5. Write code comments, issues, and pull requests in English.
6. Use `git mv` when renaming files.
7. Do not commit generated `out/` files, secrets, credentials, or environment
   files.

Do not change runtime behavior, agent or skill instructions, or JSON contracts
without clearly documenting the decision and its compatibility impact.

## Releases

Maintainers run the `release` workflow manually with `workflow_dispatch`.
Contributors should not bump versions; maintainers perform version bumps as
part of the release process.
