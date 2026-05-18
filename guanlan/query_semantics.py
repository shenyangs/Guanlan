# -*- coding: utf-8 -*-
"""Shared semantic helpers for fragile compound queries and proper nouns."""

from __future__ import annotations

import re
from typing import Any


def analyze_query_semantics(query: str) -> dict[str, Any]:
    """Return reusable semantic hints for query rewrite, routing, and quality."""

    text = _collapse_ws(query)
    lowered = text.lower()
    output: dict[str, Any] = {
        "matched_rules": [],
        "matched_terms": [],
        "intent_hints": [],
        "quality_intent": "",
        "alias_terms": [],
        "rewrite_terms": [],
        "query_variants": [],
        "groups": [],
        "preferred_sites": [],
        "notes": [],
    }
    for rule in _SEMANTIC_RULES:
        if not _semantic_rule_matches(rule, text, lowered):
            continue
        output["matched_rules"].append(str(rule["id"]))
        output["matched_terms"].extend(rule.get("matched_terms", ()) or rule.get("terms", ()) or ())
        output["intent_hints"].extend(rule.get("intent_hints", ()) or ())
        if not output["quality_intent"] and rule.get("quality_intent"):
            output["quality_intent"] = str(rule["quality_intent"])
        output["alias_terms"].extend(rule.get("alias_terms", ()) or ())
        output["rewrite_terms"].extend(rule.get("rewrite_terms", ()) or ())
        output["query_variants"].extend(rule.get("query_variants", ()) or ())
        output["preferred_sites"].extend(rule.get("preferred_sites", ()) or ())
        output["notes"].extend(rule.get("notes", ()) or ())
        for group in rule.get("groups", ()) or ():
            if isinstance(group, dict):
                output["groups"].append(dict(group))

    _apply_generic_suffix_semantics(text, lowered, output)
    _apply_year_event_semantics(text, lowered, output)

    output["matched_rules"] = _unique_keep_order(output["matched_rules"])
    output["matched_terms"] = _unique_keep_order(output["matched_terms"])
    output["intent_hints"] = _unique_keep_order(output["intent_hints"])
    output["alias_terms"] = _unique_keep_order(output["alias_terms"])
    output["rewrite_terms"] = _unique_keep_order(output["rewrite_terms"])
    output["query_variants"] = _unique_keep_order(output["query_variants"])
    output["preferred_sites"] = _unique_keep_order(output["preferred_sites"])
    output["notes"] = _unique_keep_order(output["notes"])
    output["groups"] = _dedupe_groups(output["groups"])
    return output


def semantic_query_variants(query: str, *, limit: int = 6) -> list[str]:
    """Return bounded semantic query variants for recovery or route display."""

    analysis = analyze_query_semantics(query)
    variants = list(analysis.get("query_variants") or [])
    rewrite_terms = [term for term in analysis.get("rewrite_terms") or [] if term not in query]
    if rewrite_terms:
        variants.insert(0, f"{_collapse_ws(query)} {' '.join(rewrite_terms[:6])}".strip())
    return _unique_keep_order(variants)[: max(limit, 0)]


def semantic_alias_terms(query: str) -> list[str]:
    """Return alias/entity terms that should count for relevance and routing."""

    analysis = analyze_query_semantics(query)
    aliases = list(analysis.get("alias_terms") or [])
    aliases.extend(analysis.get("matched_terms") or [])
    return _unique_keep_order(aliases)


def semantic_groups(query: str) -> list[dict[str, Any]]:
    """Return extra soft relevance groups for compound public-web queries."""

    return list(analyze_query_semantics(query).get("groups") or [])


