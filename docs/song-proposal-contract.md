# 歌提案契約 `bard_song_proposal` 0.3

（schema_versionは`"0.3"`が現行。`"0.2"`も受理するが`melody_from`は使えない。）

bardエージェント（LLM）が書く歌の提案JSONと、`bard-render` Skillがそれを検証・描画する契約。
検証器は提案テキストだけを判定し、歌の芸術的な良否や、歌の題材となった作業の合否を判定しない。
提案は歌の唯一の正であり、ABC・MIDI・MMLはすべて提案から決定論的に導出される。

## 最上位

```json
{
  "artifact_kind": "bard_song_proposal",
  "schema_version": "0.3",
  "title": "The Dragon of the Red Pipeline",
  "mode": "chronicle",
  "language": "en",
  "sources": [
    {"kind": "conversation_summary", "ref": "out/bard/red-pipeline/context.md", "sha256": "..."},
    {"kind": "git_log", "ref": "HEAD~20..HEAD"}
  ],
  "rationale": "Why this key, mode, meter and imagery fit the story.",
  "originality": {
    "original_lyrics": true,
    "original_melody": true,
    "no_named_artist_imitation": true,
    "no_real_person_ridicule": true
  },
  "key": {"tonic": "D", "mode": "dorian"},
  "meter": "4/4",
  "bpm": 96,
  "instruments": {"melody": 74, "accompaniment": 24},
  "vocal_range": {"low": "c4", "high": "e5"},
  "sections": [ ... ]
}
```

| フィールド | 規則 |
| --- | --- |
| `artifact_kind` | 固定値 `bard_song_proposal` |
| `schema_version` | `0.2` または `0.3`。`melody_from`は`0.3`専用 |
| `title` | 1..80文字、空白のみ不可 |
| `mode` | `chronicle` / `praise` / `lament` / `satire` / `inspire` / `lore` |
| `language` | `ja` / `en` |
| `sources` | 1件以上。`kind`は `conversation_summary` / `agent_message` / `git_log` / `file` / `user_request`。`ref`は1..200文字。`sha256`は任意（64桁hex） |
| `rationale` | 1..2000文字 |
| `originality` | 4つの真偽値がすべて `true` でなければ不合格（歌詞・旋律が自作、実在アーティスト模倣なし、実在人物への嘲笑なし） |
| `key.tonic` | `C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B` |
| `key.mode` | `major` / `minor` / `dorian` / `mixolydian` |
| `meter` | `4/4` / `3/4` / `6/8`。1拍は四分音符（6/8は八分音符を0.5拍として数え、1小節=3拍） |
| `bpm` | 60..180 の整数 |
| `instruments.melody`, `instruments.accompaniment` | General MIDI program 0..127 |
| `vocal_range.low`, `vocal_range.high` | 音名（後述）。`high - low` は 7..19半音 |
| `sections` | 1..12件 |

## セクション

```json
{
  "name": "verse 1",
  "kind": "verse",
  "chords": ["Dm", "C", "Dm", "Am", "Dm", "C", "Am Dm", "Dm"],
  "lines": [
    {
      "text": "Under the red light of the pipeline's eye",
      "units": ["Un", "der", "the", "red", "light", "of", "the", "pipe", "line's", "eye"],
      "notes": [
        {"pitch": "d4", "beats": 0.5}, {"pitch": "e4", "beats": 0.5},
        {"pitch": "f4", "beats": 1}, {"pitch": "g4", "beats": 1},
        {"pitch": "a4", "beats": 1},
        {"pitch": "g4", "beats": 0.5}, {"pitch": "f4", "beats": 0.5},
        {"pitch": "e4", "beats": 1}, {"pitch": "d4", "beats": 1},
        {"pitch": "d4", "beats": 1}
      ]
    }
  ]
}
```

