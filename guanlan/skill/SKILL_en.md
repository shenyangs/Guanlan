---
name: guanlan
description: >
  Give your AI agent eyes to see the entire internet.
  Search and read 17 platforms: Twitter/X, Reddit, YouTube, GitHub, Bilibili,
  XiaoHongShu, Douyin, Weibo, WeChat Articles, Xiaoyuzhou Podcast, LinkedIn,
  V2EX, Xueqiu, RSS, Exa web search, and any web page.
  Zero config for 8 channels. Use when the user asks to search, read, or interact
  on any supported platform, shares a URL, or asks to search the web.
  Triggers: "search twitter", "search xiaohongshu", "watch this video",
  "search the web", "look this up", "research", "youtube transcript",
  "search reddit", "read this link", "bilibili", "douyin video",
  "wechat article", "wechat official account", "weibo", "V2EX",
  "xiaoyuzhou", "podcast", "xueqiu", "stock quote",
  "install guanlan".
metadata:
  openclaw:
    homepage: local-repo
---

# 观澜 / Guanlan — Usage Guide

Upstream tools for 17 platforms. Call them directly.

Run `guanlan doctor` to check which channels are available.

## ⚠️ Workspace Rules

**Never create files in the agent workspace.** Use `/tmp/` for temporary output and `~/.guanlan/` for persistent data.

## Web — Any URL

```bash
curl -s "https://r.jina.ai/URL"
```

## Web Search (Exa)

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 50)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

## Twitter/X (bird)

```bash
bird search "query" -n 10                  # search
bird read URL_OR_ID                        # read tweet (supports /status/ and /article/ URLs)
bird user-tweets @username -n 20           # user timeline
bird thread URL_OR_ID                      # full thread
```

## YouTube (yt-dlp)

```bash
yt-dlp --dump-json "URL"                     # video metadata
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"
                                             # download subtitles, then read the .vtt file
yt-dlp --dump-json "ytsearch5:query"         # search
```

## Bilibili (yt-dlp)

```bash
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> Server IPs may get 412. Use `--cookies-from-browser chrome` or configure a proxy.

## Reddit

```bash
curl -s "https://www.reddit.com/r/SUBREDDIT/hot.json?limit=50" -H "User-Agent: guanlan/1.0"
curl -s "https://www.reddit.com/search.json?q=QUERY&limit=50" -H "User-Agent: guanlan/1.0"
```

> Server IPs may get 403. Search via Exa instead, or configure a proxy.

## GitHub (gh CLI)

```bash
gh search repos "query" --sort stars --limit 50
gh repo view owner/repo
gh search code "query" --language python
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo
```

## XiaoHongShu (mcporter)

```bash
mcporter call 'xiaohongshu.search_feeds(keyword: "query")'
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy")'
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy", load_all_comments: true)'
mcporter call 'xiaohongshu.publish_content(title: "Title", content: "Body text", images: ["/path/img.jpg"], tags: ["tag"])'
```

> Requires login. Use Cookie-Editor to import cookies.

> **Tip: Clean bloated output.** The XHS API returns large JSON with many unused fields.
> Pipe through the formatter to save context:
> ```bash
> mcporter call 'xiaohongshu.search_feeds(keyword: "query")' | guanlan format xhs
> ```
> This keeps only: title, content, author, engagement counts, image URLs, and tags.

## Douyin (mcporter)

```bash
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'
```

> No login needed.

## WeChat Articles

**Search** (`miku_ai`):
```bash
# miku_ai is installed inside the guanlan Python environment.
# Use the same interpreter that runs guanlan (handles pipx / venv installs):
GUANLAN_PYTHON=$(python3 -c "import guanlan, sys; print(sys.executable)" 2>/dev/null || echo python3)
$GUANLAN_PYTHON -c "
import asyncio
from miku_ai import get_wexin_article
async def s():
    for a in await get_wexin_article('query', 5):
        print(f'{a[\"title\"]} | {a[\"url\"]}')
asyncio.run(s())
"
```

**Read** (Camoufox — bypasses WeChat anti-bot):
```bash
cd ~/.guanlan/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> WeChat articles cannot be read with Jina Reader or curl. Use Camoufox.

## Weibo (mcporter)

