# 演示录制说明

README 中可以嵌入一段 20 到 40 秒的演示 GIF 或短视频，用来证明项目不是静态截图，而是可以真实运行的工作流平台。

## 推荐录制路径

1. 启动项目：

```powershell
docker compose up --build
```

2. 打开：

```text
http://127.0.0.1:8000
```

3. 录制以下操作：

- 登录或注册本地账号。
- 从“工作流模板”创建“客服知识库问答”。
- 点击“同步到后端”。
- 点击“同步运行”。
- 展示右侧运行日志。
- 切到“版本与审计”或“系统概览”。

## 录制建议

- 时长控制在 20 到 40 秒。
- 浏览器缩放建议设置为 90% 或 100%。
- 不要录入真实 API Key、Token、Cookie 或个人账号密码。
- 如果页面里有真实模型配置，录制前先确认 Key 被隐藏。
- 文件尽量小于 10 MB，GitHub README 加载会更快。

## 推荐文件位置

```text
docs/assets/screenshots/weaveflow-demo.gif
```

如果使用 MP4，可以放在：

```text
docs/assets/screenshots/weaveflow-demo.mp4
```

## README 嵌入方式

GIF：

```markdown
![织流 AI 演示](docs/assets/screenshots/weaveflow-demo.gif)
```

MP4 不能像图片一样稳定内嵌到 Markdown，建议上传到 GitHub Release、issue 或外部对象存储后再放链接。
