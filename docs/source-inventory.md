# Guanlan 信源盘点

生成口径：从本仓库源码只读汇总，不联网，不代表实时可用性。

## 口径边界

- `search scope`：搜索/研究时的域名白名单和优先源池，是事实核验的主入口。
- `source pack`：把高价值源按研究任务打包，给路由、推荐站点和 hotboard node 提示使用。
- `source matrix`：热榜、RSS、AI 垂类、arXiv、watchlist 等发现层入口。
- `search entrypoint catalog`：搜索引擎入口和高级检索语法的只读目录，用于解释 Baidu/Bing/DuckDuckGo/搜狗微信/头条/集思录/Google 等入口边界；不是默认联网后端。
- `channel catalog`：平台/后端能力目录，说明 auth、风险和稳定性，不等同于具体内容源。
- `hotboard catalog`：随包附带的大型热榜节点目录，数量很大，本文件按分类统计；全量节点在 `guanlan/data/hotboard_nodes.json`。

## 总览

| 项目 | 数量 |
| --- | --- |
| search scopes | 36 |
| scope 域名行数 | 579 |
| scope 去重域名 | 474 |
| source packs | 12 |
| source pack 条目 | 204 |
| source matrix 条目 | 40 |
| search entrypoint catalog | 17 |
| 热榜 source_id 入口 | 31 |
| feeds 入口 | 9 |
| Ebrun 垂类频道 | 27 |
| UAPI hotboard 平台 | 46 |
| VVHAN hotlist alias | 9 |
| TopHub 目录分类 | 15 |
| channel catalog | 20 |
| hotboard 去重节点 | 10843 |

## 一、搜索 Scope 信源矩阵

