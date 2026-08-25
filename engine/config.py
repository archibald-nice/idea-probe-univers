"""配置加载：仓库根 .env + config/*.json。纯标准库，不引入任何依赖。"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env(path=None):
    """把 .env 的 KEY=VALUE 注入 os.environ；已存在的环境变量优先，不被覆盖。"""
    p = Path(path) if path else REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def env(key, default=None):
    return os.environ.get(key, default)


def load_json_config(name):
    """读取仓库内 config/ 下的 JSON 配置文件。"""
    with (REPO_ROOT / "config" / name).open(encoding="utf-8") as f:
        return json.load(f)
