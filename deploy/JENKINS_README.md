# Jenkins CI/CD 手册（本机 Windows）

> 配套方案记录见 [`docs/CICD_PLAN.md`](../docs/CICD_PLAN.md)，流水线定义见根目录 [`Jenkinsfile`](../Jenkinsfile)。
> 目标：在本机跑 Jenkins 自动化流水线（Gitee 轮询触发 → 后端检查 → 前端构建 → 产物归档 → 部署后门）。

---

## 1. 前置条件（本机已满足 ✅）

| 项 | 版本 | 检查命令 |
|---|---|---|
| Java | 17（Temurin） | `java -version` |
| Git | 任意 | `git --version` |
| uv | 任意 | `uv --version` |
| Node / npm | 22 / 配套 | `node --version` |

> Jenkins LTS 需要 Java 17（本机已装）。后端要求 Python 3.12，由 `uv sync` 自动下载管理，无需手工安装。

## 2. 安装 Jenkins

本项目约定 Jenkins 数据目录放在仓库内（已 gitignore），方便备份与迁移：

| 目录 | 用途 |
|---|---|
| `.jenkins-home/` | JENKINS_HOME（配置、任务、构建数据） |
| `.jenkins/jenkins.war` | Jenkins 程序本体 |

### 2.1 下载（国内建议走清华镜像）

```powershell
# 清华镜像（快）
Invoke-WebRequest https://mirrors.tuna.tsinghua.edu.cn/jenkins/war-stable/latest/jenkins.war -OutFile .jenkins\jenkins.war
# 官方源（慢）
# Invoke-WebRequest https://get.jenkins.io/war-stable/latest/jenkins.war -OutFile .jenkins\jenkins.war
```

### 2.2 首次启动（前台，用于初始化）

```powershell
$env:JENKINS_HOME = "$PWD\.jenkins-home"
java -jar .jenkins\jenkins.war --httpPort=8080
```

浏览器打开 <http://localhost:8080>，按页面完成：

1. **解锁**：用初始化密码，位于 `.jenkins-home/secrets/initialAdminPassword`；
2. **安装插件**：选择 *Install suggested plugins*（含 Pipeline / Git / Credentials Binding）；
3. **创建管理员账号**（记住用户名密码）；
4. 保持默认实例地址即可。

### 2.3 注册为 Windows 服务（开机自启，之后无需手动启动）

推荐用 Jenkins 官方 MSI（`jenkins.msi`）或 NSSM 包一层服务：

```powershell
# 方式 A：官方 MSI（需要管理员权限，安装时勾选“以服务方式运行”并设置 JENKINS_HOME）
Invoke-WebRequest https://mirrors.tuna.tsinghua.edu.cn/jenkins/windows-stable/latest/jenkins.msi -OutFile .jenkins\jenkins.msi
# 然后双击安装；安装后服务名 jenkins，自动开机启动

# 方式 B：NSSM 包 java 命令（非管理员也能用，可手动设为服务）
#   nssm install jenkins "C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot\bin\java.exe" "-jar C:\...\copilot-lite\.jenkins\jenkins.war --httpPort=8080"
#   nssm set jenkins AppEnvironmentExtra JENKINS_HOME=C:\...\copilot-lite\.jenkins-home
#   nssm start jenkins
```

> ⚠️ 服务运行身份决定 PATH：若用系统服务跑，PATH 可能不含用户级目录，`Jenkinsfile` 顶部已显式补齐
> `C:\Users\asus\.local\bin`（uv）与 `C:\nvm4w\nodejs`（node），按本机实际路径核对。

## 3. 配置凭据

Jenkins → **Manage Jenkins → Credentials → Global**，添加：

| ID | 类型 | 填写 |
|---|---|---|
| `gitee-token` | Username with password | Username：Gitee 用户名；Password：Gitee 私人访问令牌（仓库 → 管理 → 私人令牌，勾选读仓库即可） |
| `feishu-app-id` | Secret text | 飞书开放平台应用 `app_id`（https://open.feishu.cn → 开发者后台 → 创建企业自建应用） |
| `feishu-app-secret` | Secret text | 同一应用的 `app_secret`；接收人 open_id 写在 `Jenkinsfile` 的 `FEISHU_OPEN_ID` |
| `deploy-ssh-key`（Phase 2） | SSH Username with private key | 私钥文件内容；Username 填服务器登录用户（如 root） |

## 4. 创建 Pipeline Job

1. Jenkins → **New Item** → 名称 `copilot-lite`，类型 **Pipeline**；
2. **General**：勾选 *GitHub Project*（可填 Gitee 地址，仅展示用）；
3. **Pipeline** 区域：
   - Definition：**Pipeline script from SCM**
   - SCM：**Git**
     - Repository URL：`https://gitee.com/zyc66x/copilot-lite.git`
     - Credentials：`gitee-token`
     - Branches to build：`*/main`
     - Script Path：`Jenkinsfile`
4. 保存后点 **Build Now** 手动触发一次，验证全绿。

## 5. 轮询触发（自动化）

`Jenkinsfile` 内已配置 `triggers { pollSCM('H/2 * * * *') }`，无需额外设置。
验证方式：本地改一行代码 → `git push` → 2 分钟内 Jenkins 自动开始构建 → 飞书收到结果。

> 若想改间隔，如每 5 分钟：`pollSCM('H/5 * * * *')`；只想手动触发：删除 triggers 段。

