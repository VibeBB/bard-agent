# ADR-0004: CI/CDとtagによるリリース

> ステータス: Accepted
> 日付: 2026-09-20

## コンテキスト

bard pluginの配布経路とリリース手順を決める必要がある。PyPI公開やDockerイメージは
過剰であり、pluginはgitリポジトリ内の`plugins/bard`だけで完結する。GitHub Actionsは
public repo向けに無料で、外部配布面を増やさずにタグから導入できる。

## 決定

1. 配布単位はgit tag（`v<version>`）とそのzip。PyPI・Dockerへの公開は行わない。
   導入指定は`github:VibeBB/bard-agent/plugins/bard#v<version>`とする。
2. リリース起動は`workflow_dispatch`のみで、main上の`check-version`ジョブが
   入力version・`pyproject.toml`・`plugins/bard/.plugin/plugin.json`の三者一致と
   タグ未存在を検査してから進む。失敗時はタグもReleaseも作られない。
3. CIは再利用workflow（`workflow_call`）として構成し、PR/pushとリリース前検証で
   同じ`verify`ジョブを使う。`independent-check`はabcm2ps・abc2midi・ghostscriptによる
   外部描画の独立検査とし、`BARD_REQUIRE_ABCM2PS=1`でskip不可にする。
   `plugin-load`は`sdk-check`依存グループ（`openhands-sdk==1.49.2`）でSDK経由の
   plugin読み込みを検査する。SDKはCI検査用の依存としてのみ使い、実行時依存にしない。
4. GitHub Actionsはすべて40桁SHAにpinし、zizmorを週次＋全pull request＋
   `.github/**`変更のpushで実行する（`zizmor`はrequired status checkなので
   PRのpathsフィルタは付けない）。
   dependabotはgithub-actionsとuvを週次監視（uvは7日cooldown）する。

## 結果

リリースはmainへのpush後にworkflow_dispatchで行い、`v<version>`タグと
Release（plugin zip＋楽譜サンプルzip）が生成される。
