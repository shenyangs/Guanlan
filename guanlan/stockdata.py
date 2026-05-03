# -*- coding: utf-8 -*-
"""Structured stock and market data helpers for Guanlan.

This module intentionally uses public, no-login endpoints and keeps the output
evidence-like: source, timestamp, and boundaries are always visible.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import requests

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GuanlanStock/1.0)",
    "Referer": "https://gu.qq.com/",
    "Accept": "application/json,text/plain,*/*",
}

QUOTE_ENDPOINT = "https://sqt.gtimg.cn"
SEARCH_ENDPOINT = "https://proxy.finance.qq.com/cgi/cgi-bin/smartbox/search"
RANK_ENDPOINT = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
MARKET_ENDPOINT = "https://proxy.finance.qq.com/cgi/cgi-bin/market/hs/index"
FUNDFLOW_ENDPOINT = "https://proxy.finance.qq.com/cgi/cgi-bin/fundflow/hsfundtab"
PLATE_ENDPOINT = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/stockinfo/plateNew"
NEWS_ENDPOINT = "https://proxy.finance.qq.com/ifzqgtimg/appstock/news/info/search"

SOURCE_NAME = "腾讯财经公开接口"
EASTMONEY_SOURCE_NAME = "东方财富公开接口"

_A_CODE_PATTERN = re.compile(r"^(?:[56]\d{5}|[031]\d{5}|4\d{5}|8\d{5}|92\d{4})$")
_HK_CODE_PATTERN = re.compile(r"^\d{5}$")
_US_TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,3})?$")
_A_CODE_IN_TEXT = re.compile(r"(?<!\d)([0568134]\d{5}|92\d{4})(?!\d)")
_US_STOPWORDS = {
    "AI",
    "API",
    "APP",
    "CEO",
    "CLI",
    "CPI",
    "ETF",
    "GDP",
    "HTTP",
    "IPO",
    "JSON",
    "LLM",
    "MCP",
    "NBA",
    "PDF",
    "PPI",
    "RSS",
    "SEC",
    "URL",
}
_SYMBOL_ALIASES = {
    "上证指数": "sh000001",
    "沪指": "sh000001",
    "深证成指": "sz399001",
    "深成指": "sz399001",
    "创业板指": "sz399006",
    "平安银行": "000001",
    "贵州茅台": "600519",
    "宁德时代": "300750",
    "寒武纪": "688256",
    "工业富联": "601138",
    "腾讯控股": "hk00700",
    "腾讯": "hk00700",
    "阿里巴巴": "hk09988",
    "美团": "hk03690",
    "英伟达": "usNVDA",
    "nvidia": "usNVDA",
    "特斯拉": "usTSLA",
    "tesla": "usTSLA",
    "苹果": "usAAPL",
    "apple": "usAAPL",
    "微软": "usMSFT",
    "microsoft": "usMSFT",
    "谷歌": "usGOOGL",
    "google": "usGOOGL",
    "meta": "usMETA",
    "亚马逊": "usAMZN",
    "amazon": "usAMZN",
}
_QUERY_NOISE_TERMS = (
    "股票",
    "股价",
    "行情",
    "实时",
    "今日",
    "今天",
    "最近",
    "最新",
    "财报",
    "公告",
    "风险",
    "资金流向",
    "主力",
    "涨跌幅",
    "涨跌",
    "盘口",
    "雪球",
    "股吧",
    "研报",
    "估值",
    "怎么样",
    "为什么",
    "分析",
    "查询",
    "查一下",
)


class StockDataError(RuntimeError):
    """Raised when a stock data endpoint cannot provide usable data."""


def infer_stock_target(query: str) -> str:
    """Infer a compact stock target from a noisy finance query."""
    raw = " ".join((query or "").split()).strip()
    if not raw:
        return ""
    code_match = _A_CODE_IN_TEXT.search(raw)
    if code_match:
        return code_match.group(1)
    lowered = raw.lower()
    for name, symbol in _SYMBOL_ALIASES.items():
        if name.lower() in lowered:
            return symbol
    upper_tokens = re.findall(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b", raw)
    for token in upper_tokens:
        if token not in _US_STOPWORDS and _US_TICKER_PATTERN.fullmatch(token):
            return f"us{token.split('.', 1)[0]}"
    cleaned = raw
    for term in _QUERY_NOISE_TERMS:
        cleaned = cleaned.replace(term, " ")
    cleaned = re.sub(r"[，。；、:：/|]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Keep the first meaningful Chinese/company token for symbol search.
    for token in cleaned.split():
        if len(token) >= 2:
            return token
    return cleaned or raw


def normalize_symbol(symbol: str) -> str:
    """Normalize common A/HK/US stock symbols to the public quote endpoint format."""
    raw = (symbol or "").strip()
    if not raw:
        return ""
    alias = _SYMBOL_ALIASES.get(raw) or _SYMBOL_ALIASES.get(raw.lower())
    if alias:
        return normalize_symbol(alias)
    compact = raw.replace(" ", "")
    if re.fullmatch(r"(?i)(sh|sz|bj)\d{6}", compact):
        return compact.lower()
    if re.fullmatch(r"(?i)hk\d{5}", compact):
        return "hk" + compact[-5:]
    if re.fullmatch(r"(?i)us[A-Z]{1,5}(?:\.[A-Z]{1,3})?", compact):
        ticker = compact[2:].split(".", 1)[0].upper()
        return f"us{ticker}"
    lower = compact.lower()
    if _A_CODE_PATTERN.fullmatch(lower):
        if re.fullmatch(r"(?:5|6)\d{5}", lower):
            return f"sh{lower}"
        if re.fullmatch(r"(?:0|3|1)\d{5}", lower):
            return f"sz{lower}"
        if re.fullmatch(r"(?:4\d{5}|8\d{5}|92\d{4})", lower):
            return f"bj{lower}"
    if _HK_CODE_PATTERN.fullmatch(lower):
        return f"hk{lower}"
    if _US_TICKER_PATTERN.fullmatch(compact.upper()) and compact.upper() not in _US_STOPWORDS:
        return f"us{compact.upper().split('.', 1)[0]}"
    return raw


def resolve_symbol(target: str) -> str:
    """Resolve a code/name/noisy query to a quote symbol."""
    inferred = infer_stock_target(target)
    normalized = normalize_symbol(inferred or target)
    if _looks_like_quote_symbol(normalized):
        return normalized
    candidates = search_stocks(inferred or target, limit=8)["items"]
    for item in candidates:
        if str(item.get("type", "")).startswith(("GP", "ZS")):
            code = str(item.get("code") or "")
            if code:
                return normalize_symbol(code)
    raise StockDataError(f"未找到可用股票/指数代码：{target}")


def quote_stock(target: str) -> dict[str, Any]:
    symbol = resolve_symbol(target)
    payload = _fetch_quote_json(symbol)
    arr = payload.get(symbol)
    if not isinstance(arr, list) or len(arr) < 35:
        raise StockDataError(f"暂无行情数据：{target}")
    quote = _quote_arr_to_obj(arr, symbol=symbol)
    quote["source"] = SOURCE_NAME
    quote["source_role"] = "market_quote"
    quote["retrieved_at"] = _now()
    quote["boundary"] = "公开行情接口可能延迟；仅作信息核验，不构成投资建议。"
    return quote


def search_stocks(keyword: str, *, limit: int = 20) -> dict[str, Any]:
    clean = infer_stock_target(keyword) or keyword
    payload = _http_get_json(
        SEARCH_ENDPOINT,
        params={"stockFlag": "1", "fundFlag": "1", "app": "official_website", "query": clean},
    )
    stocks = payload.get("stock") if isinstance(payload, dict) else []
    items: list[dict[str, Any]] = []
    if isinstance(stocks, list):
        for item in stocks[: max(limit, 0)]:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "code": str(item.get("code") or ""),
                    "name": str(item.get("name") or ""),
                    "type": str(item.get("type") or ""),
                    "match_field": str((item.get("reportInfo") or {}).get("match_field") or ""),
                    "match_level": str((item.get("reportInfo") or {}).get("match_level") or ""),
                }
            )
    return {
        "query": keyword,
        "normalized_query": clean,
        "items": items,
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "股票名称搜索只用于定位代码；后续行情、披露和新闻仍需分层核验。",
    }


def rank_stocks(
    *,
    sort: str = "turnover",
    direct: str = "down",
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    payload = _http_get_json(
        RANK_ENDPOINT,
        params={
            "_appver": "11.17.0",
            "board_code": "aStock",
            "sort_type": sort,
            "direct": direct,
            "offset": str(max(offset, 0)),
            "count": str(min(max(limit, 1), 100)),
        },
    )
    data = payload.get("data") if isinstance(payload, dict) else {}
    raw_items = data.get("rank_list") if isinstance(data, dict) else []
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "code": str(item.get("code") or ""),
                    "name": str(item.get("name") or ""),
                    "price": str(item.get("zxj") or ""),
                    "change_rate": _zdf_percent(str(item.get("zdf") or "")),
                    "turnover": str(item.get("turnover") or ""),
                    "turnover_rate": _percent(str(item.get("hsl") or "")),
                    "volume_ratio": str(item.get("lb") or ""),
                    "market_value": _billion(str(item.get("zsz") or "")),
                    "float_market_value": _billion(str(item.get("ltsz") or "")),
                    "pe_ttm": str(item.get("pe_ttm") or ""),
                    "net_main_in": _wan_text(item.get("zljlr")),
                }
            )
    return {
        "sort": sort,
        "direct": direct,
        "offset": int(data.get("offset", offset) or 0) if isinstance(data, dict) else offset,
        "total": int(data.get("total", 0) or 0) if isinstance(data, dict) else 0,
        "items": items,
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "榜单受市场时间、接口延迟和排序口径影响；不能直接推导投资结论，不构成投资建议。",
    }


def fundflow(target: str) -> dict[str, Any]:
    symbol = resolve_symbol(target)
    payload = _http_get_json(
        FUNDFLOW_ENDPOINT,
        params={"code": symbol, "type": "fiveDayFundFlow,todayFundFlow", "klineNeedDay": "20"},
    )
    if payload.get("code") not in {0, "0"}:
        raise StockDataError(str(payload.get("msg") or "资金流向接口返回错误"))
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    today = data.get("todayFundFlow") if isinstance(data.get("todayFundFlow"), dict) else {}
    five_day = data.get("fiveDayFundFlow") if isinstance(data.get("fiveDayFundFlow"), dict) else {}
    rows = []
    for item in five_day.get("DayMainNetInList") or []:
        if isinstance(item, dict):
            rows.append({"date": str(item.get("date") or ""), "main_net_in": _money_wan(item.get("mainNetIn"))})
    return {
        "symbol": symbol,
        "summary": str((today.get("summary") or {}).get("s0") or ""),
        "today": {
            "main_in": _money_wan(today.get("mainIn")),
            "main_in_rate": _percent(today.get("mainInRate")),
            "main_out": _money_wan(today.get("mainOut")),
            "main_out_rate": _percent(today.get("mainOutRate")),
            "retail_in": _money_wan(today.get("retailIn")),
            "retail_in_rate": _percent(today.get("retailInRate")),
            "retail_out": _money_wan(today.get("retailOut")),
            "retail_out_rate": _percent(today.get("retailOutRate")),
            "super_flow": _money_wan(today.get("superFlow")),
            "big_flow": _money_wan(today.get("bigFlow")),
            "normal_flow": _money_wan(today.get("normalFlow")),
            "small_flow": _money_wan(today.get("smallFlow")),
            "main_net_in": _money_wan(today.get("mainNetIn")),
        },
        "five_day_main_net_in": rows,
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "资金流向是接口口径下的交易统计，不代表因果判断或投资建议。",
    }


def related_plates(target: str) -> dict[str, Any]:
    symbol = resolve_symbol(target)
    payload = _http_get_json(PLATE_ENDPOINT, params={"code": symbol, "app": "wzq", "zdf": "1"})
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    return {
        "symbol": symbol,
        "area": _plate_items(data.get("area")),
        "industry": _plate_items(data.get("plate")),
        "concept": _plate_items(data.get("concept")),
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "板块/概念归类来自公开接口，适合作为线索，需和公司业务及公告交叉核验。",
    }


def latest_news(target: str, *, limit: int = 12) -> dict[str, Any]:
    symbol = resolve_symbol(target)
    payload = _http_get_json(NEWS_ENDPOINT, params={"page": "1", "symbol": symbol, "n": str(limit), "type": "2"})
    data = payload.get("data") if isinstance(payload, dict) else {}
    raw_items = data.get("data") if isinstance(data, dict) else []
    items: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for item in raw_items[: max(limit, 0)]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if title:
                items.append({"time": str(item.get("time") or ""), "title": title})
    return {
        "symbol": symbol,
        "items": items,
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "快讯是新闻线索，不替代公告、财报和监管披露。",
    }


def market_index() -> dict[str, Any]:
    quotes = []
    payload = _fetch_quote_json("sh000001,sz399001,sz399006")
    for symbol in ("sh000001", "sz399001", "sz399006"):
        arr = payload.get(symbol)
        if isinstance(arr, list) and len(arr) >= 35:
            quotes.append(_quote_arr_to_obj(arr, symbol=symbol))
    overview = _fetch_market_overview()
    return {
        "quotes": quotes,
        "overview": overview,
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "市场概览来自公开行情接口，可能有交易日和延迟差异；仅作研究线索。",
    }


def stock_detail(target: str, *, news_limit: int = 12) -> dict[str, Any]:
    symbol = resolve_symbol(target)
    sections: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, fn in (
        ("quote", lambda: quote_stock(symbol)),
        ("fundflow", lambda: fundflow(symbol)),
        ("plates", lambda: related_plates(symbol)),
        ("news", lambda: latest_news(symbol, limit=news_limit)),
    ):
        try:
            sections[key] = fn()
        except StockDataError as exc:
            errors[key] = str(exc)
    return {
        "query": target,
        "symbol": symbol,
        **sections,
        "errors": errors,
        "source": SOURCE_NAME,
        "retrieved_at": _now(),
        "boundary": "结构化行情适合补足动态财经页/WAF导致的缺口；财报公告和监管事项仍应回到披露源核验。",
    }


def format_search_markdown(data: dict[str, Any]) -> str:
    lines = [f"# 观澜股票搜索 / {data.get('query', '')}", ""]
    items = data.get("items") or []
    if not items:
        lines.append("暂无匹配股票/指数。")
    else:
        lines.extend(["```csv", "代码,名称,类型,匹配字段,匹配级别"])
        for item in items:
            lines.append(",".join([item.get("code", ""), item.get("name", ""), item.get("type", ""), item.get("match_field", ""), item.get("match_level", "")]))
        lines.append("```")
    lines.extend(_footer(data))
    return "\n".join(lines)


def format_quote_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# 观澜行情 / {data.get('name', '')} {data.get('symbol', '')}",
        "",
        f"- 时间: {data.get('time', '')}",
        f"- 代码: {data.get('symbol', '')}",
        f"- 名称: {data.get('name', '')}",
        f"- 价格: {data.get('price', '')}",
        f"- 涨跌幅: {data.get('change_rate', '')}",
        f"- 昨收价: {data.get('previous_close', '')}",
        f"- 开盘价: {data.get('open', '')}",
        f"- 最高价: {data.get('high', '')}",
        f"- 最低价: {data.get('low', '')}",
        f"- 总市值: {data.get('market_value', '')}",
        f"- 流通市值: {data.get('circulating_value', '')}",
        f"- 市盈率: {data.get('pe', '')}",
        f"- 市净率: {data.get('pb', '')}",
        f"- 成交量: {data.get('volume', '')}",
        f"- 量比: {data.get('volume_ratio', '')}",
        f"- 换手率: {data.get('turnover_rate', '')}",
    ]
    lines.extend(_footer(data))
    return "\n".join(lines)


def format_rank_markdown(data: dict[str, Any]) -> str:
    lines = [f"# 观澜股票榜单 / {data.get('sort')} {data.get('direct')}", ""]
    items = data.get("items") or []
    if not items:
        lines.append("暂无榜单数据。")
    else:
        lines.extend(["```csv", "代码,名称,现价,涨跌幅,成交额,换手率,量比,总市值,流通市值,市盈率TTM,主力净流入"])
        for item in items:
            lines.append(
                ",".join(
                    [
                        item.get("code", ""),
                        item.get("name", ""),
                        item.get("price", ""),
                        item.get("change_rate", ""),
                        item.get("turnover", ""),
                        item.get("turnover_rate", ""),
                        item.get("volume_ratio", ""),
                        item.get("market_value", ""),
                        item.get("float_market_value", ""),
                        item.get("pe_ttm", ""),
                        item.get("net_main_in", ""),
                    ]
                )
            )
        lines.append("```")
    lines.extend(_footer(data))
    return "\n".join(lines)


def format_fundflow_markdown(data: dict[str, Any]) -> str:
    lines = [f"# 观澜资金流向 / {data.get('symbol', '')}", ""]
    if data.get("summary"):
        lines.append(f"> {data['summary']}")
        lines.append("")
    today = data.get("today") or {}
    lines.extend(
        [
            "```csv",
            "类别,流入,流入占比,流出,流出占比",
            f"主力,{today.get('main_in', '')},{today.get('main_in_rate', '')},{today.get('main_out', '')},{today.get('main_out_rate', '')}",
            f"散户,{today.get('retail_in', '')},{today.get('retail_in_rate', '')},{today.get('retail_out', '')},{today.get('retail_out_rate', '')}",
            "```",
            "",
            f"- 超大单净流入: {today.get('super_flow', '')}",
            f"- 大单净流入: {today.get('big_flow', '')}",
            f"- 中单净流入: {today.get('normal_flow', '')}",
            f"- 小单净流入: {today.get('small_flow', '')}",
            f"- 主力净流入: {today.get('main_net_in', '')}",
        ]
    )
    rows = data.get("five_day_main_net_in") or []
    if rows:
        lines.extend(["", "## 近5日主力净流入", "", "```csv", "日期,主力净流入"])
        for row in rows:
            lines.append(f"{row.get('date', '')},{row.get('main_net_in', '')}")
        lines.append("```")
    lines.extend(_footer(data))
    return "\n".join(lines)


def format_market_index_markdown(data: dict[str, Any]) -> str:
    lines = [f"# 观澜大盘概览 / {data.get('retrieved_at', '')}", ""]
    quotes = data.get("quotes") or []
    if quotes:
        lines.extend(["## 指数", "", "```csv", "代码,名称,价格,涨跌幅,昨收价,开盘价,最高价,最低价"])
        for item in quotes:
            lines.append(",".join([item.get("code", ""), item.get("name", ""), item.get("price", ""), item.get("change_rate", ""), item.get("previous_close", ""), item.get("open", ""), item.get("high", ""), item.get("low", "")]))
        lines.append("```")
    overview = data.get("overview") or {}
    if overview:
        lines.extend(["", "## 市场分布"])
        for key in ("up_count", "flat_count", "down_count", "up_limit_count", "down_limit_count"):
            if overview.get(key) not in {None, ""}:
                labels = {
                    "up_count": "上涨",
                    "flat_count": "平盘",
                    "down_count": "下跌",
                    "up_limit_count": "涨停",
                    "down_limit_count": "跌停",
                }
                lines.append(f"- {labels[key]}: {overview.get(key)}")
        if overview.get("amount"):
            lines.append(f"- 成交额: {overview.get('amount')}")
        if overview.get("news_title"):
            lines.append(f"- 市场快讯: {overview.get('news_title')}")
    lines.extend(_footer(data))
    return "\n".join(lines)


def format_detail_markdown(data: dict[str, Any]) -> str:
    lines = [f"# 观澜个股结构化数据 / {data.get('symbol', '')}", ""]
    if data.get("quote"):
        lines.append(_without_footer(format_quote_markdown(data["quote"])))
    if data.get("fundflow"):
        lines.extend(["", _without_footer(format_fundflow_markdown(data["fundflow"]))])
    if data.get("plates"):
        lines.extend(["", _without_footer(_format_plates(data["plates"]))])
    if data.get("news"):
        lines.extend(["", _without_footer(_format_news(data["news"]))])
    errors = data.get("errors") or {}
    if errors:
        lines.extend(["", "## 未取到的结构化部分"])
        for key, value in errors.items():
            lines.append(f"- {key}: {value}")
    lines.extend(_footer(data))
    return "\n".join(lines)


def _fetch_quote_json(query_code: str) -> dict[str, Any]:
    response = _http_get(QUOTE_ENDPOINT, params={"q": query_code, "fmt": "json"})
    try:
        return json.loads(response.content.decode("gbk", errors="ignore"))
    except json.JSONDecodeError as exc:
        raise StockDataError("行情接口返回解析失败") from exc


def _fetch_market_overview() -> dict[str, Any]:
    payload = _http_get_json(
        MARKET_ENDPOINT,
        params={
            "type": "0",
            "_appName": "ios",
            "_appver": "11.38.0",
            "openid": "anonymous",
            "fskey": "anonymous",
            "access_token": "",
            "lang": "zh_CN",
        },
    )
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return {}
    ups = data.get("ups_downs_dsb") if isinstance(data.get("ups_downs_dsb"), dict) else {}
    turnover = data.get("turnover_dsb") if isinstance(data.get("turnover_dsb"), dict) else {}
    all_turnover = turnover.get("all") if isinstance(turnover.get("all"), dict) else {}
    news = data.get("news") if isinstance(data.get("news"), dict) else {}
    return {
        "up_count": ups.get("up_count"),
        "flat_count": ups.get("flat_count"),
        "down_count": ups.get("down_count"),
        "up_limit_count": ups.get("up_limit_count"),
        "down_limit_count": ups.get("down_limit_count"),
        "up_ratio_comment": ups.get("up_ratio_comment"),
        "amount": _money_yuan(all_turnover.get("amount")),
        "amount_change": _money_yuan(all_turnover.get("amount_change")),
        "news_title": news.get("title"),
        "news_time": news.get("time"),
    }


def _quote_arr_to_obj(arr: list[Any], *, symbol: str) -> dict[str, str]:
    prefix = {"1": "sh", "51": "sz", "62": "bj", "100": "hk", "200": "us"}.get(_get(arr, 0), "")
    index_offset = 1 if prefix in {"us", "hk"} else 0
    return {
        "symbol": symbol,
        "market": prefix,
        "code": _get(arr, 2),
        "name": _get(arr, 1),
        "price": _get(arr, 3),
        "change": _get(arr, 31),
        "change_rate": _zdf_percent(_get(arr, 32)),
        "previous_close": _get(arr, 4),
        "open": _get(arr, 5),
        "high": _get(arr, 33),
        "low": _get(arr, 34),
        "volume": _volume(_get(arr, 36)),
        "market_value": _billion(_get(arr, 45)),
        "circulating_value": _billion(_get(arr, 44)),
        "turnover_rate": _percent(_get(arr, 38)),
        "pe": _get(arr, 39),
        "pb": _get(arr, 46),
        "volume_ratio": _get(arr, 49 + index_offset),
        "time": _format_quote_time(_get(arr, 30)),
    }


def _http_get_json(url: str, *, params: dict[str, Any]) -> dict[str, Any]:
    try:
        return _http_get(url, params=params).json()
    except ValueError as exc:
        raise StockDataError("接口返回解析失败") from exc


def _http_get(url: str, *, params: dict[str, Any]) -> requests.Response:
    try:
        response = requests.get(url, params=params, headers=COMMON_HEADERS, timeout=10)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise StockDataError(f"结构化财经接口不可用：{exc}") from exc


def _looks_like_quote_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"(?:sh|sz|bj)\d{6}|hk\d{5}|us[A-Z]{1,5}", value))


def _plate_items(raw: Any) -> list[dict[str, str]]:
    items = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                items.append({"name": str(item.get("name") or ""), "change_rate": _zdf_percent(str(item.get("zdf") or ""))})
    return items


def _format_plates(data: dict[str, Any]) -> str:
    lines = [f"## 相关板块 / {data.get('symbol', '')}"]
    for title, key in (("地域", "area"), ("行业", "industry"), ("概念", "concept")):
        rows = data.get(key) or []
        if rows:
            lines.extend(["", f"### {title}"])
            for row in rows[:20]:
                lines.append(f"- {row.get('name', '')}: {row.get('change_rate', '')}")
    lines.extend(_footer(data))
    return "\n".join(lines)


def _format_news(data: dict[str, Any]) -> str:
    lines = [f"## 快讯 / {data.get('symbol', '')}", ""]
    items = data.get("items") or []
    if not items:
        lines.append("暂无快讯。")
    else:
        for item in items:
            lines.append(f"- [{item.get('time', '')}] {item.get('title', '')}")
    lines.extend(_footer(data))
    return "\n".join(lines)


def _footer(data: dict[str, Any]) -> list[str]:
    return [
        "",
        "## 边界",
        f"- 数据源: {data.get('source') or SOURCE_NAME}",
        f"- 获取时间: {data.get('retrieved_at') or _now()}",
        f"- 提醒: {data.get('boundary') or '公开数据仅作研究线索，不构成投资建议。'}",
    ]


def _without_footer(text: str) -> str:
    marker = "\n\n## 边界\n"
    if marker in text:
        return text.split(marker, 1)[0].rstrip()
    return text.rstrip()


def _get(arr: list[Any], index: int, default: str = "") -> str:
    if index < len(arr):
        return str(arr[index])
    return default


def _format_quote_time(raw: str) -> str:
    if len(raw) == 14 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}:{raw[12:14]}"
    return raw


def _zdf_percent(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("%"):
        return text if text.startswith("-") or text.startswith("+") else f"+{text}"
    return f"{text}%" if text.startswith("-") else f"+{text}%"


def _percent(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.endswith("%") else f"{text}%"


def _money_wan(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    return f"{number / 10000:.2f}万"


def _wan_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.endswith("万") else f"{text}万"


def _money_yuan(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    return f"{number:.2f}"


def _billion(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.endswith("亿") else f"{text}亿"


def _volume(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return str(value or "")
    return f"{number / 10000:.2f}万手"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
