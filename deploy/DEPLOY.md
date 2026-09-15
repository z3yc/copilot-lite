# 云端部署指南

> 把 Copilot-Lite 部署到云服务器（2C4G 轻量，¥50/月内），浏览器直接访问。
> 前置：代码已在 Gitee（`https://gitee.com/zyc66x/copilot-lite.git`），部署编排文件在 `deploy/`。

---

## 1. 服务器选购

| 平台 | 推荐配置 | 参考价格 | 说明 |
|---|---|---|---|
| 腾讯云轻量 | 2C4G · 50GB SSD · 4M 带宽 | ¥30-50/月（新用户常打折） | 国内访问快，可选宝塔面板 |
| 阿里云轻量 | 2C4G · 60GB SSD | ¥40-60/月 | 同上 |
| 华为云/其他 | 2C4G | 类似 | 选带 **Docker 镜像** 的更省事 |

**必须项**：Linux（Ubuntu 22.04 / CentOS 7+）、2 核 4G 起、公网 IP、安全组放行 **80/443** 端口。

> 💡 隐私策略（混合模式）：云端只部署框架与脱敏示例数据；公司敏感文档**只在本地模式**使用。

---

## 2. 服务器初始化

### 2.1 SSH 登录

```bash
# 本地终端（Windows 用 PowerShell / Git Bash）
ssh root@你的服务器IP
```

### 2.2 安装 Docker（Ubuntu 示例）

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker
docker --version   # 验证
```

### 2.3 安装 docker compose 插件

```bash
apt-get update && apt-get install -y docker-compose-plugin
docker compose version
```

---

## 3. 部署 Copilot-Lite

### 3.1 克隆代码

```bash
cd /opt
git clone https://gitee.com/zyc66x/copilot-lite.git
cd copilot-lite
```

### 3.2 配置环境变量

```bash
cd deploy
cp .env.example .env
vim .env   # 必填：DEEPSEEK_API_KEY / SECRET_KEY / POSTGRES_PASSWORD / QDRANT_API_KEY / REDIS_PASSWORD
```

`.env` 关键项（密钥生成命令见 `.env.example` 内注释）：
```
DEEPSEEK_API_KEY=sk-xxx          # 必填
SECRET_KEY=<强随机值>             # 必填（云模式默认值会被启动自检拒绝）
# 超级管理员账号（可选，建议配置，见下方「超级管理员账号」说明）：
SUPER_ADMIN_USERNAME=demo         # 默认 demo
SUPER_ADMIN_PASSWORD=<强口令>      # 非空才会在启动时创建/提升该超管
POSTGRES_PASSWORD=<强随机口令>    # 必填（compose 缺省拒绝启动，须与 DATABASE_URL 一致）
DATABASE_URL=postgresql+asyncpg://copilot:<口令>@postgres:5432/copilot
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=<强随机值>         # 必填（Qdrant 开启 API Key 认证）
REDIS_PASSWORD=<强随机口令>       # 必填
REDIS_URL=redis://:<口令>@redis:6379/0
# 云端前端与后端同域部署（nginx 反代），无需配置 CORS_ORIGINS；
# 如前后端不同域，需在 .env 配置 CORS_ORIGINS=["https://你的前端域名"]
```

> 🔑 **超级管理员账号（demo）**：`SUPER_ADMIN_PASSWORD` 设为非空后，后端启动时会自动创建
> （或把同名已存在账号提升为）`role=admin` 的超管，默认用户名 `demo`；**未配置密码则不创建**。
> 超管有两个额外能力：① 是唯一可走环境变量 `DEEPSEEK_API_KEY` 兜底调用模型的账号
> （普通注册用户必须在「个人中心 → 模型设置」各自配置 Key，禁止白嫖部署方 Key）；
> ② 可访问管理后台 `/admin`（`ADMIN_ENABLED=true` 时）。登录入口与普通用户相同
> （前端「登录」页，用户名 `demo` + 你设置的密码）。

### 3.3 一键部署（推荐）

> 前端已进镜像（`deploy/Dockerfile.web` 多阶段构建），服务器**无需安装 Node**，
> 也无需手动构建 `web/dist`——只需 Docker。

```bash
cd /opt/copilot-lite
bash deploy/deploy.sh
```

脚本流程：拉取最新 `main`（仅快进合并，绝不覆盖服务器本地改动）→
`docker compose up -d --build`（构建后端 + 前端镜像）→ 健康检查（最多 120s）；
**失败自动回滚**到上一版代码并重建。

```bash
bash deploy/deploy.sh rollback   # 手动回滚到上一版代码并重建
```

> 可用环境变量覆盖：`APP_DIR`（默认 `/opt/copilot-lite`）、`BRANCH`（默认 `main`）、
> `HEALTH_URL`、`WAIT_SECONDS`。

首次构建会 `uv sync` / `npm ci`，约 3-8 分钟；
BGE 嵌入 / reranker 模型（约 1.1GB）首次使用从 hf-mirror 下载，
已挂载 `models` 卷持久化，重建容器不重复下载。

### 3.4 手动启动（等价，便于排查）

```bash
cd /opt/copilot-lite/deploy
docker compose up -d --build
```

### 3.5 验证

```bash
cd /opt/copilot-lite/deploy        # 以下 compose 命令需在 deploy/ 目录下执行

