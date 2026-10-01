## SBOM attestations

The publisher generates an SPDX-2.3 SBOM for the digest-pinned tools image,
attests it with predicate type `https://spdx.dev/Document/v2.3`, and uploads
the SBOM artifact for 30 days. The `sbom_attestation` URL is recorded in the
lock after publication. Locked-image checks verify it when present and warn
when it is absent; unpinned locks cannot carry this metadata.
# ADR-0012: Attest published tools images

## Status

Accepted

## Date

2026-10-01

## Context

The `bard-tools` image is published to GHCR and pinned by digest in the
installed plugin. A digest identifies immutable image content, but the
publisher does not otherwise attach verifiable information about the workflow
that produced that image.

## Decision

- Generate a GitHub build-provenance attestation for the published
  `ghcr.io/vibebb/bard-tools` image and push the attestation to the registry.
- Store the attestation URL in `tools-image.json` alongside the digest and
  existing publication metadata.
- Keep the image digest as the runtime pin; the attestation is provenance
  metadata and does not change image selection.

## Consequences

- Published tool images have an attestation URL recorded with their digest.
- Existing image-lock readers continue to use the image and digest fields and
  tolerate the additional metadata.

## Launcher-side verification

`BARD_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or `off`.
The renderer verifies the lock entry with `gh attestation verify` immediately
before pulling. `render_score_png.py --prewarm` verifies even when the pinned
image is already local. In `auto`, an image override, missing attestation,
missing `gh`, or failed `gh auth status` prints one note and skips verification; once
verification starts, failure or timeout stops the pull. `require` treats the
skip conditions as errors, while `off` never verifies. A locally present
image is not re-verified during ordinary rendering.
