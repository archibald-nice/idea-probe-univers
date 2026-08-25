#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎回归测试（零依赖，无 pytest）：python3 tests/test_engine.py"""
import json
import os
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

from engine import archive, distill, reddit_fetch  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   {}".format(name))
    else:
        FAIL += 1
        print("  FAIL {}".format(name))


# ------------------------------------------------------------- parse_response
print("[distill.parse_response]")
base = '{"findings":[{"id":"a","title":"t","claim":"c","evidence":["u"],"confidence":8}]}'
check("纯 JSON", len(distill.parse_response(base)) == 1)
check("```json 围栏", len(distill.parse_response("```json\n" + base + "\n```")) == 1)
check("围栏+尾随废话",
      len(distill.parse_response("```json\n" + base + "\n```\n以上是提炼结果。")) == 1)
check("前后散文包裹",
      len(distill.parse_response("好的，结果如下：\n" + base + "\n请查收。")) == 1)
try:
    distill.parse_response('{"no_findings": []}')
    check("缺 findings 抛错", False)
except ValueError:
    check("缺 findings 抛错", True)
try:
    distill.parse_response('完全不是JSON')
    check("非 JSON 抛错", False)
except Exception:
    check("非 JSON 抛错", True)

# ------------------------------------------------------------------ validate
print("[distill.validate]")
posts = [
    {"sub": "SubA", "cluster": "pain", "title": "P1", "selftext": "",
     "score": 10, "num_comments": 5,
     "permalink": "https://www.reddit.com/r/SubA/comments/x/1/"},
    {"sub": "SubB", "cluster": "request", "title": "P2", "selftext": "",
     "score": 20, "num_comments": 9,
     "permalink": "https://www.reddit.com/r/SubB/comments/y/2/"},
    {"sub": "SubC", "cluster": "ideas", "title": "P3", "selftext": "",
     "score": 15, "num_comments": 7,
     "permalink": "https://www.reddit.com/r/SubC/comments/z/3/"},
]
U1, U2, U3 = (p["permalink"] for p in posts)
existing = {"ids": {"dup-id"}, "evidences": {U3},
            "titles": ["买菜清单应用没人做货架动线"]}
items = [
    # 有效条目
    {"id": "good-one", "title": "声乐谱仍锁在付费墙后", "claim": "断言一",
     "evidence": [U1], "confidence": 9},
    # 编造 evidence → 丢弃
    {"id": "hallucin", "title": "编造链接条目", "claim": "断言二",
     "evidence": ["https://www.reddit.com/r/Fake/comments/w/9/"],
     "confidence": 10},
    # 低置信度 → 丢弃
    {"id": "low-conf", "title": "低置信度条目", "claim": "断言三",
     "evidence": [U1], "confidence": 6},
    # id 撞存量 → 丢弃
    {"id": "dup-id", "title": "撞存量ID条目", "claim": "断言四",
     "evidence": [U1], "confidence": 9},
    # evidence 撞存量（U3 已归档过）→ 丢弃
    {"id": "dup-ev", "title": "撞存量证据条目", "claim": "断言五",
     "evidence": [U3], "confidence": 9},
    # 标题与存量相似度 ≥0.8 → 丢弃
    {"id": "dup-title", "title": "买菜清单应用没人做货架动线呀", "claim": "断言六",
     "evidence": [U1], "confidence": 9},
    # 超长标题 → 丢弃
    {"id": "too-long", "title": "这" * 41, "claim": "断言七",
     "evidence": [U1], "confidence": 9},
    # 第二有效条目（置信度更高，排序应在前）
    {"id": "good-two", "title": "夜班静音交易市场", "claim": "断言八",
     "evidence": [U2], "confidence": 10},
]
picked = distill.validate(items, posts, existing)
got_ids = [p["id"] for p in picked]
check("仅 2 条存活且按置信度降序",
      got_ids == ["good-two", "good-one"])
check("_cluster 取自 evidence 帖",
      picked[0]["_cluster"] == "request" and picked[1]["_cluster"] == "pain")

# max_items 截断：构造 5 条互不相似的有效条目，截取前 3
many = [{"id": "m{}".format(i),
         "title": t, "claim": "断言", "evidence": [U1],
         "confidence": 7 + i}
        for i, t in enumerate(["猫咪行为学", "股票异动学", "睡眠周期学",
                               "咖啡因代谢", "键盘布局学"])]
got = distill.validate(many, posts, existing, max_items=3)
check("max_items 截断且保序",
      [p["id"] for p in got] == ["m4", "m3", "m2"])

