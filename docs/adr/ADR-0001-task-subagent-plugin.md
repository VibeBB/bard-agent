# ADR-0001: bardをtask sub-agentのpluginとして配布する

> ステータス: Accepted
> 日付: 2026-09-20

## コンテキスト

OpenHands Software Agent SDK v1.49.3にはsub-agentを起こす機構が3つある。

| 機構 | 仕組み | 親の履歴 | hook境界 |
| --- | --- | --- | --- |
| `task`（`TaskToolSet` + `AgentDefinition`） | 親が`task(prompt, subagent_type)`を呼び、新規`LocalConversation`が完走して最終応答文字列を返す。`resume`で同じ子会話を継続できる | 渡らない（promptのみ） | 子は自身の`hooks:`を持つ |
| `delegate`（`DelegateTool`） | `spawn`で名前付き子を作り`delegate`で複数promptをThread並列実行する | 渡らない | 同上 |
| `workflow`（`WorkflowToolSet`） | LLMが書いたPython `async def main(wf)`を親プロセス内で`exec`する | 渡らない | script本体はhook／security analyzerの外 |

OpenHandsアプリ（Agent Canvas）の既定toolには`task`だけが含まれ、利用者設定
`enable_sub_agents`（既定off）で有効化される（OpenHands/OpenHands#14122）。pluginの
`agents/*.md`は同じregistryへ登録されるため、有効化後は通常の会話から
`task(subagent_type="bard")`で呼べる。`delegate`と`workflow`はアプリに露出していない。

## 決定

1. bardはOpenHands plugin（`plugins/bard`）として配布し、`agents/bard.md`と
   `agents/bard-critic.md`の2つのAgentDefinitionを`task`で呼ぶ。`delegate`と`workflow`は
   採用しない。`workflow`はhook境界の外で任意Pythonが動くため、`delegate`はbard 1体の
   用途に対して過剰で、かつアプリの標準経路にないためである。
2. task sub-agentは親の会話履歴を受け取らない。題材は次の二本立てで渡す。
   - 親が`/bard:sing`（`commands/sing.md`）の手順で直近の会話・出来事・登場人物・感情の起伏を
     `out/bard/<slug>/context.md`へ要約し、そのpathをpromptで渡す。
   - bardは親と同じworkspaceを共有するため、`git log`、diff、README、ADR等を自ら読む。
3. `task`が使えない環境（`enable_sub_agents`がoff、または`task_tool_set`が無い）では、
   `/bard:sing`は親エージェント自身に`agents/bard.md`の手順を実行させる（fallback）。
   標準機能の設定を推奨し、独自の代替基盤は作らない。
4. criticは`task(subagent_type="bard-critic")`でbardから呼ぶ。criticは所見を返すだけで、
   提案を書き換えず、合否権限を持たない。
5. 他のエージェント（例: acd-agentのAgentDefinition）からも、bard pluginがinstall済みなら
   同じ`task`経路で呼べる。bard側に特別な入口は設けない。

## 影響

- Agent Canvasで使うには`enable_sub_agents`を有効にする。手順はREADMEに記す。
- 題材の要約は親の責任であり、bardは要約と自ら読んだworkspaceの情報だけを歌う。
  親が要約に含めなかった会話内容は歌に現れない。
- SDKのsub-agentが将来親の文脈を受け取れるようになった場合は本ADRを見直す。
