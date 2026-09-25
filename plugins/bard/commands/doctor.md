---
description: Probe the bard plugin install — plugin root, docker on PATH, and the bard-tools image pin.
allowed-tools:
  - terminal
---

# /bard:doctor

Resolve the bard plugin root the same way the hooks do
(`$BARD_PLUGIN_ROOT`, `${OPENHANDS_PROJECT_DIR}/plugins/bard`,
`~/.agents/plugins/bard`, `~/.openhands/plugins/installed/bard`) into
`$BARD_PLUGIN`, then run:

```bash
p=$(for c in "${BARD_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/bard" "${HOME:-}/.agents/plugins/bard" "${HOME:-}/.openhands/plugins/installed/bard"; do [ -f "$c/hooks/scripts/bard_doctor.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || { echo "bard plugin root unresolved" >&2; exit 1; }; python3 "$p/hooks/scripts/bard_doctor.py"
```

Report the `additionalContext` findings verbatim — plugin root resolution,
plugin layout, `docker` on `PATH`, and the `bard-tools` pin in
`skills/bard-render/tools-image.json`. A `missing` docker probe or an
unpinned `bard-tools` digest means `score.png` cannot render; name the
failing capability before proceeding to song work.