| scope | 名称 | 类型 | 信任 | 域名数 | 域名 |
| --- | --- | --- | --- | --- | --- |
| party_central | 党央媒与中央重点媒体 | 党央媒 | 5 | 15 | `people.com.cn, xinhuanet.com, cctv.com, cntv.cn, qstheory.cn, 12371.cn, gmw.cn, ce.cn, cnr.cn, cri.cn, chinanews.com.cn, china.com.cn,`<br>`chinadaily.com.cn, news.cctv.com, banyuetan.org` |
| gov | 政府与部委网站 | 政府/部委 | 5 | 17 | `gov.cn, mfa.gov.cn, ndrc.gov.cn, miit.gov.cn, mofcom.gov.cn, mof.gov.cn, stats.gov.cn, samr.gov.cn, nhc.gov.cn, nmpa.gov.cn, moj.gov.cn,`<br>`court.gov.cn, npc.gov.cn, wenshu.court.gov.cn, pbc.gov.cn, csrc.gov.cn, cac.gov.cn` |
| local_official | 核心地方官媒 | 地方官媒 | 4 | 18 | `bjd.com.cn, jfdaily.com, thepaper.cn, eastday.com, southcn.com, ycwb.com, xhby.net, dzwww.com, dahe.cn, rednet.cn, cnhubei.com, cqnews.net,`<br>`newssc.org, yunnan.cn, fjnews.com, hinews.cn, gxnews.com.cn, hebnews.cn` |
| business | 商业与产业媒体 | 商业/产业媒体 | 3 | 13 | `36kr.com, huxiu.com, cyzone.cn, iyiou.com, ebrun.com, tmtpost.com, geekpark.net, pingwest.com, leiphone.com, donews.com, jiemian.com, yicai.com, latepost.com` |
| ecommerce | 电商与零售垂类 | 电商/零售垂类 | 3 | 10 | `ebrun.com, iyiou.com, donews.com, jiemian.com, linkshop.com, ccfa.org.cn, 100ec.cn, chuhai-club.com, cifnews.com, egainnews.com` |
| tech_dev | 科技与开发者社区 | 科技/开发者社区 | 3 | 28 | `v2ex.com, juejin.cn, segmentfault.com, csdn.net, cnblogs.com, oschina.net, infoq.cn, 51cto.com, sspai.com, ithome.com, linux.do, nodeseek.com,`<br>`52pojie.cn, geekpark.net, ifanr.com, leiphone.com, jiqizhixin.com, qbitai.com, aiera.com.cn, readhub.cn, solidot.org, the-decoder.com, techcrunch.com, venturebeat.com, wired.com, marktechpost.com, artificialintelligence-news.com, testerhome.com` |
| wps_office | 金山办公/WPS 与 AI Office | 办公软件/AI Office/SaaS | 3 | 56 | `wps.cn, 365.wps.cn, bbs.wps.cn, security.wps.cn, kdocs.cn, wps.com, kingsoftoffice.com, ir.kingsoft.com, microsoft.com,`<br>`support.microsoft.com, techcommunity.microsoft.com, office.com, microsoft365.com, workspace.google.com, notion.so, coda.io, canva.com,`<br>`gamma.app, beautiful.ai, tome.app, prezi.com, pitch.com, feishu.cn, larkoffice.com, yuque.com, shimo.im, processon.com, jianguoyun.com,`<br>`ithome.com, sspai.com, 36kr.com, huxiu.com, geekpark.net, leiphone.com, jiqizhixin.com, qbitai.com, aiera.com.cn, infoq.cn, v2ex.com,`<br>`juejin.cn, producthunt.com, g2.com, capterra.com, reddit.com, news.ycombinator.com, lingxi.wps.cn, kimi.com, doubao.com, openai.com,`<br>`anthropic.com, deepmind.google, simonwillison.net, oneusefulthing.org, karpathy.ai, blog.samaltman.com, github.com` |
| cybersecurity | 网络安全/CVE/反诈 | 网络安全/漏洞/反诈 | 5 | 18 | `nvd.nist.gov, cisa.gov, mitre.org, cve.org, cnvd.org.cn, cnnvd.org.cn, cert.org.cn, cert.org, openssl.org, msrc.microsoft.com,`<br>`security.googleblog.com, krebsonsecurity.com, osv.dev, security-tracker.debian.org, ubuntu.com, access.redhat.com, cert.europa.eu, bbs.kanxue.com` |
| academic | 学术与论文检索 | 学术/论文检索 | 4 | 22 | `elsevier.com, engineeringvillage.com, sciencedirect.com, ieee.org, acm.org, springer.com, webofscience.com, clarivate.com, cnki.net,`<br>`wanfangdata.com.cn, cqvip.com, xueshu.baidu.com, crossref.org, datacite.org, openalex.org, ncbi.nlm.nih.gov, europepmc.org, zenodo.org, doaj.org, semanticscholar.org, core.ac.uk, unpaywall.org` |
| science | 科学机构与科研新闻 | 科学机构/科研新闻 | 5 | 19 | `nasa.gov, esa.int, nature.com, science.org, sciencemag.org, arxiv.org, pnas.org, noirlab.edu, stsci.edu, nih.gov, ncbi.nlm.nih.gov,`<br>`europepmc.org, openalex.org, datacite.org, zenodo.org, lmsys.org, bair.berkeley.edu, ml.cmu.edu, eleuther.ai` |
| university | 高校招生与院系官网 | 高校/院系官网 | 5 | 15 | `edu.cn, tsinghua.edu.cn, cs.tsinghua.edu.cn, yz.tsinghua.edu.cn, gradadmission.tsinghua.edu.cn, pku.edu.cn, eecs.pku.edu.cn, zju.edu.cn,`<br>`fudan.edu.cn, sjtu.edu.cn, ustc.edu.cn, nju.edu.cn, hit.edu.cn, whu.edu.cn, buaa.edu.cn` |
| test_prep | 考试与培训资料 | 考试/培训/备考 | 3 | 10 | `ielts.org, toefl.cn, ets.org, neea.edu.cn, chinaielts.org, chsi.com.cn, eol.cn, koolearn.com, xdf.cn, zhihu.com` |
| finance | 财经与资本市场 | 财经/资本市场 | 4 | 20 | `cninfo.com.cn, sse.com.cn, szse.cn, csrc.gov.cn, stats.gov.cn, pbc.gov.cn, cls.cn, eastmoney.com, stcn.com, cnstock.com, yicai.com,`<br>`xueqiu.com, sec.gov, cs.com.cn, 21jingji.com, wallstreetcn.com, eeo.com.cn, nbd.com.cn, caixin.com, gelonghui.com` |
| finance_quote | 行情、指数与板块 | 财经/行情数据 | 3 | 12 | `quote.eastmoney.com, eastmoney.com, finance.sina.com.cn, xueqiu.com, 10jqka.com.cn, csindex.com.cn, sse.com.cn, szse.cn, finance.yahoo.com,`<br>`nasdaq.com, marketwatch.com, cn.investing.com` |
| finance_company | 公司基本面与投资者关系 | 财经/公司一手 | 5 | 7 | `cninfo.com.cn, sse.com.cn, szse.cn, hkexnews.hk, sec.gov, nasdaq.com, annualreports.com` |
| finance_disclosure | 公告、披露与监管 | 财经/公告披露 | 5 | 9 | `cninfo.com.cn, sse.com.cn, szse.cn, bse.cn, hkexnews.hk, csrc.gov.cn, sec.gov, pbc.gov.cn, safe.gov.cn` |
| finance_news | 财经新闻与市场快讯 | 财经/新闻报道 | 4 | 13 | `cls.cn, stcn.com, cnstock.com, cs.com.cn, yicai.com, caixin.com, 21jingji.com, eastmoney.com, wallstreetcn.com, reuters.com, bloomberg.com,`<br>`eeo.com.cn, nbd.com.cn` |
| finance_macro | 宏观金融与官方数据 | 财经/宏观数据 | 5 | 11 | `stats.gov.cn, pbc.gov.cn, safe.gov.cn, mof.gov.cn, ndrc.gov.cn, csrc.gov.cn, imf.org, worldbank.org, oecd.org, fred.stlouisfed.org, cmegroup.com` |
| finance_sentiment | 市场讨论与投资者情绪样本 | 财经/情绪样本 | 2 | 5 | `xueqiu.com, guba.eastmoney.com, eastmoney.com, weibo.com, zhihu.com` |
| finance_research | 研报、行业报告与观点 | 财经/研报观点 | 3 | 11 | `eastmoney.com, data.eastmoney.com, pdf.dfcfw.com, stock.finance.sina.com.cn, cnstock.com, stcn.com, iresearch.com.cn, 199it.com,`<br>`qianzhan.com, leadleo.com, gelonghui.com` |
| social_web | 社交与内容平台公开页 | 社交/内容平台 | 2 | 11 | `weibo.com, xiaohongshu.com, zhihu.com, bilibili.com, douyin.com, toutiao.com, kuaishou.com, douban.com, tousu.sina.com.cn, 12365auto.com, v2ex.com` |
| career | 招聘/薪资/面经 | 招聘/职场/薪资 | 3 | 11 | `levels.fyi, glassdoor.com, linkedin.com, nowcoder.com, yingjiesheng.com, zhipin.com, liepin.com, lagou.com, maimai.cn, teamblind.com, indeed.com` |
| sports | 体育赛事/转会/数据 | 体育/赛事/转会 | 3 | 10 | `espn.com, skysports.com, theathletic.com, fifa.com, uefa.com, nba.com, mlb.com, hupu.com, dongqiudi.com, transfermarkt.com` |
| weather_disaster | 天气/灾害/预警 | 天气/灾害/预警 | 5 | 9 | `nmc.cn, cma.gov.cn, weather.com.cn, jma.go.jp, noaa.gov, mem.gov.cn, nhc.noaa.gov, usgs.gov, gdacs.org` |
| podcast | 播客/音频/RSS | 播客/音频/RSS | 3 | 8 | `xiaoyuzhoufm.com, podcasts.apple.com, spotify.com, podcastaddict.com, podchaser.com, listennotes.com, google.com, rss.com` |
| entertainment | 文娱与内容消费 | 文娱/内容平台 | 3 | 28 | `douban.com, maoyan.com, piaofang.maoyan.com, lighthouse.alibaba.com, taopiaopiao.com, mtime.com, 1905.com, bilibili.com, weibo.com,`<br>`v.qq.com, iqiyi.com, youku.com, mgtv.com, taptap.cn, gamersky.com, 3dmgame.com, ign.com.cn, indienova.com, bangumi.tv, pixiv.net,`<br>`mangapedia.com, manba.co.jp, comic-walker.com, bookwalker.jp, movie.douban.com, taptap.com, gcores.com, yystv.cn` |
| global_entertainment | 欧美娱乐与音乐产业 | 欧美文娱/音乐产业 | 3 | 12 | `variety.com, deadline.com, hollywoodreporter.com, billboard.com, rollingstone.com, people.com, ew.com, pitchfork.com, stereogum.com,`<br>`nme.com, grammy.com, officialcharts.com` |
| jp_kr_entertainment | 日韩娱乐与 K-pop/J-pop | 日韩文娱/K-pop/J-pop | 3 | 12 | `soompi.com, oricon.co.jp, natalie.mu, entertain.naver.com, koreaherald.com, koreatimes.co.kr, mdpr.jp, realsound.jp, mantan-web.jp,`<br>`allkpop.com, koreaboo.com, tokyohive.com` |
| standards | 标准、规范与合规原文 | 标准/规范/合规原文 | 5 | 14 | `std.samr.gov.cn, samr.gov.cn, tc260.org.cn, iso.org, iec.ch, nist.gov, csrc.nist.gov, w3.org, ietf.org, rfc-editor.org, oasis-open.org,`<br>`standards.ieee.org, etsi.org, itu.int` |
| global_official | 英文官方/监管与公共机构 | 英文官方/监管 | 5 | 16 | `usa.gov, whitehouse.gov, congress.gov, federalregister.gov, sec.gov, ftc.gov, fda.gov, nist.gov, iso.org, iec.ch, cdc.gov, who.int,`<br>`oecd.org, worldbank.org, europa.eu, ec.europa.eu` |
| company_primary | 公司一手资料 | 公司一手资料 | 5 | 29 | `openai.com, anthropic.com, googleblog.com, blog.google, microsoft.com, azure.microsoft.com, aws.amazon.com, aboutamazon.com, meta.com,`<br>`ai.meta.com, nvidia.com, tsmc.com, apple.com, tesla.com, bytedance.com, doubao.com, volcengine.com, stripe.com, shopify.com,`<br>`luckincoffee.com, deepmind.google, research.google, mistral.ai, x.ai, cursor.com, openrouter.ai, runwayml.com, midjourney.com,`<br>`machinelearning.apple.com` |
| developer | 英文开发者与开源 | 英文开发者/开源 | 4 | 32 | `github.com, docs.github.com, stackoverflow.com, developer.mozilla.org, docs.python.org, nodejs.org, npmjs.com, pypi.org, crates.io,`<br>`rubygems.org, packagist.org, search.maven.org, pkg.go.dev, osv.dev, rfc-editor.org, ietf.org, w3.org, oasis-open.org, huggingface.co, pytorch.org, kubernetes.io, docs.docker.com, cloudflare.com, vercel.com, milvus.io, qdrant.tech, weaviate.io, trychroma.com, github.blog, blog.cloudflare.com, developer.nvidia.com, hellogithub.com` |
| global_news | 国际主流新闻 | 国际主流媒体 | 4 | 14 | `reuters.com, apnews.com, bbc.com, cnn.com, nytimes.com, washingtonpost.com, theguardian.com, ft.com, wsj.com, bloomberg.com, cnbc.com,`<br>`taipeitimes.com, theverge.com, technologyreview.com` |
| industry_analysis | 英文产业与分析 | 英文产业/分析 | 3 | 14 | `gartner.com, forrester.com, mckinsey.com, bain.com, bcg.com, a16z.com, stratechery.com, theinformation.com, semianalysis.com,`<br>`trendforce.com, tomshardware.com, anandtech.com, ben-evans.com, similarweb.com` |
| community_sample | 英文社区样本 | 英文社区样本 | 2 | 12 | `reddit.com, news.ycombinator.com, lobste.rs, medium.com, dev.to, producthunt.com, quora.com, simonwillison.net, oneusefulthing.org,`<br>`interconnects.ai, karpathy.ai, blog.samaltman.com` |
| market_review | 英文评价与消费样本 | 评价/消费样本 | 2 | 14 | `g2.com, capterra.com, trustpilot.com, trustradius.com, amazon.com, apps.apple.com, play.google.com, qimai.cn, diandian.com, producthunt.com,`<br>`store.steampowered.com, steamdb.info, alternativeto.net, appbrain.com` |

