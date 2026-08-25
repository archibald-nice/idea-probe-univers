#!/bin/bash
# idea-engine 调度包装：launchd 环境不加载 shell 配置，这里补齐运行环境。
# 成功静默（日志照写）；失败由 python 侧告警 + 非零退出码，本脚本原样透传。
set -u
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR" || exit 1

mkdir -p logs

export IDEA_ENGINE_CRON=1
# .env 里的 HTTP_PROXY/HTTPS_PROXY 会被 engine/config.load_env() 注入，
# urllib 自动读取，无需在此 source zshrc。

python3 idea_engine.py >> logs/run.log 2>&1
exit $?
