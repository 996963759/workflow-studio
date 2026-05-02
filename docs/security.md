# 安全与边界

## 已实现

- 本地账号注册 / 登录。
- Bearer Token 认证。
- 工作流、运行历史、知识库按用户隔离。
- 工具节点默认只允许请求 `localhost`、`127.0.0.1`、`::1`。
- 知识库上传限制为 Markdown / TXT。
- 单个知识文档限制为 1MB。
- 模型 API Key 通过环境变量配置，不返回给前端。
- 团队空间级模型 API Key 会在后端做本地保护存储，前端只返回掩码，不回显完整 Key。
- Docker Compose 部署默认使用 PostgreSQL 和 Redis，异步任务状态会落库，Worker 重启后可恢复未完成任务。
- 团队空间级审计日志会记录关键写操作和运行入队操作。

## 当前边界

- 密码使用 PBKDF2 哈希保存，但还没有密码重置流程。
- Token 当前没有过期时间和刷新机制。
- 当前已有团队空间和 owner/editor/viewer 角色权限，但还没有成员邀请链接和管理员后台。
- 当前没有 HTTPS 配置，需要部署层提供。
- 当前已有基础审计日志，但还没有操作回放、日志导出和长期归档策略。
- 当前知识库是本地哈希向量检索，不是真实 embedding/pgvector 检索。

## 生产化建议

- 生产环境使用 PostgreSQL，并设置高强度 `POSTGRES_PASSWORD` 和 `MODEL_CONFIG_SECRET`。
- 生产异步任务使用 Redis + 独立 Worker，并为 Redis/PostgreSQL 设置持久卷和备份。
- 增加 token 过期、刷新和撤销策略。
- 增加成员邀请和管理员后台。
- 部署时使用 HTTPS 和反向代理。
- 增加审计日志导出、保留周期和异常操作告警。
