#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机灵感引擎主入口（PRD v0.2 §4 架构的 idea_engine.py）。

用法:
  python3 idea_engine.py              # 正式跑：抓取 → DeepSeek 提炼 → 归档
  python3 idea_engine.py --dry-run    # 只抓取并打印将发给 LLM 的 prompt（不调 LLM 不写盘）
  python3 idea_engine.py --selftest   # 离线样例走通 校验/去重/归档 全链路（无需 key，写入 data-selftest/）

静默约定:
  - 无新料（含全网源不可达/断网）→ 静默退出 0        （验收：断网 24h 零告警）
  - 本轮无合格灵感（宁缺毋滥）    → 静默退出 0
  - 有料但处理失败                → ALERT 日志 + 退出码 1
"""
import os
import sys

from engine import alert, archive, config, distill, reddit_fetch
from engine.providers import get_provider


def run(argv):
    config.load_env()
    log = alert.get_logger()
    engine_cfg = config.load_json_config("engine.json")

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
