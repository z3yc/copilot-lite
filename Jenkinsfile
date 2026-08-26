// ============================================================
// Copilot-Lite CI/CD 流水线（Jenkins 声明式）
// 运行环境：本机 Windows（bat 命令）。若未来迁移到 Linux runner，
// 把 bat 换成 sh 即可（命令本体一致）。
//
// 凭据（Jenkins → Manage Jenkins → Credentials）：
//   gitee-token     — Gitee 私人访问令牌（只读），类型 Username with password
//                     （用户名填 Gitee 用户名，密码填私人令牌）
//   feishu-webhook  — 飞书群机器人 WebHook URL，类型 Secret text（可不配，不配则不通知）
//   deploy-ssh-key  — （Phase 2）云服务器 SSH 私钥，类型 SSH Username with private key
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
    }

    parameters {
        booleanParam(name: 'DEPLOY_ENABLED', defaultValue: false,
                     description: '（Phase 2）启用自动部署到云服务器')
        string(name: 'DEPLOY_SERVER', defaultValue: '',
               description: '（Phase 2）云服务器地址，格式 user@host，如 root@1.2.3.4')
    }

    triggers {
        // 每 2 分钟轮询一次 Gitee（本机 NAT 环境用轮询，无需公网穿透）
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

        // ---------- Deploy（后门）----------
        // Phase 1（无服务器）：DEPLOY_ENABLED=false → 本阶段跳过。
        // Phase 2：勾选参数并填 DEPLOY_SERVER，启用 SSH 自动部署。
        stage('Deploy') {
            when {
                expression { return params.DEPLOY_ENABLED && params.DEPLOY_SERVER?.trim() }
            }
            steps {
                script {
                    withCredentials([
                        sshUserPrivateKey(credentialsId: 'deploy-ssh-key', keyFileVariable: 'SSH_KEY')
                    ]) {
                        // 1) 服务器上准备产物接收目录
                        bat "ssh -i \"%SSH_KEY%\" -o StrictHostKeyChecking=no ${params.DEPLOY_SERVER} \"mkdir -p /opt/copilot-lite/web/dist.new\""
                        // 2) 上传前端产物
                        bat "scp -i \"%SSH_KEY%\" -o StrictHostKeyChecking=no -r web\\dist\\* ${params.DEPLOY_SERVER}:/opt/copilot-lite/web/dist.new/"
                        // 3) 远端执行部署脚本（拉码 + 重建容器 + 健康检查 + 失败回滚）
                        bat "ssh -i \"%SSH_KEY%\" -o StrictHostKeyChecking=no ${params.DEPLOY_SERVER} \"bash /opt/copilot-lite/deploy/deploy_remote.sh\""
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                // 飞书通知（未配置 feishu-webhook 凭据则静默跳过）
                try {
                    withCredentials([string(credentialsId: 'feishu-webhook', variable: 'FEISHU_WEBHOOK')]) {
                        def result = currentBuild.currentResult
                        def icon = (result == 'SUCCESS') ? '✅' : '❌'
                        def text = "${icon} Copilot-Lite CI/CD\\n构建 #${env.BUILD_NUMBER}：${result}\\n分支：${env.GIT_BRANCH ?: 'main'}\\n耗时：${currentBuild.durationString}"
                        writeFile file: 'feishu.json', text: "{\"msg_type\":\"text\",\"content\":{\"text\":\"${text}\"}}"
                        bat 'curl.exe -s -X POST -H "Content-Type: application/json" --data-binary @feishu.json %FEISHU_WEBHOOK%'
                    }
                } catch (e) {
                    echo "未配置飞书 WebHook 凭据，跳过通知：${e}"
                }
            }
        }
    }
}
