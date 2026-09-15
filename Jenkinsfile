// ============================================================
// Copilot-Lite CI/CD 流水线（Jenkins 声明式）
// 运行环境：本机 Windows（bat 命令）。若未来迁移到 Linux runner，
// 把 bat 换成 sh 即可（命令本体一致）。
//
// 凭据（Jenkins → Manage Jenkins → Credentials）：
//   gitee-token        — Gitee 私人访问令牌（只读），类型 Username with password
//                         （用户名填 Gitee 用户名，密码填私人令牌）
//   feishu-app-id      — 飞书应用 app_id，类型 Secret text
//   feishu-app-secret  — 飞书应用 app_secret，类型 Secret text
//   deploy-ssh-key     — （Phase 2）云服务器 SSH 私钥，类型 SSH Username with private key
//
// 参数（Jenkins 页面可改）：
//   DEPLOY_ENABLED  — （Phase 2）勾选启用自动部署
//   DEPLOY_SERVER   — （Phase 2）格式 user@服务器IP
//
// ⚠️ Windows 服务默认 PATH 不含用户级目录，这里显式补齐 uv / node；
//    若本机安装位置不同，修改下面 PATH 行。
// ============================================================

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
    }

    environment {
        // 用户级工具目录（uv / nvm4w node）前置，保留系统 PATH（${env.PATH} 在流水线启动时求值）
        // 若本机安装位置不同，修改前面两段路径即可
        PATH = "C:\\Users\\asus\\.local\\bin;C:\\nvm4w\\nodejs;${env.PATH}"
        GITEE_URL = 'https://gitee.com/zyc66x/copilot-lite.git'
        // 飞书通知目标：接收人的 open_id（非机密，可放仓库；如换人接收改这里）
        FEISHU_OPEN_ID = 'ou_6bc25da3c78f41193e801d900dcaaa62'
    }

    parameters {
        booleanParam(name: 'DEPLOY_ENABLED', defaultValue: false,
                     description: '（Phase 2）启用自动部署到云服务器')
        string(name: 'DEPLOY_SERVER', defaultValue: '',
               description: '（Phase 2）云服务器地址，格式 user@host，如 root@1.2.3.4')
    }

    triggers {
        // 轮询 Gitee：每 2 分钟"检查"一次，只有发现新提交才构建（廉价检查，无提交不构建）
        // 效果 = 提交后最多 2 分钟内自动触发。如需改频率：H/10 * * * *（10 分钟）、H 9 * * *（每天）
        pollSCM('H/2 * * * *')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout([
                    $class           : 'GitSCM',
                    branches         : [[name: '*/main']],
                    userRemoteConfigs: [[url: "${GITEE_URL}", credentialsId: 'gitee-token']],
                    extensions       : [[$class: 'CleanCheckout']]
                ])
            }
        }

        stage('Backend CI') {
            steps {
                dir('backend') {
                    bat 'if not exist reports mkdir reports'
                    bat 'uv sync --frozen'
                    bat 'uv run ruff check .'
                    bat 'uv run python scripts/db_init_sql.py --check'
                    bat 'uv run pytest --junitxml=reports\\junit.xml'
                }
            }
            post {
                always {
                    junit testResults: 'backend/reports/junit.xml', allowEmptyResults: true
                }
            }
        }

        stage('Frontend CI') {
            steps {
                dir('web') {
                    bat 'npm ci'
                    bat 'npm run build'   // = tsc -b && vite build（含类型检查）
                    bat 'npm test'        // = vitest run
                }
            }
        }

        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'web/dist/**', fingerprint: true
            }
        }

        // ---------- Deploy（后门，默认关闭）----------
        // Phase 1（无服务器）：DEPLOY_ENABLED=false → 本阶段跳过。
        // Phase 2：勾选参数并填 DEPLOY_SERVER，SSH 执行服务器上一键部署脚本
        //          （deploy/deploy.sh：拉码 + 构建镜像 + 重建容器 + 健康检查 + 失败回滚）。
        //          不再上传任何产物：前端已进镜像（deploy/Dockerfile.web）。
        stage('Deploy') {
            when {
                expression { return params.DEPLOY_ENABLED && params.DEPLOY_SERVER?.trim() }
            }
            steps {
                script {
                    withCredentials([
                        sshUserPrivateKey(credentialsId: 'deploy-ssh-key', keyFileVariable: 'SSH_KEY')
                    ]) {
                        // SSH 主机校验：accept-new 仅首次连接自动记录主机指纹，之后严格校验
                        // （取代 StrictHostKeyChecking=no 的中间人风险；
                        //   首次部署前建议手工 ssh 一次核对服务器指纹）
                        // 服务器上执行一键部署（拉码 + 构建镜像 + 重建 + 健康检查 + 失败回滚）
                        // 不再上传任何产物：前端已进镜像（deploy/Dockerfile.web）
                        bat "ssh -i \"%SSH_KEY%\" -o StrictHostKeyChecking=accept-new ${params.DEPLOY_SERVER} \"bash /opt/copilot-lite/deploy/deploy.sh\""
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                // 飞书通知（应用私聊消息；未配置 feishu-app-id / feishu-app-secret 凭据则静默跳过）
                try {
                    withCredentials([
                        string(credentialsId: 'feishu-app-id', variable: 'FEISHU_APP_ID'),
                        string(credentialsId: 'feishu-app-secret', variable: 'FEISHU_APP_SECRET')
                    ]) {
                        def result = currentBuild.currentResult
                        // 中文/emoji 用 unicode 转义书写（反斜杠+u+4位十六进制，规避本机 GBK 字面量损坏）；
                        // 注意：注释里不要出现 "反斜杠u" 字样，Groovy 词法器会在注释中也解析它。
                        def ok = (result == 'SUCCESS')
                        def statusIcon = ok ? '\u2705' : '\u274C'                     // check/ cross marks
                        def statusCn   = ok ? '\u6210\u529F' : '\u5931\u8D25'         // 成功 / 失败
                        // 消息正文：用真实换行（\n），最后由 jsonStr 统一转义成 JSON 合法的 \n
                        def text = "\uD83E\uDD16 Copilot-Lite CI/CD \u6784\u5EFA\u62A5\u544A\n" +          // title
                            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n" +  // divider
                            "\uD83D\uDCCC \u6784\u5EFA\uFF1Amain #${env.BUILD_NUMBER}\n" +                  // build line
                            "\uD83D\uDCCA \u7ED3\u679C\uFF1A${statusIcon} ${statusCn}\n" +                  // result line
                            "\u23F1\uFE0F \u8017\u65F6\uFF1A${currentBuild.durationString}\n" +            // duration line
                            "\uD83C\uDF3F \u5206\u652F\uFF1A${env.GIT_BRANCH ?: 'main'}\n" +              // branch line
                            "\uD83D\uDD17 \u8BE6\u60C5\uFF1A${env.BUILD_URL}"                              // detail link
                        // 失败/中止时附加错误摘要（最多 12 条）
                        // 策略：优先 junit.xml（pytest 直接产出，UTF-8 无损、中文不乱码）；
                        //       junit 缺失（前端等失败）时回退到构建日志正则提取。
                        if (!ok) {
                            try {
                                def picked = [] as LinkedHashSet
                                def junitPath = env.WORKSPACE + '\\backend\\reports\\junit.xml'
                                if (fileExists(junitPath)) {
                                    // readFile 默认平台编码（GBK），junit 是 UTF-8——必须显式指定
                                    def xml = readFile(file: junitPath, encoding: 'UTF-8')
                                    def tcRe = ~/<testcase classname="([^"]+)" name="([^"]+)"[^>]*>\s*<failure message="([^"]*)"/
                                    def mm = (xml =~ tcRe)
                                    while (mm.find() && picked.size() < 12) {
                                        def name = mm.group(2)
                                        def msg = mm.group(3)
                                        msg = msg.replace('&#10;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&amp;', '&')
                                        if (msg.length() > 160) msg = msg.substring(0, 160)
                                        picked.add(name + ' - ' + msg)
                                    }
                                }
                                if (!picked) {
                                    def base = env.WORKSPACE - '\\workspace\\copilot-lite'
                                    def logPath = base + '\\jobs\\' + env.JOB_NAME + '\\builds\\' + env.BUILD_NUMBER + '\\log'
                                    def logLines = readFile(file: logPath, encoding: 'UTF-8').readLines()
                                    def errRe = ~/(?i)(FAILED|Found \d+ errors|error TS|Exception|AssertionError|Traceback|not recognized|Cannot find|No test report|Finished: FAILURE|ERROR: script)|(?-i:^E\s{1,2}\w)/
                                    for (l in logLines) {
                                        if (picked.size() >= 12) break
                                        if (l.length() > 250) continue
                                        if (l =~ errRe) picked.add(l.trim())
                                    }
                                }
                                if (picked) {
                                    // 错误摘要小节（⚠ 错误摘要：）
                                    text += '\n\n\u26A0 \u9519\u8BEF\u6458\u8981\uFF1A\n' + picked.join('\n')
                                }
                            } catch (ignoreLog) {
                                echo "错误摘要读取失败（不影响消息）：${ignoreLog}"
                            }
                        }
                        // JSON 字符串转义（content 是"字符串化的 JSON"，必须两层转义，否则飞书 230001）
                        def jsonStr = { s -> '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"' }
                        def content = '{"text":' + jsonStr(text) + '}'
                        // 1) 获取 tenant_access_token（writeFile 必须显式 UTF-8，否则 Windows GBK 环境
                        //    会把中文写坏、emoji 写成 '?'，导致飞书 9499/230001）
                        writeFile file: 'feishu-token-req.json', encoding: 'UTF-8',
                            text: '{"app_id":' + jsonStr(env.FEISHU_APP_ID) + ',"app_secret":' + jsonStr(env.FEISHU_APP_SECRET) + '}'
                        def tokenResp = bat(returnStdout: true,
                            script: 'curl.exe -s -X POST -H "Content-Type: application/json" --data-binary @feishu-token-req.json https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal').trim()
                        env.FEISHU_TOKEN = (tokenResp =~ /"tenant_access_token":"([^"]+)"/)[0][1]
                        // 2) 发送私聊消息（encoding: 'UTF-8' 必须显式指定）
                        writeFile file: 'feishu-msg.json', encoding: 'UTF-8',
                            text: '{"receive_id":' + jsonStr(FEISHU_OPEN_ID) + ',"msg_type":"text","content":' + jsonStr(content) + '}'
                        bat 'curl.exe -s -X POST -H "Authorization: Bearer %FEISHU_TOKEN%" -H "Content-Type: application/json" --data-binary @feishu-msg.json "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id" || echo FEISHU_SEND_FAILED'
                    }
                } catch (e) {
                    echo "飞书通知失败（不影响构建结果）：${e}"
                }
            }
        }
    }
}
