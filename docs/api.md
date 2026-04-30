# API 摘要

默认地址：

```text
http://127.0.0.1:8000
```

除 `/api/health`、`/api/provider-status`、认证接口外，其余接口需要：

```text
Authorization: Bearer <token>
```

## 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册账号并返回 token |
| POST | `/api/auth/login` | 登录并返回 token |
| GET | `/api/auth/me` | 获取当前用户 |
| POST | `/api/auth/logout` | 退出当前 token |

## 工作流

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/workflows` | 当前用户工作流列表 |
| POST | `/api/workflows/validate` | 校验工作流结构 |
| POST | `/api/workflows` | 创建工作流 |
| GET | `/api/workflows/{workflow_id}` | 获取工作流 |
| PUT | `/api/workflows/{workflow_id}` | 更新工作流 |
| DELETE | `/api/workflows/{workflow_id}` | 删除工作流并清理运行历史 |

## 运行历史

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/runs` | 直接运行传入的工作流，不保存工作流 |
| GET | `/api/runs` | 当前用户运行历史 |
| GET | `/api/runs?workflow_id={id}` | 某个工作流的运行历史 |
| DELETE | `/api/runs` | 清空当前用户运行历史 |
| DELETE | `/api/runs?workflow_id={id}` | 清空某个工作流的运行历史 |
| GET | `/api/runs/{run_id}` | 获取单条运行历史 |
| DELETE | `/api/runs/{run_id}` | 删除单条运行历史 |
| POST | `/api/workflows/{workflow_id}/runs` | 运行已保存工作流并保存历史 |

## 知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge/status` | 当前用户知识库状态 |
| GET | `/api/knowledge/documents` | 当前用户文档列表 |
| POST | `/api/knowledge/documents` | 上传 Markdown / TXT |
| DELETE | `/api/knowledge/documents/{filename}` | 删除文档 |

## 状态

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/provider-status` | DeepSeek / OpenAI 配置状态 |

