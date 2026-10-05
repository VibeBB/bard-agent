# Agents

All three are `task` sub-agent definitions (Markdown + YAML frontmatter); the
SDK passes `hooks:` frontmatter into each sub-conversation.

## bard

- `model: vibebb-author`; `tools: terminal, file_editor, grep, glob,
  task_tracker, task_tool_set`; `max_iteration_per_run: 120`,
  `max_budget_per_run: 6.0`; `permission_mode: never_confirm`.
- Writes songs per Stages 0–8 (see [workflow.md](workflow.md)). May dispatch
  `bard-critic` itself via `task`.
- Frontmatter hooks: `protect-song-artifacts` (pre_tool_use
  `file_editor|apply_patch|terminal`), `safety-rail` (pre_tool_use `terminal`),
  `record-vision-tool-event` (post_tool_use `inspect_image_with_vision`),
  `require-records` (session_start + stop).

## bard-cue

- `model: vibebb-author`; `tools: terminal, file_editor, grep, glob,
  task_tracker`; `max_iteration_per_run: 60`, `max_budget_per_run: 3.0`;
  `permission_mode: never_confirm`.
- Designs `bard_cue_set` cue sets; answers ux-creator `*.ux-request.json`
  liaison requests. No `task` tool.
- Frontmatter hooks: `protect-song-artifacts`, `safety-rail`,
  `require-records` (session_start + stop).

## bard-critic

- `model: vibebb-review`; `tools: terminal, grep, glob` (read-only — no file
  editor, no task); `max_iteration_per_run: 24`, `max_budget_per_run: 1.0`.
- Reviews `song.proposal.json`/`song.md`/context for prosody, singability,
  imagery, mode fit, form, originality. Returns findings only; never rewrites
  the song. Writes no VRP records — its reply names which findings warrant a
  decision record and supplies the impression text for bard to record.
- Frontmatter hooks: `protect-song-artifacts`, `safety-rail` only.