| フィールド | 規則 |
| --- | --- |
| `name` | 1..32文字、`[A-Za-z0-9 _-]`、歌全体で一意 |
| `kind` | `intro` / `verse` / `chorus` / `bridge` / `outro`。`name`の先頭の語が `intro` / `verse` / `chorus` / `refrain` / `bridge` / `outro`（小文字化して比較）なら`kind`は対応する種別でなければならない（`refrain`は`chorus`に対応） |
| `chords` | 小節ごとに1要素、1..32小節。要素は1つまたは空白区切り2つのコード記号（2つなら小節を前後半に等分） |
| `melody_from` | 任意（schema 0.3のみ）。それより前のセクション名を指し、そのセクションの`chords`と各行の`notes`を複製する（下記「旋律の再利用」） |
| `lines` | 0件以上（`intro`/`outro`は0件可、それ以外は1件以上）。`lines: []`の`intro`/`outro`は小節数×1小節の拍数のインストゥルメンタル区間となり、旋律は休み・伴奏のみ鳴る（ABCは各コード区間に`z`全小節休符、MMLは`r`、Markdownは`_(instrumental)_`/`_（間奏）_`を出力、`w:`行は出さない）。行がある場合、行の`notes`の合計拍数を順に並べたものがセクションの総拍数（小節数×1小節の拍数）と**一致**しなければならない |

### コード記号

`<root><quality>`。`root`は`key.tonic`と同じ表記集合、`quality`は空（長三和音）/ `m` / `dim` / `7` / `maj7` / `m7` / `sus4` / `sus2`。
コードのrootは調の音階に属さなければならない（借用和音は0.2では不可）。
最後のセクションの最後のコードのrootは`key.tonic`でなければならない。

### 行

| フィールド | 規則 |
| --- | --- |
| `text` | 1..200文字 |
| `units` | 歌唱単位の列。`en`は音節、`ja`はモーラ。`~`は直前の単位の引き延ばし（メリスマ）、`-`は休符位置 |
| `reading` | 任意（`ja`のみ）。ひらがな・カタカナ・ーと空白・句読点だけで書く読み仮名。ある場合、`units`の一致検査は`text`ではなく`reading`に対して行い、`text`は漢字を含んでよい。`en`では指定不可 |
| `notes` | `units`と同数。`pitch`は音名または`r`（休符）。`beats`は `0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4` のいずれか |

`units`と`text`の整合（決定論的検査）:

- `en`: `units`のうち`~`と`-`を除いたものを連結し、`text`から空白と `,.;:!?'"()-—` を除いたものと大文字小文字を無視して一致しなければならない。
- `ja`: `reading`がある場合は`reading`から、無い場合は`text`から、空白と句読点（`、。！？「」・…—`）を除いたものと一致しなければならない。モーラ分割は提案側の責任だが、各単位は1..2文字（拗音・長音・促音は前の文字に付ける）とする。漢字を含む歌詞は`text`に書き`reading`へ読み仮名を置く。

`notes[i].pitch == "r"` ⇔ `units[i] == "-"`。`units[i] == "~"`の音は直前の音と同じか隣接（順次進行）の音でなければならない。

### 旋律の再利用（melody_from）

反復形式（同じ旋律に別の歌詞を載せる）のために、セクションは`melody_from: "<それより前のセクション名>"`を宣言できる。

- schema_versionは`"0.3"`が必須（`0.2`では不合格）。
- 参照先は`sections`内で**それより前**に現れるセクションの`name`。未知または後方の名前は不合格。
- 参照先自身が`melody_from`を使っている場合は不合格（連鎖不可）。
- 複製側のセクションは`chords`キーを省略し、各行は`notes`キーを省略しなければならない。
- 複製側は参照先と同じ行数・行ごとの`units`数・`-`（休符）の位置を持たなければならない。
- 複製された`chords`/`notes`には通常の検査がすべて適用される（拍数一致、ダウンビート和音、音域、跳躍、カデンツなど）。

### 音名

`[a-g](#|b)?[0-9]`（例 `d4`, `f#4`, `bb3`）。MIDI番号は `c4 = 60`。

## 旋律規則（不合格条件）

1. 休符以外のすべての音は `vocal_range.low..high` 内。
2. 休符以外のすべての音は調の音階に属する。`minor`は導音（長7度）も許す。
3. 各小節の第1拍で鳴り始める旋律音は、その小節（前半）のコードの構成音でなければならない（休符は可）。
4. 隣接する2音の跳躍は完全8度（12半音）以内。
5. 歌全体の最後の旋律音は`key.tonic`の音階度1・3・5のいずれか。
6. 休符以外の音が16個以上、行が4行以上（`intro`/`outro`を除く）。
7. 総イベント数（旋律音 + 和音音）は8192以下。
8. 4音以上を持つ各行の`notes`の`beats`値は少なくとも2種類含まなければならない。
9. `rationale`中で `refrain` / `chorus` / `verse` / `サビ` / `リフレイン` に続く引用（`「」`・`"`・`“”`、4文字以上）は、空白正規化後にいずれかの行の`text`か`title`に部分一致しなければならない（改訂で古くなった歌詞引用を検出するため）。
10. `melody_from`は上記「旋律の再利用」の規則すべてに従う。

