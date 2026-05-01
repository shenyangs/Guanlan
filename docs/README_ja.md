# Guanlan

> 流れを観察し、源をたどり、境界を明確に保つ。

Guanlan は、AI エージェント向けの中国語インターネット検索・信源ルーティングツールです。公開ウェブ検索、URL 読み取り、中国語ホットリスト、信源分類を組み合わせ、エージェントが出典を保ったまま調査できるようにします。

正式なドキュメントは中国語版を基準に管理しています。

- [中文 README](../README.md)
- [Agent 使用说明](agent-usage.md)
- [中文互联网设计](chinese-web-design.md)
- [排障手册](troubleshooting.md)
- [来源说明](SOURCE_ATTRIBUTION.md)

## 主要コマンド

```bash
guanlan search "keyword" --profile china --limit 50
guanlan search "keyword" --profile china --scope party_central
guanlan search "keyword" --profile china --scope ecommerce
guanlan read "https://example.com/article"
guanlan read "https://example.com/article" --backend direct
guanlan hotnews baidu --limit 50
guanlan doctor --trace
```

## 設計メモ

Guanlan はステルスクローラーではなく、アカウント操作自動化ツールでもありません。基本方針は読み取り優先、低干渉、信源明示、認証の明示的許可です。Cookie、ブラウザ、Keychain、ログイン状態へのアクセスは、ユーザーが明確に求めた場合だけ扱います。
