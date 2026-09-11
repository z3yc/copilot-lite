# 🛠 修复日志：线上部署安全加固（P5 前置）

> 主题：线上部署前的安全加固（HTTPS / 口令 / 认证 / 容器 / SSH / 回滚）
> 约定：每完成一项 → `git commit`（一次提交一个改动）→ 本文件登记复盘
> 位置：与其余日志同目录（仓库外），git 历史 + commit message 为仓库内记录

## 进度总览

| # | 改动项 | 提交 | 复盘 |
|---|---|---|---|
| S1 | nginx HTTPS/TLS 模板 + 安全头 + 上传体 + SSE 超时 | `61d144a` | ✅ |
| S2 | compose 加固（DB 强口令/restart/资源限制/健康检查） | `e4e9446`（与 S3 合并） | ✅ |
| S3 | Qdrant API Key + Redis requirepass 认证 | `e4e9446`（与 S2 合并） | ✅ |
| S4 | Dockerfile 固定 uv + 非 root + 瘦身 + .dockerignore | `88b0ab5` | ✅ |
| S5 | 部署脚本 SSH 加固 + 后端回滚 | `65dd910` | ✅ |
| S6 | DEPLOY.md HTTPS 四步流程 + 安全自检 10 项 | `c1dd611` | ✅ |

## 逐项复盘记录

### S1 nginx HTTPS 与安全头（`61d144a`）
- **改动**：nginx.conf 重写——80 段加 client_max_body_size 55m（对齐 50MB 上传，修默认 1MB 拦截大文档）、gzip、三个安全响应头（nosniff/DENY/Referrer-Policy）、SSE 超时 300→360s（工具轮最长≈LLM_TIMEOUT 60s×5 轮）；预留 443 server 段模板（TLSv1.2/1.3 + HSTS），证书就绪后取消注释即用
- **踩坑**：443 段必须默认注释——证书缺失时 nginx 直接启动失败，会阻断首次部署；HSTS 只放 443 段（HTTP 阶段发 HSTS 会把用户锁死）
- **面试话术**："TLS 不是可选项：明文 HTTP 会泄露 JWT 和密码。nginx 层我做了安全头、上传体对齐、SSE 超时预算三件事，HTTPS 段做成开关模板。"

### S2+S3 compose 加固与基础设施认证（`e4e9446`）
- **改动**：POSTGRES_PASSWORD 改 `${...:?}` 必填语法（弱口令不再硬编码进仓库）；qdrant 开启 `QDRANT__SERVICE__API_KEY`、redis `--requirepass`；全部服务加 restart: unless-stopped、资源限制（backend 2G/qdrant 1G/pg 512M/redis 128M/web 64M）、redis/web 健康检查补齐、backend depends_on 改 service_healthy；后端 QDRANT_API_KEY 配置 + QdrantClient 传 api_key（本地模式忽略）
- **踩坑**：① redis 健康检查最初写 `redis-cli -a "$$REDIS_PASSWORD"`——容器内没有这个环境变量，探活必失败；改用 `environment: REDISCLI_AUTH`，口令不进命令行；② compose 密码注入 DATABASE_URL 与 POSTGRES_PASSWORD 两处必须一致
- **面试话术**："基础设施认证三件：数据库强口令、Qdrant API Key、Redis requirepass——内网不是不设防的理由；所有口令走环境变量注入，仓库零明文。"

### S4 Dockerfile 与构建上下文（`88b0ab5`）
- **改动**：uv 镜像固定 `ghcr.io/astral-sh/uv:0.11.14`（对应本机版本，latest 漂移不可复现）；镜像内建 app 用户（uid 1000）非 root 运行；/models 预创建并 chown（命名卷首次挂载继承镜像目录属主）；compose 健康检查直用 `/app/.venv/bin/python`（省 uv run 开销）；.dockerignore 排除 .venv/cli/.venv/.jenkins-home/面试准备/ 等私有与大目录
- **踩坑**：非 root + 挂载卷的经典坑——root 创建的卷非 root 写不了；解法是镜像内预建目录 chown，Docker 首次挂载空卷会继承镜像属主
- **面试话术**："容器最小权限 + 可复现构建：固定工具链版本、非 root 运行、.dockerignore 把私有内容挡在构建上下文之外。"

### S5 部署脚本 SSH 加固（`65dd910`）
- **改动**：Jenkinsfile `StrictHostKeyChecking=no` → `accept-new`（首次记录指纹，之后严格校验，防中间人）；deploy_remote.sh `git reset --hard` → `merge --ff-only`（分叉拒绝强拉，保护服务器本地改动）；健康检查失败回滚从"只回滚前端"升级为"前端产物 + 后端代码 checkout 回部署前 SHA"
- **面试话术**："自动部署的破坏性操作要收口：reset --hard 会销毁服务器上的本地改动，ff-only 分叉即停；回滚要覆盖所有层而不只是前端。"

### S6 DEPLOY.md 上线指引（`c1dd611`）
- **改动**：HTTPS 四步流程（域名解析 → certbot webroot 签发 → 挂载证书 + 启用 443 段 → crontab 自动续期）；必填密钥清单（SECRET_KEY/POSTGRES_PASSWORD/QDRANT_API_KEY/REDIS_PASSWORD）；上线安全自检 10 项清单
- **面试话术**："部署文档必须可照抄执行——密钥生成命令、证书挂载路径、续期 crontab 都写死，还附一份上线前逐项打勾的安全清单。"

## 整体复盘

| 问题 | 回答 |
|---|---|
| 最难的坑？ | 非 root 容器 + 卷属主（镜像内预授权）；redis 健康检查的环境变量作用域（容器内没有 compose 变量） |
| 方法论沉淀？ | "内网≠安全"：数据库/向量库/缓存一律加认证；"默认注释的开关"：TLS 段做成模板，避免证书缺失阻断首启 |
| 面试素材？ | "上线前安全自检 10 项"可直接讲；六项改动=六次提交，工程习惯可视化 |

> 待办提醒：真实上线时按 DEPLOY.md §3.6 申请证书启用 HTTPS；deploy/.env 的密钥已在本地生成（2026-08-27），上线服务器时同步填入。
