---
name: testing-bard-renderer
description: bardレンダラーの生成物を独立ABC・MIDIツールとブラウザで検証する手順。歌詞位置、メリスマ、休符、文字コード、SDK pluginロードを確認する。
---

# bardレンダラーの独立検証

## 環境

- 製品の依存は`uv sync`で用意する。
- 検証ツールはリポジトリ外のscratch venvへ導入する。
  `uv venv /tmp/bard-tools`、`uv pip install --python /tmp/bard-tools/bin/python mido music21 markdown pyyaml openhands-sdk==1.49.3`。
- ABCの独立CLIは`abcmidi abcm2ps`。譜面PNG化にはGhostscript、
  PDF化には`ps2pdf`が使える。日本語フォントが利用可能か確認する。
- SDK pinはリポジトリが対象とする版と照合する。LLMを呼ばないPlugin.loadにAPI keyは不要。

## 実行と独立検査

1. 英日fixtureを、実行ごとに新しいディレクトリへCLIで描画する。
   自己read-back成功だけで合格とせず、provenanceのSHA256を再計算する。
2. `mido.MidiFile(path, charset="utf-8")`で3トラック・480 PPQ・チャンネル・
   program・tempo・拍子・音ON/OFFを確認する。midoの既定charsetはlatin1なので、
   日本語タイトルがそのままでは文字化けすることがある。
3. melodyの音高・開始位置・長さを提案JSONから独立に計算して比較する。
   末尾休符がある場合は、旋律トラックのend_tickだけを曲全体の長さと同一視しない。
4. `abc2midi song.abc -o independent.mid`と
   `abcm2ps song.abc -O score.ps`を実行し、終了コードと診断を保存する。
   abc2midiは冒頭に小さなtickオフセットを付けることがあるため、
   開始tickを正規化して旋律を照合する。
5. `gs -dSAFER -dBATCH -dNOPAUSE -sDEVICE=png16m -r150 -sOutputFile=score.png score.ps`
   で譜面画像を作る。abcm2psがエラーでもPSを書くことがあるため、
   画像が存在するだけで成功と判定しない。
6. 歌詞の`w:`は休符を自動スキップする。休符に`*`を足すと次の音を消費する。
   メリスマ`_`を含む歌詞位置数は休符を除いた音数に対応させ、実譜面で位置を確認する。
   語中メリスマ・語末メリスマ・休符直後を別々に確認する。
7. Python Markdownの`tables`と`fenced_code`拡張でsong.mdをHTML化し、
   Chromeで開いて上下をスクロールする。題名・歌詞・表・ABC・根拠・出典を撮影する。
   元のMarkdownを改変して表示不備を隠さない。Canvas実機確認と呼ばない。
8. `Plugin.load(plugin_root)`でagents/skills/commandsの名前と数を照合する。
   ロード成功をtask実行・LLM作曲の成功として扱わない。

## Devin Secrets Needed

なし。ローカルの生成物検証とSDK pluginロードには認証不要。
