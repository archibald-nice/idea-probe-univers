"""Reddit 抓取：双通道（2026-08 现实校准：免 key JSON 端点已被 Reddit 封锁）。

实测结论（2026-08-25，经代理）：
- www/old.reddit.com/*.json → 403 / HTML 拦截页（浏览器 UA 也不放行）
- www.reddit.com/r/{sub}/top/.rss → 可用但限流极紧（单 IP 连续请求秒级 429）

因此提供两条通道：
- oauth（首选）：官方 API。需一次性在 reddit.com/prefs/apps 创建应用，
  把 client_id / secret 填进 .env；限额宽裕（60 次/分），字段完整含 score。
- rss（兜底）：免凭据 Atom feed；无 score 字段，跳过互动度过滤，
  且 sub 之间必须长间隔（默认 65s）避免 429。

REDDIT_TRANSPORT=auto|oauth|rss 控制，auto = 有凭据走 oauth，否则 rss。
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# 给 Reddit 的自标识 UA（官方 API 要求真实联系方式风格）；RSS 用浏览器 UA 才放行
SCRIPT_UA = "macos:idea-probe-univers:v0.3 (personal research; local script)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

_token_cache = {"value": None, "expires_at": 0.0}


class FetchError(RuntimeError):
    pass


def _http(url, headers=None, data=None, method="GET", timeout=25):
    req = urllib.request.Request(url, headers=headers or {},
                                 data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- OAuth 通道

def _get_access_token():
    """client_credentials 方式获取 app-only token，带内存缓存。"""
    now = time.time()
    if _token_cache["value"] and now < _token_cache["expires_at"]:
        return _token_cache["value"]
    cid = os.environ.get("REDDIT_CLIENT_ID", "")
    secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not (cid and secret):
        raise FetchError("oauth 通道需要 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET")
    basic = base64.b64encode(
        "{}:{}".format(cid, secret).encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode(
        {"grant_type": "client_credentials"}).encode("utf-8")
    raw = _http(
        "https://www.reddit.com/api/v1/access_token",
        headers={"Authorization": "Basic {}".format(basic),
                 "User-Agent": SCRIPT_UA,
                 "Content-Type": "application/x-www-form-urlencoded"},
        data=body, method="POST",
    )
    d = json.loads(raw)
    token = d.get("access_token")
    if not token:
        raise FetchError("获取 access_token 失败: {}".format(raw[:200]))
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + int(d.get("expires_in", 3600)) - 120
    return token


def fetch_sub_oauth(sub, timeframe="day", limit=40, retries=2):
    """官方 API 抓取单个 sub，返回原始 post data 列表（字段完整）。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            url = ("https://oauth.reddit.com/r/{}/top"
                   "?t={}&limit={}&raw_json=1").format(sub, timeframe, limit)
            raw = _http(url, headers={
                "Authorization": "Bearer {}".format(_get_access_token()),
                "User-Agent": SCRIPT_UA,
                "Accept": "application/json",
            })
            data = json.loads(raw)
            return [c["data"] for c in data.get("data", {}).get("children", [])]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503) and attempt < retries:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(10 * (attempt + 1))
                continue
    raise FetchError("oauth r/{} 抓取失败: {}".format(sub, last_err))


# ------------------------------------------------------------------ RSS 通道

def fetch_sub_rss(sub, timeframe="day", limit=40, retries=2):
    """Atom feed 兜底抓取。429 时指数退避（RSS 限流恢复以分钟计）。"""
    url = "https://www.reddit.com/r/{}/top/.rss?t={}&limit={}".format(
        sub, timeframe, limit)
    last_code = None
    for attempt in range(retries + 1):
        try:
            xml_text = _http(url, headers={
                "User-Agent": BROWSER_UA,
                "Accept": "application/atom+xml, application/xml",
            })
            root = ET.fromstring(xml_text)
            out = []
            for e in root.findall("a:entry", ATOM_NS):
                link_el = e.find("a:link", ATOM_NS)
                title_el = e.find("a:title", ATOM_NS)
                content_el = e.find("a:content", ATOM_NS)
                href = (link_el.get("href") or "") if link_el is not None else ""
                raw_html = (content_el.text or "") if content_el is not None else ""
                text = re.sub(r"<[^>]+>", " ", raw_html)
                text = re.sub(r"\s+", " ", text).strip()
                out.append({
                    "subreddit": sub,
                    "title": (title_el.text or "").strip() if title_el is not None else "",
                    "selftext": text[:1500],
                    "score": None,          # RSS 无互动数据
                    "num_comments": None,
                    "permalink": href.split("?")[0],
                })
            return out
        except urllib.error.HTTPError as e:
            last_code = e.code
            if e.code == 429 and attempt < retries:
                time.sleep(90 * (attempt + 1))  # 分钟级冷却
                continue
            raise
        except Exception:
            if attempt < retries:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    raise FetchError("rss r/{} 抓取失败: http={}".format(sub, last_code))


# ---------------------------------------------------------------- 过滤与汇总

def filter_posts(posts, min_score=10, min_comments=3):
    """按互动度过滤并裁剪为喂给 LLM 的精简结构。

    RSS 来源的帖子 score/num_comments 为 None，视为通过（排序本身已由 top 编码质量）。
    """
    out = []
    for p in posts:
        if p.get("stickied") or p.get("pinned") or p.get("over_18"):
            continue
        score = p.get("score")
        comments = p.get("num_comments")
        if score is not None and score < min_score:
            continue
        if comments is not None and comments < min_comments:
            continue
        permalink = p.get("permalink") or ""
        if permalink.startswith("/"):
            permalink = "https://www.reddit.com" + permalink
        out.append({
            "sub": p.get("subreddit"),
            "title": (p.get("title") or "").strip(),
            "selftext": (p.get("selftext") or "").strip()[:1500],
            "score": score,
            "num_comments": comments,
            "permalink": permalink.split("?")[0],
        })
    return out


def resolve_transport():
    which = os.environ.get("REDDIT_TRANSPORT", "auto").strip().lower()
    if which in ("oauth", "rss"):
        return which
    has_creds = bool(os.environ.get("REDDIT_CLIENT_ID")
                     and os.environ.get("REDDIT_CLIENT_SECRET"))
    return "oauth" if has_creds else "rss"


def fetch_clusters(clusters, min_score=10, min_comments=3,
                   listing=None, timeframe="day", limit=40,
                   per_sub_sleep=None, **_ignored):
    """按簇遍历启用 sub：抓取 + 过滤 + 按 permalink 跨 sub 去重。

    - oauth 通道：sub 间隔默认 3s（限额充裕）
    - rss   通道：sub 间隔默认 75s（实测冷却约 75s 恢复，连续请求立即 429）
    - 单 sub 失败静默跳过；全部失败返回空列表（上层走断网静默分支）
    """
    transport = resolve_transport()
    if per_sub_sleep is None:
        per_sub_sleep = 3 if transport == "oauth" else 75
    fetch_one = fetch_sub_oauth if transport == "oauth" else fetch_sub_rss

    merged = {}
    for cluster in clusters:
        if not cluster.get("enabled", True):
            continue
        for i, sub in enumerate(cluster["subs"]):
            if i or merged:
                time.sleep(per_sub_sleep)
            try:
                posts = filter_posts(
                    fetch_one(sub, timeframe=timeframe, limit=limit),
                    min_score=min_score, min_comments=min_comments)
            except Exception:
                continue
            for p in posts:
                merged.setdefault(p["permalink"],
                                  dict(p, cluster=cluster["name"]))
    return list(merged.values())
