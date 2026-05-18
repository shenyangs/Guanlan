# -*- coding: utf-8 -*-
"""Shared WPS / AI Office semantic routing assets.

The terms in this module are intentionally product-and-scene oriented. They
help Guanlan broaden WPS/AI Office discovery without turning every generic AI
query into a WPS query.
"""

from __future__ import annotations

import re
from typing import Any


def _unique(items: list[str] | tuple[str, ...]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = str(item).strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(clean)
    return output


def _norm(value: str) -> str:
    return " ".join((value or "").split()).lower()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", _norm(value))


def _term_matches(text: str, compact: str, term: str) -> bool:
    clean = str(term).strip().lower()
    if not clean:
        return False
    if re.fullmatch(r"[a-z0-9_.+-]+", clean):
        return bool(re.search(rf"\b{re.escape(clean)}\b", text, flags=re.I))
    return clean in text or clean.replace(" ", "") in compact


WPS_LANE_TERMS: dict[str, tuple[str, ...]] = {
    "wps_ai": (
        "WPS AI",
        "WPSAI",
        "金山办公 AI",
        "AI伴写",
        "AI 伴写",
        "AI伴写2.0",
        "AI写作",
        "AI 写作",
        "AI写文档",
        "AI 写文档",
        "AI润色",
        "AI 润色",
        "AI总结",
        "AI 总结",
        "AI阅读",
        "AI 阅读",
        "AI阅读PDF",
        "AI 阅读 PDF",
        "PDF总结",
        "PDF 总结",
        "PDF文档问答",
        "AI全文总结",
        "AI写公式",
        "AI 写公式",
        "数据问答",
        "条件格式",
        "智能报表",
        "AI文档生成PPT",
        "AI 文档生成 PPT",
        "AI处理表格",
        "AI 处理表格",
        "AI表格",
        "AI 表格",
        "表格分析",
        "AI数据分析",
        "AI 数据分析",
        "AI设计",
        "AI 设计",
        "AIPPT",
        "AI PPT",
        "AI做PPT",
        "AI 做PPT",
        "边聊边改",
        "HTML素材",
        "HTML 素材",
        "AI大模型 HTML",
        "AI 大模型 HTML",
        "PPT动态增强",
        "PPT 动态增强",
    ),
    "lingxi": (
        "WPS灵犀",
        "WPS 灵犀",
        "灵犀",
        "lingxi",
        "AI 原生办公",
        "AI原生办公",
        "AI办公全能伙伴",
        "Office 办公智能体",
        "办公智能体",
        "演示智能体",
        "表格智能体",
        "文档智能体",
        "AI搜索",
        "AI 搜索",
        "深度搜索",
        "多文件解读",
        "文件解读",
        "语音文档对话",
        "灵犀语音助手",
        "文档开口说话",
        "截图问答",
        "划词工具栏",
        "AI创作",
        "AI 创作",
        "信息溯源",
        "思维导图",
        "生成文档",
        "生成PPT大纲",
        "生成 PPT 大纲",
        "DeepSeek-R1",
        "WPS灵犀圈子",
    ),
    "claw_agent": (
        "灵犀 Claw",
        "灵犀Claw",
        "Claw",
        "AI 执行 Agent",
        "AI执行 Agent",
        "AI执行",
        "执行 Agent",
        "数字员工",
        "AI员工",
        "任务拆解",
        "工具调用",
        "tool calling",
        "MCP",
        "MCP协议",
        "skill",
        "CLI",
        "电脑操作",
        "浏览器操作",
        "系统操作",
        "本地系统操作",
        "端侧大模型",
        "离线运行",
        "虚拟机沙箱",
        "长周期运行",
        "AI记忆",
        "AI 工时",
        "AI工时",
        "AI替你干活",
        "AI 替你干活",
        "外部 SaaS 连接",
        "外部SaaS连接",
        "AI分身",
        "AI 分身",
        "AI项目管理",
        "AI 项目管理",
    ),
    "ai_office_adjacent": (
        "AI PPT",
        "AIPPT",
        "AI 笔记",
        "AI笔记",
        "WPS笔记",
        "WPS 笔记",
        "AI 知识库",
        "AI知识库",
        "AI办公工具",
        "AI 办公工具",
        "AI办公软件",
        "AI 办公软件",
        "AI办公助手",
        "AI 办公助手",
        "KaaS",
        "Knowledge as a Service",
        "MonkeyOCR",
        "文档解析",
        "智能文档库",
        "AI Docs",
        "企业大脑",
        "办公自动化",
        "移动办公",
        "WPS for Pad",
        "WPS Pad",
        "原生桌面级Office",
        "原生桌面级 Office",
        "桌面级办公",
        "平板办公",
        "国际版",
        "iPad办公",
        "iPad 办公",
        "鸿蒙办公",
        "分布式能力",
        "跨端协同",
        "分布式协同",
        "跨端续写",
        "无感调用",
        "碰一碰传图",
        "跨端复制粘贴",
        "文档秒开",
        "多端智能办公",
        "WPS云文档",
        "WPS 云文档",
        "AI原生笔记",
        "AI 原生笔记",
        "龙虾直写",
        "龙虾",
        "语音转写",
        "图片结构化处理",
        "多模态录入",
        "内容重构",
        "开源Skill仓库",
        "开源 Skill 仓库",
        "原子能力接口",
        "工具协同",
        "知识沉淀",
        "HTML素材库",
        "HTML 素材库",
        "多模态文档解析",
        "文档智能解析",
        "复杂表格解析",
        "表格结构还原",
        "知识广场",
        "AI生成知识库简介",
        "AI 生成知识库简介",
        "一键创建知识库",
        "知识孤岛",
        "私有文档对话",
        "毫秒级召回",
        "SDK开放",
        "SDK 开放",
    ),
    "competitor_context": (
        "Microsoft 365 Copilot",
        "Microsoft Office",
        "Microsoft 365",
        "Copilot",
        "Google Gemini for Workspace",
        "Google Workspace",
        "Notion AI",
        "Canva",
        "Gamma",
        "Tome",
        "Beautiful.ai",
        "Adobe Express",
        "飞书",
        "钉钉",
        "企业微信",
        "腾讯 WorkBuddy",
        "WorkBuddy",
        "腾讯文档 AI",
        "Kimi",
        "豆包",
        "Claude Code",
        "GitHub Copilot",
        "GitHub Codex",
        "Cursor",
    ),
    "risk_context": (
        "会员套娃",
        "套娃",
        "又要收费",
        "大会员白买",
        "积分消耗",
        "积分定价",
        "隐私",
        "数据安全",
        "幻觉",
        "格式错乱",
        "产品混淆",
        "AI 功能再升级",
        "AI功能再升级",
        "WPS AI 升级版",
        "大会员",
    ),
}

WPS_BRAND_TERMS: tuple[str, ...] = (
    "金山办公",
    "金山文档",
    "金山协作",
    "WPS",
    "WPS AI",
    "WPSAI",
    "WPS365",
    "WPS 365",
    "WPS Office",
    "Kingsoft Office",
    "kdocs",
    "WPS灵犀",
    "WPS 灵犀",
    "灵犀 Claw",
    "灵犀Claw",
    "lingxi",
)

WPS_CONTEXT_TERMS: tuple[str, ...] = (
    "办公",
    "office",
    "文档",
    "ppt",
    "表格",
    "pdf",
    "知识库",
    "笔记",
    "协作",
    "多人协作",
    "效率",
    "职场",
    "汇报",
    "总结",
    "论文",
    "简历",
    "写作",
    "阅读",
    "数据分析",
    "设计",
    "素材",
    "移动办公",
    "平板",
    "鸿蒙",
    "智能体",
    "数字员工",
    "工具调用",
    "自动化",
)

WPS_AGENT_CONTEXT_TERMS: tuple[str, ...] = (
    "办公",
    "office",
    "文档",
    "ppt",
    "表格",
    "pdf",
    "知识库",
    "笔记",
    "协作",
    "效率",
    "职场",
    "汇报",
    "智能体",
    "数字员工",
    "工具调用",
    "自动化",
    "办公软件",
    "云文档",
    "多维表格",
    "多人协作",
    "移动办公",
    "平板",
    "鸿蒙",
)

WPS_AMBIGUOUS_AI_TERMS: tuple[str, ...] = (
    "AI Agent",
    "Agent",
    "智能体",
    "MCP",
    "skill",
    "token",
    "工具调用",
    "tool calling",
    "computer use",
    "browser automation",
)

WPS_UNAMBIGUOUS_VERTICAL_TERMS: tuple[str, ...] = (
    "办公AI",
    "AI办公",
    "智能办公",
    "AI Office",
    "Office AI",
    "AI办公工具",
    "AI 办公工具",
    "AI办公软件",
    "AI 办公软件",
    "AI办公助手",
    "AI 办公助手",
    "办公套件",
    "办公软件",
    "办公软件推荐",
    "Office 替代",
    "Office替代",
    "国产办公软件",
    "协同办公",
    "多人协作办公",
    "文档协作",
    "内容协作",
    "云文档",
    "智能文档",
    "智能表格",
    "智能表单",
    "多维表格",
    "PPT生成",
    "生成PPT",
    "AI PPT",
    "PPT AI",
    "AIPPT",
    "演示文稿",
    "presentation ai",
    "文档编辑软件",
    "表格软件",
    "PPT制作软件",
    "PPT 制作软件",
    "PDF编辑工具",
    "PDF 编辑工具",
    "文字处理",
    "电子表格",
    "PDF编辑",
    "企业云盘",
    "数字资产管理",
    "国产化办公",
    "国产办公",
    "信创办公",
    "政企办公",
    "办公安全",
    "办公Agent",
    "Office Agent",
    "文档Agent",
    "PPT Agent",
    "AI 笔记",
    "AI笔记",
    "AI 知识库",
    "AI知识库",
    "KaaS",
    "MonkeyOCR",
    "文档解析",
    "智能文档库",
    "WPS云文档",
    "WPS 云文档",
    "WPS for Pad",
    "原生桌面级Office",
    "原生桌面级 Office",
    "平板办公",
    "鸿蒙办公",
    "办公自动化",
    "移动办公",
)

WPS_OFFICE_TERMS: tuple[str, ...] = tuple(
    _unique(
        [
            *WPS_BRAND_TERMS,
            *WPS_UNAMBIGUOUS_VERTICAL_TERMS,
            *WPS_LANE_TERMS["wps_ai"],
            *WPS_LANE_TERMS["lingxi"],
            *WPS_LANE_TERMS["ai_office_adjacent"],
        ]
    )
)


def analyze_wps_semantics(query: str) -> dict[str, Any]:
    """Classify a query into WPS semantic lanes and safe trigger state."""
    text = _norm(query)
    compact = _compact(query)
    lane_matches: dict[str, list[str]] = {}
    for lane, terms in WPS_LANE_TERMS.items():
        matches = [term for term in terms if _term_matches(text, compact, term)]
        if matches:
            lane_matches[lane] = _unique(matches)

    brand_matches = [term for term in WPS_BRAND_TERMS if _term_matches(text, compact, term)]
    vertical_matches = [term for term in WPS_UNAMBIGUOUS_VERTICAL_TERMS if _term_matches(text, compact, term)]
    ambiguous_matches = [term for term in WPS_AMBIGUOUS_AI_TERMS if _term_matches(text, compact, term)]
    context_matches = [term for term in WPS_CONTEXT_TERMS if _term_matches(text, compact, term)]
    agent_context_matches = [term for term in WPS_AGENT_CONTEXT_TERMS if _term_matches(text, compact, term)]

    has_brand = bool(brand_matches)
    has_vertical = bool(vertical_matches)
    has_contextual_ai = bool(ambiguous_matches and agent_context_matches)
    has_lane_signal = bool({"wps_ai", "lingxi", "ai_office_adjacent"} & set(lane_matches))
    is_wps_office = bool(has_brand or has_vertical or has_contextual_ai or has_lane_signal)

    lanes = list(lane_matches)
    if is_wps_office and has_contextual_ai and "claw_agent" not in lanes:
        lanes.append("claw_agent")

    return {
        "is_wps_office": is_wps_office,
        "lanes": _unique(lanes),
        "matches": lane_matches,
        "brand_terms": _unique(brand_matches),
        "vertical_terms": _unique(vertical_matches),
        "ambiguous_ai_terms": _unique(ambiguous_matches),
        "context_terms": _unique(context_matches),
    }


def wps_semantic_summary(query: str) -> dict[str, Any]:
    analysis = analyze_wps_semantics(query)
    return {
        "brand_terms": analysis["brand_terms"][:8],
        "vertical_terms": analysis["vertical_terms"][:8],
        "ambiguous_ai_terms": analysis["ambiguous_ai_terms"][:8],
        "context_terms": analysis["context_terms"][:8],
        "lane_terms": {lane: terms[:8] for lane, terms in analysis["matches"].items()},
    }


def is_wps_office_semantic_query(query: str) -> bool:
    return bool(analyze_wps_semantics(query).get("is_wps_office"))


def wps_office_subroute(query: str) -> str:
    analysis = analyze_wps_semantics(query)
    lanes = set(analysis.get("lanes") or [])
    compact = _compact(query)
    text = _norm(query)
    if "lingxi" in lanes or "claw_agent" in lanes or "claw" in compact:
        return "lingxi"
    if "wps365" in compact or "wps 365" in text or "365.wps" in compact:
        return "wps365"
    if "wps_ai" in lanes or "wpsai" in compact or "wps ai" in text or "aippt" in compact or "ai ppt" in text:
        return "wps_ai"
    if "ai_office_adjacent" in lanes:
        return "adjacent"
    return "general"


def wps_route_query_variants(query: str) -> list[str]:
    """Return high-signal WPS variants. Caller may cap to preserve speed."""
    clean = " ".join((query or "").split())
    analysis = analyze_wps_semantics(clean)
    lanes = set(analysis.get("lanes") or [])
    subroute = wps_office_subroute(clean)
    variants: list[str] = []

    if subroute == "wps_ai" or "wps_ai" in lanes:
        variants.extend(
            [
                f"{clean} AI伴写2.0 AI PPT 边聊边改 PDF文档问答 AI写公式 数据问答 条件格式",
                f"{clean} AI写文档 AI润色 AI总结 AI阅读PDF AI处理表格 AI设计 职场效率 论文 汇报 总结 简历",
                f"{clean} Gamma Canva Tome Beautiful.ai Adobe Express Copilot AI PPT 对比",
                f"{clean} 国产 AI PPT 工具 横评 实测 榜单 效率场景",
            ]
        )
        if "html" in _norm(clean) or "素材" in clean or "交互式" in clean:
            variants.insert(0, f"{clean} WPS AIPPT HTML素材 代码嵌入 交互式演示 教学课件 资源库")
    if subroute == "adjacent" or "ai_office_adjacent" in lanes:
        adjacent_variants = [
            f"{clean} AI 笔记 AI 知识库 KaaS 文档解析 OCR MonkeyOCR",
            f"{clean} 智能文档库 AI Docs AI Hub Copilot Pro 企业大脑 知识广场 知识服务",
            f"{clean} WPS for Pad iPadOS App Store 国际版 Apple Pencil 原生桌面级 Office",
            f"{clean} 鸿蒙 HarmonyOS 小艺 分布式协同 跨端续写 无感调用 碰一碰传图",
            f"{clean} WPS笔记 AI原生笔记 龙虾直写 语音转写 图片结构化处理 MCP CLI",
            f"{clean} WPS云文档 政务服务 交通出行 应急路况 一键分享 多端协同 民生服务",
            f"{clean} Notion AI Mem 飞书知识库 Microsoft Copilot 办公 Agent 对比",
        ]
        compact_clean = _compact(clean)
        if "笔记" in clean or "龙虾" in clean:
            adjacent_variants.insert(0, f"{clean} WPS笔记 AI原生笔记 龙虾直写 语音转写 图片结构化处理 MCP CLI")
        if any(term in compact_clean for term in ("wpsforpad", "ipad", "鸿蒙", "harmonyos")):
            adjacent_variants.insert(0, f"{clean} WPS for Pad iPadOS App Store 国际版 鸿蒙 HarmonyOS 小艺 分布式协同")
        if "云文档" in clean or "路况" in clean:
            adjacent_variants.insert(0, f"{clean} WPS云文档 政务服务 交通出行 应急路况 一键分享 多端协同 民生服务")
        variants.extend(adjacent_variants)
    if subroute == "lingxi" or {"lingxi", "claw_agent"} & lanes:
        variants.extend(
            [
                f"{clean} AI办公全能伙伴 原生 Office 智能体 演示智能体 表格智能体 文档智能体 语音文档对话",
                f"{clean} 深度搜索 多文件解读 信息溯源 思维导图 生成文档 Office 办公智能体 对话式办公",
                f"{clean} 灵犀 Claw 数字员工 MCP skill 工具调用 端侧大模型 虚拟机沙箱 AI替你干活",
                f"{clean} Microsoft Copilot 飞书 钉钉 企业微信 WorkBuddy Agent 对比",
            ]
        )
    if subroute == "wps365":
        variants.extend(
            [
                f"{clean} 企业大脑 组织协同 AI Office 政企 金融 行业落地",
                f"{clean} 办公智能体 知识库 数字资产管理 协同平台 选题",
                f"{clean} Microsoft 365 Copilot Google Workspace 飞书 钉钉 企业微信",
            ]
        )
    if not variants:
        variants.extend(
            [
                f"{clean} 办公软件推荐 Office 替代 国产办公软件 文档 表格 演示 PDF 云文档 AI 功能",
                f"{clean} Microsoft Office Microsoft 365 飞书文档 钉钉文档 腾讯文档 Google Workspace Notion 对比",
                f"{clean} 行业热点 选题 办公智能体 AI Agent AI PPT 文档协作",
                f"{clean} 企业 AI 上下文 知识库 多维表格 多人协作 移动办公 自动化",
                f"{clean} WPS云文档 政务服务 交通出行 应急路况 一键分享 多端协同 民生服务",
            ]
        )

    variants.extend(
        [
            f"{clean} 金山办公 WPS AI WPS 365 官方 发布 产品 文档",
            f"{clean} 办公 AI PPT 文档协作 SaaS 信创 行业 趋势 移动办公 平板办公 鸿蒙",
            f"{clean} 用户评价 体验 吐槽 知乎 小红书 B站 V2EX",
            f"{clean} Agent API skill MCP 插件 自动化 文档协作 开发者 开源Skill仓库",
            f"{clean} 安全 权限 数据合规 信创 等保 国产化",
        ]
    )
    return _unique([variant for variant in variants if variant != clean])


def wps_strategy_variants(query: str) -> list[dict[str, str]]:
    clean = " ".join((query or "").split())
    return [
        {"role": "topic_radar", "query": variant, "reason": "补 WPS/AI Office 语义 lane 的高信号选题词"}
        for variant in wps_route_query_variants(clean)
    ]
