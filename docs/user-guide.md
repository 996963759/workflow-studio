# 用户教程

这份文档用于完整体验织流 AI。README 只保留项目概览和快速启动，具体操作步骤放在这里。

## 本地启动

推荐直接运行：

```powershell
.\scripts\start-dev.ps1
```

如果 PowerShell 提示禁止运行脚本，使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

脚本会检查依赖并启动后端和前端。启动后访问：

```text
http://127.0.0.1:5173
```

手动启动前端：

```powershell
npm.cmd install
npm.cmd run dev
```

手动启动后端：

```powershell
python -m venv server/.venv
server\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

后端健康检查：

```text
http://127.0.0.1:8000/api/health
```

## 第一次体验

1. 注册一个本地账号，后续使用账号密码登录。
2. 登录后会自动进入默认团队空间。
3. 从左侧“工作流模板”创建“客服知识库问答”。
4. 点击“同步到后端”，把当前工作流保存到后端数据库。
5. 点击“同步运行”，在右侧查看逐节点运行日志。
6. 打开“运行历史”，查看历史结果、搜索、筛选和删除记录。
7. 打开“版本与审计”，查看版本快照、发布状态、版本对比和审计日志。
8. 打开“系统概览”，查看数据库、队列、模型、知识库、成员和成本估算状态。

## 工作流编辑

- 点击左侧节点库可以新增节点。
- 点击左侧“工作流模板”可以一键创建可运行示例工作流。
- 在左侧“我的工作流”里可以新建、切换、搜索、排序、复制、归档、恢复和删除工作流。
- “仅本地”表示还没保存到后端，“已同步”表示本地和后端一致，“未同步改动”表示已同步过但本地又改过。
- 默认会隐藏已归档工作流，勾选“显示归档”后可以查看并恢复。
- 顶部工作流名称可以直接编辑。
- 在画布中拖拽节点并连接节点端点可以调整流程。
- 点击节点后，在右侧节点配置中修改名称、用途、提示词和输出变量。
- 节点配置字段下方会显示错误或提醒，点击“恢复默认配置”可以重置当前节点配置。
- 在支持变量的配置项下方点击变量按钮，可以快速插入 `{{变量名}}`。
- 条件分支可以选择变量、判断方式和判断值；条件节点右侧有“真”和“假”两个出口。

## 运行和同步

- 编辑内容会写入浏览器 `localStorage`，下次打开会自动恢复。
- 点击“保存”会手动确认保存全部本地工作流。
- 点击“同步到后端”会把当前工作流保存到后端数据库。
- 点击“同步全部”会批量同步未归档且未同步的工作流。
- 点击“从后端加载”会把后端工作流导入或更新到前端列表。
- 点击“同步运行”会调用 FastAPI 执行当前已同步工作流，并保存运行历史。
- 点击“异步入队”会把当前工作流提交到后端运行队列，前端会轮询任务状态，完成后自动加载运行结果。
- 当前工作流有“未同步改动”时，后端运行会先拦截，避免运行旧版本。
- 如果后端版本比本地上次同步时间更新，前端会停止覆盖并提示先从后端加载。

## 团队空间和权限

- 登录后会自动进入默认团队空间。
- 工作流、运行历史、异步任务、知识文档和模型配置都按团队空间隔离。
- 角色权限：owner 可管理成员，editor 可编辑工作流和知识库，viewer 可查看和运行。
- 团队空间 owner 可查看成员、调整角色和移除成员。
- 团队空间 owner 可创建、复制、撤销邀请码，用户可用邀请码加入团队。

## 模型配置

可以在右侧“模型状态”里保存当前团队空间的模型配置。保存后，该空间内所有工作流运行都会优先使用这份配置。

支持的模型能力：

- DeepSeek / OpenAI 兼容大模型节点
- 阿里云百炼 / DashScope 文字转语音节点
- 阿里云百炼 / DashScope 图片生成节点
- PaiSmart 外部 RAG 地址和 Token

如果团队空间没有保存模型配置，后端会继续读取环境变量；如果也没有环境变量，会回退为模拟输出。

可选环境变量示例：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:DASHSCOPE_API_KEY="你的阿里云百炼 API Key"
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

## 知识库

右侧“知识库”面板可以查看、上传和删除 Markdown / TXT 文档。后端运行“知识检索”节点时，默认读取当前团队空间的本地文档。

本地知识库目录：

```text
server/data/knowledge/
```

上传后会写入 SQLite 本地向量索引，检索时混合关键词命中和哈希向量相似度，不需要额外安装向量数据库。项目内置示例文档：

```text
server/data/knowledge/customer-support.md
```

可以用“退款多久到账”“API 调用失败”这类输入体验检索效果。

## 工具节点

工具节点可以填写请求地址、方法、请求头 JSON 和请求体 JSON。后端运行时会真实调用本机 HTTP 接口。

默认只允许请求：

```text
localhost
127.0.0.1
::1
```

这样可以避免演示时误请求外网。

## 导入导出

- 点击“导出”会下载当前工作流 JSON 文件。
- 点击“导入”可以载入之前导出的 JSON 文件，并作为新的工作流加入列表。
- 点击“重置”会恢复为内置示例工作流。

## Docker 运行

```powershell
docker compose up --build
```

容器会启动 PostgreSQL、Redis、Kafka、FastAPI API 和独立 Worker。API 会自动执行 Alembic 迁移，异步任务会先落库再把 `job_id` 发布到 Kafka；如果 Worker 或服务重启，未完成任务会自动重新入队。

查看服务状态：

```powershell
docker compose ps
docker compose logs -f api worker
```

## 数据库迁移

项目已接入 SQLAlchemy ORM 和 Alembic。

升级数据库结构：

```powershell
server\.venv\Scripts\python.exe -m alembic upgrade head
```

生成迁移草稿：

```powershell
server\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "描述变更"
```

## 测试和体检

统一回归测试：

```powershell
.\scripts\test-all.ps1
```

如果 PowerShell 提示禁止运行脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-all.ps1
```