## 二、Source Pack 研究源包

| pack | 条目 | tier | 覆盖 scope | 域名 | 主要证据角色 |
| --- | --- | --- | --- | --- | --- |
| policy_research | 10 | core:10 | gov:1, party_central:9 | `gov.cn, people.com.cn, xinhuanet.com, news.cctv.com, qstheory.cn, banyuetan.org, gmw.cn, ce.cn, cnr.cn, chinanews.com.cn` | authoritative_report, official_primary, official_narrative, policy_interpretation, macro_policy_report, news_signal |
| tech_research | 33 | core:25, vertical:8 | tech_dev:11, business:4, ecommerce:1, company_primary:11, science:5, industry_analysis:1 | `ithome.com, sspai.com, 36kr.com, huxiu.com, tmtpost.com, ebrun.com, geekpark.net, ifanr.com, leiphone.com, jiqizhixin.com, qbitai.com,`<br>`aiera.com.cn, latepost.com, infoq.cn, readhub.cn, solidot.org, openai.com, anthropic.com, deepmind.google, research.google, mistral.ai,`<br>`x.ai, cursor.com, openrouter.ai, runwayml.com, midjourney.com, machinelearning.apple.com, lmsys.org, bair.berkeley.edu, ml.cmu.edu,`<br>`eleuther.ai, arxiv.org, semianalysis.com` | company_primary, industry_analysis, product_primary, industry_report, ai_news_signal, research_primary |
| finance_research | 14 | core:10, vertical:2, sample:2 | finance_news:10, finance_quote:1, finance_sentiment:2, finance_research:1 | `cls.cn, stcn.com, cnstock.com, cs.com.cn, yicai.com, 21jingji.com, wallstreetcn.com, eeo.com.cn, nbd.com.cn, caixin.com, eastmoney.com,`<br>`xueqiu.com, guba.eastmoney.com, gelonghui.com` | market_news, sentiment_sample, market_timeline, industry_report, investigative_report, market_quote |
| public_opinion_research | 10 | sample:9, vertical:1 | social_web:7, tech_dev:1, community_sample:2 | `weibo.com, zhihu.com, xiaohongshu.com, bilibili.com, douban.com, tousu.sina.com.cn, 12365auto.com, v2ex.com, reddit.com, news.ycombinator.com` | complaint_sample, developer_discussion, public_discussion_signal, question_answer_sample, consumer_note_sample, video_attention_signal |
| market_review_research | 9 | core:4, vertical:4, sample:1 | market_review:9 | `apps.apple.com, play.google.com, g2.com, capterra.com, trustpilot.com, trustradius.com, qimai.cn, diandian.com, producthunt.com` | saas_review_sample, app_store_review, app_market_signal, consumer_review_sample, product_launch_signal |
| competitive_watch_research | 8 | sample:1, core:6, vertical:1 | market_review:3, business:4, industry_analysis:1 | `producthunt.com, g2.com, capterra.com, 36kr.com, huxiu.com, tmtpost.com, latepost.com, similarweb.com` | saas_review_sample, industry_report, industry_analysis, product_launch_signal, traffic_signal |
| entertainment_research | 14 | core:8, sample:2, vertical:4 | entertainment:14 | `movie.douban.com, douban.com, maoyan.com, piaofang.maoyan.com, lighthouse.alibaba.com, 1905.com, mtime.com, bilibili.com, weibo.com,`<br>`taptap.com, gamersky.com, 3dmgame.com, gcores.com, yystv.cn` | box_office, film_news, game_news, game_culture, rating_sample, review_sample |
| developer_research | 22 | core:7, vertical:7, sample:8 | developer:6, tech_dev:10, cybersecurity:1, community_sample:5 | `github.com, huggingface.co, github.blog, blog.cloudflare.com, developer.nvidia.com, v2ex.com, juejin.cn, segmentfault.com, oschina.net,`<br>`cnblogs.com, csdn.net, infoq.cn, hellogithub.com, testerhome.com, linux.do, nodeseek.com, bbs.kanxue.com, simonwillison.net, oneusefulthing.org,`<br>`interconnects.ai, karpathy.ai, blog.samaltman.com` | developer_article, developer_news, developer_discussion, technical_commentary, ai_commentary, code_host, model_hub |
| academic_discovery | 10 | core:5, vertical:5 | academic:10 | `crossref.org, datacite.org, openalex.org, ncbi.nlm.nih.gov, europepmc.org, zenodo.org, doaj.org, semanticscholar.org, core.ac.uk, unpaywall.org` | doi_metadata_primary, dataset_doi_metadata, scholarly_graph, biomedical_index, research_repository, journal_directory, scholarly_discovery, open_access_discovery, open_access_status |
| standards_research | 12 | core:8, vertical:4 | standards:12 | `std.samr.gov.cn, tc260.org.cn, iso.org, iec.ch, nist.gov, w3.org, ietf.org, rfc-editor.org, oasis-open.org, standards.ieee.org, etsi.org, itu.int` | standard_original, standard_catalog, web_standard_original, internet_standard_original, rfc_original, telecom_standard_original |
| wps_office_research | 44 | core:15, vertical:17, sample:12 | wps_office:44 | `wps.cn, 365.wps.cn, bbs.wps.cn, security.wps.cn, kdocs.cn, wps.com, ir.kingsoft.com, lingxi.wps.cn, microsoft.com, support.microsoft.com,`<br>`techcommunity.microsoft.com, workspace.google.com, kimi.com, doubao.com, notion.so, canva.com, gamma.app, beautiful.ai, feishu.cn,`<br>`larkoffice.com, yuque.com, shimo.im, ithome.com, sspai.com, 36kr.com, huxiu.com, leiphone.com, jiqizhixin.com, qbitai.com, infoq.cn,`<br>`openai.com, anthropic.com, deepmind.google, simonwillison.net, oneusefulthing.org, karpathy.ai, blog.samaltman.com, news.ycombinator.com,`<br>`github.com, v2ex.com, juejin.cn, g2.com, producthunt.com, reddit.com` | competitor_primary, product_primary, collaboration_product, presentation_ai_tool, company_primary, document_collaboration |
| university_official | 10 | core:10 | university:10 | `tsinghua.edu.cn, pku.edu.cn, fudan.edu.cn, sjtu.edu.cn, zju.edu.cn, nju.edu.cn, ustc.edu.cn, hit.edu.cn, whu.edu.cn, buaa.edu.cn` | university_official |

