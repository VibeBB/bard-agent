---
description: 吟遊詩人bardにこの会話とワークスペースの出来事を歌わせる。
argument-hint: "[chronicle|praise|lament|satire|inspire|lore] [題材の一言]"
allowed-tools:
  - terminal
  - file_editor
  - task_tool_set
---

# /bard:sing

bard sub-agentは親の会話履歴を受け取らない。親であるあなたが題材を要約して渡す。

1. 引数からモードと題材を読む。モードが無ければ`chronicle`、題材が無ければ「この会話で
   起きたこと」とする。歌詞の言語は引数か会話の言語に合わせる（`ja`/`en`）。
2. `out/bard/<slug>/`を作る。`<slug>`は題材から作る英小文字とハイフンの短い名前。
3. `out/bard/<slug>/context.md`へ次を書く（会話の言語で、300..1500字）:
   - 何が起きたか（時系列、5..12項目。具体的なファイル名・テスト名・エラー文を含める）
   - 登場した役割（人名は書かず「利用者」「レビュアー」「CI」「別のエージェント」等）
   - 感情の起伏（詰まった所、抜けた所、まだ残っている不安）
   - 歌に入れてほしい語、入れてほしくない語
4. `task`が使える場合:

   ```text
   task(subagent_type="bard",
        description="Compose a song about this session",
        prompt="Mode: <mode>. Language: <ja|en>. Output directory: out/bard/<slug>/. Read out/bard/<slug>/context.md first, then the workspace. Subject: <題材>.")
   ```

   `task`が使えない場合（sub-agentが無効、`task_tool_set`が無い）は、そのことを
   利用者への返信（可視メッセージ）へ一言書き、plugin rootの`agents/bard.md`を読み、その手順を自分で実行する。criticも同様に
   `task`が無ければ`<plugin root>/agents/bard-critic.md`を読んで自分で別パスとして実施し、
   所見と採否を`<out dir>/critic.md`へ書く。plugin rootは
   `$BARD_PLUGIN_ROOT`、`$OPENHANDS_PROJECT_DIR/plugins/bard`、
   `$HOME/.openhands/plugins/installed/bard`の順で最初に存在するディレクトリ。
5. bardの報告を受け取ったら、題名・モード・歌詞全文を会話に表示し、`out/bard/<slug>/song.md`
   （コード表とABC譜）、`song.mid`、`song.mml`の場所を示す。歌詞は1行につきMarkdownの
   1行となるよう（行末ハードブレークかコードブロックで）表示し、一つの段落に潰さない。
   返信の末尾に`実行経路: task sub-agent`または`実行経路: fallback（taskなし）`の
   1行を必ず入れる。

歌は観測物であり、作業の合否や品質の判断ではない。既存楽曲の使用を求められても、bardは
オリジナルを書く（`docs/adr/ADR-0003`）。