def _apply_generic_suffix_semantics(text: str, lowered: str, output: dict[str, Any]) -> None:
    compact_len = len(text.replace(" ", ""))
    if compact_len <= 14 and "模式" in text:
        output["rewrite_terms"].extend(["商业模式", "案例", "复盘"])
        output["notes"].append("短品牌/组织模式词已补商业模式语境，减少被单字释义带偏。")
    if compact_len <= 14 and "营销" in text:
        output["rewrite_terms"].extend(["品牌", "联名", "复盘", "案例"])
        output["notes"].append("营销类短语已补品牌/联名/复盘语境。")
    if compact_len <= 16 and "现象" in text:
        output["rewrite_terms"].extend(["事件", "走红", "原因", "复盘"])
        output["notes"].append("现象类短语已补事件/走红/复盘语境。")
    if "退潮" in text:
        output["rewrite_terms"].extend(["趋势", "数据", "投融资", "关闭"])
    if "扩容" in text and _contains_any(lowered, ("reit", "reits", "公募reits", "基础设施reits")):
        output["rewrite_terms"].extend(["公募REITs", "证监会", "发改委", "交易所"])
    if "危机" in text and _contains_any(lowered, ("红海", "shipping", "航运")):
        output["rewrite_terms"].extend(["航运", "运价", "供应链", "影响"])


def _apply_year_event_semantics(text: str, lowered: str, output: dict[str, Any]) -> None:
    years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
    if not years:
        return
    if "医保" in text and "谈判" in text:
        output["rewrite_terms"].extend(["国家医保局", "药品目录", "名单", "结果"])
        output["notes"].append("年份+医保谈判已补主管机构、目录和结果词。")
    if _contains_any(lowered, ("发布", "获批", "名单", "结果", "谈判", "目录")):
        output["rewrite_terms"].extend(["最新", "官方", "新闻"])


def _semantic_rule_matches(rule: dict[str, Any], text: str, lowered: str) -> bool:
    for terms in rule.get("match_all", ()) or ():
        normalized = [str(term).lower() for term in terms if str(term)]
        if normalized and all(term in lowered for term in normalized):
            return True
    for term in rule.get("terms", ()) or ():
        if str(term).lower() in lowered:
            return True
    for pattern in rule.get("regexes", ()) or ():
        if re.search(str(pattern), text, flags=re.I):
            return True
    return False


