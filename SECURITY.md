# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

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

bard writes and renders song artifacts locally via the pinned `bard-tools`
image. The validator fails closed on malformed proposals, but the renderer
is not a sandbox: do not render untrusted proposals in environments where
crafted ABC/MIDI content could reach other tooling. The plugin runs inside
the parent agent's workspace and opens no network listeners itself.
