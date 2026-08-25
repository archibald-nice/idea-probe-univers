"""归档兼容层 —— 全项目唯一直接触碰磁盘路径与字段结构的模块。

格式基准 = PRD §5（待用户提供存量 archive.jsonl 后，仅需在本模块对齐真实格式）：

    {"first_seen_at": ISO8601,
     "finding": {"id", "title", "claim", "evidence": [...], "method"}}

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


def record(finding_id, title, claim, evidence, method, first_seen_at=None):
    """构造一条与 PRD §5 完全一致的归档记录。"""
    return {
        "first_seen_at": first_seen_at or datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
        "finding": {
            "id": finding_id,
            "title": title,
            "claim": claim,
            "evidence": evidence,
            "method": method,
        },
    }


def load_existing():
    """读取存量归档，产出去重所需的索引。坏行跳过，不抛异常。"""
    ids, evidences, titles = set(), set(), []
    path = archive_path()
    if not path.exists():
        return {"ids": ids, "evidences": evidences, "titles": titles}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            finding = json.loads(line)["finding"]
        except Exception:
            continue
        ids.add(finding.get("id"))
        titles.append(finding.get("title") or "")
        for u in finding.get("evidence") or []:
            evidences.add(u.split("?")[0])
    return {"ids": ids, "evidences": evidences, "titles": titles}


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
