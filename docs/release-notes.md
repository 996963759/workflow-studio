# 发布说明

## 当前版本能力

- 可视化工作流画布
- 多节点类型：输入、大模型、知识检索、HTTP 工具、文字转语音、图片生成、条件分支、最终回答
- 本地草稿保存和 JSON 导入导出
- 后端工作流持久化
- 工作流版本快照、手动保存版本和版本恢复 API
- 团队空间级审计日志
- 前端版本与审计面板，支持查看版本、保存版本、恢复版本和查看审计记录
- 运行历史
- DeepSeek / OpenAI 调用
- 阿里云百炼 / DashScope TTS 和图片生成调用，未配置 Key 时回退模拟输出
- 用户级知识库
- 本地账号和多用户隔离
- 团队空间和 owner/editor/viewer 角色权限
- 右侧管理中心分区入口
- 系统概览接口和管理中心系统页
- 系统页展示安全设置摘要，不暴露密钥内容
- 异步运行队列，支持本地线程、数据库轮询、Redis + Worker 和 Kafka + Worker 部署
- 本地哈希向量知识库和 PaiSmart 外部 RAG 适配
- SQLAlchemy ORM
- Alembic 数据库迁移
- Docker Compose，包含 PostgreSQL、Redis、Kafka、API 和 Worker
- unittest + smoke test + Playwright E2E

## 下一步建议

- 拆分 `src/App.tsx` 为多个前端组件。
- 增加成员邀请链接和管理员后台。
- 将知识库升级为真实 embedding + pgvector/Milvus。
- 增加工作流发布态、版本对比和运行成本统计。
- 增加外网工具白名单、请求审计和插件执行器。