def _dedupe_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        name = str(group.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        output.append(
            {
                "name": name,
                "aliases": _unique_keep_order([str(alias) for alias in group.get("aliases", []) if str(alias)]),
                "required": bool(group.get("required", False)),
            }
        )
    return output


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _unique_keep_order(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _collapse_ws(str(value))
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


_SEMANTIC_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "new_quality_productive_forces",
        "terms": ("新质生产力",),
        "intent_hints": ("policy",),
        "quality_intent": "policy",
        "matched_terms": ("新质生产力",),
        "alias_terms": ("新质生产力", "国务院", "发改委", "政策", "官方"),
        "rewrite_terms": ("国务院", "发改委", "政策", "官方", "原文"),
        "query_variants": ("新质生产力 国务院 发改委 政策 官方 原文",),
        "groups": (
            {
                "name": "new_quality_productive_forces",
                "aliases": ("新质生产力", "国务院", "发改委", "政策"),
                "required": True,
            },
        ),
    },
    {
        "id": "prepared_food_national_standard",
        "terms": ("预制菜国标",),
        "match_all": (("预制菜", "国标"),),
        "intent_hints": ("policy", "standards_compliance"),
        "quality_intent": "policy",
        "matched_terms": ("预制菜", "国标"),
        "alias_terms": ("预制菜", "国家标准", "市场监管总局", "征求意见", "官方"),
        "rewrite_terms": ("国家标准", "市场监管总局", "征求意见", "官方"),
        "query_variants": ("预制菜 国家标准 市场监管总局 征求意见 官方",),
        "groups": (
            {
                "name": "prepared_food_national_standard",
                "aliases": ("预制菜", "国家标准", "市场监管总局", "征求意见"),
                "required": True,
            },
        ),
    },
    {
        "id": "device_upgrade_policy",
        "terms": ("大规模设备更新", "设备更新改造"),
        "match_all": (("设备更新", "万亿"),),
        "intent_hints": ("policy",),
        "quality_intent": "policy",
        "matched_terms": ("设备更新", "万亿"),
        "alias_terms": ("设备更新", "大规模设备更新", "设备更新改造", "国务院", "工信部", "商务部"),
        "rewrite_terms": ("大规模设备更新", "设备更新改造", "国务院", "工信部", "商务部", "政策"),
        "query_variants": ("大规模设备更新改造 万亿 国务院 工信部 商务部 政策",),
        "groups": (
            {
                "name": "device_upgrade_policy",
                "aliases": ("设备更新", "大规模设备更新", "设备更新改造", "国务院", "工信部", "商务部"),
                "required": True,
            },
        ),
    },
    {
        "id": "data_export_assessment",
        "terms": ("数据出境安全评估",),
        "match_all": (("数据出境", "安全评估"),),
        "intent_hints": ("standards_compliance", "policy"),
        "quality_intent": "standards_compliance",
        "matched_terms": ("数据出境", "安全评估"),
        "alias_terms": ("数据出境", "安全评估", "数据出境安全评估办法", "网信办", "申报", "指南"),
        "rewrite_terms": ("数据出境安全评估办法", "网信办", "申报", "指南"),
        "query_variants": ("数据出境安全评估办法 网信办 申报 指南",),
        "groups": (
            {
                "name": "data_export_assessment",
                "aliases": ("数据出境", "安全评估", "网信办", "申报", "指南"),
                "required": True,
            },
        ),
    },
    {
        "id": "flexible_workforce_policy",
        "terms": ("灵活用工", "新就业形态"),
        "match_all": (("劳动法", "灵活用工"),),
        "intent_hints": ("policy", "legal_judicial"),
        "quality_intent": "policy",
        "matched_terms": ("灵活用工", "新就业形态"),
        "alias_terms": ("灵活用工", "新就业形态", "人社部", "劳动权益", "政策"),
        "rewrite_terms": ("灵活用工", "新就业形态", "人社部", "劳动权益", "政策"),
        "query_variants": ("灵活用工 新就业形态 人社部 政策 劳动权益",),
        "groups": (
            {
                "name": "flexible_workforce_policy",
                "aliases": ("灵活用工", "新就业形态", "人社部", "劳动权益"),
                "required": True,
            },
        ),
    },
    {
        "id": "health_insurance_negotiation",
        "terms": ("医保谈判", "医保目录调整"),
        "match_all": (("医保", "谈判"),),
        "intent_hints": ("policy", "medical_health"),
        "quality_intent": "medical_health",
        "matched_terms": ("医保", "谈判"),
        "alias_terms": ("国家医保谈判", "国家医保局", "药品目录", "名单", "降价", "结果"),
        "rewrite_terms": ("国家医保局", "药品目录", "名单", "降价", "结果"),
        "query_variants": ("国家医保谈判 国家医保局 药品目录 名单 降价 结果",),
        "groups": (
            {
                "name": "health_insurance_negotiation",
                "aliases": ("医保", "谈判", "国家医保局", "药品目录", "名单"),
                "required": True,
            },
        ),
    },
    {
        "id": "tsmc_arizona",
        "terms": ("台积电亚利桑那",),
        "match_all": (("台积电", "亚利桑那"), ("tsmc", "arizona")),
        "intent_hints": ("company_primary", "global_industry", "tech"),
        "quality_intent": "company",
        "matched_terms": ("台积电", "亚利桑那"),
        "alias_terms": ("台积电", "TSMC", "亚利桑那", "Arizona", "fab", "美国工厂"),
        "rewrite_terms": ("TSMC", "Arizona fab", "美国工厂", "投资", "3nm"),
        "query_variants": ("TSMC Arizona fab 台积电 美国 亚利桑那 工厂 投资",),
        "preferred_sites": ("tsmc.com", "trendforce.com", "cnbc.com"),
        "groups": (
            {
                "name": "tsmc_arizona_fab",
                "aliases": ("台积电", "TSMC", "亚利桑那", "Arizona", "fab", "美国工厂"),
                "required": True,
            },
        ),
    },
    {
        "id": "chiikawa_fandom",
        "terms": ("chiikawa", "吉伊卡哇", "ちいかわ"),
        "intent_hints": ("entertainment",),
        "quality_intent": "entertainment",
        "matched_terms": ("chiikawa",),
        "alias_terms": ("chiikawa", "吉伊卡哇", "ちいかわ", "B站", "微博", "小红书", "Bangumi"),
        "rewrite_terms": ("吉伊卡哇", "ちいかわ", "微博", "B站", "小红书", "Bangumi"),
        "query_variants": ("chiikawa 吉伊卡哇 ちいかわ 微博 B站 小红书 Bangumi",),
        "groups": (
            {
                "name": "chiikawa_fandom",
                "aliases": ("chiikawa", "吉伊卡哇", "ちいかわ", "Bangumi", "B站"),
                "required": True,
            },
        ),
    },
    {
        "id": "pangdonglai_retail",
        "terms": ("胖东来",),
        "intent_hints": ("industry", "ecommerce", "reputation"),
        "quality_intent": "industry",
        "matched_terms": ("胖东来",),
        "alias_terms": ("胖东来", "零售模式", "商超", "服务模式", "案例"),
        "rewrite_terms": ("零售模式", "商超", "服务模式", "案例", "供应链"),
        "query_variants": ("胖东来 零售模式 商超 服务模式 案例 供应链",),
        "groups": (
            {
                "name": "pangdonglai_retail",
                "aliases": ("胖东来", "零售模式", "商超", "服务模式"),
                "required": True,
            },
        ),
    },
    {
        "id": "sauce_latte_marketing",
        "terms": ("酱香拿铁",),
        "match_all": (("酱香", "拿铁"), ("瑞幸", "茅台")),
        "intent_hints": ("industry", "ecommerce", "reputation"),
        "quality_intent": "industry",
        "matched_terms": ("酱香拿铁",),
        "alias_terms": ("酱香拿铁", "瑞幸", "茅台", "联名", "营销", "销量"),
        "rewrite_terms": ("瑞幸", "茅台", "联名", "营销", "复盘", "销量"),
        "query_variants": ("瑞幸 茅台 酱香拿铁 联名 营销 复盘 销量",),
        "groups": (
            {
                "name": "sauce_latte_marketing",
                "aliases": ("酱香拿铁", "瑞幸", "茅台", "联名", "营销"),
                "required": True,
            },
        ),
    },
    {
        "id": "zibo_bbq_event",
        "terms": ("淄博烧烤",),
        "intent_hints": ("local", "industry", "public_opinion"),
        "quality_intent": "local",
        "matched_terms": ("淄博烧烤",),
        "alias_terms": ("淄博烧烤", "网红城市", "走红", "事件", "复盘"),
        "rewrite_terms": ("网红城市", "走红", "事件", "复盘", "2023"),
        "query_variants": ("淄博烧烤 网红城市 走红 事件 复盘 2023",),
        "groups": (
            {
                "name": "zibo_bbq_event",
                "aliases": ("淄博烧烤", "网红城市", "走红", "事件"),
                "required": True,
            },
        ),
    },
    {
        "id": "consumer_trend_economy",
        "terms": ("谷子经济", "露营经济", "露营经济退潮"),
        "intent_hints": ("industry", "ecommerce"),
        "quality_intent": "industry",
        "matched_terms": ("经济",),
        "alias_terms": ("谷子经济", "露营经济", "新消费", "趋势", "数据"),
        "rewrite_terms": ("新消费", "趋势", "数据", "行业报告"),
        "query_variants": ("露营经济 退潮 趋势 数据 投融资 行业报告", "谷子经济 新消费 趋势 数据 行业报告"),
    },
    {
        "id": "reits_expansion",
        "terms": ("reits", "reit", "公募reits", "基础设施reits"),
        "intent_hints": ("finance",),
        "quality_intent": "finance",
        "matched_terms": ("REITs",),
        "alias_terms": ("REITs", "公募REITs", "扩容", "证监会", "发改委", "交易所"),
        "rewrite_terms": ("公募REITs", "扩容", "证监会", "发改委", "交易所"),
        "query_variants": ("REITs 扩容 公募REITs 证监会 发改委 交易所",),
    },
    {
        "id": "red_sea_shipping",
        "terms": ("红海危机",),
        "intent_hints": ("global_industry", "industry"),
        "quality_intent": "industry",
        "matched_terms": ("红海危机",),
        "alias_terms": ("红海危机", "航运", "运价", "供应链", "shipping"),
        "rewrite_terms": ("航运", "运价", "供应链", "shipping", "影响"),
        "query_variants": ("红海危机 航运 运价 供应链 shipping 影响",),
    },
    {
        "id": "car_t_therapy",
        "terms": ("car-t", "car t", "car-t疗法"),
        "intent_hints": ("medical_health", "academic"),
        "quality_intent": "medical_health",
        "matched_terms": ("CAR-T",),
        "alias_terms": ("CAR-T", "CAR-T疗法", "临床", "适应症", "NMPA", "CDE"),
        "rewrite_terms": ("临床", "适应症", "审批", "NMPA", "CDE", "指南"),
        "query_variants": ("CAR-T 疗法 临床 适应症 审批 NMPA CDE 指南",),
        "groups": (
            {
                "name": "car_t_therapy",
                "aliases": ("CAR-T", "CAR-T疗法", "临床", "适应症", "NMPA", "CDE"),
                "required": True,
            },
        ),
    },
    {
        "id": "vector_database",
        "terms": ("向量数据库", "vector database"),
        "intent_hints": ("tech", "academic"),
        "quality_intent": "tech",
        "matched_terms": ("向量数据库",),
        "alias_terms": ("向量数据库", "Milvus", "Qdrant", "Weaviate", "Chroma", "GitHub"),
        "rewrite_terms": ("Milvus", "Qdrant", "Weaviate", "Chroma", "GitHub", "对比"),
        "query_variants": ("向量数据库 Milvus Qdrant Weaviate Chroma GitHub 对比",),
    },
    {
        "id": "graph_neural_network",
        "terms": ("图神经网络", "graph neural network"),
        "regexes": (r"\bGNN\b",),
        "intent_hints": ("tech", "academic"),
        "quality_intent": "tech",
        "matched_terms": ("图神经网络",),
        "alias_terms": ("图神经网络", "GNN", "arXiv", "GitHub", "应用"),
        "rewrite_terms": ("GNN", "arXiv", "GitHub", "教程", "应用"),
        "query_variants": ("图神经网络 GNN arXiv GitHub 教程 应用",),
    },
    {
        "id": "lora_finetune",
        "terms": ("lora", "qlora", "大模型微调"),
        "intent_hints": ("tech",),
        "quality_intent": "tech",
        "matched_terms": ("LoRA",),
        "alias_terms": ("LoRA", "QLoRA", "Hugging Face", "PyTorch", "GitHub"),
        "rewrite_terms": ("QLoRA", "Hugging Face", "PyTorch", "GitHub", "微调"),
        "query_variants": ("大模型微调 LoRA QLoRA Hugging Face PyTorch GitHub",),
    },
    {
        "id": "prompt_engineering",
        "terms": ("prompt engineering", "提示工程"),
        "intent_hints": ("tech",),
        "quality_intent": "tech",
        "matched_terms": ("Prompt Engineering",),
        "alias_terms": ("Prompt Engineering", "提示工程", "OpenAI", "Anthropic", "prompt guide"),
        "rewrite_terms": ("提示工程", "OpenAI", "Anthropic", "prompt guide", "best practices"),
        "query_variants": ("Prompt Engineering 提示工程 OpenAI Anthropic prompt guide best practices",),
    },
)