## 三、热榜与发现层 Source Matrix

### 热榜入口总表

这张表把两种粒度放到一起：`source_id` 行是可以直接执行的热榜入口，`provider/catalog` 行是能展开更多入口的聚合器或本地目录。

| 层级 | 入口 | 名称/范围 | 后端/平台 | 状态 | 域名/目录 | 证据角色/用途 |
| --- | --- | --- | --- | --- | --- | --- |
| source_id | today | 今日多源热榜 | guanlan | stable | baidu/weibo/bilibili/ithome/v2ex 等 | multi_source_snapshot |
| source_id | tech | 科技与开发者多源快照 | guanlan | stable | IT之家/新智元/V2EX/Linux.do/Hacker News 等 | multi_source_snapshot |
| source_id | alerts | 官方安全与灾害预警 | guanlan | stable | CISA KEV/USGS | official_alert_snapshot |
| source_id | baidu | 百度热搜 | baidu | stable | baidu.com | fresh_trend_signal |
| source_id | weibo | 微博热搜 | weibo | best-effort | weibo.com | public_discussion_signal |
| source_id | bilibili-hot-search | B站热搜 | bilibili | stable | bilibili.com | video_attention_signal |
| source_id | bilibili | B站热门视频 | bilibili | best-effort | bilibili.com | video_attention_signal |
| source_id | ithome | IT之家资讯 | ithome | stable | ithome.com | tech_news_signal |
| source_id | sspai | 少数派文章 | sspai | stable | sspai.com | tech_reading_signal |
| source_id | hackernews | Hacker News | hackernews | stable | news.ycombinator.com | developer_discussion_signal |
| source_id | linuxdo | Linux.do 每日热门 | linuxdo | best-effort | linux.do | developer_discussion_signal |
| source_id | cisa-kev | CISA 已知在野利用漏洞目录 | cisa | stable | cisa.gov | official_security_alert |
| source_id | usgs-earthquakes | USGS 显著地震 | usgs | stable | earthquake.usgs.gov | official_disaster_alert |
| source_id | xinzhiyuan | 新智元 | xinzhiyuan | stable | aiera.com.cn | ai_news_signal |
| source_id | youtube-ai-rss | YouTube AI 频道 RSS | youtube | stable | youtube.com | video_source_signal |
| source_id | zeli-hn | Zeli HN 24h | zeli | best-effort | zeli.app | developer_discussion_signal |
| source_id | buzzing | Buzzing | buzzing | best-effort | buzzing.cc | global_tech_signal |
| source_id | zhihu | 知乎热榜 | zhihu | experimental | zhihu.com | qa_discussion_signal |
| source_id | v2ex | V2EX 热门 | v2ex | stable | v2ex.com | developer_discussion_signal |
| source_id | newsnow:toutiao | 今日头条 | newsnow/toutiao | optional | toutiao.com | fresh_trend_signal |
| source_id | newsnow:thepaper | 澎湃新闻 | newsnow/thepaper | optional | thepaper.cn | news_signal |
| source_id | newsnow:ifeng | 凤凰网 | newsnow/ifeng | optional | ifeng.com | news_signal |
| source_id | newsnow:tieba | 贴吧 | newsnow/tieba | optional | tieba.baidu.com | public_discussion_signal |
| source_id | newsnow:36kr-quick | 36氪快讯 | newsnow/36kr | optional | 36kr.com | industry_news_signal |
| source_id | newsnow:juejin | 掘金热榜 | newsnow/juejin | optional | juejin.cn | developer_discussion_signal |
| source_id | newsnow:cls-telegraph | 财联社电报 | newsnow/cls | optional | cls.cn | market_news_signal |
| source_id | newsnow:cls-hot | 财联社热门 | newsnow/cls | optional | cls.cn | market_news_signal |
| source_id | newsnow:wallstreetcn-quick | 华尔街见闻快讯 | newsnow/wallstreetcn | optional | wallstreetcn.com | market_news_signal |
| source_id | newsnow:wallstreetcn-hot | 华尔街见闻热门 | newsnow/wallstreetcn | optional | wallstreetcn.com | market_news_signal |
| source_id | newsnow:github-trending-today | GitHub Trending | newsnow/github | optional | github.com | developer_signal |
| source_id | newsnow:hackernews | Hacker News | newsnow/hackernews | optional | news.ycombinator.com | developer_discussion_signal |
| provider/catalog | newsnow:* | 已登记为上方 12 个 `newsnow:*` 入口 | NewsNow | optional | newsnow base URL | 可选外部热榜后端，适合补媒体/科技/财经快讯 |
| provider/catalog | vvhan:* | `36kr, baidu, douyin, ithome, netease-news, qq-news, thepaper, weibo, zhihu` | VVHAN | optional | hot-api.vhan.eu.org/v2 | 第三方热榜聚合，适合线索发现 |
| provider/catalog | uapis:* | 46 个平台：Baidu、Bilibili、Douyin、Weibo、Zhihu、V2EX、IT之家等 | UAPI | optional | uapis.cn/hotboard | 第三方热榜聚合，失败时走缓存边界 |
| provider/catalog | tophub:* | aliases: `weibo`, `zhihu`; catalog: news/tech/ent/community/finance/ai 等 15 类 | TopHub | optional/catalog | tophub.today | 第三方热榜节点和目录发现 |
| provider/catalog | hotboard:* | common aliases 覆盖微博、知乎、百度、头条、微信、抖音、小红书、B站、GitHub、雪球等 | Hotboard | opt-in/catalog | guanlan/data/hotboard_nodes.json | 本地目录免费；详情 API 显式配置 key 后才调用 |

