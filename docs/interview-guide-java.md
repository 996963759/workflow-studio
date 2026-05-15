# Java 背景面试讲法

## 推荐定位

主语言 Java，具备后端工程基础；这个项目使用 Python/FastAPI，是为了贴近 AI 应用生态，重点展示模型接入、RAG、工作流编排、异步队列和多用户后端系统的工程化落地能力。

## 30 秒介绍

这是一个类 Dify 的 AI 工作流编排平台。前端用 React Flow 做可视化画布，后端用 FastAPI + SQLAlchemy 管理用户、团队空间、工作流、版本、运行历史和异步任务。系统支持 DeepSeek、阿里云百炼、PaiSmart RAG、本地知识库、Kafka 异步队列、权限隔离、审计日志和成本估算。

我的主语言是 Java。这个项目选择 Python/FastAPI，是因为 AI 应用生态里 Python 接模型、RAG 和外部 AI 服务更方便。我关注的是后端通用能力和 AI 应用工程化能力，这些设计可以迁移到 Spring Boot 体系。

## 面试时不要这样说

- 不要说“精通 Python”。
- 不要说“全程手写所有 AI 算法”。
- 不要把它说成普通前端 Demo。
- 不要回避主语言是 Java。

## 面试时可以这样说

> 我的主语言是 Java，后端基础主要来自 Spring 体系。这个项目后端用了 FastAPI，不是因为我放弃 Java，而是因为 AI 应用生态里 Python 接模型、RAG 和推理服务更顺手。我在项目里重点实现的是后端通用能力，比如认证权限、多租户隔离、数据库设计、异步队列、版本治理、审计日志和测试。如果换成 Spring Boot，我会按类似分层把 Controller、Service、Repository、DTO 和队列消费者拆出来。

## Java 类比

| 当前项目 | Java/Spring 类比 |
| --- | --- |
| FastAPI 路由 | Spring MVC Controller |
| Pydantic Model | DTO + Bean Validation |
| SQLAlchemy ORM | JPA / MyBatis |
| Alembic | Flyway / Liquibase |
| Bearer Token | Spring Security Token Filter |
| RunJobWorker | Kafka Consumer / Scheduled Worker |
| unittest | JUnit |
| Docker Compose | 本地联调环境 |

## 必须能讲清的 6 个文件

| 文件 | 你要会讲什么 |
| --- | --- |
| `server/src/main.py` | API 入口、路由、鉴权依赖、工作流运行接口 |
| `server/src/models.py` | 请求响应结构，类似 Java DTO |
| `server/src/orm.py` | 数据库表结构 |
| `server/src/storage.py` | 数据库读写、工作流版本、审计、运行历史 |
| `server/src/runner.py` | 工作流执行器，节点按连线拓扑顺序执行 |
| `server/src/jobs.py` | 异步任务入队、Worker 消费、失败重试 |

## 高频追问与回答

### 为什么不用 Spring Boot？

AI 应用生态里 Python 的模型 SDK、RAG 工具和实验效率更好，所以这个项目用 FastAPI 快速落地 AI 能力。但系统设计是后端通用的，认证、权限、队列、ORM、迁移、审计和测试都可以迁移到 Spring Boot。

### 你 Python 不熟，能维护吗？

我不会把自己包装成 Python 专家，但我能读懂并修改这个项目的核心链路。项目里用到的 Python 主要是 FastAPI 路由、Pydantic、SQLAlchemy、字典列表和异常处理。我更强的是后端系统设计和 Java 基础。

### 这个项目最有价值的地方是什么？

不是单纯调用大模型，而是把 AI 能力放进完整后端系统：多用户隔离、团队空间配置、工作流版本发布、异步队列、运行历史、审计日志、RAG 接入和成本估算。

### 如果用 Java 重写，你会怎么做？

用 Spring Boot 做 API，Spring Security 做认证，JPA/MyBatis 做数据访问，Flyway 做迁移，Kafka 做异步队列，Controller/Service/Repository 分层。工作流执行器可以保留同样的拓扑排序和节点运行模型。

