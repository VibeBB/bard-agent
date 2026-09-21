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
歌の生成には数分から数十分かかるため、着手前に方向を可視化し、途中で黙り込まない。

1. 引数からモードと題材を読む。モードが無ければ`chronicle`、題材が無ければ「この会話で
   起きたこと」とする。歌詞の言語は引数か会話の言語に合わせる（`ja`/`en`）。
2. 最初のtool呼び出しの思考（thought）と、最終応答の先頭に、次の3行を書く（tool呼び出しを伴わない応答はターンを終えてしまうため、単独のメッセージにはしない）:

   ```text
   モード: <mode> / 言語: <ja|en> / 題材: <一言>
   出力: out/bard/<slug>/
   実行経路: task sub-agent | fallback（taskなし）
   ```

   実行経路は、**この会話で実際に使えるツール一覧**に`task`があるかで決める。設定画面の
   「sub-agentを有効化」だけでは判断しない（profileで`tools`が明示されていると、有効化しても
   `task`が出ない）。

   ツール一覧に`task`があるなら、実行経路は必ず`task sub-agent`とし、手順5で`task`を呼ぶ。
   親であるあなたが`agents/bard.md`を読んでStageを代行してはならない（親会話内で代行した歌は
   短く質が落ちることを実機で確認している）。`fallback（taskなし）`と書けるのは、ツール一覧に
   `task`が無いときだけ。
3. `out/bard/<slug>/`を作る。`<slug>`は題材から作る英小文字とハイフンの短い名前で、末尾に
   言語を付ける（例: `welcome-developer-ja`）。そのディレクトリが既に存在して空でなければ、
   `<slug>-2`、`<slug>-3`…と番号を付けた新しいディレクトリを使う。既存の`out/bard/`配下の
   ファイルは削除も上書きもしない。
4. `out/bard/<slug>/context.md`へ次を書く（会話の言語で、300..1500字）。各項目に出所を
   `[会話]` `[git]` `[file:<path>]` `[依頼]` で付ける。会話に無いことは書かない:
   - 何が起きたか（時系列、5..12項目。具体的なファイル名・テスト名・エラー文・版番号）
   - 登場した役割（人名は書かず「利用者」「レビュアー」「CI」「別のエージェント」等）
   - 感情の起伏（詰まった所、抜けた所、まだ残っている不安）
   - 歌に入れてほしい語、入れてほしくない語
   - 他のエージェントの発言や成果物を題材にする場合は、その要約と出所（会話ID・ファイル）

   ワークスペースを読むgitコマンドは`git --no-pager log --oneline -n 30`のように必ず
   `--no-pager`を付ける。`git show`や`git log --format=%b`はpagerで止まり、後続のコマンドも
   同じ端末で待たされる。
5. `task`が使える場合:

   ```text
   task(subagent_type="bard",
        description="Compose a song about this session",
        prompt="Mode: <mode>. Language: <ja|en>. Output directory: out/bard/<slug>/. Read out/bard/<slug>/context.md first, then the workspace. Subject: <題材>.")
   ```

   `task`がツール一覧に無い場合に限り、plugin rootの`agents/bard.md`を読み、そのStage 0..7を自分で順に
   実行する（各Stageのファイルを書き、`--check`→render→critic）。criticは
   `<plugin root>/agents/bard-critic.md`を読んで別パスとして実施し、所見と採否を
   `<out dir>/critic.md`へ書く。plugin rootは`$BARD_PLUGIN_ROOT`、
   `$OPENHANDS_PROJECT_DIR/plugins/bard`、`$HOME/.openhands/plugins/installed/bard`の順で
   最初に存在するディレクトリ。
6. bardの報告を受け取ったら、次の順で会話に表示する:
   1. 題名・モード・言語・調/拍子/テンポ
   2. 歌詞全文。1行につきMarkdownの1行（行末ハードブレークかコードブロック）、一つの段落に
      潰さない
   3. `Files:` `out/bard/<slug>/song.md`（コード表とABC譜）、`song.mid`、`song.mml`、
      `song.provenance.json`、`critic.md`
   4. `Critic:` 適用した所見と見送った所見（各1行）
   5. 末尾に必ず1行: `実行経路: task sub-agent` または `実行経路: fallback（taskなし）`
      （手順2で宣言したものと一致させ、実際に呼んだ経路だけを書く。`task`があるのに
      `fallback`と書いてはならない。途中で変わったら理由を添える）

歌は観測物であり、作業の合否や品質の判断ではない。歌の良し悪しも断定しない。既存楽曲の
使用を求められても、bardはオリジナルを書く（`docs/adr/ADR-0003`）。
