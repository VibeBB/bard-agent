# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 1.1.x | Yes |

## Reporting a vulnerability

Please do not open public issues for security vulnerabilities. Report them
via GitHub's private vulnerability reporting on this repository, or by
contacting the maintainer directly. Include:

- the affected version/commit,
- a minimal reproduction (proposal JSON, command, or payload),
- impact assessment if known.

You can expect an acknowledgement within a few days. We will coordinate a
fix and disclosure with you before publishing details.

## Scope notes

bard renders songs from proposal JSON using Python-standard-library-only
scripts; the optional `score.png` advisory path shells out to `abcm2ps` and
`rsvg-convert` (from `PATH` or the digest-pinned `bard-tools` image), which
parse external ABC/SVG data as native code. Do not render untrusted
proposals where a crafted file could reach other tooling. The plugin adds
no network listeners.

Secrets must never be written to logs, inputs, or commits; see the
invariants in [AGENTS.md](AGENTS.md).
