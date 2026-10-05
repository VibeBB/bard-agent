# Skills

Skills are Markdown with YAML frontmatter under `plugins/bard/skills/`.
Keyword `triggers:` skills are model-invocable; a `paths:` glob list makes a
skill a path-triggered rule injected when a matching file is touched. The two
mechanisms are exclusive.

| Skill | Version | Kind | Governs |
| --- | --- | --- | --- |
| `bard-songcraft` | 1.1.0 | triggers (`song`, `ballad`, `lyrics`, `melody`, `jingle`, `chant`, `lament`, `bard`) | Song modes, keys/modes, chord progressions, meter/rhythm, melody rules, lyric craft (EN/JA), the originality contract |
| `bard-cuecraft` | 1.1.0 | triggers (`earcon`, `product sound`, `startup sound`, `completion sound`, `warning sound`, `beep`, `buzzer`, `chime`) | Cue purpose table, device pitch ranges, duration/loop limits, distinguishability rules (opening two notes now enforced by `render_cues.py`), originality |
| `bard-render` | 1.1.0 | triggers (`render song`, `song.proposal.json`, `abc notation`, `midi`, `mml`, `bard-render`, `歌を描画`, `ABC譜`) | Proposal contract summary, `render_song.py`/`render_cues.py`/`render_score_png.py`/`validate_score_review.py`/`lint_score.py` usage, cue-set contract summary, the pinned tools image |
| `bard-proposal-rules` | 0.1.0 | paths (`**/*.proposal.json`) | Injects contract + originality reminders whenever a `*.proposal.json` is opened or written |

Version bumps: `scripts/bump_version.py` keeps `plugin.json`, `pyproject.toml`
and all three keyword-skill SKILL.md files (`bard-render`, `bard-songcraft`,
`bard-cuecraft`) in lockstep.
