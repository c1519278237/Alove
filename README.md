# 归音（Alove）

归音是一套面向老人和异地家庭成员的双向情感协同 AI App。仓库包含可运行的 Flutter App、FastAPI 后端、SQLite/PostgreSQL 数据层、DeepSeek 接入、家庭 RAG、关怀摘要、授权审计、加密语音留言和运营安全面板。

当前交付目标是“比赛可演示、可继续试点”的完整 MVP。短信和云声线在代码上已有适配，但必须由项目方另行开通合规供应商账号与密钥。

## 已实现功能

- 手机验证码登录；本地返回测试验证码，线上支持短信 Webhook 适配器。
- 创建家庭、邀请老人、老人/子女/照护者/管理员角色。
- 老人端大字号界面、文字或手机语音识别输入、设备 TTS 朗读。
- DeepSeek Chat Completions 真实联网文字与视觉对话；未填写密钥时使用安全演示模型。
- 老人可选择图片让 AI 辅助辨认物品、文字和生活场景；图片校验后加密保存，限制5MB并附带隐私与医疗安全提示。
- AI 身份常驻提示，诈骗、转账、医疗、自伤、迷路、疑似虐待与情感依赖保护。
- TXT/Markdown/CSV/JSON/PDF/DOCX 家庭资料上传、加密分块、混合向量检索、整库重建、已确认个人记忆、证据来源展示和提示词注入防护。
- 子女表达样本上传与自动风格学习；必须由老人单独授权，且 AI 始终不能冒充真人。
- 本人声线样本授权、阿里云百炼 Qwen 声线复刻适配、撤回删除与手机系统朗读降级。
- 老人端大按钮快捷呼叫子女/照护者，并记录由本 App 发起的电话状态。
- 老人确认后转达需求，子女接收、完成并形成状态闭环。
- 周期关怀摘要：常提主题、活跃天数、需求、提醒完成、家庭留言和行动建议。
- 后台任务每小时检查一次，为已有摘要授权的老人自动生成到期周报。
- 文字留言和加密语音留言，接收方可播放并回传已查看状态。
- 提醒创建、播放/确认/跳过事件记录；当前 App 首页展示活动提醒。
- 分项授权、撤回、候选记忆确认/拒绝/删除、个人数据导出和账号删除。
- 家庭管理员安全面板：风险事件、处理闭环、AI 用量、成本估算与访问审计。
- Android、iOS、Web 工程；Windows 上已配置 Web/Android 构建链路。

## 目录

```text
apps/mobile/              Flutter Android / iOS / Web App
services/api/             FastAPI API、实时网关、后台任务
packages/shared-prompts/  版本化系统提示词
scripts/                  本地启动、测试和 Android 构建脚本
infrastructure/docker/    可选的服务器容器配置
docs/                     开发文档和 API 说明
deliverables/             Word 版项目开发文档
```

## 本机直接运行（不需要 Docker）

这台电脑本身是虚拟机，因此本地方案使用 Python + SQLite + Flutter Web，不安装 Docker Desktop，也不运行 Android 模拟器。

在仓库根目录打开两个 PowerShell 窗口，分别执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_web.ps1
```

终端出现地址后，在浏览器打开 `http://localhost:8080`。API 文档位于 `http://127.0.0.1:8000/docs`。

本地登录流程中，点击“获取验证码”后，测试验证码会直接显示在 App 页面。第一次使用时：

1. 子女创建家庭并选择“管理员/子女”身份；
2. 生成老人邀请码；
3. 老人用另一个手机号登录并填写邀请码；
4. 老人在“授权与记忆”中按需授权摘要、需求、提醒、家庭资料和表达习惯；
5. 两端即可演示对话、RAG、需求、周报、留言、提醒和安全面板。

也可以不用脚本，手动启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
Set-Location .\apps\mobile
& 'E:\DevTools\flutter\bin\flutter.bat' run -d web-server --web-port 8080 --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Node.js 不是当前 Flutter/FastAPI 技术栈的运行依赖，已安装也不会冲突。

