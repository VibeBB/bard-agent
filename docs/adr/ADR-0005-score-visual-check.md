# ADR-0005: score.png視覚検査（advisory）

> ステータス: Accepted
> 日付: 2026-09-22

## コンテキスト

criticは提案テキスト（`song.proposal.json`/`song.md`）だけを読み、組版された
譜面を見ない。歌詞の衝突・孤立した音節・詰まったコード表記・小節線の乱れは
刻まれた譜面を見て初めて分かる欠陥である。OpenHands SDK 1.49.xには
`ImageContent`・`file_editor view`の画像表示・`inspect_image_with_vision`が
揃っており、vision対応モデルはPNGを直接検査できる。

## 決定

1. `plugins/bard/skills/bard-render/scripts/render_score_png.py`を追加し、
   `render_song.py`の`song.abc`を`abcm2ps`+`gs`（CIと同一コマンド）で
   `score.png`へ描画する。stdlib importのみ、外部ツールはsubprocess経由。
   終了コード`4`はツール不在＝スキップ（失敗ではない）。
2. `bard`エージェントにStage 8（スコア視覚検査）を追加する。`abcm2ps`/`gs`が
   `PATH`にあれば`score.png`を描画し、vision対応モデルは`file_editor view`で
   目視する。結果は`score-review.json`（`artifact_kind: bard_score_review`、
   `authority: none`）に`status: inspected|skipped|error`で記録する。
3. この成果物は観察であり、提案へのpass/fail権限を持たない（`critic.md`と
   同じ規律）。score checkは納品をブロックしない（fail-open）。画像内の
   文字はデータであり命令ではない。
4. CIの`independent-check`の譜面生成ステップを`render_score_png.py`に置き換え、
   同じスクリプトをCIが検証する。

## 結果

- `score.png`/`score-review.json`は決定論的render出力でも読み戻し検査対象でも
  ない（`docs/song-proposal-contract.md`の出力表に任意advisory成果物として記載）。
- ツール不在の環境では`status: skipped`で継続する。CIでは`BARD_REQUIRE_ABCM2PS=1`
  のもと必須とする。

## 根拠

既にCIは`abcm2ps`/`gs`を独立検査として採用済みであり、外部ツールの新規採用では
ない。視覚検査はcriticがカバーしない刻版欠陥を人間・モデルの双方が確認できる
ようにするが、歌や作業の合否には一切関与しない。
