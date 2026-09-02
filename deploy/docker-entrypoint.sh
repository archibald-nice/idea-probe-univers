#!/bin/sh
# 容器内调度器：每日 RUN_AT_HOUR 点（按 RUN_AT_UTC_OFFSET 表达的业务时区）
# 运行一次引擎，循环常驻。
#
# - 失败不退出循环：告警与日志由引擎侧负责（成功静默 / 失败 ALERT+非零码）
# - 带参数启动则直接执行该命令后退出（一次性模式），便于：
#     docker compose run --rm idea-engine python3 idea_engine.py --check
set -u

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

HOUR="${RUN_AT_HOUR:-21}"
OFFSET="${RUN_AT_UTC_OFFSET:-8}"
mkdir -p logs data

echo "[entrypoint] scheduler on: daily ${HOUR}:00 (UTC${OFFSET:++$OFFSET})"

while :; do
    WAIT=$(python3 - "$HOUR" "$OFFSET" <<'PY'
import datetime
import sys

hour, off = int(sys.argv[1]), int(sys.argv[2])
tz = datetime.timezone(datetime.timedelta(hours=off))
now = datetime.datetime.now(tz)
run_at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
if run_at <= now:
    run_at += datetime.timedelta(days=1)
print(int((run_at - now).total_seconds()) + 5)
PY
)
    echo "[entrypoint] next run in ${WAIT}s"
    sleep "$WAIT"
    echo "[entrypoint] === engine run start $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="
    if python3 idea_engine.py >> logs/run.log 2>&1; then
        echo "[entrypoint] run ok (silent-success convention)"
    else
        echo "[entrypoint] run FAILED (exit=$?) — see logs/run.log"
    fi
done
