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
