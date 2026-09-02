FROM python:3.11-slim

WORKDIR /app

# 引擎零第三方依赖：纯 Python 标准库，无需 pip install
COPY idea_engine.py .
COPY engine/ engine/
COPY config/ config/

ENV PYTHONUNBUFFERED=1 \
    RUN_AT_HOUR=21 \
    RUN_AT_UTC_OFFSET=8

# 归档与日志走运行时挂载，不打进镜像
VOLUME ["/app/data", "/app/logs"]

COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