# 容器状态（全部 running/healthy）
docker compose ps

# 后端健康检查（经 nginx 80 端口，backend 仅内网 expose）
curl http://服务器IP/api/v1/health
# → {"status":"ok","app":"copilot-lite","version":"0.1.0","run_mode":"cloud"}

# 数据库迁移已由 backend 容器启动命令自动执行（alembic upgrade head）

# 排查：看后端日志
docker compose logs -f backend
```

浏览器访问：**http://服务器IP/** （Nginx → Web UI → API 代理）

---

## 3.6 启用 HTTPS（TLS）【线上安全必做】

> HTTP 明文传输登录密码与 JWT，公网部署必须上 TLS。流程：申请证书 → 挂载 → 启用 443 段 → 重建 web 容器。

### 步骤 1：域名解析（IP 直访无法签发可信证书）

```bash
# 在域名服务商处添加 A 记录：你的域名 → 服务器公网 IP
# 安全组放行 443 端口
```

### 步骤 2：安装 certbot 并签发证书（Let's Encrypt 免费）

> 80 端口已有 nginx 在跑，用 **webroot** 方式签发：宿主机 `/var/www/certbot` 已挂载进
> web 容器（见 `docker-compose.yml`），nginx 已配置 `/.well-known/acme-challenge/` 指向该目录。

```bash
apt-get update && apt-get install -y certbot
mkdir -p /var/www/certbot        # 挑战目录（compose 已挂载进 web 容器）
certbot certonly --webroot -w /var/www/certbot \
  -d 你的域名 --email 你的邮箱 --agree-tos --no-eff-email
# 证书默认落 /etc/letsencrypt/live/你的域名/{fullchain.pem,privkey.pem}
```

### 步骤 3：挂载证书并启用 443 段

在 `deploy/docker-compose.yml` 的 web 服务增加**证书目录挂载**与 443 端口
（`/var/www/certbot` 已默认挂载，无需再加）：

```yaml
  web:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.web
    volumes:
      - /var/www/certbot:/var/www/certbot:ro      # 已有：certbot webroot（ACME）
      - /etc/letsencrypt:/etc/nginx/certs:ro      # 新增：证书目录
    ports:
      - "80:80"
      - "443:443"                                  # 新增：放行 443
