"""告警：MVP = 日志 + 进程退出码（已拍板）；ENGINE_ALERT_WEBHOOK 接口预留。

静默哲学（PRD 目标 4 / §8 验收）：
- 无新料（含全网源不可达/断网）→ 正常退出 0，不告警
- 有料但处理失败（key 错、LLM 异常、归档写失败等）→ ALERT 日志 + 退出码非 0，
  若配置了 ENGINE_ALERT_WEBHOOK 则同时推送（飞书自定义机器人兼容格式）
"""
import json
import logging
import os
import sys
import urllib.request

from .config import REPO_ROOT

_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("idea_engine")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    # 手动跑也留档：直接追加到 logs/manual.log（cron 路径由包装脚本重定向 run.log）
    if not os.environ.get("IDEA_ENGINE_CRON"):
        try:
            logs_dir = REPO_ROOT / "logs"
            logs_dir.mkdir(exist_ok=True)
            fh = logging.FileHandler(logs_dir / "manual.log",
                                     encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass
    _logger = logger
    return logger


def alert_failure(message):
    """记录 ALERT 并推送预留 webhook。返回 webhook 是否推送成功。"""
    get_logger().error("ALERT %s", message)
    hook = os.environ.get("ENGINE_ALERT_WEBHOOK")
    if not hook:
        return False
    try:
        body = {"msg_type": "text",
                "content": {"text": "[idea-engine] {}".format(message)}}
        req = urllib.request.Request(
            hook,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:  # webhook 失败不再级联，日志兜底
        get_logger().error("ALERT webhoook 推送失败: %s", e)
        return False