### RSS / Feed / 垂类发现入口

| source_id | 名称 | 平台 | 类别 | 状态 | 源/URL | 证据角色 |
| --- | --- | --- | --- | --- | --- | --- |
| curated | 精品内容流 | rss | reading | stable | https://www.bestblogs.dev/{language}/feeds/rss | reading_discovery_signal |
| ai-vertical | AI 垂类精选动态源 | aihot | ai | best-effort | aihot.virxact.com | ai_vertical_discovery_signal |
| curated-sources | 精品源目录 | opml | source_catalog | stable | https://raw.githubusercontent.com/ginobefun/BestBlogs/main/BestBlogs_RSS_ALL.opml | source_catalog_entry |
| baidu-rss | 百度实时热点 RSS | baidu-rss | hotnews | best-effort | https://rss.aishort.top/?type=baidu | fresh_trend_signal |
| wechat-rss | 微信热门文章 RSS | wechat-rss | wechat | best-effort | https://rss.aishort.top/?type=wasi | wechat_article_signal |
| arxiv | arXiv 预印本 | arxiv | academic | stable | arxiv.org | preprint_record |
| watchlist | 订阅源观察 | local-watchlist | reading | stable | local/user supplied | watchlist_update_signal |

### Ebrun 电商垂类频道

| source_id | 频道 | 子频道 | 证据角色 | 公开 JSON path |
| --- | --- | --- | --- | --- |
| ebrun:recommend | 推荐 | 最新 | ecommerce_news_signal | _index/ClaudeCode/SkillJson/information_recommend.json |
| ebrun:retail | 未来零售 | 最新 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_50.json |
| ebrun:taobao-tmall | 未来零售 | 淘宝天猫 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_55.json |
| ebrun:douyin | 未来零售 | 抖音 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_56.json |
| ebrun:jd | 未来零售 | 京东 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_57.json |
| ebrun:wechat-video | 未来零售 | 视频号 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_60.json |
| ebrun:meituan | 未来零售 | 美团 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_61.json |
| ebrun:kuaishou | 未来零售 | 快手 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_59.json |
| ebrun:pinduoduo | 未来零售 | 拼多多 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_58.json |
| ebrun:xiaohongshu | 未来零售 | 小红书 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_62.json |
| ebrun:cross-border | 跨境电商 | 最新 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_51.json |
| ebrun:amazon | 跨境电商 | 亚马逊 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_68.json |
| ebrun:alibaba-international | 跨境电商 | 阿里国际 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_84.json |
| ebrun:tiktok-shop | 跨境电商 | TikTok | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_65.json |
| ebrun:temu | 跨境电商 | Temu | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_67.json |
| ebrun:shein | 跨境电商 | SHEIN | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_66.json |
| ebrun:industrial | 产业互联网 | 最新 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_52.json |
| ebrun:b2b | 产业互联网 | B2B | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_77.json |
| ebrun:industrial-tech | 产业互联网 | 产业科技 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_74.json |
| ebrun:data-elements | 产业互联网 | 数据要素 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_78.json |
| ebrun:industrial-overseas | 产业互联网 | 产业出海 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_75.json |
| ebrun:supply-chain | 产业互联网 | 数智供应链 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_79.json |
| ebrun:procurement | 产业互联网 | 数智化采购 | ecommerce_vertical_feed | _index/ClaudeCode/SkillJson/information_channel_73.json |
| ebrun:brand | 品牌 | 最新 | brand_industry_signal | _index/ClaudeCode/SkillJson/information_channel_87.json |
| ebrun:new-brand | 品牌 | 新竞争力品牌 | brand_industry_signal | _index/ClaudeCode/SkillJson/information_channel_89.json |
| ebrun:brand-globalization | 品牌 | 品牌全球化 | brand_globalization_signal | _index/ClaudeCode/SkillJson/information_channel_90.json |
| ebrun:ai | AI | 最新 | ai_ecommerce_signal | _index/ClaudeCode/SkillJson/information_channel_88.json |

