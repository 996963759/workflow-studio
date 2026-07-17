# 成熟化部署说明

这份说明用于把本地演示项目推进到更接近真实项目的运行方式。项目开发、测试和 Docker Compose 部署统一使用 PostgreSQL，避免本地 SQLite 与正式数据库行为不一致。

## 推荐技术组合

- 后端：FastAPI + SQLAlchemy + Alembic
- 数据库：PostgreSQL
- 读取缓存：Redis（短 TTL，可降级）
- 异步队列：Kafka + 独立 Worker
- 前端：React + Vite
- 部署：Docker Compose

## 数据库选择

当前项目统一使用 PostgreSQL。原因是它更适合多用户、权限、审计日志、运行历史、JSON 数据和后续 `pgvector` 向量检索，也能让开发、测试和部署环境保持一致。

## 环境变量

复制环境变量样例：

```powershell
Copy-Item .env.example .env
```

成熟化模式重点检查这些变量：

```text
DATABASE_URL=postgresql+psycopg://workflow_studio:workflow_studio_dev_password@db:5432/workflow_studio
RUN_EXECUTION_MODE=production
REDIS_URL=redis://redis:6379/0
ADMIN_OVERVIEW_CACHE_TTL_SECONDS=20
POSTGRES_DB=workflow_studio
POSTGRES_USER=workflow_studio
POSTGRES_PASSWORD=请改成高强度密码
MODEL_CONFIG_SECRET=请改成随机长字符串
SESSION_TTL_HOURS=168
WORKSPACE_INVITATION_TTL_HOURS=168
RUN_JOB_QUEUE_BACKEND=kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_RUN_JOB_TOPIC=workflow-studio-run-jobs
KAFKA_CONSUMER_GROUP=workflow-studio-workers
```

`MODEL_CONFIG_SECRET` 用来保护团队空间级模型 API Key。只要已经保存过模型 Key，就不要随意修改它，否则旧配置可能无法解密。

`RUN_EXECUTION_MODE` 支持三种模式：

- `demo`：允许模拟输出，但节点和整次运行会明确标记为“降级”。
- `development`：允许开发阶段回退，同样标记为“降级”，不会显示为成功。
- `production`：禁止模拟或失败回退；真实模型、TTS、图片或工具服务不可用时节点直接失败。

正式环境必须显式设置为 `production`。Docker Compose 为方便本地演示默认使用 `development`。

## Docker Compose 启动

在项目根目录执行：

```powershell
docker compose up --build
```

启动后访问：

```text
http://127.0.0.1:8000
```

查看服务状态：

```powershell
docker compose ps
```

查看 API 和 Worker 日志：

```powershell
docker compose logs -f api worker
```

API 容器启动时会自动执行：

```powershell
python -m alembic upgrade head
```

这会把 PostgreSQL 数据库结构迁移到最新版本。

## 健康检查

访问：

```text
http://127.0.0.1:8000/api/health
```

成熟化模式下预期类似：

```json
{
  "status": "ok",
  "database": "postgresql",
  "queue_backend": "kafka"
}
```

如果 `database` 不是 `postgresql`，说明当前后端连接到了错误的数据库。

## 本地开发模式

本地开发推荐：

```powershell
.\scripts\start-dev.ps1
```

这种方式要求本机已经有 PostgreSQL 和 Kafka；如果希望一次性启动完整依赖，推荐使用 `docker compose up --build`。自动化测试会使用 PostgreSQL 测试库，并把队列临时覆盖为 `thread`。

## 成熟项目还应继续补齐

- Token 过期、刷新和撤销
- 管理员后台
- pgvector 或外部向量数据库
- 队列失败重试、死信队列和任务取消
- 生产日志归档、监控和告警
- HTTPS、反向代理和备份策略
