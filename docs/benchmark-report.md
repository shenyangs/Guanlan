# Guanlan Public Quality Report / 观澜公开质量报告

- 版本: `v0.8.0`
- 生成时间: `2026-07-24T06:34:29Z`
- 口径: 确定性基准、评测套件、路由回归和质量门禁默认不触网；公网漂移只从 live-smoke 历史读取。

## 1. Deterministic Benchmark

- 场景数: 24
- 结果: pass=24 warn=0 fail=0
- 分数: 100.0
- 失败样例: 无

## 2. Eval Suite chinese-web-v1

- 任务数: 100
- 结果: pass=100 warn=0 fail=0
- 分数: 100.0
- 类别分布:
  - `academic`: total=10 pass=10 warn=0 fail=0
  - `ecommerce`: total=10 pass=10 warn=0 fail=0
  - `entertainment`: total=10 pass=10 warn=0 fail=0
  - `finance`: total=10 pass=10 warn=0 fail=0
  - `hot`: total=10 pass=10 warn=0 fail=0
  - `local`: total=10 pass=10 warn=0 fail=0
  - `local_llm`: total=10 pass=10 warn=0 fail=0
  - `policy`: total=10 pass=10 warn=0 fail=0
  - `reputation`: total=10 pass=10 warn=0 fail=0
  - `tech`: total=10 pass=10 warn=0 fail=0

## 3. Routing Regression Inventory

- 夹具: `tests/fixtures/routing_regression_cases.jsonl`
- 总数: 159
- Case types: {"near_miss": 40, "negative": 2, "positive": 117}
- 高风险类目覆盖:
  - `finance`: pass {"near_miss": 7, "positive": 9}
  - `legal_policy`: pass {"near_miss": 5, "positive": 19}
  - `entertainment`: pass {"near_miss": 1, "positive": 14}
  - `education_university`: pass {"near_miss": 2, "positive": 3}
  - `sports_local_life`: pass {"near_miss": 1, "negative": 1, "positive": 9}
  - `tech_wps`: pass {"near_miss": 6, "negative": 1, "positive": 27}
- 覆盖缺口: 无

## 4. Quality Gate Signals

| Gate | pass | warn | fail | score |
| --- | ---: | ---: | ---: | ---: |
| `foundational` | 9 | 0 | 0 | 100.0 |
| `coverage` | 10 | 0 | 0 | 100.0 |
| `regression` | 20 | 0 | 0 | 100.0 |
| `robustness` | 31 | 0 | 0 | 100.0 |
| `backend_fixtures` | 5 | 0 | 0 | 100.0 |
| `performance` | 4 | 0 | 0 | 100.0 |

## 5. Deterministic Reliability Baseline

- 状态: `configured`
- 参考版本: `v0.7.9`
- 保护项: benchmark, eval_suite, quality_regression, quality_robustness
- 边界: Deterministic quality baseline. It guards known regression, robustness, benchmark, and eval behavior; public-network availability remains a separate live-smoke concern.

## 6. Live Smoke Trend

- 状态: `no_history`
- 历史路径: `~/.guanlan/quality/live-smoke-history.jsonl`
- 边界: 未发现本地 live-smoke 历史；公开报告不伪造公网实时分数。

## 7. Distribution Surface

- 状态: `not_probed`
- 边界: 默认报告不触网；运行 scripts/distribution_status.py 可单独验证 GitHub/PyPI/Homebrew/官网。

## 8. Legacy Inventory

- 文件: `guanlan/web/_legacy_web_impl.py`
- LOC: 10127
- 顶层函数: 276
- 显式兼容入口: _bing_cjk_drift_active, _format_read_watch, _record_bing_cjk_drift, backend_order, build_query_strategy, build_research_packet, detect_search_quality_profile, rank_results, read_batch, read_url, read_url_with_trace, search_quality_summary, search_web
- 同步函数: `_sync_legacy_overrides`
- 分桶:
  - `compat`: 158
  - `other`: 11
  - `read`: 17
  - `renderers`: 25
  - `research`: 25
  - `search`: 40

## Boundary

- 确定性通过不代表公网实时一定可用；公网阻断、ICP/403、搜索后端漂移需要看 live-smoke 和 distribution status。
- pip 本机证书错误会标成 `local_tls_error`，不等同于 PyPI 仍是旧版。
- legacy inventory 是后续拆分清单，不是新增功能承诺。
