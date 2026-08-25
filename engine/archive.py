"""归档兼容层 —— 全项目唯一直接触碰磁盘路径与字段结构的模块。

格式基准 = 存量实物 docs/archive.jsonl（93 条，2026-08-25 比对）：

    {"first_seen_at": ISO8601 带微秒,
     "finding": {"id"(数字序号-slug), "title"?, "claim"?, "evidence": [...],
                 "method", 以及原版深度分析的可选富化字段}}

兼容策略：新记录只产核心五字段 + confidence（0~1 浮点，跟随实物口径）；
富化字段（gap/verdict/tags...）属原版深度分析产物，不伪造。存量自身
title 缺失 26/93、claim 缺失 6/93 —— 字段可选性已被消费端容忍。

落盘两处（目录由 ARCHIVE_DIR 环境变量控制，默认 data/）：
1. {ARCHIVE_DIR}/findings/YYYY-MM-DD/<id>.json   单条 finding 文件（原版习惯）
2. {ARCHIVE_DIR}/archive.jsonl                    逐行追加，digest 未来直接消费
"""
import datetime
import json
import os
import re

from .config import REPO_ROOT


def _base_dir():
    return REPO_ROOT / os.environ.get("ARCHIVE_DIR", "data")


def archive_path():
    return _base_dir() / "archive.jsonl"


def record(finding_id, title, claim, evidence, method,
           confidence=None, first_seen_at=None):
    """构造归档记录。

    - confidence 跟随实物口径：0~1 浮点（调用方负责换算），可选字段
    - first_seen_at 默认带微秒（实物形如 2026-08-05T18:11:27.307305+00:00）
    """
    finding = {
        "id": finding_id,
        "title": title,
        "claim": claim,
        "evidence": evidence,
        "method": method,
    }
    if confidence is not None:
        finding["confidence"] = confidence
    return {
        "first_seen_at": first_seen_at or datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="microseconds"),
        "finding": finding,
    }


def next_seq(existing_ids):
    """延续存量的小序号前缀惯例（'321-guitar-...'），从最大序号 +1。

    存量实测（93 条）：75 条为小序号（28~602，有断档），18 条为后期
    改用的 Unix 时间戳级大数值。这里忽略 >=10^6 的类时间戳前缀，
    只延续小序号系列；若全无小序号则从 94 起步。
    """
    mx = 0
    for fid in existing_ids or ():
        m = re.match(r"^(\d+)-", str(fid or ""))
        if m:
            n = int(m.group(1))
            if n < 10 ** 6:
                mx = max(mx, n)
    return (mx or 93) + 1


def _strip_seq(fid):
    """'321-guitar-and-...' → 'guitar-and-...'；无前缀则原样返回。"""
    return re.sub(r"^\d+-", "", str(fid or ""))


def load_existing():
    """读取存量归档，产出去重所需的索引。坏行跳过，不抛异常。

    - ids 存「剥掉数字序号前缀」的裸 id（'321-guitar-...' → 'guitar-...'），
      保证写入侧加前缀后跨天仍可按 id 去重
    - raw_ids 保留原样，供 next_seq 延续序号
    """
    ids, raw_ids, evidences, titles = set(), set(), set(), []
    path = archive_path()
    if not path.exists():
        return {"ids": ids, "raw_ids": raw_ids,
                "evidences": evidences, "titles": titles}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            finding = json.loads(line)["finding"]
        except Exception:
            continue
        fid = str(finding.get("id") or "")
        raw_ids.add(fid)
        ids.add(_strip_seq(fid))
        titles.append(finding.get("title") or "")
        for u in finding.get("evidence") or []:
            evidences.add(u.split("?")[0])
    return {"ids": ids, "raw_ids": raw_ids,
            "evidences": evidences, "titles": titles}


def append(records):
    """追加写入 archive.jsonl 与当日 findings/*.json，返回写成功的 id 列表。"""
    base = _base_dir()
    base.mkdir(parents=True, exist_ok=True)
    day = datetime.date.today().isoformat()
    findings_dir = base / "findings" / day
    findings_dir.mkdir(parents=True, exist_ok=True)

    written = []
    with archive_path().open("a", encoding="utf-8") as f:
        for rec in records:
            fid = rec["finding"]["id"]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            safe = re.sub(r"[^a-zA-Z0-9\-_]", "-", fid)[:80]
            (findings_dir / (safe + ".json")).write_text(
                json.dumps(rec, ensure_ascii=False, indent=2),
                encoding="utf-8")
            written.append(fid)
    return written
