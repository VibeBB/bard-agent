# ADR-0008: Score-render toolchain distributed as a pinned container image

> Status: Accepted
> Date: 2026-09-23

## Context

Stage 8 (`score.png` visual check) needs `abcm2ps` and `rsvg-convert` plus a
font covering the lyric script (ADR-0005, ADR-0007). On the OpenHands runtime
these tools are not part of the base image, so Stage 8 silently skipped with
exit code 4 unless an operator installed them with `sudo apt-get` on every
host — an installation step outside the plugin's reach, verified in practice
during the v1.1.0 evaluation. The OpenHands runtime does expose a docker
daemon, so an image can replace the host install.

## Decision

- Ship `docker/bard-tools.Dockerfile` (ubuntu base + `abcm2ps`, `abcmidi`,
  `librsvg2-bin`, `fonts-ipafont`; build-time smoke render) and publish it to
  GHCR as `bard-tools` via `publish-bard-images.yml` on `docker/**` pushes to
  main and manual dispatch.
- Pin the consumed image by digest in
  `plugins/bard/skills/bard-render/tools-image.json`, inside the plugin tree
  so the file ships with a plugin install. The publish workflow opens a
  lock-update pull request that rewrites it; `ci.yml` is dispatched on the
  lock branch because `GITHUB_TOKEN`-created PRs trigger no `pull_request`
  workflow.
- `render_score_png.py` falls back to `docker run` only when the host tools
  are absent and a digest is pinned: pull the image once (skip when already
  present), mount the ABC directory read-only and the output directory
  read-write, run the identical `abcm2ps -g` + `rsvg-convert` pipeline with
  `--network none` and a read-only root filesystem, as the calling uid/gid.
- `BARD_TOOLS_IMAGE` overrides the pin for local testing; the `--json` result
  records `renderer: host|docker` and the image ref.

## Consequences

- Hosts without `abcm2ps`/`rsvg-convert` but with docker get Stage 8 renders
  with no host packages; hosts with neither still report exit 4 (advisory
  skip, unchanged contract).
- The plugin stays standard-library-only: docker is invoked as an external
  binary, the same relationship as `abcm2ps` — no new Python dependency, no
  coupling to a music library.
- The pinned digest makes the fallback reproducible; `latest` is never a
  verification target.
- Container `score.png` bytes can differ from host bytes (different tool
  versions); the PNG is advisory material and not part of the provenance
  output set, so this changes no contract.
- Songcraft guidance already prevents the adjacent-syllable collision this
  toolchain surfaces (see `%%vocalspace` in `render_abc`); this ADR covers
  distribution only.
