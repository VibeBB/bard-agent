# Commands

Slash commands live in `plugins/bard/commands/` and dispatch on plain text.

## `/bard:sing [mode] [subject]`

- Modes: `chronicle` (default), `praise`, `lament`, `satire`, `inspire`,
  `lore`. No subject → "what happened in this conversation".
- Steps: pick a `songs/<slug>/` dir (never overwrite), write `context.md`
  (parent summarizes the conversation), dispatch `task(subagent_type="bard")`
  or run the stages itself when `task` is unavailable; run the critic pass;
  report title/mode/key/tempo/lyrics/files.
- Output: the `songs/<slug>/` file set (see [workflow.md](workflow.md)).

## `/bard:cue [piezo|speaker] [product] [purposes | *.ux-request.json]`

- Steps: read device + product + request (purpose list or an SLP v2
  `*.ux-request.json` — validated before work); create `cues/<slug>/`; write
  `context.md`; dispatch `task(subagent_type="bard-cue")` or run the stages
  itself; verify `cues.proposal.json`, `cues.json`, `cues.md`,
  `cues.provenance.json` and per-cue mid/mml exist.
- For a liaison request it finishes with `bard_cli.py ux-respond` (see
  [sister-cooperation.md](sister-cooperation.md)).
- Output: the `cues/<slug>/` file set; the `cues.json` path for
  `ux import --from bard`.

## `/bard:inbox [workspace root]`

- Runs `bard_cli.py ux-inbox`, dispatches `new`/`stale` requests to `bard-cue`
  (sound requests) or `bard` (songs), records decision + impression, answers
  each request with `ux-respond` carrying gate verdicts
  (`cue-set-contract`/`song-proposal-contract`, `readback`, `score-review`
  when PNGs exist), and reports resulting states.

## `/bard:doctor`

- Runs `bard_doctor.py`: reports plugin-root resolution, layout, `docker` on
  PATH, the `bard-tools` pin, and the liaison inbox counts. Advisory; never
  fails.
