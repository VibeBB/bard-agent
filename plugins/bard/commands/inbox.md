---
description: List open ux-creator liaison requests and dispatch them to the bard sub-agents.
argument-hint: "[workspace root]"
allowed-tools:
  - terminal
  - file_editor
  - task_tool_set
---

# /bard:inbox

Sibling-agent liaison (SLP v2): ux-creator drops `*.ux-request.json` files in the workspace;
bard answers each with a `*.ux-response.json` beside it.

1. Resolve the plugin root as the first existing directory of `$BARD_PLUGIN_ROOT`,
   `$OPENHANDS_PROJECT_DIR/plugins/bard`, `$HOME/.agents/plugins/bard`,
   `$HOME/.openhands/plugins/installed/bard`, then run:

   ```bash
   python3 <plugin root>/scripts/bard_cli.py ux-inbox [--root <workspace>]
   ```

2. For each request in state `new` or `stale`: read the request file, then dispatch via
   `task` — `subagent_type="bard-cue"` for cue/earcon/sound requests,
   `subagent_type="bard"` for song requests — passing the request path and a cue or song
   output directory under `cues/<slug>/` or `songs/<slug>/`.
3. After the work lands, record a decision and an impression for the request
   (`record decision`, `record impression`), then answer it:

   ```bash
   python3 <plugin root>/scripts/bard_cli.py ux-respond --json - <<'JSON'
   {"request": "<path>.ux-request.json", "status": "done",
    "reason": "<why this response>",
    "artifacts": ["cues/<slug>/cues.json"],
    "gate_verdicts": [{"gate": "cue-set-contract", "verdict": "pass"},
                       {"gate": "readback", "verdict": "pass"}],
    "decision_refs": ["<event_id>"], "impression_refs": ["<event_id>"],
    "questions_for_user": []}
   JSON
   ```

   Gate verdicts come from `render_*.py --check` (`cue-set-contract` /
   `song-proposal-contract`), the read-back inside the render (`readback`), and a vision
   review (`score-review`) when PNGs exist. `done` requires ≥1 artifact, ≥1 decision_ref and
   ≥1 impression_ref, and no fail/unknown gate verdicts — otherwise respond
   `needs_info`/`rejected`/`deferred` with a ≥20-character `reason`.
4. Report each request's state and the response paths written. Requests are advisory work
   items; nothing here gates or approves the UX contract.
