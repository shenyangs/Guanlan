# Brand Communications Workflows

Use these playbooks for brand PR, marketing, campaign, external relations, media relations, and reputation work.

## Shared Answer Frame

For communications users, produce a practical brief rather than a raw search dump:

- `Situation`: what is visible now, with dates and source types.
- `Signals`: official statements, media reporting, community samples, hot/trend signals.
- `Risks`: what could be misread, amplified, or missing.
- `Evidence gaps`: what must be verified before external action.
- `Next actions`: read more, monitor, prepare statement, map stakeholders, or hold.

Do not present platform heat as fact. Use language like "visible heat on these public sources" instead of "the internet believes".

## Reputation / Word-Of-Mouth Scan

Use when the user asks "大家怎么看", "口碑如何", "有没有负面", "品牌最近舆论".

```bash
guanlan research "品牌/产品 用户评价 口碑 负面 风险" --preset reputation --limit 80 --advisor --format context
guanlan search "品牌/产品 用户评价 投诉 值不值得买" --profile china --limit 80 --trace
guanlan hotnews today --limit 80 --trends
guanlan sources explain "品牌/产品 用户评价 口碑"
```

Read representative URLs across official, vertical media, review/community, and complaint/discussion samples. Keep "sample" language for social/community evidence.

## Crisis / Negative Trend Tracking

Use when the task involves a sudden issue, accusation, boycott, accident, service outage, regulatory notice, or viral controversy.

```bash
guanlan timeline "品牌/事件 最新进展 原因 回应" --limit 80 --format context
guanlan research "品牌/事件 官方回应 媒体报道 社区讨论 风险" --profile china --limit 80 --advisor
guanlan hotnews today --limit 80 --trends
guanlan search "品牌/事件 site:gov.cn" --profile china --limit 80 --trace
```

Prioritize timestamps and original statements. Separate:

- brand/company response;
- regulator or platform notice;
- media summaries;
- user/KOL samples;
- rumor or unverified screenshots.

If a page is dynamic or gated, diagnose before using it:

```bash
guanlan diagnose page "URL"
```

## Campaign / Launch Terrain

Use when planning a launch, campaign theme, event, spokesperson, or media angle.

```bash
guanlan route "品牌 活动 主题 用户兴趣 竞品 传播风险" --json
guanlan research "品牌 活动 主题 竞品 用户讨论 媒体报道" --profile china --limit 80 --advisor
guanlan hotnews today --limit 80 --trends
guanlan feeds curated --limit 80
```

Output:

- audience language and recurring phrases;
- current news hooks;
- platform-fit signals;
- claims to avoid;
- possible official/vertical sources to read.

For AI, tech, gaming, digital product, or developer-facing campaigns, include RSS/feeds because hot social search alone misses important technical sources.

## Competitor Messaging Comparison

Use for category narrative, competitor launch, brand positioning, or "我们和竞品怎么讲".

```bash
guanlan compare "品牌A" "品牌B" --focus "传播声量 卖点 口碑 风险 用户样本" --limit 80 --format context
guanlan dossier "品牌A" --focus "业务 传播 口碑 风险" --limit 80 --format context
guanlan dossier "品牌B" --focus "业务 传播 口碑 风险" --limit 80 --format context
```

Separate owned messaging from earned media and user language. Do not infer market share or purchase intent unless the evidence directly supports it.

## Media / Stakeholder Mapping

Use when the user needs "哪些媒体在写", "有哪些垂类源", "谁在讨论", "外联前先看版图".

```bash
guanlan search "品牌/行业 媒体 报道 观察 评论" --profile china --limit 80 --trace
guanlan sources explain "品牌/行业 媒体 报道"
guanlan research "品牌/行业 媒体报道 垂类媒体 社区讨论" --profile china --limit 80 --advisor
```

This skill must not automate outreach, scraping private contact data, messaging, following, commenting, or posting. Keep the output to public source mapping and evidence-based context.

## Daily Monitoring Brief

Use when the user asks for a daily pulse, watch brief, or "今天有什么和品牌/行业有关".

```bash
guanlan hotnews today --limit 80 --trends
guanlan search "品牌/行业 今天 最新 动态" --profile china --limit 80 --trace
guanlan feeds curated --limit 80
```

For each item, tag it as:

- `action_now`: likely needs review or response;
- `watch`: monitor but no immediate response;
- `background`: useful context only;
- `discard`: weak or irrelevant.

## Output Language

Prefer concise Chinese. Use "可见样本", "公开来源", "初步信号", "待核验", "建议补读原文" to avoid overclaiming.
