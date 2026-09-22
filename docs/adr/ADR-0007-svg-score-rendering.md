# ADR-0007: score.png描画をSVG+rsvg-convert経路へ移行

> ステータス: Accepted
> 日付: 2026-09-22

## コンテキスト

ADR-0005で導入した`score.png`は`abcm2ps`→`gs`（PostScript経由）で描画して
いたが、CIの譜面画像から日本語歌詞が欠落する問題が観測された
（`warning: char XXXX not treated`）。調査の結果、原因はフォント欠如ではなく
abcm2psのPS出力経路の構造にある: 同経路は出力時に各文字を選択フォントの
エンコーディングへ対応づける必要があり、pango/fontconfigが対応グリフを持つ
フォントを解決できない環境では、その文字を警告付きで**静かに落とす**。
CIで`fonts-ipafont`を導入してからはCJKフォントが解決され歌詞は描画されるが、
フォント欠如時に文字が無言で消える構造は残ったままである。

一方`abcm2ps`の`-g`（SVG）出力経路は、全ての文字をUTF-8の`<text>`要素として
書き出し、フォントカバレッジを描画時に要求しない。フォント解決はラスタライズ
側に移るため、文字が欠落する構造自体が存在しない。CJKフォントの無い環境でも
欠落ではなく代替ボックス（tofu）として描かれ、目視で検出できる。

## 決定

1. `render_score_png.py`の描画経路を`abcm2ps -g`（SVG）→ `rsvg-convert`
   （librsvg）→ PNGに切り替える。PostScript/Ghostscript経路は廃止する。
   stdlib importのみ・外部ツールはsubprocess経由の不変条件は維持する。
   `rsvg-convert`は単一バイナリのaptパッケージ（`librsvg2-bin`）で、
   pango/fontconfigによるフォント解決を持つ。
2. CIの`independent-check`のapt行を`abcm2ps abcmidi librsvg2-bin
   fonts-ipafont`に更新する（`ghostscript`は外す）。
3. 終了コード・`score-review.json`・Stage 8の契約は変更しない。
   `score.png`がadvisory成果物である規律（`authority: none`、fail-open）は
   ADR-0005のままである。

## 結果

- フォント欠如環境でも歌詞テキストは欠落せず、代替ボックスとして画像に残る。
  視覚検査が「消えた文字」を欠陥と誤認する余地がなくなる。
- 外部ツール依存が`ghostscript`から`librsvg2-bin`へ置き換わる。
  `rsvg-convert`不在時は従来どおり終了コード`4`でスキップする。
- `render_score_png.py`のJSON出力は`score_ps`の代わりに`score_svg`を返す。

## 根拠

- 代替レンダラーとしてabc2svg（npm・node実行系が新たに必要）、abcjs
  （ブラウザDOM前提）、Verovio（ABC対応が部分的・重量）、LilyPond+abc2ly
  （`w:`歌詞対応が不確か・巨大な依存）を比較したが、いずれもabcm2psを
  残しつつSVG経路へ替える方式より重い。cairosvgは実測でCJKの`<text>`を
  欠落させたため却下した。
- `librsvg`はpangoベースで、CIが既に導入する`fonts-ipafont`と同一の
  fontconfig経路でフォントを解決する。abcm2psとlibrsvg2-binはともに
  Ubuntu universeの保守パッケージであり、GPL結合も発生しない
  （subprocess実行、ADR-0003の境界内）。
- Ghostscriptは本用途では不要になり、依存面が縮小する。
