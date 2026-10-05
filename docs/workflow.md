# Workflow

## Song stages (`agents/bard.md`, Stages 0–8)

Each stage writes its file in the output directory (`songs/<slug>/`) before the
next begins; a stage that writes nothing did not happen.

| Stage | What happens | Writes | Records left |
| --- | --- | --- | --- |
| 0 — Plugin root, skills, contract | Resolves the 4-root plugin path, reads `bard-songcraft` + `bard-render` SKILL.md | — | — |
| 1 — Gather | Reads `context.md`, `git log`, README/ADRs; tags each fact `[会話]`/`[file:]`/`[git]` | `notes.md` | decision (which facts to sing), impression |
| 2 — Story | Arc + section list from the mode tables | `story.md` | decision (form/arc), impression |
| 3 — Lyrics | Lyrics per section; counts lyric units per line | `lyrics.md` | impression |
| 4 — Harmony/rhythm | Key/mode/meter/bpm/progressions per section | `plan.md` | decision (mode/key/meter/tempo), impression |
| 5 — Melody + proposal | Writes the proposal JSON from the earlier files | `song.proposal.json` | decision (prosody/melody choices), impression |
| 6 — Render | `render_song.py --check` then render; `--svg` rasterize `song.contour.svg` (exit 4 = docker/pin missing → advisory skip) | `song.abc`, `song.mid`, `song.mml`, `song.md`, `song.contour.svg`, `song.provenance.json`, `song.contour.png` | impression; vision review of `song.contour.png` (checklist `melody-contour`) |
| 7 — Critic | `task(subagent_type="bard-critic")`, apply/decline findings | `critic.md` | decision per applied/declined finding, impression |
| 8 — Score visual check | `render_score_png.py --abc`, view `score.png`, write `score-review.json` | `score.png`, `score-review.json` | vision review `score-engraving` (via `--record`) |
| finish | — | — | directory impression; `record status` |

## Cue stages (`agents/bard-cue.md`)

1. **read** — `context.md` plus the optional `*.ux-request.json`.
2. **design** — contour, pitch band, rhythm, tempo per cue from the cuecraft
   tables; opening notes must differ between cues. → `design.md`.
3. **cue set** — `cues.proposal.json` (`bard_cue_set` 0.1).
4. **check** — `render_cues.py --cues … --out-dir … --check` (exit 2 = reject,
   fix only listed reasons).
5. **render** — same command without `--check`: `cue-<id>.mid`,
   `cue-<id>.mml`, `cues.json`, `cues.md`, `cues.provenance.json`,
   `cues.timeline.svg`; rasterize to `cues.timeline.png` (advisory skip on
   exit 4) and view it.

Records at each stage: decisions for contour-per-purpose, pitch band vs device,
distinctiveness, loop; impressions per stage file; a `cue-timeline` vision
review; final directory impression + `record status`.
