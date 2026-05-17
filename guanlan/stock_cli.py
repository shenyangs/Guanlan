# -*- coding: utf-8 -*-
"""CLI surface for Guanlan structured stock data."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from guanlan import stockdata


def add_stock_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "stock",
        help="Fetch structured stock quotes, rankings, fund flow, market overview, and agent stock plans",
    )
    _add_stock_arguments(parser)
    return parser


def build_standalone_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guanlan-stock",
        description="观澜结构化股票数据：行情、榜单、资金流向、大盘概览和 Agent 股票任务指南",
    )
    _add_stock_arguments(parser)
    return parser


def _add_stock_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="stock_command", help="Stock data commands")

    p_plan = sub.add_parser("plan", aliases=["guide"], help="Explain the stock-first workflow for agents")
    p_plan.add_argument("query", nargs="?", default="", help="Optional stock/finance query")
    p_plan.add_argument("--json", action="store_true", help="Print JSON")

    p_search = sub.add_parser("search", aliases=["lookup"], help="Search stock/index codes by name or symbol")
    p_search.add_argument("query", help="Stock name, ticker, or noisy finance query")
    p_search.add_argument("--limit", type=int, default=20, help="Maximum number of candidates")
    p_search.add_argument("--json", action="store_true", help="Print JSON")

    p_quote = sub.add_parser("quote", aliases=["price"], help="Fetch one stock/index quote")
    p_quote.add_argument("target", help="Stock code/name/ticker, e.g. 600519, 贵州茅台, NVDA")
    p_quote.add_argument("--json", action="store_true", help="Print JSON")

    p_detail = sub.add_parser("detail", help="Fetch quote, fund flow, plates, and latest news")
    p_detail.add_argument("target", help="Stock code/name/ticker")
    p_detail.add_argument("--news-limit", type=int, default=12, help="Maximum number of news items")
    p_detail.add_argument("--json", action="store_true", help="Print JSON")

    p_fundflow = sub.add_parser("fundflow", aliases=["flow", "moneyflow"], help="Fetch fund-flow statistics")
    p_fundflow.add_argument("target", help="Stock code/name/ticker")
    p_fundflow.add_argument("--json", action="store_true", help="Print JSON")

    p_news = sub.add_parser("news", help="Fetch latest stock news")
    p_news.add_argument("target", help="Stock code/name/ticker")
    p_news.add_argument("--limit", type=int, default=12, help="Maximum number of news items")
    p_news.add_argument("--json", action="store_true", help="Print JSON")

    p_plate = sub.add_parser("plate", help="Fetch related area/industry/concept plates")
    p_plate.add_argument("target", help="Stock code/name/ticker")
    p_plate.add_argument("--json", action="store_true", help="Print JSON")

    p_rank = sub.add_parser("rank", help="Fetch A-share ranking list")
    p_rank.add_argument("--sort", default="turnover", help="Sort key: turnover, volumeRatio, exchange, priceRatio, netMainIn")
    p_rank.add_argument("--direct", choices=["down", "up"], default="down", help="Sort direction")
    p_rank.add_argument("--offset", type=int, default=0, help="Result offset")
    p_rank.add_argument("--limit", "--count", dest="limit", type=int, default=20, help="Maximum number of rows, 1-100")
    p_rank.add_argument("--json", action="store_true", help="Print JSON")

    p_index = sub.add_parser("index", aliases=["market", "overview"], help="Fetch A-share market overview")
    p_index.add_argument("--json", action="store_true", help="Print JSON")


def run_stock_command(args: argparse.Namespace) -> None:
    command = getattr(args, "stock_command", "") or ""
    if not command:
        raise SystemExit("请指定 stock 子命令，例如：guanlan stock plan \"宁德时代 股价\" 或 guanlan stock quote 600519")
    try:
        payload, text = _run_stock_command(args)
    except stockdata.StockDataError as exc:
        raise SystemExit(f"观澜股票数据错误：{exc}") from exc
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)


def run_stock_tool(arguments: dict[str, Any] | None = None) -> dict[str, Any] | str:
    """Run the stock data layer for MCP/HTTP surfaces."""
    args = arguments or {}
    command = _normalize_stock_command(str(args.get("command") or "quote"))
    output_format = str(args.get("format") or "markdown")
    namespace = argparse.Namespace(
        stock_command=command,
        query=args.get("query") or args.get("target") or "",
        target=args.get("target") or args.get("query") or "",
        limit=int(args.get("limit") or args.get("count") or 20),
        news_limit=int(args.get("news_limit") or 12),
        sort=str(args.get("sort") or "turnover"),
        direct=str(args.get("direct") or "down"),
        offset=int(args.get("offset") or 0),
        json=output_format == "json",
    )
    payload, text = _run_stock_command(namespace)
    return payload if output_format == "json" else text


def _run_stock_command(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    command = _normalize_stock_command(str(args.stock_command))
    if command == "plan":
        payload = stockdata.build_stock_guide(str(getattr(args, "query", "") or getattr(args, "target", "") or ""))
        return payload, stockdata.format_stock_guide_markdown(payload)
    if command == "search":
        payload = stockdata.search_stocks(str(args.query), limit=int(args.limit))
        return payload, stockdata.format_search_markdown(payload)
    if command == "quote":
        payload = stockdata.quote_stock(str(args.target))
        return payload, stockdata.format_quote_markdown(payload)
    if command == "detail":
        payload = stockdata.stock_detail(str(args.target), news_limit=int(args.news_limit))
        return payload, stockdata.format_detail_markdown(payload)
    if command == "fundflow":
        payload = stockdata.fundflow(str(args.target))
        return payload, stockdata.format_fundflow_markdown(payload)
    if command == "news":
        payload = stockdata.latest_news(str(args.target), limit=int(args.limit))
        return payload, _format_news(payload)
    if command == "plate":
        payload = stockdata.related_plates(str(args.target))
        return payload, _format_plates(payload)
    if command == "rank":
        payload = stockdata.rank_stocks(
            sort=str(args.sort),
            direct=str(args.direct),
            offset=int(args.offset),
            limit=int(args.limit),
        )
        return payload, stockdata.format_rank_markdown(payload)
    if command == "index":
        payload = stockdata.market_index()
        return payload, stockdata.format_market_index_markdown(payload)
    raise StockCommandError(f"未知 stock 子命令：{command}")


def _format_news(payload: dict[str, Any]) -> str:
    lines = [f"# 观澜个股快讯 / {payload.get('symbol', '')}", ""]
    items = payload.get("items") or []
    if not items:
        lines.append("暂无快讯。")
    else:
        for item in items:
            lines.append(f"- [{item.get('time', '')}] {item.get('title', '')}")
    lines.extend(["", "## 边界", f"- 数据源: {payload.get('source', '')}", f"- 获取时间: {payload.get('retrieved_at', '')}", f"- 提醒: {payload.get('boundary', '')}"])
    return "\n".join(lines)


def _format_plates(payload: dict[str, Any]) -> str:
    lines = [f"# 观澜相关板块 / {payload.get('symbol', '')}"]
    for title, key in (("地域", "area"), ("行业", "industry"), ("概念", "concept")):
        rows = payload.get(key) or []
        if rows:
            lines.extend(["", f"## {title}"])
            for row in rows[:20]:
                lines.append(f"- {row.get('name', '')}: {row.get('change_rate', '')}")
    lines.extend(["", "## 边界", f"- 数据源: {payload.get('source', '')}", f"- 获取时间: {payload.get('retrieved_at', '')}", f"- 提醒: {payload.get('boundary', '')}"])
    return "\n".join(lines)


class StockCommandError(stockdata.StockDataError):
    """CLI-level stock command error."""


def _normalize_stock_command(command: str) -> str:
    aliases = {
        "guide": "plan",
        "lookup": "search",
        "price": "quote",
        "flow": "fundflow",
        "moneyflow": "fundflow",
        "market": "index",
        "overview": "index",
    }
    return aliases.get((command or "").strip().lower(), (command or "").strip().lower())


def main(argv: list[str] | None = None) -> None:
    parser = build_standalone_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "stock_command", ""):
        parser.print_help()
        raise SystemExit(0)
    run_stock_command(args)


if __name__ == "__main__":
    main(sys.argv[1:])
