# bard-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/bard-agent)

Part of the [VibeBB](https://github.com/VibeBB) agent family:
[bard-agent](https://github.com/VibeBB/bard-agent) ·
[electrical-circuit-agent](https://github.com/VibeBB/electrical-circuit-agent) ·
[mechanical-agent](https://github.com/VibeBB/mechanical-agent) ·
[wire-agent](https://github.com/VibeBB/wire-agent)

**English** | [日本語](#日本語)

<a id="english"></a>
## English

`bard-agent` adds the **bard** minstrel to OpenHands (Agent Canvas). It turns a
development workspace, the user's conversation, and conversations with other
agents into original lyrics and melodies, then exports lyrics, ABC notation,
MIDI, and MML.

> Target: OpenHands Software Agent SDK v1.49.5 / OpenHands Agent Canvas

## What it can do

| Mode | What it sings |
| --- | --- |
| `chronicle` | Turn what happened into a chronological epic |
| `praise` | Praise a success, release, or merge |
| `lament` | Write a lament for a lost feature or failure |
| `satire` | Satirize bugs or technical debt (never real people or organizations) |
| `inspire` | Sing a short song that encourages the next step |
| `lore` | Tell the design history preserved in a README or ADR as lore |

Lyrics follow the language of the conversation (Japanese or English). Outputs
are written to `songs/<slug>/`:

- `song.md` — one-page Agent Canvas preview (lyrics, compact chord lines, and
  the complete ABC score)
- `song.abc` — ABC 2.1
- `song.mid` — Standard MIDI File format 1 (melody and accompaniment)
- `song.mml` — `bard-mml 0.1`
- `song.proposal.json` / `song.provenance.json` — the canonical song proposal
  and its provenance
- `notes.md` / `story.md` / `lyrics.md` / `plan.md` — intermediate songwriting
  files for each stage
- `context.md` / `critic.md` — the parent's conversation summary and the
  critic's observations and disposition
- `score.png` / `score-review.json` — optional visual check output (advisory;
  rendered inside the pinned `bard-tools` docker image when docker and the
  image pin are available — see [docker/README.md](docker/README.md))

The proposal contract is schema 0.3. Repeated sections can use `melody_from`
to copy chords and melody from an earlier section, keeping proposal JSON short.
Use `--check` when you only want validation; it writes nothing and lists the
reasons.

## How it works

```text
User ── /bard:sing ──▶ parent agent
                         ├─ summarize the conversation in context.md
                         └─ task(subagent_type="bard") ──▶ bard
                                                            ├─ read context.md and the workspace (git log, README, ADRs)
                                                            ├─ write song.proposal.json
                                                            ├─ validate and render with render_song.py (fail-closed)
                                                            └─ task(subagent_type="bard-critic") ──▶ observations (no verdict authority)
```

- A `task` sub-agent does not receive the parent's conversation history, so the
  parent summarizes it in `context.md` while bard reads the workspace itself.
- The proposal JSON is the sole source of truth. ABC, MIDI, and MML are derived
  deterministically by a Python-standard-library-only script and read back for
  equality checks ([contract](docs/song-proposal-contract.md)).
- Quoting or adapting existing songs, imitating real artists, and mocking real
  people are prohibited. Rendering requires every `originality` declaration to
  be `true`.

Design decisions are recorded in [docs/adr/](docs/adr/) — see the index in
[docs/README.md](docs/README.md).

## Installation via Agent Canvas WebGUI

From Agent Canvas (the OpenHands web GUI), install the plugin from a GitHub
release tag. The following procedure was verified with OpenHands agent-server
1.46-series releases.

1. Open **Customize** in the left sidebar and select the **Plugins** tab.
2. Click **Add plugin**, enter the following three values, and click
   **Install**.

   | Field | Value |
   | --- | --- |
   | Source | `github:VibeBB/bard-agent` |
   | Ref | `v1.0.0` / the latest tag from [Releases](https://github.com/VibeBB/bard-agent/releases) |
   | Path | `plugins/bard` |

3. Installation is complete when **bard** appears as enabled. The plugin is
   installed at `~/.openhands/plugins/installed/bard/`, with `agents/`,
   `commands/`, `hooks/`, and `skills/` in place. Starting a new conversation loads the
   `bard-songcraft` and `bard-render` skills and the `/bard:sing` command
   automatically (the conversation shows “skills ready” immediately after it
   starts).
4. To use sub-agents, optionally enable `enable_sub_agents` in Agent Canvas
   settings. The plugin also works with it disabled (see the fallback below).

For update caveats (Agent Canvas caches plugin sources per source string),
sub-agent activation notes, and API-based install verification, see
[docs/operations.md](docs/operations.md).

For a non-GUI installation, place `plugins/bard` in the project directory
(`$OPENHANDS_PROJECT_DIR/plugins/bard`), point `BARD_PLUGIN_ROOT` at the plugin
directory, or use the SDK:

```python
PluginSource("github:VibeBB/bard-agent", ref="v1.0.0", repo_path="plugins/bard")
```

## Usage (Agent Canvas WebGUI)

1. Open a **new chat** and select the workspace (repository) to sing about.
2. Enter `/bard:sing`, followed by a mode and subject:

   Plugin commands may not appear in the composer's `/` autocomplete palette; type
   `/bard:sing …` as plain text and send it — it dispatches the same way.

   ```text
   /bard:sing chronicle Read this workspace's git history and README and sing its development as an epic.
   /bard:sing praise today's release
   /bard:sing satire flaky tests
   ```

   The default mode is `chronicle`; without a subject, the subject is “what
   happened in this conversation”. Lyrics use the language of the argument or
   conversation (`ja`/`en`).
3. The parent agent summarizes the conversation in
   `songs/<slug>/context.md`. bard reads the workspace (`git log`, README,
   and ADRs), writes the song, and validates and renders it with
   `render_song.py`. Completion usually takes 10–15 minutes in practice,
   depending on the LLM and workspace size.
4. When complete, the conversation displays the title, mode, key, time
   signature, tempo, full lyrics, and a list of output files. Outputs are in
   `songs/<slug>/`; open them from **Show panel** in the upper right or read
   `song.md` in Markdown preview. Play `song.mid` with any MIDI player and
   render or play `song.abc` with an ABC tool such as abcjs.

When `enable_sub_agents` is disabled (the default), `/bard:sing` briefly says
so, then the parent agent follows `agents/bard.md` itself; the critic reads
`agents/bard-critic.md` and performs a separate self-critique (recorded in
`critic.md`). When enabled, bard and bard-critic run as `task` sub-agents. Both
paths produce and validate the same outputs.

In this project, songs are observations, not verdicts about the pass/fail status
or quality of the work. If asked to use an existing song, bard writes an
original one.

## Layout

```text
plugins/bard/
├── .plugin/plugin.json
├── agents/bard.md, bard-critic.md
├── commands/sing.md
├── hooks/                               # stop hook reporting song render status
└── skills/
    ├── bard-songcraft/SKILL.md          # songwriting decision tables and copyright contract
    └── bard-render/                     # proposal JSON validation and rendering (stdlib only)
        ├── SKILL.md
        └── scripts/render_song.py
docs/                                    # contract, ADRs, research, and the docs index
tests/                                   # renderer and plugin-asset checks
```

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q
```

Try the renderer directly:

```bash
uv run python plugins/bard/skills/bard-render/scripts/render_song.py \
    --proposal tests/fixtures/valid_en.json --out-dir songs/example
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor setup and
[AGENTS.md](AGENTS.md) for the working contract. The release process is
documented in [docs/operations.md](docs/operations.md).

## License

BSD-3-Clause ([LICENSE](LICENSE)). Provenance for generated songs is recorded
in `song.provenance.json` with `license: BSD-3-Clause`.

<a id="日本語"></a>
## 日本語

[English](#english) | **日本語**

OpenHands（Agent Canvas）に吟遊詩人 **bard** を追加するpluginです。開発中のワークスペース、
利用者との会話、他のエージェントとの会話を題材に、オリジナルの歌詞と旋律を作り、
歌詞・ABC譜・MIDI・MMLとして書き出します。

> 対象: OpenHands Software Agent SDK v1.49.5 / OpenHands Agent Canvas

## できること

| モード | 歌う内容 |
| --- | --- |
| `chronicle` | 起きたことを時系列で叙事詩に |
| `praise` | 成功・リリース・mergeの称賛 |
| `lament` | 失われた機能や失敗の哀歌 |
| `satire` | バグや技術的負債への風刺（実在の人物・団体は対象にしない） |
| `inspire` | 次の一歩を鼓舞する短い歌 |
| `lore` | READMEやADRに残る設計の由来を伝承として |

歌詞の言語は会話に合わせて日本語または英語。出力は`songs/<slug>/`に

- `song.md` — Agent Canvasのpreviewで読む一枚（歌詞・コンパクトなコード行・ABC譜全文）
- `song.abc` — ABC 2.1
- `song.mid` — Standard MIDI File format 1（旋律 + 伴奏）
- `song.mml` — `bard-mml 0.1`
- `song.proposal.json` / `song.provenance.json` — 歌の正となる提案と来歴
- `notes.md` / `story.md` / `lyrics.md` / `plan.md` — 作詞過程の中間ファイル（stage別）
- `context.md` / `critic.md` — 親が書いた会話の要約と、critic の所見・採否
- `score.png` / `score-review.json` — 任意の譜面目視チェック出力（advisory。
  digest 固定の `bard-tools` docker image 内でレンダリングされます。docker と
  image pin が利用できる場合のみ — [docker/README.md](docker/README.md) 参照）

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
  ワークスペースを自ら読む二本立てにしています。
- 歌の唯一の正は提案JSONで、ABC・MIDI・MMLはPython標準ライブラリだけのscriptが決定論的に
  導出し、読み戻して一致を確認します（[契約](docs/song-proposal-contract.md)）。
- 既存楽曲の引用・翻案、実在アーティストの模倣、実在人物への嘲笑は禁止し、`originality`
  宣言がすべて`true`でなければ描画しません。

設計の決定は [docs/adr/](docs/adr/) に記録しています — 索引は
[docs/README.md](docs/README.md) を参照してください。

## インストール（Agent Canvas WebGUI）

Agent Canvas（OpenHands のWeb GUI）からGitHubのリリースタグを指定して導入します。
以下は実機（OpenHands agent-server 1.46 系）で確認した手順です。

1. 左サイドバーの **カスタマイズ**（Customize）を開き、**Plugins** タブを選びます。
2. **プラグインを追加** を押し、次の3項目を入力して **インストール** を押します。

   | 項目 | 値 |
   | --- | --- |
   | ソース（source） | `github:VibeBB/bard-agent` |
   | リファレンス（ref） | `v1.0.0`（[Releases](https://github.com/VibeBB/bard-agent/releases) の最新タグ） |
   | パス（path） | `plugins/bard` |

3. 一覧に **bard** が「有効」で表示されれば導入完了です。導入先は
   `~/.openhands/plugins/installed/bard/` で、`agents/`・`commands/`・`hooks/`・`skills/` がそのまま置かれます。
   会話を新規作成すると `bard-songcraft`・`bard-render` Skill と `/bard:sing` command が自動で
   読み込まれます（会話開始直後に「スキル準備完了」と表示されます）。
4. （任意）sub-agent を使う場合は Agent Canvas の設定で `enable_sub_agents` を有効にします。
   無効のままでも動きます（後述の fallback）。

更新時の注意（Agent Canvas は source 文字列ごとに plugin を cache します）、sub-agent
有効化の挙動、API での導入確認は [docs/operations.md](docs/operations.md) を参照してください。

GUIを使わない場合は、プロジェクト直下に `plugins/bard` を置く（`$OPENHANDS_PROJECT_DIR/plugins/bard`）か、
環境変数 `BARD_PLUGIN_ROOT` で plugin ディレクトリを指すか、SDKで
`PluginSource("github:VibeBB/bard-agent", ref="v1.0.0", repo_path="plugins/bard")` を使います。

## 使い方（Agent Canvas WebGUI）

1. **新規チャット** を開き、歌わせたいワークスペース（リポジトリ）を選びます。
2. 入力欄に `/bard:sing` に続けてモードと題材を書いて送ります。

   プラグインのコマンドが作曲欄の `/` オートコンプリートパレットに表示されないことがあります。
   `/bard:sing …` をプレーンテキストで入力して送信すれば、同じようにdispatchされます。

   ```text
   /bard:sing chronicle このワークスペースの開発の歩みを、gitの履歴とREADMEを読んで叙事詩として歌ってください。
   /bard:sing praise 今日のリリース
   /bard:sing satire flakyなテスト
   ```

   モードを省くと `chronicle`、題材を省くと「この会話で起きたこと」になります。歌詞の言語は
   引数か会話の言語（`ja`/`en`）に合わせます。
3. 親エージェントが会話を `songs/<slug>/context.md` に要約し、bard が workspace（`git log`、README、
   ADR）を読んで作詞作曲、`render_song.py` で検証・描画します。実機では完了までおおむね 10〜15 分
   （LLMとworkspaceの規模に依存）でした。
4. 完了すると会話に題名・モード・調・拍子・テンポ・歌詞全文と、書き出したファイルの一覧が表示されます。
   成果物はワークスペース内の `songs/<slug>/` にあり、右上の **パネルを表示** からファイルを
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
├── hooks/                               # 歌の描画状態を報告する stop hook
└── skills/
    ├── bard-songcraft/SKILL.md          # 作詞作曲の決定表と著作権契約
    └── bard-render/                     # 提案JSONの検証と描画（stdlibのみ）
        ├── SKILL.md
        └── scripts/render_song.py
docs/                                    # 契約、ADR、リサーチ、ドキュメント索引
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
    --proposal tests/fixtures/valid_en.json --out-dir songs/example
```

貢献者向けのセットアップは [CONTRIBUTING.md](CONTRIBUTING.md)、作業契約は
[AGENTS.md](AGENTS.md) を参照してください。リリース手順は
[docs/operations.md](docs/operations.md) に記載しています。

## ライセンス

BSD-3-Clause（[LICENSE](LICENSE)）。生成された歌の来歴は`song.provenance.json`に
`license: BSD-3-Clause`として記録されます。
