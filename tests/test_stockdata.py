# -*- coding: utf-8 -*-
"""Tests for Guanlan structured stock data helpers."""

from unittest.mock import patch

import pytest

from guanlan import stockdata
from guanlan.cli import main


def _quote_arr() -> list[str]:
    arr = [""] * 55
    arr[0] = "1"
    arr[1] = "贵州茅台"
    arr[2] = "600519"
    arr[3] = "1384.79"
    arr[4] = "1401.17"
    arr[5] = "1400.00"
    arr[30] = "20260430161422"
    arr[31] = "-16.38"
    arr[32] = "-1.17"
    arr[33] = "1401.17"
    arr[34] = "1380.00"
    arr[36] = "52753"
    arr[38] = "0.42"
    arr[39] = "20.97"
    arr[44] = "17341.31"
    arr[45] = "17341.31"
    arr[46] = "6.40"
    arr[49] = "1.12"
    return arr


def test_infer_and_normalize_stock_target():
    assert stockdata.infer_stock_target("贵州茅台 股价 财报") == "600519"
    assert stockdata.infer_stock_target("宁德时代 最近风险") == "300750"
    assert stockdata.infer_stock_target("上证指数 今日 行情") == "sh000001"
    assert stockdata.normalize_symbol("600519") == "sh600519"
    assert stockdata.normalize_symbol("000001") == "sz000001"
    assert stockdata.normalize_symbol("00700") == "hk00700"
    assert stockdata.normalize_symbol("NVDA") == "usNVDA"
    assert stockdata.normalize_symbol("024051") == "024051"


def test_quote_stock_parses_public_quote_payload(monkeypatch):
    monkeypatch.setattr(stockdata, "resolve_symbol", lambda _target: "sh600519")
    monkeypatch.setattr(stockdata, "_fetch_quote_json", lambda _symbol: {"sh600519": _quote_arr()})

    quote = stockdata.quote_stock("贵州茅台")

    assert quote["symbol"] == "sh600519"
    assert quote["name"] == "贵州茅台"
    assert quote["change_rate"] == "-1.17%"
    assert quote["time"] == "2026-04-30 16:14:22"
    assert quote["quote_time"] == "2026-04-30 16:14:22"
    assert quote["status"] == "ok"
    assert "不构成投资建议" in quote["boundary"]
    assert quote["freshness"]["quote_time"] == "2026-04-30 16:14:22"
    assert any("guanlan stock detail" in command for command in quote["next_commands"])


def test_quote_stock_falls_back_to_sina_quote(monkeypatch):
    class FakeResponse:
        content = (
            'var hq_str_sh600519="贵州茅台,1400.00,1401.17,1384.79,1401.17,1380.00,'
            '1384.79,1384.80,5275300,731000000,,,,,,,,,,,,,,,,,,,,,2026-04-30,16:14:22,00";'
        ).encode("gbk")

    monkeypatch.setattr(stockdata, "resolve_symbol", lambda _target: "sh600519")
    monkeypatch.setattr(stockdata, "_fetch_quote_json", lambda _symbol: (_ for _ in ()).throw(stockdata.StockDataError("腾讯接口不可用")))
    monkeypatch.setattr(stockdata, "_http_get", lambda *_args, **_kwargs: FakeResponse())

    quote = stockdata.quote_stock("贵州茅台")

    assert quote["source"] == stockdata.SINA_SOURCE_NAME
    assert quote["source_chain"] == [f"{stockdata.SOURCE_NAME}:failed", f"{stockdata.SINA_SOURCE_NAME}:ok"]
    assert quote["price"] == "1384.79"
    assert quote["quote_time"] == "2026-04-30 16:14:22"
    assert quote["change_rate"] == "-1.17%"
    assert "tencent_quote" in quote["fallback_errors"]


def test_search_stocks_uses_cleaned_query(monkeypatch):
    calls = []

    def fake_json(_url, *, params):
        calls.append(params)
        return {"stock": [{"code": "sz300750", "name": "宁德时代", "type": "GP-A-CYB", "reportInfo": {"match_field": "secu_name", "match_level": "full_match"}}]}

    monkeypatch.setattr(stockdata, "_http_get_json", fake_json)

    data = stockdata.search_stocks("宁德时代 股价", limit=5)

    assert calls[0]["query"] == "300750"
    assert data["items"][0]["code"] == "sz300750"
    assert data["items"][0]["name"] == "宁德时代"


