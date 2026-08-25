"""提炼环节：prompt 组装、响应解析、反幻觉校验与去重。

prompt 核心（PRD §4）：只留未被满足的需求，宁缺毋滥，必须带 evidence。
产出语言（已拍板）：title/claim 统一中文，evidence 保留原帖链接。
"""
import datetime
import json
import re
from difflib import SequenceMatcher

SYSTEM_PROMPT = """你是灵感提炼引擎。输入是若干 Reddit 帖子（JSON 数组）。你的任务：
1. 只识别「未被满足的真实需求 / 反直觉的洞察」，用中文输出为断言（claim），水准参照："吉他手有免费谱子20年了，歌手却要付费——为什么没人解决？"这种一针见血的程度；
2. 宁缺毋滥：最多输出 5 条，没有合格的就输出空数组，绝不为凑数硬造；
3. 每条必须给出 evidence：从输入帖子的 permalink 字段里【原样复制】1~3 条，禁止编造输入中不存在的任何链接；
4. title 不超过 24 个汉字；claim 是一句完整中文断言，点出「现象 + 缺口/为什么值得注意」，不要写成帖子摘要；
5. confidence 为 1~10 整数自评，只保留你打分 ≥7 的条目；
6. id 用英文小写 slug（短横线连接，体现主题即可）。
严格只输出如下 JSON，不要输出任何其他文字：
{"findings":[{"id":"free-guitar-tabs-vs-paid-vocal-sheets","title":"...","claim":"...","evidence":["https://www.reddit.com/..."],"confidence":8}]}"""

_USER_TMPL = """今天是 {today}。以下是来自 Reddit 的 {n} 条高互动帖子（JSON 数组）：

{posts_json}

请按系统规则提炼。记住：只留未被满足的需求，宁缺毋滥，evidence 必须原样取自上面的 permalink。"""


def build_user_prompt(posts):
    slim = [
        {k: p[k] for k in ("sub", "cluster", "title", "selftext",
                           "score", "num_comments", "permalink")}
        for p in posts
    ]
    return _USER_TMPL.format(
        today=datetime.date.today().isoformat(),
        n=len(slim),
        posts_json=json.dumps(slim, ensure_ascii=False, indent=1),
    )


def _extract_first_json_object(text):
    """从任意文本中扫描出第一个完整平衡的 {...} 块（容忍字符串内的花括号）。"""
    start = text.find("{")
    if start < 0:
        raise ValueError("输出中找不到 JSON 对象")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("JSON 对象不完整（括号不平衡）")


def parse_response(text):
    """解析 LLM 输出。

    容忍三种常见污染：```json 代码围栏、前后多余说明文字、围栏外尾随内容。
    提取第一个完整 JSON 对象后必须含 findings 数组，否则抛错交给上层告警。
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(_extract_first_json_object(text))
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("LLM 输出缺少 findings 数组: {}".format(text[:200]))
    return items


def validate(items, source_posts, existing, max_items=5,
             min_confidence=7, max_title_len=40, max_claim_len=200,
             similar_threshold=0.8):
    """三道闸门：反幻觉 evidence 校验 → 与存量去重 → 置信度截断。

    - evidence 只认输入帖子里真实存在的 permalink（防编造）
    - id 已存在 / evidence 撞存量 / 标题相似度过高 → 视为重复丢弃
    - 按 confidence 降序取前 max_items 条（目标 3~5 条，宁缺毋滥）
    返回字段化列表，附 _cluster 供 method 文案使用。
    """
    url2post = {p["permalink"]: p for p in source_posts}
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("id") or "").strip()
        title = str(it.get("title") or "").strip()
        claim = str(it.get("claim") or "").strip()
        try:
            conf = int(it.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        ev = [u for u in (it.get("evidence") or [])
              if isinstance(u, str) and u in url2post]
        if not (fid and title and claim and ev):
            continue
        if conf < min_confidence:
            continue
        if len(title) > max_title_len or len(claim) > max_claim_len:
            continue
        # —— 去重（id 按剥离序号前缀后的裸 id 比对，跨天前缀不变性）——
        if re.sub(r"^\d+-", "", fid) in existing["ids"]:
            continue
        norm_ev = [u.split("?")[0] for u in ev]
        if any(e in existing["evidences"] for e in norm_ev):
            continue
        seen_titles = [o["title"].lower() for o in out]
        seen_titles += [t.lower() for t in existing["titles"]]
        if any(SequenceMatcher(None, title.lower(), t).ratio() >= similar_threshold
               for t in seen_titles):
            continue
        out.append({
            "id": fid,
            "title": title,
            "claim": claim,
            "evidence": ev,
            "confidence": conf,
            "_cluster": url2post[ev[0]]["cluster"],
        })
    out.sort(key=lambda x: -x["confidence"])
    return out[:max_items]
