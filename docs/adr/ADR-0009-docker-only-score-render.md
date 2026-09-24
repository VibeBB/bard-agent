# ADR-0009: Docker-only score rendering (supersedes the ADR-0008 fallback split)

> Status: Accepted
> Date: 2026-09-24
> Supersedes: the host-tools branch of ADR-0008

## Context

ADR-0008 shipped `bard-tools` as a *fallback*: `render_score_png.py` preferred
host `abcm2ps`/`rsvg-convert` and only engaged the pinned image when those
binaries were absent. That split meant two render environments (host package
versions vs. the pinned image) and host-setup steps the plugin cannot control
or verify. The OpenHands runtimes this plugin targets expose a docker daemon,
and wire/mech/circuit already treat the pinned tools image as the single
execution environment through their launchers.

## Decision

- `render_score_png.py` always renders inside the digest-pinned `bard-tools`
  image (`tools-image.json`, overridable via `BARD_TOOLS_IMAGE`). The host
  `abcm2ps`/`rsvg-convert` path, the `renderer: host|docker` result field, and
  the "not on PATH" skip message are removed. Exit code 4 now means "docker
  not on PATH or no usable pinned image".
- `bard_doctor.py` probes `docker` and the `tools-image.json` pin; the
  `abcm2ps`/`rsvg-convert` probes are removed.
- CI `independent-check` pulls the pinned image instead of apt-installing the
  ABC tools; the opt-in real-render gate is renamed `BARD_REQUIRE_DOCKER=1`
  (previously `BARD_REQUIRE_ABCM2PS=1`), and the abcm2ps contract check in
  `tests/test_render_song.py` runs through the image.
- Host installs of the score toolchain are no longer consulted anywhere;
  hosts without docker report exit 4 (advisory skip), the same contract as a
  host without the tools before.

## Consequences

- One render environment: the PNG bytes depend only on the pinned image, not
  on which host packages happen to be installed.
- `tools-image.json` stops being an optional pin: with no digest the render
  stays inert, but there is no host path left to cover that case.
- Local `docker build` or pull issues are surfaced as exit 4/5 instead of a
  silent host render; `BARD_TOOLS_IMAGE` remains the escape hatch for testing
  a candidate image.
- The plugin stays standard-library-only; docker remains an external binary
  boundary, unchanged from ADR-0008.