## 6. 飞书通知（应用私聊）

Jenkinsfile 通过**飞书开放平台应用**直接私聊通知（不依赖群机器人 WebHook）：

1. 飞书开放平台（https://open.feishu.cn）创建**企业自建应用** → 获取 `app_id` / `app_secret`；
2. 应用需开通权限：`im:message`（发送消息）；开发者后台 → 权限管理 → 开通；
3. 获取接收人 `open_id`（本机测试已用：`ou_6bc25da3c78f41193e801d900dcaaa62`），写入 `Jenkinsfile` 的 `FEISHU_OPEN_ID`；
4. 把 `app_id` / `app_secret` 存凭据 `feishu-app-id` / `feishu-app-secret`；
5. 未配置凭据时流水线自动跳过通知（不报错）。

## 7. 部署阶段启用（Phase 2，服务器到位后）

1. 服务器按 [`DEPLOY.md`](DEPLOY.md) 初始化：装 Docker、克隆仓库到 `/opt/copilot-lite`、配置 `deploy/.env`；
2. 生成密钥对：`ssh-keygen -t ed25519`，公钥追加到服务器 `~/.ssh/authorized_keys`，私钥存凭据 `deploy-ssh-key`；
3. 打开 Job → **Build with Parameters**：
   - 勾选 `DEPLOY_ENABLED`
   - `DEPLOY_SERVER` 填 `root@服务器IP`
4. 之后每次 push main，CI 通过后自动执行 `deploy/deploy_remote.sh`（拉码 → 替换前端产物 → 重建容器 → 健康检查 → 失败回滚）。

## 8. 常见问题排查

| 现象 | 原因 | 解决 |
|---|---|---|
| API 用 `用户名+登录密码` 的 Basic 认证返回 401 | Jenkins 2.5xx 安全加固：**API 认证只接受 API Token，不接受登录密码** | 登录 UI 后 `admin → Configure → API Token` 生成 Token；之后 `Authorization: Basic base64(用户名:Token)` |
| 表单登录总是跳 `/loginError`（密码明明正确） | 用户 `config.xml` 损坏（如手工改哈希时丢了 `</passwordHash>` 闭合标签），启动日志报 `Failed to load ...config.xml` | 检查 `.jenkins-home/logs` 与启动日志的 `SEVERE hudson.model.User#loadFromUserConfigFile`；修复 XML 后重启 |
| 手工编辑用户配置后不生效 | Jenkins 启动时会重新加载/序列化用户配置 | 改 `.jenkins-home/users/*/config.xml` 前先停 Jenkins，改完再启动；保持 XML 结构完整，可用 `python -m xml.dom.minidom 文件` 校验 |
| `uv` / `npm` 不是内部或外部命令 | Windows 服务 PATH 不含用户目录 | 核对 `Jenkinsfile` 顶部 PATH 行与本机实际安装路径一致 |
| bat 步骤挂死（`[Pipeline] bat` 后无任何输出、进程杀不掉） | **Job 名含中文** → 工作区路径含非 ASCII 字符（如 `workspace\工作`），cmd 代码页处理挂起 | **Job 名必须用 ASCII**（如 `copilot-lite`）；已踩坑：`工作` Job 的 bat 全部挂死，删除重建为 ASCII 名后恢复正常 |
| 飞书消息内容报 `230001 content is not a string in json format` | Jenkinsfile 里的中文/emoji 字面量在本机 GBK 环境加载时字节损坏（`writeFile` 产物含非法 UTF-8） | 通知消息保持**纯 ASCII**（见 `Jenkinsfile` post 段注释）；已实测 ASCII 消息发送成功 |
| API POST 返回 `400 Nothing is submitted` / `This page expects a form submission` | Jenkins 2.5xx 拒绝无 body 的 POST，且需要表单提交 | POST 带 form 参数：`curl -d "x=1" -H "Content-Type: application/x-www-form-urlencoded"`；带 crumb 头 |
| 构建一直停在 Checkout | Gitee 令牌失效 / 权限不足 | Jenkins → Credentials 更新 `gitee-token` |
| `pytest` 覆盖率失败 | 未达 80% 门槛 | 后端补测试；门槛在 `backend/pyproject.toml` addopts |
| 轮询不触发 | Job 未保存 / pollSCM 未生效 | 保存 Job；确认 Jenkins 时间正常；可用 *Build Now* 验证流水线本身 |
| 飞书收不到通知 | WebHook 失效 / 关键词不匹配 / 凭据缺失 | 用 curl 手工 POST 一次验证 WebHook；检查机器人安全设置 |
| 构建慢 | npm ci / uv sync 全量安装 | 属正常；后续可加缓存（`pipeline-maven` 风格或 `web/node_modules` 复用） |
| 端口 8080 被占 | 其他程序占用 | 换端口：`java -jar jenkins.war --httpPort=9090` |

## 9. 目录速查

```
copilot-lite/
├── Jenkinsfile                 # 流水线定义（提交到 git）
├── .jenkins-home/              # JENKINS_HOME（gitignore，勿提交）
├── .jenkins/jenkins.war        # Jenkins 程序（gitignore，勿提交）
├── deploy/
│   ├── deploy_remote.sh        # 服务器端部署脚本（Phase 2 使用）
│   └── JENKINS_README.md       # 本手册
└── docs/CICD_PLAN.md           # 方案记录与实施清单
```
