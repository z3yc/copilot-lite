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
vim .env   # 填入 DEEPSEEK_API_KEY（必填），按需改数据库密码
```

`.env` 关键项：
```
DEEPSEEK_API_KEY=sk-xxx          # 必填
DATABASE_URL=postgresql+asyncpg://copilot:copilot@postgres:5432/copilot
QDRANT_URL=http://qdrant:6333
```

### 3.3 构建前端静态资源

> web 服务（nginx）挂载 `../web/dist`，**必须先构建出该目录**。
> 服务器需 Node 18+（vite 5 要求）。

```bash
# 在服务器上构建（推荐，保证与后端同机）
cd /opt/copilot-lite/web && npm ci && npm run build && cd ../deploy
# 或本地构建后把 web/dist 上传到服务器
```

### 3.4 一键启动

```bash
cd /opt/copilot-lite/deploy
docker compose up -d --build
```

首次启动会拉取镜像 + 构建后端（uv sync 依赖），约 3-8 分钟；
BGE 嵌入 / reranker 模型（约 1.1GB）首次使用从 hf-mirror 下载，
已挂载 `models` 卷持久化，重建容器不重复下载。

### 3.5 验证

```bash
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
| 内存不足 | 4G 跑 5 容器偏紧 | 关掉 redis（当前未实际使用）或升级 4G 以上 |
| 迁移报错 | 表已存在 | `docker compose exec backend uv run alembic stamp head` |

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
