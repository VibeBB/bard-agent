# bard-tools image

`bard-tools.Dockerfile` packages the score-render toolchain — `abcm2ps`,
`abcmidi`, `rsvg-convert`, and `fonts-ipafont` — as the single execution
environment for `score.png`. The image is published to
`ghcr.io/vibebb/bard-tools` and consumed by
`plugins/bard/skills/bard-render/scripts/render_score_png.py`: the script
pulls the digest-pinned image recorded in
[`plugins/bard/skills/bard-render/tools-image.json`](../plugins/bard/skills/bard-render/tools-image.json)
and runs the render pipeline inside the container with `--network none` and
a read-only root filesystem. The song directory is the only bind mount. The
host needs nothing but docker — host installs of `abcm2ps`/`rsvg-convert`
are never consulted.

An empty `digest` in `tools-image.json` means no published image exists yet;
the render then stays inert and the script reports the tools as missing.

## Publishing

`.github/workflows/publish-bard-images.yml` builds and pushes
`ghcr.io/<owner>/bard-tools:<sha>-tools` plus the `latest` alias, measures the
tool versions in the published image, and opens a pull request that updates
`tools-image.json`. It runs on `workflow_dispatch` and on pushes to `main`
that touch `docker/**`, the publish workflow, or the two lock scripts. Because
`GITHUB_TOKEN`-created PRs do not trigger `pull_request` workflows, the
workflow dispatches `ci.yml` on the lock branch explicitly and only then
enqueues the PR (merge-queue ruleset); if auto-merge is blocked, the pin PR
is left open for manual merge.

To republish after a Dockerfile or workflow change, merge the change to
`main` (the push trigger publishes automatically) or dispatch the workflow
manually.
