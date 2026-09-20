# エージェント作業契約

> 対象: OpenHands Software Agent SDK v1.49.2、Python 3.12+

本書は本リポジトリでの実装・検証・文書化の作業契約である。READMEは製品概要、
`docs/`は仕様と運用方針、`docs/adr/`は設計決定とする。
README、docs、Issue、PR、コミットメッセージは日本語、コードのコメントと識別子は英語とする。

## 目的

bardは、OpenHandsワークスペースでの作業、利用者との会話、他エージェントとの会話を題材に
作詞・作曲する吟遊詩人エージェントである。OpenHands plugin（`plugins/bard`）として配布し、
親エージェントは`task` tool（`subagent_type: bard`）で呼び出す。

## 構成

```text
plugins/bard/
├── .plugin/plugin.json
├── agents/
│   ├── bard.md               # 作詞作曲する吟遊詩人（task sub-agent）
│   └── bard-critic.md        # 批評家（合否権限なし）
├── commands/sing.md          # /bard:sing — 親に文脈収集とtask呼び出しを指示
├── skills/
│   ├── bard-songcraft/       # 作詞・作曲理論の決定表、モード別の書き方、著作権契約
│   └── bard-render/          # 提案JSONの検証とABC/MIDI/MML/歌詞/provenance描画（stdlibのみ）
│       ├── SKILL.md
│       ├── scripts/
│       └── tests/
docs/
├── song-proposal-contract.md # 提案JSON契約の正
├── adr/
└── research/
tests/                        # plugin資材の整合検査
```

## 不変条件

- 歌の唯一の正は提案JSON（`docs/song-proposal-contract.md`）であり、ABC・MIDI・MMLは
  そこから決定論的に導出する。同じ提案は byte-identical な出力を生む。
- bard、critic、Skillのいずれも作業（コード、設計、PR）の合否を判定しない。歌は観測物で
  あり、題材となった作業へ逆流させない。criticは所見を返すだけで、提案を書き換えない。
- 検証器は提案テキストだけを判定する。契約違反、parse失敗、読み戻し不一致はfail-closedとし、
  部分的な出力を書かない。
- `bard-render`のscriptはPython標準ライブラリだけを使う。音楽ライブラリのimport結合は行わず、
  GPL/AGPLコードをimport結合しない。外部ツール（FluidSynth、LilyPond等）は現時点で採用しない。
- 既存楽曲の歌詞・旋律の引用・翻案、実在アーティストの名指し模倣、実在人物への嘲笑を禁止する。
  提案の`originality`はすべて`true`でなければ描画しない。
- テキストを読み書きする経路では`encoding="utf-8"`を明示する。
- API key、token、secretをログ、入力、commitに書かない。
- 外部由来コードを含むファイルでは元のライセンス表記と帰属を維持し、自作ファイルへ無関係な
  第三者著作権表記を追加しない。

## plugin境界

- 独自tool、event、history、executor基盤は作らず、OpenHands SDKへ委譲する。
- sub-agentの呼び出しは`task`（`TaskToolSet`）だけを使う。`delegate`と`workflow`は不採用
  （ADR-0001）。
- task sub-agentは親の会話履歴を受け取らない。題材は親が`context.md`へ要約して渡し、bardが
  ワークスペース（git log、ファイル）を自ら読む二本立てとする（ADR-0001）。
- AgentDefinitionは`skills:`を宣言せず、SKILL.mdをpromptからパス参照する。plugin rootは
  `$BARD_PLUGIN_ROOT`、`$OPENHANDS_PROJECT_DIR/plugins/bard`、
  `$HOME/.openhands/plugins/installed/bard`の順で解決する。
- Skillsのtriggerは`triggers:`（KeywordTrigger）を使う。

## 検証

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q
```

Markdownのみの変更では`git diff --check`と相対リンクの確認だけでよい。
検証器には判定対象を故意に壊すnegative testを用意し、壊した提案が不合格になることを確認する。

## CI/CD

- `.github/workflows/ci.yml`はpush main・PR・`workflow_call`で動き、`verify`（Python 3.12/3.13
  matrix: ruff・format・pyright・pytest）、`independent-check`（abcm2ps必須化・楽譜PNG生成）、
  `plugin-load`（`sdk-check`グループの`openhands-sdk==1.49.2`で`Plugin.load`を検査）を行う。
- `.github/workflows/release.yml`は`workflow_dispatch`専用。`bump`入力（既定patch）または
  `version`入力の明示指定から`scripts/bump_version.py`がplugin.json・pyproject.toml・
  両SKILL.md・uv.lockの版を更新しmainへcommitし、`v<version>`タグ未存在を検査後、
  verify→install-smokeを経て`gh release create`でタグとReleaseを作成する。
- `.github/workflows/workflow-lint.yml`は`.github/**`の変更と週次でzizmorを実行する。
- すべての`uses:`は40桁のSHA pinに`# vX.Y.Z`コメントを付ける。checkoutは
  `persist-credentials: false`、各jobに`timeout-minutes`を付ける。
- `dependabot.yml`はgithub-actionsとuvを週次で監視する（uvは`cooldown: 7`日）。

## Git

日本語コミットを使い、`git add .`、amend、`--no-verify`、force push、mainへのpush、
`reset --hard`、`clean -fd`、`checkout -- file`、`stash drop`を使わない。
生成された`out/`、秘密情報、環境ファイルをcommitしない。ファイルの改名は`git mv`で行う。
