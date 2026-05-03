# Guanlan

> 흐름을 보고, 출처를 따르고, 경계를 분명히 둡니다.

Guanlan은 AI 에이전트를 위한 CLI-first 중국어 인터넷 조사 및 출처 라우팅 도구입니다. 단순한 검색 래퍼가 아니라, 질문을 적절한 출처 풀로 라우팅하고, 공개 페이지를 읽고, 핫토픽을 관찰하고, 증거 패킷을 만들며, downstream agent가 공식 자료, 언론 보도, 사용자 샘플, 공개 웹 맥락을 구분할 수 있게 합니다.

공식 문서는 중국어 버전을 기준으로 관리합니다. 이 한국어 문서는 국제 사용자와 Agent 통합을 위한 동기화 요약입니다.

## 먼저 볼 문서

| 문서 | 용도 |
| --- | --- |
| [中文 README](../README.md) | 공식 포지셔닝, 설치, 예시, 릴리스 정보. |
| [변경 로그](../CHANGELOG.md) | 버전별 기능 변화와 경계 조정. |
| [Agent Playbook](agent-playbook.md) | Agent의 장기 기억: 동적 워크플로, benchmark 규칙, fallback 규칙. |
| [Agent 使用说明](agent-usage.md) | Agent용 search/read/hotnews/archive/MCP 사용법. |
| [출력 계약](contract.md) | CLI / MCP / HTTP / RAG 통합에서 안정적으로 사용할 필드. |
| [本地大模型联网指南](local-llm.md) | Ollama, LM Studio, Open WebUI 등 로컬 모델에 증거 맥락을 제공하는 방법. |
| [排障手册](troubleshooting.md) | Keychain, 네트워크, Cookie, 플랫폼 실패 진단. |
| [来源说明](SOURCE_ATTRIBUTION.md) | 참고한 오픈소스 프로젝트와 공개 출처. |

## 현재 안정적으로 사용할 수 있는 기능

- 중국어 웹에 맞춘 공개 검색, source card, evidence role, 품질 점수, 넓은 기본 후보 풀.
- URL 읽기: Jina Reader 우선, 직접 HTML fallback, 품질 리포트, strict mode, batch, cache, snapshot.
- `hotnews` 기반 중국어 핫리스트와 trend clustering. 실패한 출처와 stale cache도 표시합니다.
- `research`, `compare`, `timeline`, `dossier` 기반 증거 패킷, 비교표, 사건 타임라인, 대상 dossier.
- 로컬 archive / RAG 브리지: SQLite/FTS, ingest audit, prompt-ready context, Wiki export, LangChain/LlamaIndex/OpenWebUI pack.
- Agent 통합: CLI-first, 선택적 MCP, 선택적 로컬 read-only HTTP service, 로컬 모델용 prompt/context.

## v0.4.1 검색 안정성 개선

- Query guard: 의미 없는 입력이나 키보드 난타형 query는 백엔드 호출 전에 거부하고, 랜덤 페이지 대신 diagnostics를 반환합니다.
- Query rewrite: 짧은 사실형 query, 짧은 평판/구매 query, 지나치게 긴 query를 보수적으로 확장하거나 압축합니다.
- Recovery search: DuckDuckGo fallback과 multi-entity fan-out으로 빈 결과나 첫 번째 대상만 나오는 문제를 줄입니다.
- Agent workflow plan: 품질 요약이 `2-step`, `3-step`, `4-step` 중 어떤 Guanlan 워크플로를 먼저 완료해야 하는지 설명합니다.
- JSON 빈 결과에도 `diagnostics`를 포함할 수 있어, Agent가 “검색 실패”가 아니라 “query 재작성 필요”라고 보고할 수 있습니다.

## 주요 명령

```bash
guanlan capabilities
guanlan welcome
guanlan search "query" --profile china --limit 80
guanlan search "정책 주제" --profile china --scope party_central --trace
guanlan search "제품 리뷰" --profile china --scope ecommerce --format context
guanlan route "복합 중국어 조사 과제" --json
guanlan research "query" --profile china --advisor
guanlan compare "A" "B" --focus "가격 평판 리스크" --limit 80 --format context
guanlan timeline "사건 최신 진행" --limit 80 --format context
guanlan dossier "회사 또는 제품" --focus "사업 평판 리스크" --limit 80 --format context
guanlan read "https://example.com/article" --quality-report
guanlan hotnews today --limit 80 --trends
guanlan feeds curated --limit 80
guanlan archive ingest-research "query" --limit 80
guanlan archive context "query" --limit 20
guanlan doctor --trace
```

## Agent 워크플로 규칙

Guanlan을 단 한 번의 generic `search` 호출로 축소하지 마세요.

- `2-step`: 결과가 이미 사용 가능하면 `search -> read`.
- `3-step`: 일반 조사 또는 품질 신호가 약할 때 `route -> research -> scoped search`.
- `4-step`: 최신/핫 이슈는 `hotnews`, 기술/AI/개발자 주제는 `feeds`, 출처 다양성이 좁으면 `compare/timeline/dossier`를 추가합니다.

적절한 Guanlan 워크플로를 완료한 뒤에도 핵심 증거가 부족할 때만 generic `web_search` / `web_fetch`로 fallback합니다.

## 안전 메모

Guanlan은 은밀한 크롤러도, 계정 자동화 프레임워크도 아닙니다. 읽기 우선, 낮은 간섭, 출처 투명성, 명시적 인증을 기본 원칙으로 합니다. Cookie, 브라우저, Keychain, 로그인 상태 접근은 사용자가 명확히 요청한 경우에만 다룹니다. 게시, 댓글, 좋아요, 팔로우, 메시지 전송은 자동으로 수행하지 않습니다.
