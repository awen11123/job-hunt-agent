# Job Hunt Agent

面向 AI Agent / LLM 应用工程师求职流程的本地工作台。项目代码、测试和合成示例可以公开，真实投递记录、面经、账号信息与密钥只保存在使用者自己的电脑或私有 Notion 中。

当前本地 Web MVP 不依赖 Codex、Notion 或任何大模型 API：

- Excel 是投递记录的唯一数据源，不建立 SQLite 等第二份投递数据库。
- 面经默认保存为本地 Markdown 文件和本地索引。
- 所有写操作先展示变更预览，明确确认后才写入。
- 写 Excel 前创建备份，并在 WPS/Excel 占用文件时停止写入。
- Web 服务只监听 `127.0.0.1`，写接口使用进程内会话凭证保护。

## 开发启动

需要 Python 3.12+ 和 Node.js。首次运行先安装依赖并构建前端：

```powershell
python -m pip install -e .
cd frontend
npm install
npm run build
cd ..
```

启动本地应用：

```powershell
python -m job_hunt_agent.web.launcher
```

启动器会选择一个空闲的本机端口，等健康检查通过后再打开默认浏览器。首次进入后，在“设置”中填写 Excel 投递表、本地备份目录和本地面经目录。用户配置默认位于系统应用数据目录的 `JobHuntAgent/config.json`，其中不保存会话凭证或模型密钥。

## 数据与可选集成

投递看板直接读取和更新用户指定的 `.xlsx` 文件，因此在 WPS 在线文档中查看同一文件时，不需要维护额外同步表。面经先写入本地 Markdown；Notion 仅作为可选的私有同步目标。

基础功能不需要模型。后续模型适配可选择 DeepSeek、通义千问、Moonshot、其他 OpenAI 兼容接口或本地 Ollama，不能把 API Key 写进仓库或普通配置文件。Notion 的连接方式见 [docs/notion-setup.md](docs/notion-setup.md)。

## 隐私边界

- GitHub 只保存源代码、文档、测试和合成数据。
- 真实 Excel、面经 Markdown、备份、日志、Notion 页面地址和联系人信息不进入仓库。
- `.env`、API Key、Notion Token 和本机会话凭证不提交、不写入公开文件。
- `frontend/dist` 是本机构建产物，不提交到 GitHub；发布阶段再由构建流程打包。

## 验证

```powershell
python -X utf8 -m pytest -q
cd frontend
npm test -- --run
npm run typecheck
npm run build
cd ..
python -X utf8 scripts/privacy_scan.py README.md docs examples frontend scripts src tests
```
