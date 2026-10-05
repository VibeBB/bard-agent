# Performance and limits

## Render budgets (host scripts)

- `render_song.py` / `render_cues.py` are pure-stdlib and fast (<1 s for the
  shipped fixtures); validation is fail-closed with `MAX_EVENTS`,
  `MAX_CUES=16`, `MAX_NOTES=16` per cue, per-purpose duration caps
  (`confirm`/`cancel` ≤300 ms, default ≤3000 ms).
- Contour SVG: `CONTOUR_PX_PER_BEAT=36`, 8 bars per row, wrapped rows; timeline
  SVG scales to `max_ms * 0.28` px wide.

## Container renders

- `docker pull` timeout: 600 s; attestation verify 120 s; `gh auth status`
  probe 15 s. `docker image inspect` precedes pull so a cached image skips it.
- Exit 4 (docker or pin missing) is an advisory skip everywhere it's invoked —
  never an error.

## Scans

- Stop hook and `ux-inbox` scan at depth ≤4 and skip `.git`, `.venv`,
  `node_modules`, `__pycache__`, `.pytest_cache`.
- `report_song_status.py` scans `songs/`/`cues/` under the same limits.

## Agent limits

| Agent | max_iteration_per_run | max_budget_per_run |
| --- | --- | --- |
| bard | 120 | 6.0 |
| bard-cue | 60 | 3.0 |
| bard-critic | 24 | 1.0 |

## Known limits

- Song/cue content is LLM-generated; identical inputs may yield different
  proposals between runs (rendered outputs are deterministic per proposal).
- `record status` prints JSON to stdout; it takes no `--json` payload flag.
- Vision review of sister-plugin images happens only when a prompt or hook
  event triggers it — there is no automatic watcher.
- MIDI outputs have no audio review step; correctness is checked by read-back
  and visual proxies only.
