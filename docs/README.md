# bard-agent documentation index

| Document | Contents |
|---|---|
| [`../README.md`](../README.md) | Product overview |
| [`../AGENTS.md`](../AGENTS.md) | Working contract |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributor setup and PR guidance |
| [`../SECURITY.md`](../SECURITY.md) | Vulnerability reporting and scope |
| [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) | Third-party licenses and pins |
| [`song-proposal-contract.md`](song-proposal-contract.md) | Canonical song proposal JSON contract |
| [`cue-set-contract.md`](cue-set-contract.md) | Product sound cue set JSON contract |
| [`operations.md`](operations.md) | Release process, plugin update notes, verification recipes |
| [`research/sdk-v1.50.0-feature-evaluation.md`](research/sdk-v1.50.0-feature-evaluation.md) | OpenHands SDK v1.50.0 and uv 0.12.21 adoption review |
| [`research/sdk-v1.50.1-feature-evaluation.md`](research/sdk-v1.50.1-feature-evaluation.md) | OpenHands SDK v1.50.1 adoption decisions |
| [`../docker/README.md`](../docker/README.md) | `bard-tools` score-render image |

## Accepted ADR list

| ADR | Title |
|---|---|
| [0001](adr/ADR-0001-task-subagent-plugin.md) | Distributing bard as a `task` sub-agent plugin |
| [0002](adr/ADR-0002-song-proposal-contract.md) | Proposal JSON as sole truth; stdlib-only ABC/MIDI/MML rendering |
| [0003](adr/ADR-0003-copyright-and-license-policy.md) | Copyright and license policy |
| [0004](adr/ADR-0004-ci-cd-release-by-tag.md) | CI/CD and tag-driven releases |
| [0005](adr/ADR-0005-score-visual-check.md) | score.png visual check (advisory) |
| [0006](adr/ADR-0006-oracle-consult-tools-not-adopted.md) | `ask_oracle` / `tom_consult` not adopted |
| [0007](adr/ADR-0007-svg-score-rendering.md) | score.png rendering via SVG + `rsvg-convert` |
| [0008](adr/ADR-0008-score-tools-docker-image.md) | Score-render toolchain distributed as a pinned container image |
| [0009](adr/ADR-0009-docker-only-score-render.md) | Docker-only score rendering (image is the only render path) |
| [0010](adr/ADR-0010-score-review-vision-contract.md) | `score-review.json` adopts the shared `vision_review` record contract |
| [0011](adr/ADR-0011-product-sound-cues.md) | Product sound cues as a separate `bard_cue_set` contract |
| [0012](adr/ADR-0012-attest-published-tools-images.md) | Attest published tools images |
