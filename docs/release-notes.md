# 发布说明

## 当前版本能力

- 可视化工作流画布
- 多节点类型：输入、大模型、知识检索、HTTP 工具、条件分支、最终回答
- 本地草稿保存和 JSON 导入导出
- 后端工作流持久化
- 运行历史
- DeepSeek / OpenAI 调用
- 用户级知识库
- 本地账号和多用户隔离
- 团队空间和 owner/editor/viewer 角色权限
- 异步运行队列，支持本地线程、数据库轮询和 Redis + Worker 部署
- 本地哈希向量知识库和 PaiSmart 外部 RAG 适配
- SQLAlchemy ORM
- Alembic 数据库迁移
- Docker Compose，包含 PostgreSQL、Redis、API 和 Worker
- unittest + smoke test + Playwright E2E

## 下一步建议

- 拆分 `src/App.tsx` 为多个前端组件。
- 增加成员邀请链接、角色变更审计和管理员后台。
- 将知识库升级为真实 embedding + pgvector/Milvus。
- 增加工作流版本发布、回滚和运行成本统计。
- 增加外网工具白名单、请求审计和插件执行器。
