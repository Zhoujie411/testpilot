# TestPilot

面向中小研发团队的低代码接口自动化测试与质量门禁平台。

当前仓库是 MVP 项目骨架，包含：

- FastAPI 后端：项目管理、环境管理、接口测试用例、执行记录
- Vue 3 + Vite 前端：项目概览和测试用例列表
- B2C 测试工具箱：时间戳转换、图片压缩、指定尺寸裁切
- AI 测试用例 Agent：LangChain + LangGraph ReAct、附件理解、会话记忆
- 自定义大模型：OpenAI/Codex、跃迁维度及其他 OpenAI-compatible 服务
- 测试用例导出：Excel 与 XMind
- SQLite 本地开发数据库；后续可切换 PostgreSQL
- Docker Compose 预留 PostgreSQL 与 Redis 服务

## 快速启动

### 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

后端地址：<http://localhost:8000>  
接口文档：<http://localhost:8000/docs>

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：<http://localhost:5173>

部署到服务器后，前端会默认请求当前服务器主机的 `8000` 端口。也可以在构建时设置：

```bash
VITE_API_BASE_URL=https://api.example.com npm run build
```

后端 MVP 默认允许跨域访问。正式环境建议限制为你的前端域名：

```bash
CORS_ORIGINS=https://test.example.com uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## AI 测试 Agent

进入顶部“AI 测试 Agent”，先添加模型配置，再创建会话。支持的附件格式：

- PDF、DOCX、XLSX、CSV
- TXT、Markdown、JSON、YAML、XML、HTML、日志

单个附件最大 10MB。附件保存在 `backend/uploads/`，解析后的文本、会话消息和记忆保存在 SQLite。

也支持直接读取需求链接：在输入区点击 🔗 把公网链接抓取为会话附件，或在对话中直接粘贴 http/https 链接，Agent 会调用 `fetch_requirement_url` 工具抓取真实正文。仅支持无需登录、且正文在 HTML 中静态输出的公网页面；需登录的系统（Confluence、飞书等）以及 JavaScript 动态渲染的原型页（墨刀、Axure 在线分享等）无法提取正文，会返回明确提示，请导出文件后上传。链接抓取带 SSRF 防护（拒绝内网/回环地址、限制重定向 5 次、单页 5MB 上限）。

模型配置支持两种调用模式：

- `Responses API`：适合 OpenAI 官方支持该接口的模型
- `Chat Completions`：适合多数 OpenAI-compatible 第三方服务

模型 ID 不做硬编码，请填写你的服务商账号实际可用的模型 ID。API Key 使用 `TESTPILOT_SECRET_KEY` 加密后保存；正式部署前必须设置稳定的随机密钥：

```bash
cd backend
cp .env.example .env
# 编辑 .env 后启动
uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

若更换 `TESTPILOT_SECRET_KEY`，此前保存的 API Key 将无法解密，需要重新添加模型配置。

## 登录与权限

- `admin`：管理用户与模型配置，可以审计所有 Agent 会话
- `user`：使用项目、工具箱和自己的 Agent 会话

首次启动前，需要在 `backend/.env` 设置初始化管理员：

```env
TESTPILOT_ADMIN_USERNAME=admin
TESTPILOT_ADMIN_PASSWORD=至少12位的强密码
```

JWT 默认有效期为 8 小时，登录状态存储在浏览器当前标签页的 `sessionStorage`。完整的 Nginx、systemd 与 Certbot HTTPS 部署步骤见 `deploy/README.md`。

## MVP 路线

1. 完成接口用例编辑器、环境变量与断言配置
2. 增加批量执行、历史报告和失败重试
3. 对接 GitLab CI/Jenkins，并提供质量门禁 API
4. 增加飞书、钉钉、企业微信通知

## 目录结构

```text
testpilot/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ database.py
│  │  ├─ models.py
│  │  └─ routers/
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  ├─ package.json
│  └─ vite.config.js
└─ docker-compose.yml
```
