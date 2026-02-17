# ScamVax Backend

家庭防骗演习平台 — FastAPI 后端

## 项目结构

```
scamvax-backend/
├── app/
│   ├── api/
│   │   ├── share.py          # POST /api/share/create, GET /api/share/{id}/audio
│   │   └── webpage.py        # GET /s/{share_id}（挑战网页）
│   ├── core/
│   │   ├── config.py         # 配置（pydantic-settings）
│   │   ├── database.py       # SQLAlchemy async 引擎
│   │   └── scheduler.py      # 定时清理任务（APScheduler）
│   ├── models/
│   │   └── share.py          # Share 数据模型
│   ├── services/
│   │   ├── audio.py          # 音频校验 + 处理
│   │   ├── tts.py            # Qwen3-TTS-VC 调用
│   │   ├── storage.py        # Cloudflare R2 操作
│   │   └── share.py          # Share 业务逻辑（创建/访问/销毁）
│   └── main.py               # FastAPI 入口
├── scripts/
│   └── migrations/           # Alembic 迁移脚本
├── requirements.txt
├── render.yaml               # Render 部署配置
└── .env.example              # 环境变量模板
```

## 本地开发

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入真实的 API Key 和数据库连接
```

### 3. 启动本地 PostgreSQL（可用 Docker）

```bash
docker run -d \
  --name scamvax-postgres \
  -e POSTGRES_DB=scamvax \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgres:16
```

### 4. 运行服务

```bash
uvicorn app.main:app --reload
```

访问 http://localhost:8000/docs 查看 API 文档

## API 契约

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/share/create` | 上传录音，生成挑战链接 |
| GET  | `/s/{share_id}` | 挑战网页（计数 + 过期检查） |
| GET  | `/api/share/{share_id}/audio` | 受控音频流（不暴露 R2 直链） |
| GET  | `/health` | 健康检查 |

## 部署到 Render

1. 推送代码到 GitHub
2. 在 Render Dashboard 创建新服务，关联仓库
3. 使用 `render.yaml` 自动配置
4. 在 Render 环境变量中填入：
   - `DASHSCOPE_API_KEY`
   - `R2_ENDPOINT_URL` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`

## 安全注意事项

- `DASHSCOPE_API_KEY` 仅后端环境变量，**绝不**出现在 App 或网页代码中
- R2 Bucket 禁止公开读，音频只通过受控接口提供
- 生产环境 `APP_ENV=production` 会自动关闭 `/docs` 接口
- 用户原声在处理完成后立即丢弃，不存储

## TODO（接入真实服务前）

- [ ] IAP 收据验证（App Store / Google Play 服务端验证）
- [ ] 奖励次数系统（关卡完成 → 发放 token）
- [ ] 完善 Alembic 迁移配置
- [ ] 添加 Sentry 错误监控
- [ ] 速率限制改用 Redis（当前用 DB 查询，高并发时需优化）
