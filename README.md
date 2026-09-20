# bard-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/uist1idrju3i/bard-agent)

OpenHands（Agent Canvas）に吟遊詩人 **bard** を追加するpluginです。開発中のワークスペース、
利用者との会話、他のエージェントとの会話を題材に、オリジナルの歌詞と旋律を作り、
歌詞・ABC譜・MIDI・MMLとして書き出します。

> 対象: OpenHands Software Agent SDK v1.49.2 / OpenHands Agent Canvas

## できること

| モード | 歌う内容 |
| --- | --- |
| `chronicle` | 起きたことを時系列で叙事詩に |
| `praise` | 成功・リリース・mergeの称賛 |
| `lament` | 失われた機能や失敗の哀歌 |
| `satire` | バグや技術的負債への風刺（実在の人物・団体は対象にしない） |
| `inspire` | 次の一歩を鼓舞する短い歌 |
| `lore` | READMEやADRに残る設計の由来を伝承として |

歌詞の言語は会話に合わせて日本語または英語。出力は`out/bard/<slug>/`に

- `song.md` — Agent Canvasのpreviewで読む一枚（歌詞・コンパクトなコード行・ABC譜全文）
- `song.abc` — ABC 2.1
- `song.mid` — Standard MIDI File format 1（旋律 + 伴奏）
- `song.mml` — `bard-mml 0.1`
- `song.proposal.json` / `song.provenance.json` — 歌の正となる提案と来歴
- `notes.md` / `story.md` / `lyrics.md` / `plan.md` — 作詞過程の中間ファイル（stage別）
- `context.md` / `critic.md` — 親が書いた会話の要約と、critic の所見・採否

提案契約はschema 0.3。反復するセクションは`melody_from`で前のセクションのコードと
メロディを複製できるので、提案JSONが短くなります。検証だけしたいときは`--check`を
使います（何も書かずに理由を列挙）。

## 仕組み

```text
利用者 ── /bard:sing ──▶ 親エージェント
                          ├─ context.md に会話を要約
                          └─ task(subagent_type="bard") ──▶ bard
                                                             ├─ context.md と workspace（git log、README、ADR）を読む
                                                             ├─ song.proposal.json を書く
                                                             ├─ render_song.py で検証・描画（fail-closed）
                                                             └─ task(subagent_type="bard-critic") ──▶ 所見（合否権限なし）
```

- `task` sub-agentは親の会話履歴を受け取らないため、親が`context.md`へ要約し、bardが
  ワークスペースを自ら読む二本立てにしています（[ADR-0001](docs/adr/ADR-0001-task-subagent-plugin.md)）。
- 歌の唯一の正は提案JSONで、ABC・MIDI・MMLはPython標準ライブラリだけのscriptが決定論的に
  導出し、読み戻して一致を確認します（[契約](docs/song-proposal-contract.md)、
  [ADR-0002](docs/adr/ADR-0002-song-proposal-contract.md)）。
- 既存楽曲の引用・翻案、実在アーティストの模倣、実在人物への嘲笑は禁止し、`originality`
  宣言がすべて`true`でなければ描画しません（[ADR-0003](docs/adr/ADR-0003-copyright-and-license-policy.md)）。

## インストール（Agent Canvas WebGUI）

Agent Canvas（OpenHands のWeb GUI）からGitHubのリリースタグを指定して導入します。
以下は実機（OpenHands agent-server 1.46 系）で確認した手順です。

