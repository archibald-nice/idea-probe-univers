# idea-probe-univers

本机灵感引擎（Idea Engine）——Reddit 热帖 → LLM 提炼「claim + evidence」→ 归档兼容 `archive.jsonl`。

> **当前状态**：MVP 代码就位（2026-08-25 开工）。离线自测通过；待办：填 key、接入存量归档格式比对、安装调度。

## 文档

- [docs/本机灵感引擎_PRD_v0.1.md](docs/本机灵感引擎_PRD_v0.1.md) — PRD v0.2 定稿 + §10 现实校准附录

## 快速开始

```bash
# 1. 配置（必填 DEEPSEEK_API_KEY；建议填 REDDIT_CLIENT_ID/SECRET 与代理）
cp .env.example .env

# 2. 体检：key 连通性 / 代理可达性 / Reddit 通道，一条命令出报告
python3 idea_engine.py --check

# 3. 离线自检：不联网不需要 key，走通 校验/去重/归档 全链路
python3 idea_engine.py --selftest

# 4. 试抓取：真实抓 Reddit 并打印将发给 LLM 的 prompt，不调 API 不写盘
python3 idea_engine.py --dry-run

# 5. 正式跑
python3 idea_engine.py
```

**失败分类**（决定告警还是静默）：抓取错误分为 `auth`（凭据错/被封）、`other`（代码异常）→ 触发告警；`network/rate/server`（断网、限流、对方故障）→ 静默次日重试。全部 sub 失败且含致命类时抛 `SourceAuthError` 走告警路径，配置错误不会被「无新料」掩盖。

## 测试

```bash
python3 tests/test_engine.py   # 零依赖回归套件：解析容错/校验去重/归档格式/过滤/错误分类
```

## 架构

```
config/subs.json          预选 sub 清单（簇分组，手动增删）
        │
engine/reddit_fetch.py    双通道抓取：oauth（官方 API，首选）/ rss（兜底，75s 间隔）
        │                 过滤：stickied/NSFW 剔除、min_score/min_comments 门槛
idea_engine.py            主流程编排
        │
engine/distill.py         中文 claim prompt（宁缺毋滥）+ 反幻觉校验 + 三重去重
        │
engine/providers.py       LLM 抽象：DeepSeek 先行，LLM_PROVIDER=kimi 一键切换
        │
engine/archive.py         ★唯一接触磁盘格式的模块★
        ├─ {ARCHIVE_DIR}/archive.jsonl            逐行追加，digest 未来直接消费
        └─ {ARCHIVE_DIR}/findings/YYYY-MM-DD/*.json
```

**格式契约**（PRD §5，全项目仅 `engine/archive.py` 一处实现）：

```json
{"first_seen_at": "...", "finding": {"id", "title", "claim", "evidence": [...], "method"}}
```

存量 `archive.jsonl` 到位后：把它所在目录设为 `.env` 的 `ARCHIVE_DIR`，再按实物对齐该模块字段即可无缝并入。

## 调度（每日 21:00）

`scripts/com.archie.idea-engine.plist` 为 launchd 配置（macOS 无 crontab）：

```bash
cp scripts/com.archie.idea-engine.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.archie.idea-engine.plist
```

## 静默约定（PRD 目标 4）

| 情形 | 行为 |
| --- | --- |
| 无新料 / 全网源不可达 / 断网 | 静默退出 0，零告警 |
| 本轮无合格灵感（宁缺毋滥） | 静默退出 0 |
| 有料但处理失败（key 错、LLM 异常等） | `logs/run.log` 记 ALERT + 退出码 1；配置了 `ENGINE_ALERT_WEBHOOK` 则推送 |

## 已知现实约束（2026-08-25 实测）

- Reddit 免 key JSON 端点已被封锁（403 / HTML 拦截页），故采用双通道：官方 OAuth API（免费创建 script 应用即得凭据）首选；RSS Atom feed 兜底，单 IP 约 75s 冷却一轮。
- RSS 无 score 数据，互动度过滤自动跳过（top 排序本身已编码质量），质量把关后移到 LLM 闸门。
