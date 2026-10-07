# Architecture

## Components

bard-agent is an OpenHands plugin (`plugins/bard`) — Markdown agent definitions,
slash commands, skills and hooks; there is no daemon and no MCP server. Three
layers:

1. **Prompts** (`agents/`, `commands/`, `skills/`): who bard is, what stages it
   follows, the music theory decision tables. No executable logic.
2. **Deterministic scripts** (`skills/bard-render/scripts/`,
   `plugins/bard/scripts/`, `hooks/scripts/`): Python 3.12+, standard library
   only, run on the host `python3`. They validate contracts, render
   projections, write VRP records, answer liaison requests, and guard files.
3. **Pinned container** (`ghcr.io/vibebb/bard-tools`, digest-locked by
   `skills/bard-render/tools-image.json`): holds `abcm2ps` and `rsvg-convert`.
   Score/contour/timeline PNG rasterization happens only inside this image —
   the host never falls back to a local ABC/SVG tool (ADR-0008, ADR-0009).

## Data flow

```text
user ──/bard:sing──▶ parent agent ──context.md──▶ bard (task sub-agent)
   │                                                │ reads workspace
   │                                                ▼
   │                              song.proposal.json (sole truth)
   │                                                │ render_song.py
   │                                                ▼
   │                     song.abc/.mid/.mml/.md/contour.svg/provenance
   │                                                │ render_score_png.py
   │                                          (docker, pinned image)
   │                                                ▼
   │                                   score.png / song.contour.png
   │                                                │ vision review
   ▼                                                ▼
ux-creator ──*.ux-request.json──▶ /bard:inbox ──▶ bard-cli ux-respond
                                                  └── *.ux-response.json
observations/bard/*.jsonl ◀── bard_cli.py record … (decisions, impressions,
                              vision-reviews) — written through the CLI only
```

## Plugin layout

```text
plugins/bard/
├── .plugin/plugin.json          # plugin manifest
├── agents/                      # bard.md, bard-cue.md, bard-critic.md
├── commands/                    # sing.md, cue.md, inbox.md, doctor.md
├── hooks/
│   ├── hooks.json               # session_start / pre_tool_use / post_tool_use / stop
│   ├── records-policy.json      # VRP policy: artifact globs, stop-denial bound
│   └── scripts/                 # hook scripts (stdlib only; _records.py and
│                                # require_records.py are canonical across the family)
├── scripts/                     # bard_cli.py, bard_records.py, bard_liaison.py
└── skills/
    ├── bard-songcraft/          # songwriting decision tables + originality contract
    ├── bard-cuecraft/           # product cue purposes, device ranges, originality rules
    ├── bard-render/             # validators + renderers + tools-image.json pin
    └── bard-proposal-rules/     # path-triggered rule on *.proposal.json
```

## Execution environments

- **Host python3**: every plugin script (`hooks/scripts`, `plugins/bard/scripts`,
  `skills/bard-render/scripts`). No third-party imports; they must run wherever
  the agent SDK spawns `python3`.
- **`bard-tools` image**: `abcm2ps -g` (ABC→SVG), `rsvg-convert` (SVG→PNG).
  `render_score_png.py` runs the image with `--network none --cap-drop ALL
  --security-opt no-new-privileges --read-only --tmpfs /tmp -e HOME=/tmp` and
  read-only input mounts. The image contains no Python; host scripts stay out
  of it by design.

## Plugin-root resolution

Every hook command, agent prompt and command doc resolves the plugin root as
the first existing directory of:

1. `$BARD_PLUGIN_ROOT`
2. `$OPENHANDS_PROJECT_DIR/plugins/bard`
3. `$HOME/.agents/plugins/bard`
4. `$HOME/.openhands/plugins/installed/bard`
5. `$HOME/plugins/installed/bard`
6. `$OH_PERSISTENCE_DIR/plugins/installed/bard`

Candidates 5–6 cover the OpenHands docker conversation runtime, whose inner
`HOME` is `/var/openhands/.openhands`; docker is unavailable inside it, so
`render_score_png.py` fails closed there with runtime-switch guidance.

Unresolved root: advisory hooks exit 0 (they degrade, never crash); the
`pre_tool_use` `protect-song-artifacts` guard keeps its fail-closed exit 2.