```

然后取消 `deploy/nginx.conf` 中 **443 server 段的注释** 和 **80 段的 301 跳转注释**，
重建 web **镜像**（配置已进镜像，仅重启不会生效）：

```bash
cd /opt/copilot-lite/deploy && docker compose up -d --build web
curl -I https://你的域名/   # 应看到 301/200 与 Strict-Transport-Security 头
```

### 步骤 4：自动续期

```bash
# certbot 证书 90 天有效；加 crontab 自动续期 + 重载 nginx
crontab -e
# 0 3 * * * certbot renew --quiet && docker restart deploy-web-1
```

---

## 4. 验证完整功能

| 功能 | 验证方式 |
|---|---|
| Web 界面 | 浏览器打开 http://IP/ 看到对话页 |
| 流式对话 | 发消息，回复逐字出现（SSE 生效） |
| 知识库 | 上传一篇 Markdown，状态变 ready |
| RAG 问答 | 问"根据文档，XXX 是什么"看引用 |
| 待办 | 让助手创建/查询待办 |

---

## 5. 常见问题排查

| 现象 | 原因 | 解决 |
|---|---|---|
| 80 端口无法访问 | 安全组未放行 | 云控制台安全组放行 80/443 |
| 上传文档失败/摄取失败 | BGE 模型下载慢 | 代码已默认 hf-mirror 镜像；网络差可预下载模型后挂载卷 |
| SSE 打字机卡顿 | Nginx 缓冲 | 已配置 `proxy_buffering off`（deploy/nginx.conf） |
| 后端容器重启循环 | 数据库连接失败 | 等 postgres healthcheck 通过；检查 .env 密码 |
| 改了口令后连不上，日志报 `password authentication failed` | 已有 `pgdata` 卷只在**首次初始化**时写入 `POSTGRES_PASSWORD`，之后改 `.env` 不生效 | 保留数据：`docker compose exec postgres psql -U copilot -c "ALTER USER copilot PASSWORD '<新口令>'"`；确认可丢数据：`docker compose down` 后 `docker volume rm deploy_pgdata`（**不要用 `down -v`**，会一并删掉 models/qdrantdata） |
| 内存不足 | 4G 跑 5 容器偏紧 | 关掉 redis（当前未实际使用）或升级 4G 以上 |
| 迁移报错 | 表已存在 | `docker compose exec backend uv run alembic stamp head` |
| 迁移报 relation does not exist | 0.12.1 已修复迁移链缺表（categories / memory_facts）；旧库建议重建 | `docker compose down && docker volume rm deploy_pgdata && docker compose up -d --build`（只删库卷，保留 models/qdrantdata，**勿用 `down -v`**） |
| 想手工建库 / 迁移链推不动 | — | 导入幂等初始化 SQL：`cd deploy && docker compose exec -T postgres psql -U copilot -d copilot < sql/init_postgres.sql`（建表 + 写入 alembic head，之后 `alembic upgrade` 为 no-op；见 [`sql/README.md`](sql/README.md)） |

---

## 6. 成本估算（月度）

| 项 | 费用 |
|---|---|
| 云服务器 2C4G | ¥30-50 |
| DeepSeek API（个人演示量） | ¥1-5 |
| 域名（可选，IP 直访可省） | ¥0-10/年 |
| **合计** | **<¥60/月** |

---

## 7. 面试演示建议

1. **演示前**：提前上传 2-3 篇文档（脱敏），准备 3 个演示问题（知识库问答/待办/普通对话）
2. **演示中**：先展示 Web 界面流式效果 → 问知识库问题展示引用 → 问待办展示工具调用
3. **演示后**：可展示 `/docs`（OpenAPI 文档）与 `docker compose ps`（架构可视化）

> 隐私红线：云端**不要**上传真实公司文档，使用脱敏示例数据。

---

## 8. 上线安全自检清单（每次部署前逐项确认）

| # | 检查项 | 说明 |
|---|---|---|
| 1 | HTTPS 已启用 | 80 强制跳 443、HSTS 生效（curl -I https://域名 可见） |
| 2 | SECRET_KEY 为强随机值 | 云模式启动自检会拒绝默认值，但请确认 .env 已覆盖 |
| 3 | POSTGRES_PASSWORD 非默认 | compose 缺省拒绝启动；口令与 DATABASE_URL 一致 |
| 4 | Qdrant/Redis 已认证 | QDRANT_API_KEY 与 REDIS_PASSWORD 已配置且不为空 |
| 5 | 端口收敛 | 仅 80/443 对外（安全组）；backend/postgres/qdrant/redis 仅内网 |
| 6 | 非 root 运行 | 后端容器 USER app（Dockerfile 已固化） |
| 7 | CORS 与部署形态一致 | 同域部署无需配置；跨域时白名单仅放行可信域名 |
| 8 | 限流与预算生效 | LLM_DAILY_TOKEN_BUDGET 按需开启；API_CHAT_RATE_LIMIT 按用户限频 |
| 9 | 镜像与依赖可复现 | uv 版本固定（Dockerfile tag）、uv.lock --frozen 安装 |
| 10 | 备份与回滚 | pgdata/qdrantdata/models 卷持久化；`deploy.sh` 健康检查失败自动回滚，亦可 `bash deploy/deploy.sh rollback` |