## 启用真实 DeepSeek

首次配置：

```powershell
Copy-Item .env.example .env
notepad .env
```

只在本机 `.env` 中填写：

```dotenv
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=你的DeepSeek密钥
AI_MODEL=deepseek-v4-flash-vision-exp
```

重启后端后，`http://127.0.0.1:8000/health` 的 `ai_provider` 会从 `demo` 变为 `deepseek`。`.env` 已被 Git 忽略，禁止把密钥提交到仓库。

## Android 真机

本机无法嵌套虚拟化，所以使用真实 Android 手机：

1. 手机和电脑连接同一局域网，打开开发者模式和 USB 调试；
2. 后端用 `--host 0.0.0.0` 启动，并允许 Windows 防火墙的 8000 端口；
3. 查询电脑局域网地址，例如 `192.168.1.23`；
4. 构建 APK：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_android.ps1 -ApiBaseUrl http://192.168.1.23:8000/api/v1
```

产物：`apps/mobile/build/app/outputs/flutter-apk/app-debug.apk`。可以用 Android Studio 或 `adb install -r` 安装。当前 APK 是本地调试签名；正式发布必须创建并妥善保管独立签名密钥。

iOS 源码和权限配置已经生成，但 Windows 不能完成 iOS 签名和打包，需要 macOS、Xcode 和 Apple Developer 账号。

## 测试

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_all.ps1
```

也可逐项运行：

```powershell
& '.venv\Scripts\python.exe' -m ruff check services/api/app services/api/tests
& '.venv\Scripts\python.exe' -m pytest services/api/tests -c services/api/pyproject.toml
Set-Location apps/mobile
& 'E:\DevTools\flutter\bin\cache\dart-sdk\bin\dart.exe' analyze
& 'E:\DevTools\flutter\bin\flutter.bat' test --no-pub
```

## 上线前需要的外部资源

本地演示不需要服务器。公开上线至少需要：

- 一台境内或目标地区可用的 Linux 服务器，试点建议 2 核 4GB 起；
- 域名、HTTPS 证书、PostgreSQL、备份和监控；
- DeepSeek API 密钥；
- 合规短信服务，将 `SMS_PROVIDER` 设置为 `webhook` 后接腾讯云/阿里云适配器；
- 对象存储和 CDN（当前本地语音使用加密磁盘存储）；
- Android/iOS 开发者账号和隐私政策；
- 若要声线复刻，另行申请阿里云百炼密钥并设置 `VOICE_PROVIDER=dashscope_qwen`；DeepSeek 不提供 TTS。

服务器可使用 `docker-compose.production.yml` 部署 PostgreSQL、API、Web 和 Caddy HTTPS；由于本机不能再虚拟化，该配置只用于云服务器，不是本机运行前提。

## 明确边界

- “关怀摘要”不是医学健康诊断，只汇总老人明确授权的主题、需求和互动信号。
- 当前对话语音输入/朗读使用手机或浏览器系统能力；DeepSeek 负责语言理解、生成与图片分析。
- 视觉分析可能出错，不能仅凭图片确认药品真伪、疾病诊断、用药剂量或转账信息。
- 家人语音留言是真实音频；AI 声线复刻需要本人授权、单独百炼密钥和上线前合规审核。
- Android 已支持本地系统通知；跨设备服务端推送仍需上线时接入 APNs/FCM/国内厂商推送。
- SQLite 适合单机演示；多人试点应切换 PostgreSQL，并使用正式迁移、密钥管理和备份策略。

完整设计依据见 [项目开发文档](docs/PROJECT_DEVELOPMENT_DOCUMENT.md)、[MVP API](docs/api/MVP_API.md) 和 [上线部署与成本测算](docs/DEPLOYMENT_AND_COST.md)。
