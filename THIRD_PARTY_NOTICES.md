# Third-Party Notices

bard is licensed BSD-3-Clause (see LICENSE). The render scripts use only the
Python standard library; the components below are bundled in the optional
`bard-tools` container image or used during development. Copyleft components
run only as unmodified external processes — they are never imported or
linked into bard's code, keeping the license boundary described in
[AGENTS.md](AGENTS.md). This file is not legal advice.

## Container image components (`docker/bard-tools.Dockerfile`)

### abcm2ps

- License: GPL-3.0-or-later
- Package: `abcm2ps` (Debian 13 apt)
- Source: <https://github.com/lewdlime/abcm2ps>
- Role: renders `song.abc` to SVG inside the optional score-check image.
  Invoked as a subprocess only.

### abcmidi (abc2midi)

- License: GPL-2.0-or-later
- Package: `abcmidi` (Debian 13 apt)
- Source: <https://ifdo.ca/~seymour/runabc/top.html>
- Copyright: James Allwright, Seymour Shlien, et al.
- Role: ABC → MIDI conversion utility, smoke-checked in the image.
  Invoked as a subprocess only.

### librsvg2 (rsvg-convert)

- License: LGPL-2.1-or-later
- Package: `librsvg2-bin` (Debian 13 apt)
- Source: <https://gitlab.gnome.org/GNOME/librsvg>
- Role: SVG → PNG rasterization inside the score-check image.
  Invoked as a subprocess only; not linked.

### fonts-ipafont

- License: IPA Font License Agreement v1.0
- Package: `fonts-ipafont` (Debian 13 apt)
- Source: <https://ipafont.ipa.go.jp/>
- Role: Japanese (IPA) glyphs for rendered scores. Font files are used at
  render time only and are not modified.

### fontconfig

- License: MIT-style (fontconfig license)
- Package: `fontconfig` (Debian 13 apt)
- Source: <https://www.freedesktop.org/wiki/Software/fontconfig/>

### Debian base image

- Image: `debian:13-slim`
- Source: <https://hub.docker.com/_/debian>
- Debian copyright notices and licenses follow the base image.

## Development tools

Used to build and verify the project; not distributed.

| Tool | License |
| --- | --- |
| ruff | MIT |
| pyright | MIT |
| pytest | MIT |
| uv | Apache-2.0 / MIT |
| zizmor (CI) | MIT |
| hatchling | MIT |
| OpenHands SDK (`openhands-sdk`) | MIT |

## Notes

- GPL/LGPL components above execute as standalone binaries in the
  `bard-tools` container — never as libraries imported into bard's Python
  code — so bard's own BSD-3-Clause license is unaffected.
- License texts for Debian packages are available in-image under
  `/usr/share/doc/<package>/copyright`.
- If you add a bundled component, update this file in the same change.
