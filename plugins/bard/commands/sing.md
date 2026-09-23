---
description: Have the bard minstrel sing about this conversation and what happened in the workspace.
argument-hint: "[chronicle|praise|lament|satire|inspire|lore] [one-line subject]"
allowed-tools:
  - terminal
  - file_editor
  - task_tool_set
---

# /bard:sing

The bard sub-agent does not receive the parent's conversation history — you,
the parent, summarize the subject and pass it on. Song generation takes
minutes to tens of minutes, so make the direction visible before starting
and do not go silent mid-run.

1. Read the mode and subject from the arguments. Without a mode use
   `chronicle`; without a subject use "what happened in this conversation".
   The lyric language follows the argument or the conversation language
   (`ja`/`en`).
2. Write the following three lines in the thought of the first tool call
   and at the top of the final response (a response without a tool call
   ends the turn, so do not send them as a standalone message):

   ```text
   モード: <mode> / 言語: <ja|en> / 題材: <one line>
   出力: out/bard/<slug>/
   実行経路: task sub-agent | fallback（taskなし）
   ```

   Decide the execution path from whether `task` exists in **the tool list
   actually available in this conversation** — not from the "enable
   sub-agents" setting (if `tools` is set explicitly in the profile, `task`
   does not appear even with the setting on).

   If `task` is in the tool list, the path must be `task sub-agent` and you
   call `task` in step 5. You, the parent, must NOT read `agents/bard.md`
   and run its Stages yourself (songs handled inside the parent
   conversation were confirmed in real runs to be shorter and weaker).
   `fallback（taskなし）` may only be written when `task` is absent.
3. Create `out/bard/<slug>/`. `<slug>` is a short lowercase-and-hyphen
   name derived from the subject, suffixed with the language (e.g.
   `welcome-developer-ja`). If that directory already exists and is not
   empty, use `<slug>-2`, `<slug>-3`, … instead. Never delete or overwrite
   existing files under `out/bard/`.
4. Write `out/bard/<slug>/context.md` (in the conversation language,
   300..1500 characters). Tag each item's source with `[会話]` `[git]`
   `[file:<path>]` `[依頼]`. Do not write anything not present in the
   conversation:
   - what happened (chronological, 5..12 items; concrete file names, test
     names, error text, version numbers)
   - the roles that appeared (no personal names — use "利用者",
     "レビュアー", "CI", "別のエージェント", etc.)
   - emotional beats (where things got stuck, where they unblocked, what
     unease remains)
   - words to include in the song, words to avoid
   - when the subject is another agent's messages or artifacts, their
     summary and source (conversation id, file)

   Prefix every git command used to read the workspace with `--no-pager`,
   e.g. `git --no-pager log --oneline -n 30`. `git show` and
   `git log --format=%b` can stop in the pager and block every later
   command on the same terminal.
   If `file_editor`'s `create` returns `Parameter file_text is required`
   (or `create` fails twice in a row on the same path), do not retry
   `create`: write the file in one terminal command with a
   `cat > <path> <<'EOF'` … `EOF` heredoc and continue the stage. If the
   terminal rejects the heredoc as multiple commands, use
   `printf '%s\n' '<line>' '<line>' > <path>`. Never restart the stage
   from the beginning. Verify 300..1500 characters with
   `wc -m out/bard/<slug>/context.md`, and verify each item is tagged with
   `grep -c '\[会話\]\|\[git\]\|\[file:\|\[依頼\]' out/bard/<slug>/context.md`
   returning at least 1. If too long, shorten the chronological items
   without dropping the emotional beats or the word lists, and rewrite
   until both checks pass before calling `task`.
5. When `task` is available:

   ```text
   task(subagent_type="bard",
        description="Compose a song about this session",
        prompt="Mode: <mode>. Language: <ja|en>. Output directory: out/bard/<slug>/. Read out/bard/<slug>/context.md first, then the workspace. Subject: <subject>.")
   ```

   If `task` returns an iteration-limit/timeout error, run
   `ls out/bard/<slug>/` and immediately call `task` again with the same
   `subagent_type="bard"`, appending to the prompt:
   `Resume: the following stage files already exist: <list>. Continue from
   the first missing stage; do not rewrite existing files.` Do this at
   most twice. Only when two resumes fail (or two non-iteration/timeout
   task errors happen in a row) may you switch to the fallback path,
   stating the reason on the `実行経路` line of the final response. Do not
   ask the user whether to continue.

   Even on the fallback path you must write every stage file (`notes.md`,
   `story.md`, `lyrics.md`, `plan.md`, `song.proposal.json`, `critic.md`).
   A stage that writes nothing is treated as never having run.

   Only when `task` is absent from the tool list: read `agents/bard.md` at
   the plugin root and run its Stages 0..7 in order yourself (write each
   Stage's file, `--check` → render → critic). Run the critic as a
   separate pass by reading `<plugin root>/agents/bard-critic.md` and
   writing its observations and disposition to `<out dir>/critic.md`. The
   plugin root is the first existing directory of `$BARD_PLUGIN_ROOT`,
   `$OPENHANDS_PROJECT_DIR/plugins/bard`,
   `$HOME/.openhands/plugins/installed/bard`.
6. When you receive bard's report, display it in this order:
   First run `ls -l --time-style=full-iso out/bard/<slug>/` and confirm
   that `notes.md`, `story.md`, `lyrics.md`, `plan.md`,
   `song.proposal.json`, `song.md`, `song.abc`, `song.mid`, `song.mml`,
   `song.provenance.json`, and `critic.md` are all present. If any are
   missing, enumerate them under `Missing:` in the report — never claim
   they exist.
   `score.png` and `score-review.json` are optional advisory artifacts
   (when `abcm2ps`/`rsvg-convert` are available a vision-capable model
   inspects the score and writes its findings to score-review.json). Their
   absence is not a missing file, but list them under `Files:` when
   present.
   `critic.md` must contain a `DECISIONS` block with `APPLIED` or
   `DECLINED: <reason>` for each finding. You may report `APPLIED` only
   when `song.provenance.json` is newer than the critic.md findings (i.e.
   a re-render happened after the fix). Without a re-render, report the
   findings as `DECLINED: not re-rendered`.
   1. Title, mode, language, key/meter/tempo
   2. The complete lyrics — one Markdown line per lyric line (trailing
      hard break or a code block); do not collapse them into one paragraph
   3. `Files:` `out/bard/<slug>/song.md` (chord sheet and ABC score),
      `song.mid`, `song.mml`, `song.provenance.json`, `critic.md`
   4. `Critic:` applied findings and declined findings (one line each)
   5. The last line of the message must be exactly one of these literal
      strings: `実行経路: task sub-agent` or
      `実行経路: fallback（taskなし）` (the fallback form may append
      ` — <reason>`). It must match what you declared in step 2 and
      reflect the path actually called. Never write `fallback` when `task`
      was available; if the path changed mid-run, append the reason.
      Before sending, confirm the message's final line starts with
      `実行経路: `.

A song is an observation, not a judgment of the work's pass/fail status or
quality, and the song itself is not graded either. If asked to use an
existing song, bard writes an original one (`docs/adr/ADR-0003`).
