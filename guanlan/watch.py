# -*- coding: utf-8 -*-
"""Standing intent watch/radar helpers for Guanlan.

This is intentionally a thin Guanlan-native layer: no daemon, no vector DB, no
notification channel. A watch intent stores the user's long-running concern and
reuses existing search/feed/research surfaces when an agent fires it.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guanlan.limits import DEFAULT_FEEDS_LIMIT, DEFAULT_SEARCH_LIMIT
from guanlan.profiles import VALID_PROFILES

STORE_VERSION = 1
DEFAULT_WATCH_LIMIT = 30
MAX_SEEN_PER_INTENT = 1000


def default_watch_store_path() -> Path:
    return Path.home() / ".guanlan" / "watch-intents.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _watch_store_path(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path else default_watch_store_path()


def _empty_store() -> dict[str, Any]:
    return {"version": STORE_VERSION, "intents": []}


def load_watch_store(path: str | Path | None = None) -> dict[str, Any]:
    store_path = _watch_store_path(path)
    if not store_path.exists():
        return _empty_store()
    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    intents = data.get("intents")
    if not isinstance(intents, list):
        intents = []
    return {"version": int(data.get("version") or STORE_VERSION), "intents": intents}


def save_watch_store(store: dict[str, Any], path: str | Path | None = None) -> Path:
    store_path = _watch_store_path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": STORE_VERSION, "intents": list(store.get("intents") or [])}
    tmp = store_path.with_suffix(store_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(store_path)
    return store_path


def _slugify(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    if not lowered:
        lowered = "watch"
    return lowered[:48].strip("-") or "watch"


def _unique_intent_id(base: str, existing_ids: set[str]) -> str:
    candidate = _slugify(base)
    if candidate not in existing_ids:
        return candidate
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:6]
    candidate = f"{candidate[:40].strip('-')}-{digest}"
    if candidate not in existing_ids:
        return candidate
    idx = 2
    while f"{candidate}-{idx}" in existing_ids:
        idx += 1
    return f"{candidate}-{idx}"


def _clean_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        cleaned.append(value)
        seen.add(value)
    return cleaned[:12]


def _normalize_profile(profile: str | None) -> str:
    value = (profile or "china").strip()
    return value if value in VALID_PROFILES else "china"


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def create_watch_intent(
    query: str,
    *,
    name: str = "",
    intent_id: str = "",
    profile: str = "china",
    scope: str = "",
    site: str = "",
    preset: str = "",
    feed_source: str = "auto",
    watchlist_path: str = "",
    lens: str = "",
    schedule: str = "",
    tags: list[str] | None = None,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("watch intent query is required")
    store = load_watch_store(store_path)
    existing_ids = {str(item.get("id") or "") for item in store.get("intents") or []}
    created_at = _now_iso()
    generated_id = intent_id.strip() or _unique_intent_id(name or clean_query, existing_ids)
    if generated_id in existing_ids:
        raise ValueError(f"watch intent id already exists: {generated_id}")
    intent = {
        "id": generated_id,
        "name": name.strip() or clean_query[:80],
        "query": clean_query,
        "profile": _normalize_profile(profile),
        "scope": scope.strip(),
        "site": site.strip(),
        "preset": preset.strip(),
        "feed_source": (feed_source or "auto").strip() or "auto",
        "watchlist_path": watchlist_path.strip(),
        "lens": lens.strip(),
        "schedule": schedule.strip(),
        "tags": _clean_tags(tags),
        "created_at": created_at,
        "updated_at": created_at,
        "last_fired_at": "",
        "seen": {},
    }
    store.setdefault("intents", []).append(intent)
    save_watch_store(store, store_path)
    return _public_intent(intent, include_seen=False)


def list_watch_intents(*, store_path: str | Path | None = None, include_seen: bool = False) -> list[dict[str, Any]]:
    store = load_watch_store(store_path)
    return [_public_intent(item, include_seen=include_seen) for item in store.get("intents") or []]


def get_watch_intent(identifier: str, *, store_path: str | Path | None = None, include_seen: bool = False) -> dict[str, Any]:
    _store, _idx, intent = _find_intent(identifier, store_path=store_path)
    return _public_intent(intent, include_seen=include_seen)


def remove_watch_intent(identifier: str, *, store_path: str | Path | None = None) -> dict[str, Any]:
    store, idx, intent = _find_intent(identifier, store_path=store_path)
    removed = store["intents"].pop(idx)
    save_watch_store(store, store_path)
    return _public_intent(removed or intent, include_seen=False)


def build_watch_plan(
    query: str,
    *,
    profile: str = "china",
    scope: str = "",
    site: str = "",
    preset: str = "",
    feed_source: str = "auto",
    watchlist_path: str = "",
    lens: str = "",
    schedule: str = "",
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("watch plan query is required")
    profile = _normalize_profile(profile)
    effective_limit = max(limit, 1)
    route_plan = _route_plan(clean_query, profile=profile, scope=scope, site=site, limit=effective_limit)
    intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    resolved_feed = _resolve_feed_source(feed_source, intents)
    inferred_preset = preset.strip() or _preset_for_intents(intents)
    add_parts = ["guanlan", "watch", "add", clean_query]
    if profile:
        add_parts.extend(["--profile", profile])
    if scope:
        add_parts.extend(["--scope", scope])
    if site:
        add_parts.extend(["--site", site])
    if inferred_preset:
        add_parts.extend(["--preset", inferred_preset])
    if resolved_feed:
        add_parts.extend(["--feed-source", resolved_feed])
    if watchlist_path:
        add_parts.extend(["--watchlist", watchlist_path])
    if lens:
        add_parts.extend(["--lens", lens])
    if schedule:
        add_parts.extend(["--schedule", schedule])
    research_parts = ["guanlan", "research", clean_query, "--limit", str(max(effective_limit, 80)), "--read-top", "3"]
    if inferred_preset:
        research_parts.extend(["--preset", inferred_preset])
    if profile:
        research_parts.extend(["--profile", profile])
    return {
        "query": clean_query,
        "mode": "standing_intent",
        "boundary": "local_watch_plan; no daemon; no notification; fire reuses Guanlan search/feed surfaces",
        "route_plan": route_plan,
        "suggested_feed_source": resolved_feed,
        "suggested_preset": inferred_preset,
        "lens": lens.strip(),
        "schedule": schedule.strip(),
        "storage": str(default_watch_store_path()),
        "commands": {
            "create": _shell_join(add_parts),
            "diagnostic_fire": "guanlan watch fire <id> --limit 30",
            "recording_fire": "guanlan watch fire <id> --record-seen --limit 30",
            "deep_research": _shell_join(research_parts),
        },
        "notes": [
            "第一版 watch 是轻量拉取式雷达，不启动后台服务；定时可交给外部 Agent/cron 调用 fire。",
            "fire 默认不写 seen，适合诊断；加 --record-seen 才更新去重状态。",
            "向量匹配暂不默认启用；先用 Guanlan 路由、搜索、RSS 和来源质量做低依赖匹配。",
        ],
    }


def fire_watch_intent(
    identifier: str,
    *,
    limit: int = DEFAULT_WATCH_LIMIT,
    feed_limit: int | None = None,
    search_limit: int | None = None,
    search_backend: str = "auto",
    record_seen: bool = False,
    store_path: str | Path | None = None,
    cache_ttl: int = 0,
) -> dict[str, Any]:
    store, idx, intent = _find_intent(identifier, store_path=store_path)
    fired_at = _now_iso()
    limit = max(limit, 1)
    route_plan = _route_plan(
        str(intent.get("query") or ""),
        profile=str(intent.get("profile") or "china"),
        scope=str(intent.get("scope") or ""),
        site=str(intent.get("site") or ""),
        limit=max(search_limit or limit, 1),
    )
    route_intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    feed_source = _resolve_feed_source(str(intent.get("feed_source") or "auto"), route_intents)
    search_items, search_error = _collect_search_items(
        intent,
        limit=max(search_limit or limit, 1),
        backend=search_backend,
        cache_ttl=cache_ttl,
    )
    feed_items, feed_error = _collect_feed_items(
        intent,
        source=feed_source,
        limit=max(feed_limit or min(limit, DEFAULT_FEEDS_LIMIT), 1),
        route_intents=route_intents,
    )
    combined = _merge_items([*search_items, *feed_items], query=str(intent.get("query") or ""))
    seen = dict(intent.get("seen") or {})
    output_items: list[dict[str, Any]] = []
    for rank, item in enumerate(combined[:limit], 1):
        fingerprint = item["fingerprint"]
        row = dict(item)
        row["rank"] = rank
        row["is_new"] = fingerprint not in seen
        output_items.append(row)
        if record_seen:
            seen[fingerprint] = {
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "source": row.get("source", ""),
                "first_seen_at": seen.get(fingerprint, {}).get("first_seen_at") or fired_at,
                "last_seen_at": fired_at,
            }
    if record_seen:
        intent["seen"] = _trim_seen(seen)
        intent["last_fired_at"] = fired_at
        intent["updated_at"] = fired_at
        store["intents"][idx] = intent
        save_watch_store(store, store_path)
    diagnostics = {
        "search": {"status": "error" if search_error else "ok", "error": search_error, "count": len(search_items)},
        "feeds": {"status": "error" if feed_error else "ok", "error": feed_error, "source": feed_source, "count": len(feed_items)},
        "record_seen": record_seen,
        "match_mode": "route_keyword_source_quality",
    }
    new_count = sum(1 for item in output_items if item.get("is_new"))
    return {
        "intent": _public_intent(intent, include_seen=False),
        "fired_at": fired_at,
        "route_plan": route_plan,
        "diagnostics": diagnostics,
        "items": output_items,
        "new_count": new_count,
        "repeated_count": len(output_items) - new_count,
        "boundary": "watch_fire; no notification; seen state changes only when record_seen=true",
        "next_steps": _watch_next_steps(intent, new_count=new_count, feed_source=feed_source),
    }


def format_watch_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Guanlan Watch 计划",
        "",
        f"- 关注意图: {plan.get('query', '')}",
        f"- 建议 feed: {plan.get('suggested_feed_source', '')}",
        f"- 建议 preset: {plan.get('suggested_preset', '') or 'general'}",
        f"- 边界: {plan.get('boundary', '')}",
        "",
        "## 推荐命令",
    ]
    commands = plan.get("commands") or {}
    for key in ("create", "diagnostic_fire", "recording_fire", "deep_research"):
        if commands.get(key):
            lines.append(f"- {key}: `{commands[key]}`")
    notes = plan.get("notes") or []
    if notes:
        lines.extend(["", "## 说明"])
        lines.extend([f"- {note}" for note in notes])
    route_plan = plan.get("route_plan") or {}
    if route_plan:
        intents = ", ".join((route_plan.get("primary_intents") or []) + (route_plan.get("secondary_intents") or []))
        scopes = ", ".join(route_plan.get("preferred_scopes") or [])
        lines.extend(["", "## 路由", f"- intents: {intents or 'general'}", f"- scopes: {scopes or 'open_web'}"])
    return "\n".join(lines)


def format_watch_list_markdown(intents: list[dict[str, Any]]) -> str:
    if not intents:
        return "# Guanlan Watch\n\n当前没有保存的长期关注意图。用 `guanlan watch add \"关注主题\"` 创建一个。"
    lines = ["# Guanlan Watch", ""]
    for item in intents:
        lines.append(f"- `{item.get('id')}` {item.get('name')}")
        lines.append(f"  query: {item.get('query')}")
        meta = []
        for key in ("profile", "scope", "site", "feed_source", "schedule", "last_fired_at"):
            if item.get(key):
                meta.append(f"{key}={item[key]}")
        if meta:
            lines.append(f"  {', '.join(meta)}")
    return "\n".join(lines)


def format_watch_intent_markdown(intent: dict[str, Any]) -> str:
    lines = [
        f"# Guanlan Watch / {intent.get('id')}",
        "",
        f"- 名称: {intent.get('name')}",
        f"- 关注意图: {intent.get('query')}",
        f"- profile: {intent.get('profile')}",
        f"- scope: {intent.get('scope') or 'auto'}",
        f"- site: {intent.get('site') or 'none'}",
        f"- feed_source: {intent.get('feed_source')}",
        f"- schedule: {intent.get('schedule') or 'manual'}",
        f"- lens: {intent.get('lens') or 'default'}",
        f"- seen_count: {intent.get('seen_count', 0)}",
        f"- last_fired_at: {intent.get('last_fired_at') or 'never'}",
    ]
    if intent.get("tags"):
        lines.append(f"- tags: {', '.join(intent.get('tags') or [])}")
    return "\n".join(lines)


def format_watch_fire_markdown(report: dict[str, Any]) -> str:
    intent = report.get("intent") or {}
    lines = [
        f"# Guanlan Watch Fire / {intent.get('id', '')}",
        "",
        f"- 关注意图: {intent.get('query', '')}",
        f"- 本次候选: {len(report.get('items') or [])}",
        f"- 新线索: {report.get('new_count', 0)}",
        f"- 重复线索: {report.get('repeated_count', 0)}",
        f"- 边界: {report.get('boundary', '')}",
    ]
    diagnostics = report.get("diagnostics") or {}
    lines.append(f"- feeds: {(diagnostics.get('feeds') or {}).get('source', '')} / {(diagnostics.get('feeds') or {}).get('status', '')}")
    if (diagnostics.get("search") or {}).get("error"):
        lines.append(f"- search_error: {(diagnostics.get('search') or {}).get('error')}")
    if (diagnostics.get("feeds") or {}).get("error"):
        lines.append(f"- feeds_error: {(diagnostics.get('feeds') or {}).get('error')}")
    lines.extend(["", "## 线索"])
    for item in report.get("items") or []:
        marker = "NEW" if item.get("is_new") else "seen"
        title = item.get("title") or "(untitled)"
        url = item.get("url") or ""
        source = item.get("source") or item.get("origin") or ""
        role = item.get("evidence_role") or ""
        if url:
            lines.append(f"{item.get('rank')}. [{marker}] [{source}] {title} - {url}")
        else:
            lines.append(f"{item.get('rank')}. [{marker}] [{source}] {title}")
        if role:
            lines.append(f"   role: {role}")
        if item.get("summary"):
            lines.append(f"   摘要: {item['summary']}")
    next_steps = report.get("next_steps") or []
    if next_steps:
        lines.extend(["", "## 下一步"])
        lines.extend([f"- {step}" for step in next_steps])
    return "\n".join(lines)


def _public_intent(intent: dict[str, Any], *, include_seen: bool) -> dict[str, Any]:
    row = dict(intent)
    seen = row.get("seen") if isinstance(row.get("seen"), dict) else {}
    row["seen_count"] = len(seen)
    if not include_seen:
        row.pop("seen", None)
    return row


def _find_intent(identifier: str, *, store_path: str | Path | None = None) -> tuple[dict[str, Any], int, dict[str, Any]]:
    needle = identifier.strip()
    if not needle:
        raise ValueError("watch intent id or name is required")
    store = load_watch_store(store_path)
    for idx, item in enumerate(store.get("intents") or []):
        if needle in {str(item.get("id") or ""), str(item.get("name") or "")}:
            return store, idx, item
    raise KeyError(f"watch intent not found: {needle}")


def _route_plan(query: str, *, profile: str, scope: str, site: str, limit: int) -> dict[str, Any]:
    from guanlan.router import build_route_plan

    return build_route_plan(
        query,
        scope=scope or None,
        site=site or None,
        profile=profile or None,
        limit=max(limit, 1),
    ).to_dict()


def _preset_for_intents(intents: list[str]) -> str:
    ordered = [
        "company",
        "wps_office",
        "cybersecurity",
        "finance",
        "global_entertainment",
        "jp_kr_entertainment",
        "entertainment",
        "sports",
        "science",
        "career",
        "academic",
        "university",
        "tech",
        "reputation",
        "policy",
    ]
    mapping = {"company_primary": "company", "university_admissions": "university", "hot_trend": "general"}
    normalized = [mapping.get(intent, intent) for intent in intents]
    for candidate in ordered:
        if candidate in normalized:
            return candidate
    return "general"


def _resolve_feed_source(feed_source: str, intents: list[str]) -> str:
    requested = (feed_source or "auto").strip()
    if requested and requested != "auto":
        return requested
    intent_set = set(intents)
    if "academic" in intent_set:
        return "arxiv"
    if "hot_trend" in intent_set:
        return "baidu-rss"
    return "curated"


def _collect_search_items(
    intent: dict[str, Any],
    *,
    limit: int,
    backend: str,
    cache_ttl: int,
) -> tuple[list[dict[str, Any]], str]:
    from guanlan.web.search import search_web

    try:
        rows = search_web(
            str(intent.get("query") or ""),
            limit=max(limit, 1),
            site=str(intent.get("site") or "") or None,
            scope=str(intent.get("scope") or "") or None,
            backend=backend or "auto",
            profile=str(intent.get("profile") or "") or None,
            cache_ttl=max(cache_ttl, 0),
            recovery_mode="lite",
        )
    except Exception as exc:
        return [], str(exc)
    items = []
    for row in rows:
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or row.get("href") or "").strip()
        summary = str(row.get("snippet") or row.get("summary") or "").strip()
        items.append(
            _normalize_item(
                title=title,
                url=url,
                summary=summary,
                source=str(row.get("source") or "search"),
                origin="search",
                evidence_role=str(row.get("evidence_role") or row.get("source_type") or "search_result"),
                published_at=str(row.get("published_at") or row.get("date") or ""),
                extra={"source_type": row.get("source_type", ""), "matched_scope": row.get("matched_scope", "")},
            )
        )
    return items, ""


def _collect_feed_items(
    intent: dict[str, Any],
    *,
    source: str,
    limit: int,
    route_intents: list[str],
) -> tuple[list[dict[str, Any]], str]:
    from guanlan.feeds import fetch_feed_source

    query = str(intent.get("query") or "")
    keyword = query if source in {"curated", "arxiv", "curated-sources", "ai-official", "ai-media"} else None
    if source == "watchlist":
        keyword = None
    try:
        rows = fetch_feed_source(
            source,
            limit=max(limit, 1),
            keyword=keyword,
            watchlist_path=str(intent.get("watchlist_path") or "") or None,
            category="ai" if "tech" in set(route_intents) else None,
        )
    except Exception as exc:
        return [], str(exc)
    items: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        summary = str(row.get("summary") or "").strip()
        items.append(
            _normalize_item(
                title=title,
                url=url,
                summary=summary,
                source=str(row.get("source_title") or row.get("source_id") or source),
                origin=f"feeds:{source}",
                evidence_role=str(row.get("evidence_role") or "feed_signal"),
                published_at=str(row.get("published_at") or ""),
                extra={"risk_tags": row.get("risk_tags", []), "feed_status": row.get("feed_status", {})},
            )
        )
    return items, ""


def _normalize_item(
    *,
    title: str,
    url: str,
    summary: str,
    source: str,
    origin: str,
    evidence_role: str,
    published_at: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fingerprint = _fingerprint(title=title, url=url)
    return {
        "title": title,
        "url": url,
        "summary": summary[:500],
        "source": source,
        "origin": origin,
        "evidence_role": evidence_role,
        "published_at": published_at,
        "fingerprint": fingerprint,
        **(extra or {}),
    }


def _merge_items(items: list[dict[str, Any]], *, query: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in items:
        fingerprint = str(item.get("fingerprint") or _fingerprint(title=str(item.get("title") or ""), url=str(item.get("url") or "")))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        row = dict(item)
        row["fingerprint"] = fingerprint
        row["match_score"] = _lexical_match_score(query, row)
        merged.append(row)
    merged.sort(
        key=lambda row: (
            float(row.get("match_score") or 0.0),
            1 if str(row.get("origin") or "").startswith("search") else 0,
            str(row.get("published_at") or ""),
        ),
        reverse=True,
    )
    return merged


def _fingerprint(*, title: str, url: str) -> str:
    key = (url or title).strip().lower()
    if not key:
        key = title.strip().lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _lexical_match_score(query: str, item: dict[str, Any]) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    haystack = f"{item.get('title', '')} {item.get('summary', '')} {item.get('url', '')}".lower()
    hits = sum(1 for term in terms if term in haystack)
    return round(hits / max(len(terms), 1), 4)


def _query_terms(query: str) -> list[str]:
    ascii_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,}", query.lower())
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    terms = [*ascii_terms, *cjk_terms]
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped[:12]


def _trim_seen(seen: dict[str, Any]) -> dict[str, Any]:
    rows = sorted(
        seen.items(),
        key=lambda kv: str((kv[1] or {}).get("last_seen_at") or (kv[1] or {}).get("first_seen_at") or ""),
        reverse=True,
    )
    return dict(rows[:MAX_SEEN_PER_INTENT])


def _watch_next_steps(intent: dict[str, Any], *, new_count: int, feed_source: str) -> list[str]:
    query = str(intent.get("query") or "")
    steps = []
    if new_count:
        steps.append("对 NEW 线索中最关键的原始 URL 运行 `guanlan read URL --quality-report`，再下结论。")
        steps.append(f"需要沉淀长期记忆时运行 `guanlan archive ingest-research {shlex.quote(query)} --limit 80 --read-top 3`。")
    else:
        steps.append("本轮没有新线索；如果这是严肃观察，下一轮保持 80 条候选池，不要因为短期安静就判断没有变化。")
    if feed_source == "watchlist":
        steps.append("watchlist 依赖用户维护的 RSS 清单，覆盖边界应标注为 user_watchlist/feed_dependent。")
    return steps


def _shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)