# -------------------------------------------------------------------- record
print("[archive]")
rec = archive.record("fid-1", "标题", "断言",
                     ["https://e"], "方法", first_seen_at="T0")
check("PRD §5 字段结构",
      set(rec.keys()) == {"first_seen_at", "finding"} and
      set(rec["finding"].keys()) ==
      {"id", "title", "claim", "evidence", "method"})
check("first_seen_at 可注入",
      rec["first_seen_at"] == "T0")

tmpdir = tempfile.mkdtemp(prefix="idea-test-")
os.environ["ARCHIVE_DIR"] = tmpdir  # pathlib 绝对路径拼接会整体替换
written = archive.append([rec])
check("append 返回 id", written == ["fid-1"])
line = open(os.path.join(tmpdir, "archive.jsonl"),
            encoding="utf-8").read().strip()
check("jsonl 单行合法", json.loads(line)["finding"]["id"] == "fid-1")
day_dir = os.listdir(os.path.join(tmpdir, "findings"))[0]
check("findings/YYYY-MM-DD/<id>.json 落盘",
      os.path.exists(os.path.join(tmpdir, "findings", day_dir, "fid-1.json")))
ex = archive.load_existing()
check("load_existing 回读索引",
      ex["ids"] == {"fid-1"} and ex["titles"] == ["标题"])
with open(os.path.join(tmpdir, "archive.jsonl"), "a",
          encoding="utf-8") as f:
    f.write("这不是合法行\n")
check("坏行跳过不抛异常", archive.load_existing()["ids"] == {"fid-1"})

# -------------------------------------------------------------- filter_posts
print("[reddit_fetch.filter_posts]")
raw_ok = {"subreddit": "S", "title": " t ", "selftext": " body ",
          "score": 50, "num_comments": 12,
          "permalink": "/r/S/comments/a/b/", "stickied": False}
out = reddit_fetch.filter_posts([raw_ok])
check("正常帖通过并规范化",
      out and out[0]["permalink"].startswith("https://www.reddit.com/")
      and out[0]["title"] == "t")
cases = [
    ("stickied 剔除", dict(raw_ok, stickied=True)),
    ("NSFW 剔除", dict(raw_ok, over_18=True)),
    ("低分剔除", dict(raw_ok, score=5)),
    ("低评论剔除", dict(raw_ok, num_comments=2)),
]
for name, bad in cases:
    check(name, reddit_fetch.filter_posts([bad]) == [])
rss_post = {"subreddit": "S", "title": "rss", "selftext": "",
            "score": None, "num_comments": None,
            "permalink": "https://www.reddit.com/r/S/comments/c/d/"}
check("RSS 无互动数据放行", len(reddit_fetch.filter_posts([rss_post])) == 1)

# ----------------------------------------------- 错误分类与 SourceAuthError
print("[错误分类]")
ce = reddit_fetch.classify_error
check("401→auth", ce(urllib.error.HTTPError("u", 401, "m", {}, None)) == "auth")
check("429→rate", ce(urllib.error.HTTPError("u", 429, "m", {}, None)) == "rate")
check("500→server", ce(urllib.error.HTTPError("u", 500, "m", {}, None)) == "server")
check("URLError→network", ce(urllib.error.URLError("x")) == "network")
check("ValueError→other", ce(ValueError("x")) == "other")

clusters = [{"name": "t", "enabled": True, "subs": ["A", "B"]}]
orig_rss = reddit_fetch.fetch_sub_rss
reddit_fetch.resolve_transport = lambda: "rss"


def all_fail(exc):
    def fake(sub, **kw):
        raise exc
    return fake


reddit_fetch.fetch_sub_rss = all_fail(
    urllib.error.HTTPError("u", 401, "Unauthorized", {}, None))
try:
    reddit_fetch.fetch_clusters(clusters, per_sub_sleep=0)
    check("全灭含 auth → SourceAuthError", False)
except reddit_fetch.SourceAuthError:
    check("全灭含 auth → SourceAuthError", True)
reddit_fetch.fetch_sub_rss = all_fail(urllib.error.URLError("down"))
check("全灭仅 network → 静默空列表",
      reddit_fetch.fetch_clusters(clusters, per_sub_sleep=0) == [])
reddit_fetch.fetch_sub_rss = orig_rss

# ------------------------------------------------------------------- 结果
print("\npassed {}, failed {}".format(PASS, FAIL))
sys.exit(1 if FAIL else 0)