### Hotboard 本地目录统计

| cid | 分类 | 节点数 |
| --- | --- | --- |
| 1 | 综合 | 767 |
| 2 | 科技 | 609 |
| 3 | 娱乐 | 1185 |
| 4 | 社区 | 422 |
| 5 | 购物 | 141 |
| 6 | 财经 | 396 |
| 7 | 开发 | 407 |
| 8 | 高校 | 440 |
| 9 | 机构 | 1275 |
| 10 | 博客 | 4608 |
| 12 | 电子报 | 553 |
| 13 | 设计 | 40 |

Hotboard meta: fetched_at `2026-05-04T11:07:08Z`, raw_count `10858`, unique_count `10843`, pages_fetched `109`。

## 四、Channel Catalog 能力目录

| channel | 区域 | 分类 | 风险 | 稳定性 | 认证 | 批量 | 后端/说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| open_websearch | china | search | low | best-effort | none | allowed | open-webSearch MCP |
| hotnews | china | hotnews | low | best-effort | none | limited | native public endpoints |
| web | global | web | low | stable | none | allowed |  |
| rss | global | rss | low | stable | none | allowed |  |
| github | global | dev | low | stable | optional | allowed |  |
| youtube | global | video | low | best-effort | optional | limited |  |
| wechat | china | web | medium | best-effort | none | limited | 后端就绪只代表具备搜索/阅读路径，不代表公众号端到端稳定可用。 |
| weibo | china | social | medium | best-effort | optional | blocked | 公开网页线索可用性波动较大，必要时需要授权或降级为普通搜索。 |
| xiaohongshu | china | social | high | opt-in | required | blocked | 强依赖外部后端与登录态，适合按需启用，不适合默认批量读取。 |
| rednote | global | social | high | opt-in | required | blocked | OpenGuanlan visible-page assist |
| douyin | china | video | high | opt-in | external | blocked |  |
| bilibili | china | video | medium | best-effort | optional | limited |  |
| twitter | global | social | high | opt-in | required | blocked |  |
| reddit | global | social | medium | opt-in | optional | limited |  |
| linkedin | global | career | high | opt-in | required | blocked |  |
| v2ex | china | community | low | stable | none | allowed |  |
| xueqiu | china | finance | medium | best-effort | optional | limited |  |
| xiaoyuzhou | china | audio | low | opt-in | api-key | limited |  |
| zsxq | china | private_community | high | opt-in | required | blocked | zsxq-cli |
| exa_search | global | search | low | opt-in | external | allowed |  |

