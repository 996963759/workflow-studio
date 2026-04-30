# 演示流程

## 目标

用 5 到 8 分钟展示项目的完整能力：账号隔离、工作流编排、后端运行、知识库、工具节点和工程化。

## 准备

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

打开：

```text
http://127.0.0.1:5173
```

## 演示步骤

1. 注册一个本地账号并登录。
2. 从“工作流模板”创建“客服知识库问答”。
3. 展示画布节点：用户输入、知识检索、大模型、最终回答。
4. 上传一份 Markdown 知识文档。
5. 点击“同步到后端”，说明 SQLite 持久化和同步状态。
6. 点击“后端运行”，展示逐节点运行日志。
7. 打开“运行历史”，展示保存、查看、删除能力。
8. 创建第二个账号，说明看不到第一个账号的工作流和知识库。
9. 运行 `scripts/test-all.ps1`，说明 lint、build、unit test、smoke test。
10. 打开 `docs/architecture.md`，讲解执行器和数据隔离设计。

## 面试讲解重点

- 为什么按连线拓扑排序执行工作流。
- 本地草稿和后端持久化如何处理冲突。
- 如何用 Bearer Token 做用户隔离。
- 为什么引入 SQLAlchemy 和 Alembic。
- 知识库当前使用本地 Markdown/TXT 原文 + SQLite 哈希向量索引，检索时混合关键词和相似度。
