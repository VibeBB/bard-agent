# ADR-0002: 歌提案JSONを唯一の正とし、stdlibだけでABC/MIDI/MMLへ描画する

> ステータス: Accepted
> 日付: 2026-09-20

## コンテキスト

LLMは歌詞と旋律を「書く」ことはできるが、音階外の音、コードと旋律の衝突、音節数と音符数の
不一致、声域超過、拍数の不足といった機械的な誤りを頻繁に混ぜる。また、同じ歌を複数の形式
（人が読む譜、DAWで開くMIDI、テキスト音楽言語）で出す場合、形式ごとに書き直すと内容が
食い違う。

## 決定

1. 歌の唯一の正は`bard_song_proposal` 0.1 JSON（`docs/song-proposal-contract.md`）とする。
   歌詞行ごとに歌唱単位（英語は音節、日本語はモーラ）と音符を1対1で持たせ、
   `units`の連結が`text`と一致することを決定論的に検査する。
2. `bard-render` Skillの`render_song.py`が提案を検証し、`song.abc`（ABC 2.1）、
   `song.mid`（SMF format 1）、`song.mml`（`bard-mml 0.1`）、`song.md`（Agent Canvasの
   inline Markdown preview用）、`song.provenance.json`を同じ`Score`から導出する。
   同じ提案は byte-identical な出力を生む（provenanceの生成時刻を除く）。
3. 描画後に各出力を読み戻して提案と照合し、不一致なら出力を1つも書かずに非ゼロ終了する。
4. scriptはPython標準ライブラリだけを使う。music21（BSD-3）・mido（MIT）は使えるが、
   plugin installだけで動く経路を保つため採用しない。mingus等のGPLコードはimport結合しない。
   FluidSynth（LGPL）やLilyPond（GPL）による音声・楽譜PDF化はsubprocess実行なら可能だが、
   現時点では採用せず、採用時は新規ADRで扱う。
5. 提案契約の`bpm`・拍値・音階・跳躍・終止の規則は、歌える範囲に収める最小限とし、
   芸術的判断（歌詞の質、旋律の魅力、モードとの適合）は`bard-critic`の所見に委ねる。
   criticの所見は観測であり、検証器の合否に影響しない。

## 影響

- LLMは音符単位で提案を書く必要があり、1曲あたりの出力量が増える。代わりに機械的誤りは
  描画前に排除される。
- 借用和音、転調、拍子変更、3声以上の伴奏は0.1では表現できない。必要なら契約の版を上げる。
- 日本語のモーラ分割は提案側の責任であり、検証器は連結一致と1..2文字の範囲だけを検査する。
