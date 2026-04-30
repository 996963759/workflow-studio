# 简历描述

## 项目名称

AI 工作流编排平台

## 推荐一句话

基于 React Flow、FastAPI、SQLAlchemy 和 SQLite 实现的本地 AI 工作流编排平台，支持可视化节点编排、模型调用、知识库检索、工具调用、多用户隔离和后端持久化。

## 简历条目

```text
AI 工作流编排平台 | React, TypeScript, React Flow, FastAPI, SQLAlchemy, SQLite

- 基于 React Flow 实现可视化工作流编辑器，支持节点拖拽、连线、参数配置、变量插入、条件分支和运行日志。
- 使用 FastAPI + SQLAlchemy + SQLite 实现用户认证、工作流 CRUD、运行历史、归档恢复、同步状态和多用户数据隔离。
- 自研轻量工作流执行器，按连线拓扑顺序执行节点，支持变量上下文传递、失败策略、重试和分支跳过。
- 接入 DeepSeek / OpenAI API，支持真实大模型节点调用，并在未配置 Key 或调用失败时回退模拟输出。
- 实现用户级 Markdown/TXT 知识库检索和本机 HTTP 工具节点，补充 unittest、smoke test、Docker Compose、Alembic 迁移和一键启动脚本。
```

## 面试亮点

- 自研工作流执行器，不依赖 LangChain。
- 本地草稿与后端同步冲突保护。
- 多用户数据隔离和 Bearer Token 鉴权。
- SQLAlchemy ORM + Alembic 迁移。
- 工程化脚本、测试和容器化。