前端 E2E 测试：

```powershell
npx.cmd playwright install chromium
npm.cmd run e2e
```

项目体检：

```powershell
npm.cmd run doctor
```

如果要额外检查 Docker Compose 配置：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\doctor.ps1
```

## 常见问题

| 页面现象 | 常见原因 | 处理方式 |
| --- | --- | --- |
| 模型状态显示 DeepSeek 未配置 | 没有保存团队空间 Key，也没有设置 `DEEPSEEK_API_KEY` | 在右侧“模型状态”保存 DeepSeek Key，或在后端启动前设置环境变量 |
| 点击保存或测试配置后看起来没反应 | 请求正在处理或后端返回了错误 | 查看按钮下方的状态提示；如果提示后端离线，先启动后端或刷新页面 |
| 来源显示模拟输出，且没有错误原因 | 没有配置团队空间 Key，也没有配置 DeepSeek/OpenAI 环境变量 | 在右侧“模型状态”保存 DeepSeek Key，或配置环境变量后重启后端 |
| 来源显示模拟输出，并出现错误原因 | 已配置 Key，但真实调用失败 | 查看“错误原因”，重点检查 Key、余额、模型名和网络 |
| 错误原因包含 401/Authentication | Key 错误或无效 | 重新生成 API Key 并重启后端 |
| 错误原因包含 timeout | 节点超时时间太短或网络慢 | 调大大模型节点里的“超时秒数” |

## 本地存储

- `workflow-studio.workflows`：保存所有本地工作流。
- `workflow-studio.active-workflow-id`：保存当前选中的工作流。
- `workflow-studio.auth-session`：保存当前浏览器登录 token。
- `workflow-studio.active-workspace-id`：保存当前选中的团队空间。
- 旧版 `workflow-studio.current-workflow` 会在首次打开时自动迁移。
- 同步到后端后，本地工作流会记录后端 ID 和最近同步时间。

## 当前边界

这是本地单机版 / 私有化版工作流平台雏形。当前前端运行逻辑已支持变量传递和模拟执行；后端已提供 FastAPI、SQLite/PostgreSQL 工作流 CRUD、工作流结构校验、同步/异步运行、运行历史接口、本地向量知识库检索、DeepSeek / OpenAI 大模型节点最小真实调用、阿里云 TTS / 图片生成多模态节点、本机 HTTP 工具调用、本地账号隔离、团队空间和角色权限。Docker Compose 已提供 PostgreSQL、Redis 和独立 Worker 的生产化雏形；真实 embedding/pgvector 和外网工具白名单管理仍未实现。
