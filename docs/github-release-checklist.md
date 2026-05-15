# GitHub 发布检查清单

## 当前结论

当前仓库可以发布到 GitHub。已确认 Git 跟踪文件中没有真实 `.env`、本地数据库、`node_modules`、`dist` 或后端虚拟环境。

## 发布前必查

- `git status --short` 应为空。
- 不提交 `.env`。
- 不提交 `server/data/*.db`。
- 不提交真实 API Key、Token、Cookie、私钥或个人账号密码。
- `.env.example` 只保留空值、示例值或本地开发默认值。
- README 顶部应说明项目定位、技术栈、亮点和截图。
- 截图中不要出现真实 API Key、真实 Token 或个人隐私数据。

## 已排除的常见敏感文件

`.gitignore` 已排除：

- `.env`
- `node_modules`
- `dist`
- `server/.venv`
- `server/data/*.db`
- `test-results`
- `playwright-report`
- Python `__pycache__`

## 推荐 GitHub 仓库描述

```text
AI workflow orchestration studio with React Flow, FastAPI, SQLAlchemy, Kafka, RAG, team workspaces, versioning, audit logs, and model provider configuration.
```

## 推荐 Topics

```text
ai-workflow
fastapi
react
typescript
react-flow
sqlalchemy
kafka
rag
deepseek
dashscope
```

## 简历表述建议

不要写“精通 Python”。建议写：

```text
主语言 Java，熟悉 Spring Boot 后端开发；了解 Python/FastAPI，能基于 FastAPI 构建 AI 应用后端服务。
熟悉 AI 应用工程化：LLM API 集成、RAG、工作流编排、异步任务队列、模型配置管理。
```

