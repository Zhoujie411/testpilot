# TestPilot

面向中小研发团队的低代码接口自动化测试与质量门禁平台。

当前仓库是 MVP 项目骨架，包含：

- FastAPI 后端：项目管理、环境管理、接口测试用例、执行记录
- Vue 3 + Vite 前端：项目概览和测试用例列表
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
