#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机灵感引擎主入口（PRD v0.2 §4 架构的 idea_engine.py）。

用法:
  python3 idea_engine.py              # 正式跑：抓取 → DeepSeek 提炼 → 归档
  python3 idea_engine.py --dry-run    # 只抓取并打印将发给 LLM 的 prompt（不调 LLM 不写盘）
  python3 idea_engine.py --selftest   # 离线样例走通 校验/去重/归档 全链路（无需 key，写入 data-selftest/）
  python3 idea_engine.py --check      # 配置体检：key 连通性 / 代理可达性 / Reddit 通道

静默约定:
  - 无新料（含全网源不可达/断网）→ 静默退出 0        （验收：断网 24h 零告警）
  - 本轮无合格灵感（宁缺毋滥）    → 静默退出 0
  - 有料但处理失败                → ALERT 日志 + 退出码 1
"""
import os
import sys

from engine import alert, archive, config, distill, reddit_fetch
from engine.providers import get_provider


def doctor():
    """配置体检：逐项检查并打印报告。有失败项返回 1，否则 0。"""
    import os
    import socket
    from urllib.parse import urlparse

    from engine.providers import LLMError, get_provider

    ok = True

    # 1. DeepSeek key 连通性（真实调用一次，几 token 成本可忽略）
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("[待办] DEEPSEEK_API_KEY 未配置 —— 编辑 .env 填入")
        ok = False
    else:
        try:
            get_provider().chat("You are a ping.", "Reply OK",
                                json_mode=False, timeout=30)
            print("[通过] DeepSeek API 连通")
        except Exception as e:  # noqa: BLE001 体检要兜住一切并给出结论
            print("[失败] DeepSeek 调用不通: {}: {}".format(
                type(e).__name__, str(e)[:150]))
            ok = False

    # 2. 代理可达性
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy:
        print("[警告] 未配置代理 —— 实测 Reddit 直连不可达，建议 .env 填 HTTPS_PROXY")
    else:
        u = urlparse(proxy)
        try:
            s = socket.create_connection((u.hostname, u.port or 80), timeout=3)
            s.close()
            print("[通过] 代理 {} 可达".format(proxy))
        except OSError as e:
            print("[失败] 代理 {} 不可达: {}".format(proxy, e))
            ok = False

    # 3. Reddit 当前通道连通性
    which = reddit_fetch.resolve_transport()
    fetch_one = (reddit_fetch.fetch_sub_oauth if which == "oauth"
                 else reddit_fetch.fetch_sub_rss)
    try:
        posts = fetch_one("CrazyIdeas", limit=5)
        print("[通过] Reddit {} 通道连通（CrazyIdeas 抓到 {}/5 帖）".format(
            which, len(posts)))
        if which == "rss":
            print("[提示] 当前走 rss 兜底：无互动度数据且每日爬取约 7 分钟；"
                  "在 .env 配置 REDDIT_CLIENT_ID/SECRET 可切官方 API")
    except Exception as e:  # noqa: BLE001
        kind = reddit_fetch.classify_error(e)
        fatal = kind in ("auth", "other")
        print("[{}] Reddit {} 通道失败({}): {}".format(
            "失败" if fatal else "警告", which, kind, str(e)[:120]))
        ok = ok and not fatal
    return 0 if ok else 1


def run(argv):
    config.load_env()
    log = alert.get_logger()
    engine_cfg = config.load_json_config("engine.json")

    # -1. 配置体检分支
    if "--check" in argv:
        return doctor()

    # 0. 离线自测：不联网、不需要 key，写入 data-selftest/ 隔离目录
    if "--selftest" in argv:
        from engine import selftest_data
        os.environ["ARCHIVE_DIR"] = "data-selftest"
        posts = selftest_data.FAKE_POSTS
        raw = selftest_data.SELFTEST_RESPONSE
        log.info("selftest: %d fake posts, canned LLM response", len(posts))
    else:
        # 1. 抓取 + 过滤
        subs_cfg = config.load_json_config("subs.json")
        posts = reddit_fetch.fetch_clusters(subs_cfg["clusters"],
                                            **engine_cfg.get("filter", {}))
        log.info("harvest: %d posts after filter", len(posts))
        if not posts:
            print("无新料，静默退出")
            return 0

        # 2. 组 prompt
        user_prompt = distill.build_user_prompt(posts)
        if "--dry-run" in argv:
            print(user_prompt)
            return 0

        # 3. LLM 提炼
        provider = get_provider()
        log.info("distilling via %s (%s)...", provider.name, provider.model)
        raw = provider.chat(distill.SYSTEM_PROMPT, user_prompt)

    items = distill.parse_response(raw)

    # 4. 校验 + 去重
    existing = archive.load_existing()
    picked = distill.validate(items, posts, existing,
                              max_items=engine_cfg.get("max_daily", 5))
    if not picked:
        print("本轮无合格灵感（宁缺毋滥），静默退出")
        return 0

    # 5. 归档（格式与 archive.jsonl 完全兼容）
    records = [
        archive.record(
            finding_id=p["id"], title=p["title"], claim=p["claim"],
            evidence=p["evidence"],
            method="本机引擎：{}簇扫描 + DeepSeek提炼".format(p["_cluster"]),
        )
        for p in picked
    ]
    ids = archive.append(records)
    for p in picked:
        log.info("finding: [%s] %s", p["id"], p["title"])
    print("归档 {} 条: {}".format(len(ids), ", ".join(ids)))
    return 0


def main(argv):
    try:
        return run(argv)
    except Exception as e:  # 有料但处理失败 → 告警 + 非零退出
        alert.alert_failure("运行失败: {}: {}".format(type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
