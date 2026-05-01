# Guanlan

> 흐름을 보고, 출처를 따르고, 경계를 분명히 둡니다.

Guanlan은 AI 에이전트를 위한 중국어 인터넷 검색 및 출처 라우팅 도구입니다. 공개 웹 검색, URL 읽기, 중국어 핫뉴스, 출처 분류를 결합해 에이전트가 근거를 남기며 조사할 수 있게 합니다.

공식 문서는 중국어 버전을 기준으로 관리합니다.

- [中文 README](../README.md)
- [Agent 使用说明](agent-usage.md)
- [중문 인터넷 설계](chinese-web-design.md)
- [排障手册](troubleshooting.md)
- [来源说明](SOURCE_ATTRIBUTION.md)

## 주요 명령

```bash
guanlan search "keyword" --profile china --limit 50
guanlan search "keyword" --profile china --scope party_central
guanlan search "keyword" --profile china --scope ecommerce
guanlan read "https://example.com/article"
guanlan read "https://example.com/article" --backend direct
guanlan hotnews baidu --limit 50
guanlan doctor --trace
```

## 설계 메모

Guanlan은 은밀한 크롤러도, 계정 자동화 프레임워크도 아닙니다. 기본 방향은 읽기 우선, 낮은 간섭, 출처 투명성, 명시적 인증입니다. Cookie, 브라우저, Keychain, 로그인 상태 접근은 사용자가 명확히 요청한 경우에만 다룹니다.
