# Job Hunt Agent

面向 AI Agent / LLM 应用工程师求职流程的本地工作台。项目代码、测试和合成示例可以公开，真实投递记录、面经、账号信息与密钥只保存在使用者自己的电脑或私有 Notion 中。

应用不依赖 Codex、Notion 或任何大模型 API，安装后可以直接在网页界面中使用：

- Excel 是投递记录的唯一数据源，不建立 SQLite 等第二份投递数据库。
- 面经默认保存为本地 Markdown 文件和本地索引。
- 所有写操作先展示变更预览，明确确认后才写入。
- 写 Excel 前创建备份，并在 WPS/Excel 占用文件时停止写入。
- Web 服务只监听 `127.0.0.1`，写接口使用进程内会话凭证保护。
- 不配置模型时，看板、面经、复盘、本地查询和规则化投递录入仍可使用。

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

## 使用方式

1. 在“投递看板”查看、搜索和筛选当前流程，在“面经”和“复盘”查看本地记录。
2. 在右侧“求职助手”输入投递变化。写入前会出现可编辑预览，只有点击“确认写入”才会修改本地文件。
3. 不需要自然语言助手时，可以只把本项目当作 Excel 和 Markdown 的本地可视化工作台。
4. 需要开放问答或更灵活的语义理解时，再到“设置 > 模型服务”选择服务商。支持 DeepSeek、通义千问、Moonshot、OpenAI 兼容接口和 Ollama。
5. 需要云端查看面经时，到“设置 > Notion 面经”保存 Integration Token 和数据库 ID，然后在面经列表中逐条手动同步；同步失败可直接重试。

远程模型和 Notion 都是可选项。API Key 与 Notion Token 由操作系统凭证管理器保存，设置页只显示“未配置 / 已配置 / 连接成功 / 连接失败”，不会回显凭证。Ollama 默认连接本机 `127.0.0.1`，不需要 API Key。

## 数据与可选集成

投递看板直接读取和更新用户指定的 `.xlsx` 文件，因此在 WPS 在线文档中查看同一文件时，不需要维护额外同步表。面经先写入本地 Markdown；Notion 仅作为可选的私有同步目标。

远程模型只接收用户在助手中提交的文本、固定系统指令和结构化输出定义，不会自动上传整份 Excel 或本地面经目录。若一次操作涉及面经正文，确认预览会单独标出远程数据范围。Notion 同步会发送所选面经的正文和基础信息，具体边界见 [docs/privacy.md](docs/privacy.md)，连接方式见 [docs/notion-setup.md](docs/notion-setup.md)。

## 隐私边界

- GitHub 只保存源代码、文档、测试和合成数据。
- 真实 Excel、面经 Markdown、备份、日志、Notion 页面地址和联系人信息不进入仓库。
- `.env`、API Key、Notion Token 和本机会话凭证不提交、不写入公开文件。
- 模型与 Notion 凭证只写入操作系统凭证管理器；普通配置文件只保存凭证引用和非敏感连接参数。
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