```bash
# Trending topics
mcporter call 'weibo.get_trendings(limit: 20)'

# Search users
mcporter call 'weibo.search_users(keyword: "Lei Jun", limit: 10)'

# Get a user profile
mcporter call 'weibo.get_profile(uid: "1195230310")'

# Get a user's feed
mcporter call 'weibo.get_feeds(uid: "1195230310", limit: 20)'

# Get a user's hot posts
mcporter call 'weibo.get_hot_feeds(uid: "1195230310", limit: 10)'

# Search post content
mcporter call 'weibo.search_content(keyword: "artificial intelligence", limit: 20)'

# Search topics
mcporter call 'weibo.search_topics(keyword: "AI", limit: 10)'

# Get post comments
mcporter call 'weibo.get_comments(mid: "5099916367123456", limit: 50)'

# Get fans
mcporter call 'weibo.get_fans(uid: "1195230310", limit: 20)'

# Get followings
mcporter call 'weibo.get_followers(uid: "1195230310", limit: 20)'
```

> Zero config. No login needed. Uses the mobile API with auto-generated visitor cookies.

## Xiaoyuzhou Podcast (groq-whisper + ffmpeg)

```bash
# Transcribe a single podcast episode (outputs text to /tmp/)
~/.guanlan/tools/xiaoyuzhou/transcribe.sh "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

> Requires `ffmpeg` and a Groq API key (free).
> Configure the key with `guanlan configure groq-key YOUR_KEY`.
> On first run, install the tools with `guanlan install --env=auto`.
> Run `guanlan doctor` to check status.
> Output Markdown files are saved to `/tmp/` by default.

## LinkedIn (mcporter)

```bash
mcporter call 'linkedin.get_person_profile(linkedin_url: "https://linkedin.com/in/username")'
mcporter call 'linkedin.search_people(keyword: "AI engineer", limit: 10)'
```

Fallback: `curl -s "https://r.jina.ai/https://linkedin.com/in/username"`

## V2EX (public API)

```bash
# Hot topics
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: guanlan/1.0"

# Topics in a node (node_name examples: python, tech, jobs, qna)
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: guanlan/1.0"

# Topic details (extract topic_id from URLs like https://www.v2ex.com/t/1234567)
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: guanlan/1.0"

# Topic replies
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: guanlan/1.0"

# User profile
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: guanlan/1.0"
```

Python example (`V2EXChannel`):

```python
from guanlan.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# Get hot topics (default 50 items)
# Returned fields: id, title, url, replies, node_name, node_title, content(first 200 chars), created
topics = ch.get_hot_topics(limit=50)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} replies) {t['url']}")
    print(f"  id={t['id']} created={t['created']}")

# Get latest topics for a specific node
# Returned fields: id, title, url, replies, node_name, node_title, content(first 200 chars), created
node_topics = ch.get_node_topics("python", limit=5)
for t in node_topics:
    print(t["id"], t["title"], t["url"])

# Get one topic plus replies
# Returned fields: id, title, url, content, replies_count, node_name, node_title,
#                  author, created, replies (list of {author, content, created})
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])
for r in topic["replies"]:
    print(f"  {r['author']}: {r['content'][:80]}")

# Get user info
# Returned fields: id, username, url, website, twitter, psn, github, btc, location, bio, avatar, created
user = ch.get_user("Livid")
print(user["username"], user["bio"], user["github"])

# Search (not supported by the public V2EX API; returns guidance instead)
result = ch.search("asyncio")
print(result[0]["error"])  # Use built-in site search or the Exa channel instead
```

> No auth required. Results are public JSON. V2EX node names are listed at https://www.v2ex.com/planes

## Xueqiu (stock quotes + hot posts)

```python
from guanlan.channels.xueqiu import XueqiuChannel

ch = XueqiuChannel()
quote = ch.get_stock_quote("SH600519")
print(quote["name"], quote["current"], quote["percent"])
```

> Login cookie required. Configure via `guanlan configure --from-browser chrome`.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

## Troubleshooting

- **Channel not working?** Run `guanlan doctor` — it shows status and fix instructions.
- **Twitter fetch failed?** Ensure `undici` is installed: `npm install -g undici`. Configure a proxy if needed: `guanlan configure proxy URL`.

## Setting Up a Channel ("help me configure XXX")

If a channel needs setup (cookies, Docker, etc.), fetch the install guide:
docs/install.md

The user only provides cookies. Everything else is your job.