## 描画

| 出力 | 内容 |
| --- | --- |
| `song.abc` | ABC 2.1。`X:1`, `T:`, `C:bard-agent`, `M:`, `L:1/8`, `Q:1/4=<bpm>`, `K:<tonic><mode略号>`（`Ddor`, `Gmix`, `Am`, `C`）。コードは`"Dm"`形式、歌詞は`w:`行（`en`は音節を`-`で連結、`~`は`_`、休符は歌詞行に含めない（ABCでは休符は歌詞整列の対象外））。セクションごとに`%% section <name>`コメントと改行 |
| `song.mid` | SMF format 1、480 tick/拍。track 0: tempo・拍子・title。track 1: 旋律（channel 0, `instruments.melody`）。track 2: 伴奏（channel 1, `instruments.accompaniment`）。伴奏はコード変化ごとに root（第3オクターブ）+ 3度 + 5度（第4オクターブ）を保持、7th系は7度も加える |
| `song.mml` | `bard-mml 0.1`。`;`で始まるヘッダ行（title, mode, language, key, meter, bpm, license）、`@melody`, `@chord1`..`@chordN` の各voiceはモノフォニック（Nは曲中の最大和音構成音数、最低3。七和音があれば`@chord4`）。トークンは `t<bpm>`, `o<oct>`, `l<len>`, 音名（`c d e f g a b`, `+`/`-`）, `r`, `&`（タイ）, `<`/`>`（オクターブ）。長さは 1,2,4,8,16 と付点 `.`。0.75拍は`8.`、1.5拍は`4.`、3拍は`2.` |
| `song.md` | Agent Canvasのinline Markdown previewで読むための一枚。題名、モード、言語、調・拍子・テンポ、セクションごとの歌詞（`text`行、各行末に半角スペース2つのハードブレーク）とコンパクトなコード行（`Chords: | Dm | C | ... |`、分割小節は`Am Dm`）、`abc`コードフェンスに`song.abc`全文、末尾に`rationale`と`sources` |
| `song.provenance.json` | `authority: none`、`artifact_kind: bard_song_provenance`、生成時刻（UTC ISO 8601）、提案path/sha256、各出力のsha256、`sources`の写し、生成scriptのsha256、`license: BSD-3-Clause`、`originality`の写し、`bpm`/`key`/`meter`/小節数/音数 |

すべてのテキスト出力は`encoding="utf-8"`、改行`\n`。

### オプションのadvisory成果物（render出力ではない）

| 出力 | 内容 |
| --- | --- |
| `score.png` | `scripts/render_score_png.py`が`song.abc`から`abcm2ps`(`-g`、SVG)+`rsvg-convert`で描画する譜面画像。人間レビューとvision検査のための事後成果物であり、決定論的render出力にも読み戻し検査にも含まれない。`abcm2ps`/`rsvg-convert`不在時は生成しない（スキップ）。SVG経路は全文字をUTF-8の`<text>`として出力するため描画時に文字を落とさない（ADR-0007）。日本語など非ラテン文字の表示には対応フォント（例: fonts-ipafont）が必要で、無い場合は欠落ではなく代替ボックスで描かれる。歌詞内容は`lyrics.md`で判定する |
| `score-review.json` | `artifact_kind: bard_score_review`、`authority: none`。vision対応モデルが`score.png`を`file_editor view`で目視した所見（`status: inspected|skipped|error`、検査したtool・質問・所見要約・score.pngのsha256・検査時刻）。提案へのpass/fail権限を持たない観察記録 |

## 読み戻し検査（fail-closed）

- MIDI: 自身の出力を再パースし、note-onとnote-offの数がchannelごとに一致し、旋律音数が提案と一致すること。
- ABC: 生成した本文から音符トークンを再パースし、旋律音・休符の数と総拍数が提案と一致すること。
- MML: 生成テキストを再パースし、`@melody`の音数・総長さが提案と一致し、和音voiceの総長さが旋律と一致すること。

どれか1つでも一致しない場合は**すべての出力を書かず**、理由を列挙して非ゼロ終了する。
