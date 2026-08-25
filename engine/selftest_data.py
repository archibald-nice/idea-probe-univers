"""--selftest 内置样例数据：不联网、不需要 key，走通 校验→去重→写盘 全链路。

写入目录固定为 data-selftest/（通过 ARCHIVE_DIR 覆盖），绝不污染真实归档。
"""

FAKE_POSTS = [
    {
        "sub": "DoesAnybodyElse",
        "cluster": "pain",
        "title": "DAE find it absurd that guitar tabs have been free for 20 years but vocal sheet music is still paywalled?",
        "selftext": "Guitar players have ultimate-guitar with millions of free tabs. Singers somehow still pay $5 per song for official sheet music. Why has nobody solved this?",
        "score": 356,
        "num_comments": 128,
        "permalink": "https://www.reddit.com/r/DoesAnybodyElse/comments/abc123/dae_guitar_tabs_free_vocal_paid/",
    },
    {
        "sub": "SomebodyMakeThis",
        "cluster": "request",
        "title": "[Request] A grocery app that builds the list from my saved recipes AND my local store's aisle layout",
        "selftext": "Every list app ignores where things actually are in MY store. I want a route through the aisles, not an alphabetical list.",
        "score": 89,
        "num_comments": 41,
        "permalink": "https://www.reddit.com/r/SomebodyMakeThis/comments/def456/grocery_app_aisle_routing/",
    },
    {
        "sub": "Lightbulb",
        "cluster": "ideas",
        "title": "A 'quiet hours' marketplace where night-shift workers bid for daytime silence in shared apartments",
        "selftext": "Roommates could trade quiet hours like a currency.",
        "score": 12,
        "num_comments": 4,
        "permalink": "https://www.reddit.com/r/Lightbulb/comments/ghi789/quiet_hours_marketplace/",
    },
]

SELFTEST_RESPONSE = """```json
{"findings": [
  {"id": "free-tabs-vs-paid-vocal-sheets",
   "title": "吉他谱免费二十年，声乐谱仍在付费墙后",
   "claim": "乐器学习中只有吉他等弹拨类形成了众包曲谱生态，声乐谱因版权集中始终无人做免费替代——这是一个被默认了二十年的付费缺口。",
   "evidence": ["https://www.reddit.com/r/DoesAnybodyElse/comments/abc123/dae_guitar_tabs_free_vocal_paid/"],
   "confidence": 9},
  {"id": "grocery-list-aisle-routing",
   "title": "买菜清单应用没人做货架动线",
   "claim": "所有买菜清单应用都止步于清单本身，没人把用户常做菜谱与具体门店的货架布局结合生成采购动线，这是高频痛点的空白位。",
   "evidence": ["https://www.reddit.com/r/SomebodyMakeThis/comments/def456/grocery_app_aisle_routing/"],
   "confidence": 7},
  {"id": "hallucinated-link-finding",
   "title": "这条 evidence 是编造的应被丢弃",
   "claim": "校验器必须丢弃 evidence 不在输入帖子里的条目。",
   "evidence": ["https://www.reddit.com/r/Fake/comments/xxx/fake/"],
   "confidence": 10},
  {"id": "low-confidence-finding",
   "title": "低置信度条目应被丢弃",
   "claim": "置信度低于 7 的条目应被丢弃。",
   "evidence": ["https://www.reddit.com/r/Lightbulb/comments/ghi789/quiet_hours_marketplace/"],
   "confidence": 3}
]}
```

上面还有一段模型多余的话，解析器应能容忍。
"""

# selftest 预期：4 条输入 → 仅前 2 条存活（编造 evidence 和低置信度各弃 1 条）
