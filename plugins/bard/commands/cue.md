---
description: Have the bard design original product sound cues (startup, completion, warning, …) rendered as MIDI, MML and a firmware tone table.
argument-hint: "[piezo|speaker] [product] [cue purposes or a *.ux-request.json path]"
allowed-tools:
  - terminal
  - file_editor
  - task_tool_set
---

# /bard:cue

Product sound cues are short functional sounds, not songs. The bard-cue sub-agent does not
receive the parent's conversation history — you summarize the request and pass it on.

1. Read the device (`piezo` by default), the product name, and the request from the arguments.
   The request is either a `*.ux-request.json` path (from ux-creator, `target_agent: bard`) or
   a list of purposes such as `startup completion warning`. Without purposes use
   `startup completion warning`.
2. Create `cues/<slug>/` where `<slug>` is the lowercase-and-hyphen product name. If it exists
   and is not empty, use `<slug>-2`, `<slug>-3`, … Never delete or overwrite files under
   `cues/`.
3. Write `cues/<slug>/context.md` (100..1200 characters): product, device, each requested cue
   with its trigger and meaning, the UX feedback ids when known, and sounds to avoid. Tag each
   item `[会話]`, `[file:<path>]`, or `[依頼]`. Write nothing that is not in the conversation or
   the files.
4. If `task` is in the tool list actually available in this conversation:

   ```text
   task(subagent_type="bard-cue",
        description="Design product sound cues",
        prompt="Device: <piezo|speaker>. Product: <name>. Output directory: cues/<slug>/. Read cues/<slug>/context.md first<, then <ux-request path>>.")
   ```

   Only when `task` is absent, read `agents/bard-cue.md` at the plugin root and run its stages
   yourself.
5. Run `ls cues/<slug>/` and confirm `cues.proposal.json`, `cues.json`, `cues.md`,
   `cues.provenance.json`, and one `cue-<id>.mid` / `cue-<id>.mml` pair per cue exist. List any
   missing file under `Missing:` — never claim it exists.
6. Report the cue table from `cues.md`, the file list, and — for a ux-request — the
   `cues/<slug>/cues.json` path ux-creator imports with `ux import --from bard`.

A cue grants no pass/fail authority over the product it sounds for.
