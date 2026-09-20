# bard-agent

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

- `song.md` — Agent Canvasのpreviewで読む一枚（歌詞・コード表・ABC譜全文）
- `song.abc` — ABC 2.1
- `song.mid` — Standard MIDI File format 1（旋律 + 伴奏）
- `song.mml` — `bard-mml 0.1`
- `song.proposal.json` / `song.provenance.json` — 歌の正となる提案と来歴

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

## インストール（Agent Canvas）

1. Agent Canvasの設定で sub-agent（`enable_sub_agents`）を有効にします。
2. pluginを導入します。Agent Canvasのplugin導線から本リポジトリの`plugins/bard`を指定するか、
   プロジェクト直下に`plugins/bard`として置きます（`$OPENHANDS_PROJECT_DIR/plugins/bard`）。
   別の場所に置く場合は環境変数`BARD_PLUGIN_ROOT`でpluginのディレクトリを指します。
   リリース済みタグから直接導入する場合は`github:uist1idrju3i/bard-agent/plugins/bard#v0.1.0`を
   指定します。SDK経由なら`PluginSource("github:uist1idrju3i/bard-agent", ref="v0.1.0", repo_path="plugins/bard")`と同じ指定です。
3. 会話で `/bard:sing chronicle 今日のCI修正` のように呼びます。モードを省くと`chronicle`。

sub-agentを有効にできない環境では、`/bard:sing`が親エージェント自身に
`agents/bard.md`の手順を実行させます（fallback）。

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
`release` workflowを`workflow_dispatch`で手動起動し、`version`入力に`0.1.0`のような
v無しの版を入れます。main上でのみ動き、以下の順で進みます。

1. **check-version** — `pyproject.toml`、`plugins/bard/.plugin/plugin.json`、入力versionの
   三者一致と`v<version>`タグの未存在を検査し、対象SHAを確定します。
2. **verify** — 通常CI（lint・type・test）を再利用workflowとして実行します。
3. **install-smoke** — `install_plugin`で対象SHAから実際に導入し、agent/skill/commandの
   一覧を検査します。
4. **release** — pluginと楽譜サンプルのzipを作り、`gh release create`でタグ`v<version>`と
   Releaseを作成します。

途中で失敗した場合はタグもReleaseも作られません。

## ライセンス

BSD-3-Clause（[LICENSE](LICENSE)）。生成された歌の来歴は`song.provenance.json`に
`license: BSD-3-Clause`として記録されます。