def test_search_stocks_uses_local_candidate_when_backend_fails(monkeypatch):
    monkeypatch.setattr(stockdata, "_http_get_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(stockdata.StockDataError("搜索接口不可用")))

    data = stockdata.search_stocks("贵州茅台 股价", limit=5)

    assert data["diagnostics"]["fallback"] is True
    assert data["items"][0]["code"] == "sh600519"
    assert data["items"][0]["match_level"] == "local_exact"


def test_search_stocks_adds_fund_candidates(monkeypatch):
    def fake_json(url, *, params, headers=None):
        if url == stockdata.FUND_SUGGEST_ENDPOINT:
            return {
                "Datas": [
                    {
                        "CODE": "024051",
                        "NAME": "华宝中证信息技术应用创新产业ETF发起式联接C",
                        "FundBaseInfo": {
                            "FTYPE": "指数型-股票",
                            "DWJZ": 1.2155,
                            "FSRQ": "2026-05-15",
                            "JJGS": "华宝基金",
                            "JJJL": "张放",
                        },
                    }
                ]
            }
        return {"stock": []}

    monkeypatch.setattr(stockdata, "_http_get_json", fake_json)

    data = stockdata.search_stocks("024051", limit=5)

    assert data["items"][0]["code"] == "024051"
    assert data["items"][0]["asset_type"] == "etf_link"
    assert data["items"][0]["source"] == stockdata.EASTMONEY_SOURCE_NAME


def test_quote_stock_fetches_fund_nav_directly(monkeypatch):
    monkeypatch.setattr(
        stockdata,
        "_fetch_fund_valuation",
        lambda _code: {
            "fundcode": "024051",
            "name": "华宝中证信息技术应用创新产业ETF发起式联接C",
            "jzrq": "2026-05-15",
            "dwjz": "1.2155",
            "gsz": "1.2145",
            "gszzl": "-2.03",
            "gztime": "2026-05-15 15:00",
        },
    )
    monkeypatch.setattr(
        stockdata,
        "_search_funds",
        lambda _query, limit=1: [
            {
                "code": "024051",
                "name": "华宝中证信息技术应用创新产业ETF发起式联接C",
                "asset_type": "etf_link",
                "fund_type": "指数型-股票",
                "base_info": {"DWJZ": 1.2155, "FSRQ": "2026-05-15", "JJGS": "华宝基金", "JJJL": "张放"},
            }
        ],
    )

    quote = stockdata.quote_stock("024051")
    rendered = stockdata.format_quote_markdown(quote)

    assert quote["symbol"] == "fund024051"
    assert quote["source_role"] == "fund_nav"
    assert quote["asset_type"] == "etf_link"
    assert quote["net_value"] == "1.2155"
    assert quote["quote_time"] == "2026-05-15 15:00"
    assert "观澜基金/ETF净值" in rendered


def test_quote_stock_prefers_exact_fund_share_class(monkeypatch):
    monkeypatch.setattr(
        stockdata,
        "_fetch_fund_valuation",
        lambda code: {
            "fundcode": code,
            "name": "华宝中证信息技术应用创新产业ETF发起式联接C",
            "jzrq": "2026-05-15",
            "dwjz": "1.2155",
            "gsz": "1.2145",
            "gszzl": "-2.03",
            "gztime": "2026-05-15 15:00",
        },
    )

    def fake_search(query, limit=1):
        if "联接C" in query:
            return [
                {"code": "024050", "name": "华宝中证信息技术应用创新产业ETF发起式联接A", "asset_type": "etf_link", "fund_type": "指数型-股票", "base_info": {}},
                {"code": "024051", "name": "华宝中证信息技术应用创新产业ETF发起式联接C", "asset_type": "etf_link", "fund_type": "指数型-股票", "base_info": {}},
            ]
        return [{"code": "024051", "name": "华宝中证信息技术应用创新产业ETF发起式联接C", "asset_type": "etf_link", "fund_type": "指数型-股票", "base_info": {}}]

    monkeypatch.setattr(stockdata, "_search_funds", fake_search)

    quote = stockdata.quote_stock("华宝中证信息技术应用创新产业ETF发起式联接C")

    assert quote["symbol"] == "fund024051"
    assert quote["name"] == "华宝中证信息技术应用创新产业ETF发起式联接C"


def test_stock_guide_exposes_agent_first_commands():
    guide = stockdata.build_stock_guide("宁德时代 股价 财报 公告 最近风险")
    rendered = stockdata.format_stock_guide_markdown(guide)

    assert guide["recommended_first_tool"] == "guanlan_stock / guanlan stock"
    assert any(command.startswith("guanlan stock quote") for command in guide["recommended_commands"])
    assert "公告披露" in rendered
    assert "不输出买入、卖出或持有建议" in rendered


def test_stock_guide_exposes_fund_symbol_for_etf_link():
    guide = stockdata.build_stock_guide("024051")

    assert guide["normalized_symbol"] == "fund024051"
    assert "ETF" in guide["agent_trigger_terms"]
    assert any("--scope finance_quote" in command for command in guide["recommended_commands"])


def test_rank_stocks_formats_rows(monkeypatch):
    def fake_json(_url, *, params):
        assert params["count"] == "3"
        return {
            "code": 0,
            "data": {
                "offset": 0,
                "total": 1,
                "rank_list": [
                    {
                        "code": "sh688256",
                        "name": "寒武纪",
                        "zxj": "1699.96",
                        "zdf": "20.00",
                        "turnover": "2846568",
                        "hsl": "4.24",
                        "lb": "2.04",
                        "zsz": "7168.48",
                        "ltsz": "7168.48",
                        "pe_ttm": "263.84",
                        "zljlr": "31045.77",
                    }
                ],
            },
        }

    monkeypatch.setattr(stockdata, "_http_get_json", fake_json)

    data = stockdata.rank_stocks(limit=3)
    rendered = stockdata.format_rank_markdown(data)

    assert data["items"][0]["change_rate"] == "+20.00%"
    assert data["items"][0]["net_main_in"] == "31045.77万"
    assert "寒武纪" in rendered
    assert "不构成投资建议" in rendered


def test_stock_cli_quote_outputs_markdown(capsys):
    fake_quote = {
        "symbol": "sh600519",
        "code": "600519",
        "name": "贵州茅台",
        "price": "1384.79",
        "change_rate": "-1.17%",
        "previous_close": "1401.17",
        "open": "1400.00",
        "high": "1401.17",
        "low": "1380.00",
        "market_value": "17341.31亿",
        "circulating_value": "17341.31亿",
        "pe": "20.97",
        "pb": "6.40",
        "volume": "5.28万手",
        "volume_ratio": "1.12",
        "turnover_rate": "0.42%",
        "time": "2026-04-30 16:14:22",
        "source": "测试源",
        "retrieved_at": "2026-05-03 20:00:00",
        "boundary": "公开数据仅作研究线索，不构成投资建议。",
    }
    with patch("guanlan.stockdata.quote_stock", return_value=fake_quote), patch(
        "sys.argv", ["guanlan", "stock", "quote", "600519"]
    ):
        main()

    captured = capsys.readouterr()
    assert "观澜行情" in captured.out
    assert "贵州茅台" in captured.out
    assert "不构成投资建议" in captured.out


def test_stock_cli_plan_outputs_agent_guide(capsys):
    with patch("sys.argv", ["guanlan", "stock", "plan", "宁德时代 股价"]):
        main()

    captured = capsys.readouterr()
    assert "观澜股票能力指南" in captured.out
    assert "guanlan stock quote" in captured.out


def test_stock_cli_error_is_user_facing(capsys):
    with patch("guanlan.stockdata.quote_stock", side_effect=stockdata.StockDataError("接口不可用")), patch(
        "sys.argv", ["guanlan", "stock", "quote", "600519"]
    ), pytest.raises(SystemExit) as exc_info:
        main()

    assert "接口不可用" in str(exc_info.value)
