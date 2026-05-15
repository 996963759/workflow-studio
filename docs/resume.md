# 简历描述

## 项目名称

AI 工作流编排平台

## 推荐一句话

基于 React Flow、FastAPI、SQLAlchemy 和 SQLite/PostgreSQL 实现的 AI 工作流编排平台，支持可视化节点编排、模型调用、知识库检索、工具调用、多用户团队空间、权限隔离、异步队列和版本治理。

## 简历条目

```text
AI 工作流编排平台 | React, TypeScript, React Flow, FastAPI, SQLAlchemy, SQLite/PostgreSQL, Kafka, RAG

- 基于 React Flow 实现可视化工作流编辑器，支持节点拖拽、连线、参数配置、变量插入、条件分支和运行日志。
- 使用 FastAPI + SQLAlchemy 实现用户认证、团队空间、角色权限、工作流 CRUD、运行历史、归档恢复、同步状态和多用户数据隔离。
- 自研轻量工作流执行器，按连线拓扑顺序执行节点，支持变量上下文传递、失败策略、重试和分支跳过。
- 接入 DeepSeek、阿里云百炼和 PaiSmart RAG，支持团队空间级模型配置、知识库检索、TTS、图片生成和调用失败回退。
- 实现工作流版本快照、发布态、版本对比、审计日志、异步运行队列、失败重试和运行成本估算。
- 补充 unittest、Playwright E2E、Docker Compose、Alembic 迁移和本地启动脚本。
```

## 面试亮点

- 自研工作流执行器，不依赖 LangChain。
- 本地草稿与后端同步冲突保护。
- 团队空间、多用户数据隔离和 Bearer Token 鉴权。
- SQLAlchemy ORM + Alembic 迁移。
- Kafka/Redis/数据库多种异步队列后端。
- 工作流发布、版本对比、审计日志和运行成本估算。
- 工程化脚本、测试和容器化。

## Java 背景说明

简历或面试中建议这样讲：

```text
我的主语言是 Java。这个项目使用 Python/FastAPI，是因为 AI 应用生态里 Python 接模型、RAG 和外部 AI 服务更方便。项目重点展示的是后端通用工程能力和 AI 应用落地能力，包括认证权限、多租户隔离、数据库设计、异步队列、版本治理、审计日志和测试。这些设计可以迁移到 Spring Boot 体系。
```