## 五、搜索/阅读后端边界

| 层 | 入口 | 默认/说明 |
| --- | --- | --- |
| search backend | profile=china | `baidu -> bing -> duckduckgo`；Bing 中文漂移时改为 `baidu -> duckduckgo -> bing`。 |
| search backend | profile!=china | `duckduckgo -> bing`。 |
| search backend | wechat search intent | 追加 `wechat-sogou`。 |
| search backend | AnySearch | 外部搜索后端；强适配英文/技术/学术/安全/金融等 route 时按配置 fallback/preferred，可匿名额度或用户显式 key。 |
| channel search | open_websearch | open-webSearch MCP，多引擎中文搜索，取决于上游配置。 |
| channel search | exa_search | Exa via mcporter，opt-in 外部搜索。 |
| read backend | auto | 依次尝试 `wechat_article` 专项、`jina`、`direct`；需要时才走 `search_fallback`。 |
| browser assist | openguanlan | 只做用户授权的目标页可见内容补证，不读取 Cookie/Token/浏览器存储。 |

## 六、Profile 渠道顺序

| profile | 顺序 |
| --- | --- |
| china | `open_websearch, hotnews, wechat, weibo, xiaohongshu, rednote, douyin, bilibili, v2ex, xueqiu, zsxq, xiaoyuzhou, rss, web, github,`<br>`exa_search, youtube, twitter, reddit, linkedin` |
| english | `github, web, rss, exa_search, reddit, youtube, twitter, linkedin, open_websearch, hotnews, v2ex, wechat, weibo, bilibili, xiaohongshu,`<br>`rednote, douyin, xueqiu, zsxq, xiaoyuzhou` |
| hybrid | `github, open_websearch, exa_search, hotnews, web, rss, wechat, weibo, xiaohongshu, rednote, zsxq, douyin, bilibili, youtube, twitter,`<br>`reddit, v2ex, xiaoyuzhou, linkedin` |

## 源文件

- `guanlan/search_sources.py`: search scope 主矩阵。
- `guanlan/source_packs.py`: 研究源包和 hotboard node 推荐。
- `guanlan/source_registry.py`: Source Registry 2.0 适配层，包含 hotnews/feed source matrix。
- `guanlan/source_taxonomy.py`: authority/sample/freshness/risk 分类口径。
- `guanlan/hotnews.py`: 原生与外部热榜聚合入口。
- `guanlan/feeds.py`: RSS、OPML、AI 垂类、arXiv、watchlist。
- `guanlan/ebrun_channels.py`: 亿邦动力垂类频道。
- `guanlan/hotboard_catalog.py` 与 `guanlan/data/hotboard_nodes.json`: hotboard 本地目录和可选详情 API。
- `guanlan/channel_catalog.py`: 平台/渠道能力目录。
