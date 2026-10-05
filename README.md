# bard-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/bard-agent)

Part of the [VibeBB](https://vibebb.org/) agent family
([github.com/VibeBB](https://github.com/VibeBB)):
[bard-agent](https://github.com/VibeBB/bard-agent) ·
[dashboard-agent](https://github.com/VibeBB/dashboard-agent) ·
[document-agent](https://github.com/VibeBB/document-agent) ·
[electrical-circuit-agent](https://github.com/VibeBB/electrical-circuit-agent) ·
[firmware-agent](https://github.com/VibeBB/firmware-agent) ·
[fpga-agent](https://github.com/VibeBB/fpga-agent) ·
[mechanical-agent](https://github.com/VibeBB/mechanical-agent) ·
[production-engineering-agent](https://github.com/VibeBB/production-engineering-agent) ·
[simulation-agent](https://github.com/VibeBB/simulation-agent) ·
[UX-creator-agent](https://github.com/VibeBB/UX-creator-agent) ·
[wire-agent](https://github.com/VibeBB/wire-agent)

**English** | [日本語](#日本語)

<a id="english"></a>
## English

`bard-agent` is the bard of the VibeBB family — an AI helper you can use when
you design a hardware product with AI. It does two things: it **writes original
songs about the work** in your project (an epic about a release, a lament for a
deleted feature), and it **designs product sound cues** — the startup chime,
the completion tone, the warning beep a piezo buzzer or small speaker plays.

> Target: OpenHands Software Agent SDK v1.52.0 / OpenHands Agent Canvas

## What you give and what you get back

You give bard a subject (a mode like `chronicle` or `praise`, or a cue request
such as “startup completion warning”) and it writes files into your workspace:

| Folder | What is inside, in plain words |
| --- | --- |
| `songs/<slug>/` | `song.md` (a readable page with lyrics, chords and score), `song.abc` (music notation), `song.mid` (MIDI to play), `song.mml` (text notation), `song.proposal.json` (the song's single source of truth), `song.contour.svg` (melody picture), plus the working notes and the critic's report (`notes.md`, `story.md`, `lyrics.md`, `plan.md`, `critic.md`, `score.png`/`score-review.json` when the picture check ran) |
| `cues/<slug>/` | `cue-<id>.mid`/`cue-<id>.mml` per sound, `cues.json` (a tone table firmware can play directly), `cues.md` (preview), `cues.timeline.svg` (picture of all cues on one timeline), `cues.proposal.json` and `cues.provenance.json` (the source of truth and its audit trail) |
| `observations/bard/` | bard's own diary: `decisions.jsonl`, `impressions.jsonl`, `vision-reviews.jsonl` — see “Records” below |

Songs follow the conversation's language (Japanese or English). Cue sets are
for a device you name (`piezo` or `speaker`).

## How it works with sister plugins

VibeBB is a family of agents that share one workspace. **ux-creator** asks bard
for product sounds by dropping a `*.ux-request.json` liaison file in the
workspace; `/bard:inbox` lists those requests and bard answers each with a
`*.ux-response.json`. **firmware** can take `cues.json` — a plain tone table of
`freq_hz` / `start_ms` / `duration_ms` — and play it on the device. A song can
be about any sister's work: wire's harness decisions, mechanical's enclosure
iterations, production's plan — bard reads the workspace the sisters left
behind and sings it.

## How to start

### Install in Agent Canvas (OpenHands web GUI)

Verified with OpenHands agent-server 1.46-series releases:

1. Open **Customize** in the left sidebar and select the **Plugins** tab.
2. Click **Add plugin**, enter the following three values, and click
   **Install**.

   | Field | Value |
   | --- | --- |
   | Source | `github:VibeBB/bard-agent` |
   | Ref | `v1.0.0` / the latest tag from [Releases](https://github.com/VibeBB/bard-agent/releases) |
   | Path | `plugins/bard` |

3. When **bard** appears as enabled, installation is done — commands and skills
   load automatically in new conversations.
4. Optionally enable `enable_sub_agents` in settings so bard runs as a
   sub-agent; it also works without it (the parent follows the same recipe).

No GUI? Place `plugins/bard` in your project directory
(`$OPENHANDS_PROJECT_DIR/plugins/bard`), point `BARD_PLUGIN_ROOT` at it, or use
the SDK `PluginSource`. Details: [docs/operations.md](docs/operations.md).

### Commands

Plugin commands may not appear in the composer's `/` autocomplete palette; type
them as plain text — they dispatch the same way.

| Command | What it does | Example |
| --- | --- | --- |
| `/bard:sing` | Write a song about the work | `/bard:sing praise today's release` |
| `/bard:cue` | Design product sound cues | `/bard:cue piezo smart-kettle startup completion warning` |
| `/bard:inbox` | List and answer sister requests | `/bard:inbox` |
| `/bard:doctor` | Check the plugin install | `/bard:doctor` |

A `/bard:sing` run usually takes 10–15 minutes depending on the model and the
workspace. When it finishes you get the title, key, tempo, full lyrics and the
file list; open `song.md` in the preview panel or play `song.mid`.

## What it leaves as records

bard keeps a diary under `observations/bard/` so the work stays explainable:

- `decisions.jsonl` — why each musical choice was made (options considered,
  principles, risks, when to revisit);
- `impressions.jsonl` — a written impression after every stage;
- `vision-reviews.jsonl` — what bard saw when it looked at a rendered picture
  (score, melody contour, cue timeline), bound to the picture's exact bytes.

Records exist so you can trace “why does it sound like this?” later. They are
advisory evidence only — they never approve or reject anything.

## Limits and safety

- bard is a creative observer: it never judges whether work passed or failed,
  and its outputs never feed back into the work they describe.
- It writes only original music — no quoting or imitating existing songs or
  artists, no mocking real people; rendering is refused unless every
  `originality` declaration is true.
- Pictures (`score.png`, `song.contour.png`, `cues.timeline.png`) need Docker
  and the pinned `bard-tools` image; without them rendering is skipped, never
  faked on the host.
- Songs and cues are generated by an LLM; the same request can produce
  different results between runs. Rendered files are deterministic per
  proposal.

## License

BSD-3-Clause ([LICENSE](LICENSE)), © VibeBB. Generated songs record
`license: BSD-3-Clause` in `song.provenance.json`.

Technical material — architecture, the plugin boundary, CLIs, hooks, contracts,
development and CI — lives in [docs/README.md](docs/README.md).

<a id="日本語"></a>
## 日本語

[English](#english) | **日本語**

`bard-agent` は VibeBB ファミリーの吟遊詩人です。AI でハードウェア製品を設計する
「VibeBB」の仕事の中で使う、非エンジニア向けの AI ヘルパーです。できることは二つ。
**プロジェクトの仕事を題材にオリジナルの歌を作る**こと（リリースの叙事詩、消えた
機能への哀歌）、そして**製品の効果音を設計する**こと（圧電ブザーや小型スピーカーが
鳴らす起動音・完了音・警告音）です。

> 対象: OpenHands Software Agent SDK v1.52.0 / OpenHands Agent Canvas

## 渡すもの・返ってくるもの

歌のモード（`chronicle` や `praise` など）や「startup completion warning」のような
音の依頼を渡すと、ワークスペースにファイルを書き出します。

| フォルダ | 中身（やさしい言葉で） |
| --- | --- |
| `songs/<slug>/` | `song.md`（歌詞・コード・譜面が読める1ページ）、`song.abc`（楽譜記法）、`song.mid`（再生できる MIDI）、`song.mml`（テキスト記法）、`song.proposal.json`（歌の唯一の正）、`song.contour.svg`（旋律の絵）。ほかに作業メモと批評レポート（`notes.md`・`story.md`・`lyrics.md`・`plan.md`・`critic.md`、画像チェックが動いたときは `score.png`/`score-review.json`） |
| `cues/<slug>/` | 音ごとの `cue-<id>.mid`/`cue-<id>.mml`、`cues.json`（ファームウェアがそのまま鳴らせる音程表）、`cues.md`（プレビュー）、`cues.timeline.svg`（全キューのタイムライン絵）、`cues.proposal.json` と `cues.provenance.json`（正と来歴） |
| `observations/bard/` | bard の日記: `decisions.jsonl`、`impressions.jsonl`、`vision-reviews.jsonl`（後述） |

歌詞の言語は会話に合わせて日本語または英語です。キューは `piezo` または `speaker` の
どちらかのデバイス向けに作ります。

## 姉妹 plugin との連携

VibeBB は一つのワークスペースを共有するエージェントのファミリーです。**ux-creator** が
ワークスペースに `*.ux-request.json` という依頼ファイルを置くと bard が製品音を請け負い、
`/bard:inbox` がその一覧と回答（`*.ux-response.json`）を作ります。**firmware** は
`cues.json`（`freq_hz`・`start_ms`・`duration_ms` の素朴な音程表）をそのまま
デバイスで鳴らせます。歌の題材は姉妹のどの仕事でも構いません —— wire の配線決定、
mechanical の筐体改訂、production の計画まで、bard はワークスペースに残された
記録を読んで歌にします。

## はじめかた

### Agent Canvas（OpenHands Web GUI）へのインストール

実機（OpenHands agent-server 1.46 系）で確認した手順です。

1. 左サイドバーの **Customize** を開き、**Plugins** タブを選びます。
2. **Add plugin** を押し、次の3項目を入力して **Install** を押します。

   | 項目 | 値 |
   | --- | --- |
   | Source | `github:VibeBB/bard-agent` |
   | Ref | `v1.0.0`（[Releases](https://github.com/VibeBB/bard-agent/releases) の最新タグ） |
   | Path | `plugins/bard` |

3. 一覧に **bard** が「有効」で表示されれば完了です。新しい会話ではコマンドと
   スキルが自動で読み込まれます。
4. （任意）`enable_sub_agents` を有効にすると bard が sub-agent として動きます。
   無効でも動きます（親エージェントが同じ手順を実行します）。

GUI を使わない場合は `plugins/bard` をプロジェクト直下
（`$OPENHANDS_PROJECT_DIR/plugins/bard`）に置くか、`BARD_PLUGIN_ROOT` を指すか、
SDK の `PluginSource` を使います。詳しくは [docs/operations.md](docs/operations.md)。

### コマンド

プラグインのコマンドが作曲欄の `/` オートコンプリートパレットに表示されないことが
あります。プレーンテキストで入力して送信すれば同じように動きます。

| コマンド | すること | 例 |
| --- | --- | --- |
| `/bard:sing` | 仕事についての歌を作る | `/bard:sing praise 今日のリリース` |
| `/bard:cue` | 製品の効果音を設計する | `/bard:cue piezo smart-kettle startup completion warning` |
| `/bard:inbox` | 姉妹からの依頼を一覧・回答 | `/bard:inbox` |
| `/bard:doctor` | 導入状態を診断 | `/bard:doctor` |

`/bard:sing` はモデルとワークスペースの大きさによって 10〜15 分ほどかかります。
終わると題名・調・テンポ・歌詞全文とファイル一覧が返り、`song.md` をプレビュー
パネルで読むか `song.mid` を再生できます。

## 残す記録

bard は `observations/bard/` に日記を残し、あとから「なぜこの音になったか」を
追えるようにします。

- `decisions.jsonl` — 音楽的な選択の理由（検討した案、原理、リスク、見直し条件）
- `impressions.jsonl` — 各ステージ終了時の感想文
- `vision-reviews.jsonl` — 描いた画像（譜面・旋律の絵・キューのタイムライン）を
  見て書いた批評。画像のバイト列に紐付けます

記録は追跡のための証拠であり、合否を決めるゲートではありません。

## 限界と安全

- bard は創造的な観測者です。仕事の合否は決めず、成果物が判定に逆流することも
  ありません。
- 完全なオリジナルのみ書きます。既存楽曲の引用・翻案、実在アーティストの模倣、
  実在人物への嘲笑は禁止し、`originality` 宣言がすべて `true` でなければ描画しません。
- 画像（`score.png`、`song.contour.png`、`cues.timeline.png`）には Docker と
  digest 固定の `bard-tools` image が必要です。なければ描画をスキップし、
  ホストでごまかしません。
- 歌とキューは LLM が生成するので、同じ依頼でも実行ごとに違う結果になります。
  提案が同じなら描画結果は一致します。

## ライセンス

BSD-3-Clause（[LICENSE](LICENSE)）、© VibeBB。生成された歌は
`song.provenance.json` に `license: BSD-3-Clause` と記録されます。

アーキテクチャ・CLI・hook・契約・開発・CI などの技術資料は
[docs/README.md](docs/README.md) にまとめています。
