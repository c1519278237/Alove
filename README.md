# 归音（Alove）

归音是一款面向老人及异地家庭成员的双向情感协同 AI App。本仓库按照
[`docs/PROJECT_DEVELOPMENT_DOCUMENT.md`](docs/PROJECT_DEVELOPMENT_DOCUMENT.md) 实现。

当前版本是首个可运行的纵向 MVP：

- FastAPI 模块化单体后端；
- 手机验证码开发登录、家庭创建/邀请/加入；
- 老人本人授予与撤回分项授权；
- 对话原文只对所有者可见，家庭成员只能查看授权摘要；
- OpenAI 兼容模型适配层，无密钥时自动使用安全演示模型；
- 诈骗、转账、医疗与自伤风险本地前置拦截；
- 家庭知识检索、需求转达、生活状态与关怀摘要；
- WebSocket 实时文本协议，以及 ASR 音频事件占位；
- Flutter 老人端/子女端源码，支持手机语音识别与 TTS 朗读。

## 仓库结构

```text
apps/mobile/              Flutter App 源码
services/api/             FastAPI 业务 API 与实时网关
packages/shared-prompts/  版本化系统提示词
infrastructure/docker/    容器构建文件
docs/                     项目开发文档
```

## 启动后端

Windows PowerShell：

```powershell
Copy-Item .env.example .env
& '.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --app-dir services/api
```

打开：

- 健康检查：`http://127.0.0.1:8000/health`
- OpenAPI：`http://127.0.0.1:8000/docs`

本地环境请求验证码时，响应会包含 `debug_code`；`pilot` 和 `production` 环境不会返回。

### 接入真实互联网 AI

在 `.env` 中配置兼容 OpenAI Chat Completions 协议的供应商：

```dotenv
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=your-key
AI_MODEL=gpt-4.1-mini
```

密钥不得写入代码或提交 Git。若不配置，系统使用可重复测试的本地安全演示回复。

## 运行测试

```powershell
& '.venv\Scripts\python.exe' -m pytest services/api/tests -c services/api/pyproject.toml
& '.venv\Scripts\python.exe' -m ruff check services/api/app services/api/tests
```

测试覆盖登录、家庭邀请、家庭隔离、老人授权、AI 对话、安全拦截、需求闭环、摘要生成和 WebSocket 协议。

## 生成并运行 Flutter App

本机安装 Flutter 3.x 后，在仓库根目录运行一次平台脚手架生成命令：

```powershell
flutter create apps/mobile --platforms android,ios --project-name guiyin_mobile
Set-Location apps/mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

注意：执行 `flutter create` 前请确认其不会覆盖 `lib/` 与 `pubspec.yaml`；建议先提交当前代码。
Android 模拟器访问宿主机使用 `10.0.2.2`，真机需要换成局域网可访问的后端地址并配置 HTTPS。

## 当前边界

- 音频 WebSocket 协议已定义，但服务端 ASR/TTS 供应商尚未接入；移动端目前使用手机语音识别与 TTS 完成原型闭环。
- 声线功能当前只实现授权状态机，不上传训练音频，也不生成一比一克隆声线。
- 本地使用 SQLite；共享开发和试点环境应使用 PostgreSQL 16、pgvector、Redis 和对象存储。
- 关怀摘要不是健康诊断，只处理老人明确授权分享的对话。

## 安全约束

- 不提交真实老人数据、录音、授权证据、生产密钥或数据库备份。
- 家庭数据查询必须先校验家庭成员关系，禁止仅凭资源 ID 读取。
- 声线、对话摘要、需求转达和家属代建提醒均使用独立授权。
- 高风险场景优先联系真实家人、急救或警方，AI 不替代专业服务。
