# Guanlan

> 流れを観察し、源をたどり、境界を明確に保つ。

Guanlan は、AI エージェント向けの CLI-first な中国語インターネット調査・信源ルーティングツールです。単なる検索ラッパーではありません。質問を適切な信源プールへルーティングし、公開ページを読み、ホットトピックを観察し、証拠パケットを作り、下流エージェントに「公式一次情報」「メディア報道」「ユーザーサンプル」「参考コンテキスト」を区別して渡します。

正式なドキュメントは中国語版を基準に管理しています。この日本語ページは、国際ユーザーと Agent 連携向けの同期サマリーです。

## 最初に読むもの

| 文書 | 用途 |
| --- | --- |
| [中文 README](../README.md) | 正式な位置づけ、インストール、例、リリース情報。 |
| [更新ログ](../CHANGELOG.md) | バージョンごとの能力変更と境界調整。 |
| [Agent Playbook](agent-playbook.md) | Agent の長期記憶：動的ワークフロー、benchmark 規律、fallback ルール。 |
| [Agent 使用说明](agent-usage.md) | Agent 向けの検索、読み取り、熱榜、archive、MCP の使い方。 |
| [出力契約](contract.md) | CLI / MCP / HTTP / RAG 連携で安定して使えるフィールド。 |
| [本地大模型联网指南](local-llm.md) | Ollama、LM Studio、Open WebUI などのローカルモデルに証拠コンテキストを渡す方法。 |
| [排障手册](troubleshooting.md) | Keychain、ネットワーク、Cookie、プラットフォーム失敗時の切り分け。 |
| [来源说明](SOURCE_ATTRIBUTION.md) | 参照したオープンソースプロジェクトと公開ソース。 |

## 現在安定して使える能力

- 中国語インターネットに合わせた公開検索、source card、evidence role、品質スコア、広めのデフォルト候補池。
- URL 読み取り：Jina Reader 優先、直接 HTML fallback、品質レポート、strict mode、batch、cache、snapshot。
- `hotnews` による中国語ホットリストと trend clustering。失敗源や stale cache も明示。
- `research`、`compare`、`timeline`、`dossier` による証拠パケット、比較、時間線、対象档案。
- ローカル archive / RAG ブリッジ：SQLite/FTS、ingest audit、prompt-ready context、Wiki export、LangChain/LlamaIndex/OpenWebUI pack。
- Agent 連携：CLI-first、任意の MCP、任意のローカル read-only HTTP service、ローカルモデル向け prompt/context。

## v0.4.1 の検索安定化

- Query guard：無意味な入力やキーボード乱打は検索前に拒否し、ランダムなページではなく diagnostics を返します。
- Query rewrite：短い事実型 query、短い口碑/購買 query、長すぎる query を保守的に拡張または圧縮します。
- Recovery search：DuckDuckGo fallback と multi-entity fan-out で、空結果や「最初の対象だけ」の結果を減らします。
- Agent workflow plan：品質サマリーが `2-step`、`3-step`、`4-step` のどれで進むべきかを説明します。
- JSON 空結果でも `diagnostics` を返せるため、Agent は「検索失敗」ではなく「query の書き直しが必要」と報告できます。

## 主要コマンド

```bash
guanlan capabilities
guanlan welcome
guanlan search "query" --profile china --limit 80
guanlan search "政策テーマ" --profile china --scope party_central --trace
guanlan search "製品レビュー" --profile china --scope ecommerce --format context
guanlan route "複合的な中国語調査タスク" --json
guanlan research "query" --profile china --advisor
guanlan compare "A" "B" --focus "価格 評判 リスク" --limit 80 --format context
guanlan timeline "事件 最新進展" --limit 80 --format context
guanlan dossier "会社または製品" --focus "事業 評判 リスク" --limit 80 --format context
guanlan read "https://example.com/article" --quality-report
guanlan hotnews today --limit 80 --trends
guanlan feeds curated --limit 80
guanlan archive ingest-research "query" --limit 80
guanlan archive context "query" --limit 20
guanlan doctor --trace
```

## Agent ワークフロー規則

Guanlan を単発の generic `search` に縮小しないでください。

- `2-step`: 結果がすでに使える場合は `search -> read`。
- `3-step`: 通常の調査や品質シグナルが弱い場合は `route -> research -> scoped search`。
- `4-step`: 最新/ホットな話題は `hotnews`、技術/AI/開発者系は `feeds`、信源が狭い場合は `compare/timeline/dossier` を追加。

適切な Guanlan ワークフローを終えても重要証拠が足りない場合にだけ、generic `web_search` / `web_fetch` へ fallback します。

## 安全メモ

Guanlan はステルスクローラーでもアカウント自動化ツールでもありません。読み取り優先、低干渉、信源明示、認証の明示的許可を基本にしています。Cookie、ブラウザ、Keychain、ログイン状態へのアクセスは、ユーザーが明確に求めた場合だけ扱います。投稿、コメント、いいね、フォロー、メッセージ送信は自動実行しません。
