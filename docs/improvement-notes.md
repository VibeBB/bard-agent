# Improvement notes

Findings and fixes from the VRP/vision/liaison refactor (see ADR-0013).

## Fixed in this change

- **Plugin-root resolver drift** — `protect-song-artifacts` and several prompt
  texts used a 3-root chain missing `~/.agents/plugins/bard`; every hook
  command and doc now uses the same 4 roots.
- **`bump_version.py` missed `bard-cuecraft/SKILL.md`** — added, with tests.
- **`render_song.py` docstring** said schema 0.2; corrected to 0.3 (0.2
  accepted). `docker/README.md` claimed a 30-minute pin wait; corrected to 15.
- **Score-review summary was prompt-grade** (240 chars / 2 sentences);
  now shares the VRP impression rule (≥400 chars, ≥3 sentences) and can append
  the matching vision review via `--record`.
- **No melody/cue visuals** — added deterministic `song.contour.svg` and
  `cues.timeline.svg` projections plus `render_score_png.py --svg` rasterize
  inside the pinned image.
- **Cue distinctiveness was prompt-only** — `render_cues.py` now rejects two
  cues sharing their first two sounded notes (pitch + beats).
- **No records at all** — VRP v1 ported byte-for-byte (shared hooks) with a
  stdlib writer (`bard_records.py`) parity-tested against wire's writer.
- **No liaison handling** — SLP v2 `ux-inbox`/`ux-respond` implemented with
  all refusal rules; `bard_doctor` surfaces inbox counts.

## Open items

- Host-python scripts live outside the pinned image: the Docker-only rule is
  partial by design (the `bard-tools` image carries no python; only
  `abcm2ps`/`rsvg-convert` run inside it).
- Vision review of sister-produced images is prompt-driven only — nothing
  auto-watches `*.ux.json` attachments or inbox assets.
- No audio-level (listening) review of MIDI — only visual proxies
  (score/contour/timeline PNGs).
- `bard-critic` cannot see images itself (no vision tool); its review is
  text-only and bard records its impressions.
- Liaison is pull-only: no MCP push/notify; requests surface at session start
  (doctor line) and via `/bard:inbox`.
- Parity with wire's VRP is pinned only by hard-coded constants in
  `tests/test_records.py`; a drifted wire schema would not be caught until
  the constants are regenerated.