1. 左サイドバーの **カスタマイズ**（Customize）を開き、**Plugins** タブを選びます。
2. **プラグインを追加** を押し、次の3項目を入力して **インストール** を押します。

   | 項目 | 値 |
   | --- | --- |
   | ソース（source） | `github:uist1idrju3i/bard-agent` |
   | リファレンス（ref） | `v<最新版>`（[Releases](https://github.com/uist1idrju3i/bard-agent/releases) の最新タグ） |
   | パス（path） | `plugins/bard` |

3. 一覧に **bard** が「有効」で表示されれば導入完了です。導入先は
   `~/.openhands/plugins/installed/bard/` で、`agents/`・`commands/`・`skills/` がそのまま置かれます。
   会話を新規作成すると `bard-songcraft`・`bard-render` Skill と `/bard:sing` command が自動で
   読み込まれます（会話開始直後に「スキル準備完了」と表示されます）。
4. （任意）sub-agent を使う場合は Agent Canvas の設定で `enable_sub_agents` を有効にします。
   無効のままでも動きます（後述の fallback）。

### 更新時の注意

Agent Canvasはsource文字列ごとにplugin repositoryをcacheします（tagのみを取得する
refspecのため、同じsource文字列で新しいrefを指定しても古い`resolved_ref`が残ることがあります）。
1.46.0で確認した回避策: いったんアンインストールしてから、大文字小文字を変えたsource表記
（例: `github:UIST1IDRJU3I/bard-agent`）または完全な`https://github.com/uist1idrju3i/bard-agent.git`
URLで再追加し、plugin詳細の`resolved_ref`が新しいタグのSHAと一致することを確認してください。

### sub-agentが有効にならない場合

1.46.0では agent profileで"sub-agents"を有効にしても会話で`task`が使えないケースを確認しています
（settings APIは引き続き`enable_sub_agents=false`を返す）。この場合`/bard:sing`はfallback経路で
動き、返信末尾の`実行経路:`にその旨が出ます。実機ではfallbackで約34分かかった実績があります。

実機確認済みの環境は OpenHands 1.46.0 です（SDKの対象版 1.49.2 とは別の系統）。fallback経路は
実機で確認済み、task経路はまだ未検証です。

補足: SDK 1.49.2 の `AgentSettings.create_agent` は profile の `tools` が `None`（未指定）の
ときだけ `enable_sub_agents` で TaskToolSet を追加します（ソース: `openhands-sdk/openhands/sdk/settings/model.py`）。
profile で `tools` を明示していると ON でも `task` が出ません。対処: `tools` を未指定に戻すか、
`task_tool_set` を明示追加してください。1.46.0 で同じ挙動かは未確認です。

導入状態はAPIでも確認できます（`X-Session-API-Key` が必要）。`resolved_ref` がタグの
commit SHA と一致していれば、意図した版が入っています。

```bash
curl -sS -H "X-Session-API-Key: $KEY" http://127.0.0.1:8000/api/plugins/installed
```

GUIを使わない場合は、プロジェクト直下に `plugins/bard` を置く（`$OPENHANDS_PROJECT_DIR/plugins/bard`）か、
環境変数 `BARD_PLUGIN_ROOT` で plugin ディレクトリを指すか、SDKで
`PluginSource("github:uist1idrju3i/bard-agent", ref="v0.1.0", repo_path="plugins/bard")` を使います。

## 使い方（Agent Canvas WebGUI）

1. **新規チャット** を開き、歌わせたいワークスペース（リポジトリ）を選びます。
2. 入力欄に `/bard:sing` に続けてモードと題材を書いて送ります。

   ```text
   /bard:sing chronicle このワークスペースの開発の歩みを、gitの履歴とREADMEを読んで叙事詩として歌ってください。
   /bard:sing praise 今日のリリース
   /bard:sing satire flakyなテスト
   ```

   モードを省くと `chronicle`、題材を省くと「この会話で起きたこと」になります。歌詞の言語は
   引数か会話の言語（`ja`/`en`）に合わせます。
3. 親エージェントが会話を `out/bard/<slug>/context.md` に要約し、bard が workspace（`git log`、README、
   ADR）を読んで作詞作曲、`render_song.py` で検証・描画します。実機では完了までおおむね 10〜15 分
   （LLMとworkspaceの規模に依存）でした。
4. 完了すると会話に題名・モード・調・拍子・テンポ・歌詞全文と、書き出したファイルの一覧が表示されます。
   成果物はワークスペース内の `out/bard/<slug>/` にあり、右上の **パネルを表示** からファイルを
   開くか、`song.md` を Markdown preview で読みます。`song.mid` は任意のMIDIプレイヤー、`song.abc` は
   abcjs 等の ABC 描画ツールで再生・表示できます。

`enable_sub_agents` が無効（既定）の環境では、`/bard:sing` がその旨を一言伝えたうえで親エージェント
自身が `agents/bard.md` の手順を実行し、critic も `agents/bard-critic.md` を読んで別パスとして
自己批評します（所見は `critic.md`）。有効な環境では bard と bard-critic が `task` sub-agent として
動きます。どちらの経路でも成果物と検証は同じです。

歌は観測物で、作業の合否や品質の判定ではありません。既存楽曲の使用を頼まれても bard は
オリジナルを書きます。

## 構成

```text
plugins/bard/
├── .plugin/plugin.json
├── agents/bard.md, bard-critic.md
├── commands/sing.md
└── skills/
    ├── bard-songcraft/SKILL.md          # 作詞作曲の決定表と著作権契約
    └── bard-render/                     # 提案JSONの検証と描画（stdlibのみ）
        ├── SKILL.md
        └── scripts/render_song.py
docs/                                    # 契約、ADR、リサーチ
tests/                                   # 描画scriptとplugin資材の検査
```

## 開発

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q
```

描画scriptを直接試す:

```bash
uv run python plugins/bard/skills/bard-render/scripts/render_song.py \
    --proposal tests/fixtures/valid_en.json --out-dir out/bard/example
```

作業契約は[AGENTS.md](AGENTS.md)を参照してください。

## リリース

配布はgit tagで行います（[ADR-0004](docs/adr/ADR-0004-ci-cd-release-by-tag.md)）。
`release` workflowを`workflow_dispatch`で手動起動します。`bump`入力（patch/minor/major、
既定patch）か`version`入力（明示的な`X.Y.Z`上書き）を選ぶだけで版は自動決定されます。
main上でのみ動き、以下の順で進みます。

1. **bump-version** — `scripts/bump_version.py`が`plugins/bard/.plugin/plugin.json`、
   `pyproject.toml`、両SKILL.md、`uv.lock`の版を整合確認した上で新しい版を書き込み、
   `v<version>`タグの未存在を検査してからmainへcommitします。
2. **verify** — 通常CI（lint・type・test）を再利用workflowとして実行します。
3. **install-smoke** — `install_plugin`で対象SHAから実際に導入し、agent/skill/commandの
   一覧を検査します。
4. **release** — pluginと楽譜サンプルのzipを作り、`gh release create`でタグ`v<version>`と
   Releaseを作成します。

途中で失敗した場合はタグもReleaseも作られません。

## ライセンス

BSD-3-Clause（[LICENSE](LICENSE)）。生成された歌の来歴は`song.provenance.json`に
`license: BSD-3-Clause`として記録されます。
