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
- SQLAlchemy ORM
- Alembic 数据库迁移
- Docker Compose
- unittest + smoke test

## 下一步建议

- 拆分 `src/App.tsx` 为多个前端组件。
- 增加前端端到端测试。
- 将 SQLite 切换为 PostgreSQL 部署方案。
- 增加异步运行队列。
- 将知识库升级为向量检索。
- 增加团队空间和角色权限。

