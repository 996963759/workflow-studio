# 成熟化部署说明

这份说明用于把本地演示项目推进到更接近真实项目的运行方式。新手开发时仍然可以继续用 SQLite；需要做简历展示、团队协作或长期保存数据时，建议使用 PostgreSQL。

## 推荐技术组合

- 后端：FastAPI + SQLAlchemy + Alembic
- 数据库：PostgreSQL
- 异步队列：Kafka，轻量部署也可以用 Redis
- 前端：React + Vite
- 部署：Docker Compose

## 数据库选择

当前项目支持两种数据库：

- SQLite：默认本地开发模式，数据库文件在 `server/data/workflow_studio.db`
- PostgreSQL：推荐的成熟化模式，Docker Compose 已内置 `db` 服务

生产化或简历演示建议使用 PostgreSQL，原因是它更适合多用户、权限、审计日志、运行历史、JSON 数据和后续 `pgvector` 向量检索。

## 环境变量

复制环境变量样例：

```powershell
Copy-Item .env.example .env
```

成熟化模式重点检查这些变量：

```text
DATABASE_URL=postgresql+psycopg://workflow_studio:workflow_studio_dev_password@db:5432/workflow_studio
POSTGRES_DB=workflow_studio
POSTGRES_USER=workflow_studio
POSTGRES_PASSWORD=请改成高强度密码
MODEL_CONFIG_SECRET=请改成随机长字符串
SESSION_TTL_HOURS=168
RUN_JOB_QUEUE_BACKEND=kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_RUN_JOB_TOPIC=workflow-studio-run-jobs
KAFKA_CONSUMER_GROUP=workflow-studio-workers
```

`MODEL_CONFIG_SECRET` 用来保护团队空间级模型 API Key。只要已经保存过模型 Key，就不要随意修改它，否则旧配置可能无法解密。

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

如果看到 `database` 是 `sqlite`，说明当前后端还在使用本地 SQLite。

## 本地开发模式

本地新手开发仍然推荐：

```powershell
.\scripts\start-dev.ps1
```

这种方式默认使用 SQLite 和线程队列，启动简单，适合改前端、调节点、演示基础功能。

## 成熟项目还应继续补齐

- Token 过期、刷新和撤销
- 管理员后台和邀请过期策略
- pgvector 或外部向量数据库
- 队列失败重试、死信队列和任务取消
- 生产日志归档、监控和告警
- HTTPS、反向代理和备份策略
