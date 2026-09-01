# 归音上线部署与成本测算

> 版本日期：2026-09-01。云服务价格会调整，采购前应再次查看厂商价格页。

## 1. 当前可部署能力

当前仓库已经形成 Flutter App/Web、FastAPI API、PostgreSQL、Caddy HTTPS 的完整部署链路。服务器端保管模型密钥、加密家庭资料与授权记录；客户端不包含任何云服务密钥。

```text
老人/子女 App
    │ HTTPS
    ▼
Caddy ── Flutter Web 静态资源
    │ /api/*
    ▼
FastAPI
    ├─ PostgreSQL：账号、家庭、授权、摘要、提醒、审计
    ├─ 加密媒体卷：图片、语音留言、声线样本
    ├─ DeepSeek：对话与视觉理解
    ├─ Embeddings：RAG 向量化（本地哈希或兼容接口）
    ├─ DashScope Qwen：经本人授权的声线复刻与语音合成
    └─ 短信适配器：正式手机号验证码
```

已实现：

- TXT、Markdown、CSV、JSON、PDF、DOCX 上传、解析、分块、加密保存；
- 65% 向量相似度 + 35% 关键词分数的混合检索，按家庭、角色和老人授权过滤；
- 更换向量模型后的整库重建入口；
- 子女表达样本上传、自动提取称呼/短句/问候/安慰和提醒习惯；
- AI 始终声明身份，表达风格不能覆盖安全规则或冒充真人；
- 本人声线样本、老人接收范围、授权、撤回、供应商删除与设备朗读降级；
- 阿里云百炼 `qwen-voice-enrollment` + `qwen3-tts-vc-2026-01-22` 直连适配；
- 老人端大按钮快捷呼叫子女/照护者，以及仅限 App 发起的通话记录；
- 本地系统提醒、家庭留言、语音留言、需求闭环、周报、安全运营和数据导出/删除。

## 2. 服务器首次部署

推荐先用一台中国内地 2 核 4GB Linux 服务器做 50–200 人封闭试点。安装 Git 与 Docker Engine/Compose，然后执行：

```bash
git clone https://github.com/c1519278237/Alove.git
cd Alove
cp .env.production.example .env.production
```

编辑 `.env.production`，至少填写域名、PostgreSQL 密码、应用签名密钥、Fernet 加密密钥、DeepSeek 密钥。Fernet 密钥可在安全电脑上生成：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

启动：

```bash
docker compose -f docker-compose.production.yml up -d --build
docker compose -f docker-compose.production.yml ps
```

Caddy 会为已解析到服务器的域名自动申请 HTTPS。部署前应放行 80/443，数据库端口不要暴露公网。

启用声线复刻：

```dotenv
VOICE_PROVIDER=dashscope_qwen
DASHSCOPE_API_KEY=单独申请的百炼密钥
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_VOICE_MODEL=qwen3-tts-vc-2026-01-22
```

DeepSeek 密钥不能用于语音合成。未配置百炼时保持 `VOICE_PROVIDER=device_tts`，App 会使用手机系统朗读。

生产 RAG 推荐配置一个中文神经网络 Embeddings 服务：

```dotenv
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=供应商的OpenAI兼容v1地址
EMBEDDING_API_KEY=单独的向量服务密钥
EMBEDDING_MODEL=供应商模型ID
```

修改后由子女端“知识库 → 更换向量模型后重建索引”重建向量。离线 `local_hash` 可演示且零调用费，但不等同于神经语义检索。

## 3. APP 打包

Web 和 Android 会把服务器 API 地址编译进产物：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 `
  -ApiBaseUrl https://app.example.com/api/v1
```

Android 正式发布前必须创建独立 keystore，并从 `apps/mobile/android/key.properties.example` 复制出不提交 Git 的 `key.properties`。配置好后追加 `-Android` 生成签名 APK。应用商店通常优先使用 AAB，可执行：

```powershell
Set-Location .\apps\mobile
& 'E:\DevTools\flutter\bin\flutter.bat' build appbundle --release `
  --dart-define=API_BASE_URL=https://app.example.com/api/v1
```

iOS 需要 macOS、Xcode、Apple Developer 账号和 App Store Connect，Windows 无法完成最终签名。

## 4. 成本模型

以下不是报价，而是便于创业比赛和试点预算的容量模型。假设每位老人每天 10 轮 AI 对话，每轮平均 1,500 输入 token、300 输出 token、朗读 120 个汉字；每月按 30 天，1 美元按 7.2 元估算。全部输入按“缓存未命中”测算，因此相对保守。

截至本版本日期，DeepSeek `deepseek-v4-flash-vision-exp` 的缓存未命中输入价为非高峰 0.22 美元/百万 token、高峰 0.44 美元/百万 token，输出为 0.66/1.32 美元/百万 token；图片会折算为输入 token。官方价格：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

Qwen3-TTS-VC 为 0.8 元/万字符，声线注册为 0.01 元/个；中国内地新开通账户可能有时限免费额度，不能作为长期预算依据。官方价格：[Alibaba Cloud Model Studio Pricing](https://help.aliyun.com/en/model-studio/model-pricing)。

| 月活老人 | 月对话轮数 | DeepSeek（非高峰～高峰） | 克隆语音 TTS | 推荐基础设施 | 短信/存储/监控预算 | 月总预算 |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 30,000 | ¥114～228 | ¥288 | ¥80～200 | ¥110～300 | **¥600～1,020** |
| 1,000 | 300,000 | ¥1,140～2,281 | ¥2,880 | ¥460～1,500 | ¥590～1,590 | **¥5,070～8,250** |
| 10,000 | 3,000,000 | ¥11,405～22,810 | ¥28,800 | ¥5,000～15,000 | ¥3,900～8,900 | **¥49,100～75,500** |

说明：

- 100 人试点可用 2 核 4GB 单机起步。腾讯云当前中国内地通用型刊例中，2 核 4GB 从 80 元/月起，4 核 8GB 为 230 元/月；实际活动价与售罄情况以购买页为准：[腾讯云轻量服务器调价公告](https://cloud.tencent.com/document/product/1207/119345)。
- 国内验证/通知短信 10 万条/月以内为 0.045 元/条；100 人表中按 200 条/月估算，其余档按每人每月 2 条估算：[阿里云国内短信价格](https://help.aliyun.com/zh/sms/product-overview/notice-on-price-adjustment-for-domestic-sms-services-2604)。
- TTS 是当前最大的可变成本。可以只朗读较短答案、缓存不含敏感信息的固定提醒、允许老人关闭自动朗读，并以设备 TTS 降级，成本会明显降低。
- 表中没有加入人工客服、内容审核人员、市场推广、公司注册、法务、等保测评或医疗器械认证等组织成本。
- 视觉图片会提高 DeepSeek 输入 token；真实费用应由运营面板按实际 token 和 TTS 字符数每周复盘。

## 5. 一次性与年度费用

- 域名：通常几十至数百元/年，取决于后缀和注册商；HTTPS 可由 Caddy/Let's Encrypt 免费申请。
- Android 海外 Google Play：25 美元一次性注册费，[Google Play 官方说明](https://support.google.com/googleplay/android-developer/answer/6112435?hl=en-EN-2)。国内 Android 商店需分别完成主体认证和隐私审核。
- iOS：Apple Developer Program 为 99 美元/年，[Apple 官方说明](https://developer.apple.com/programs/whats-included/)。
- 上线前安全/隐私/渗透测试可先预留 ¥5,000～30,000；这是项目预算建议，不是官方收费。

## 6. 上线闸门

在向真实老人开放下载前，必须完成：

1. 撤销所有曾出现在聊天、截图、提交记录中的 API Key，重新创建生产密钥；
2. 独立生产数据库、每日自动备份、异地加密备份和恢复演练；
3. 正式短信签名/模板，关闭本地测试验证码；
4. 隐私政策、用户协议、老人授权、子女声线本人活体/身份确认与撤回渠道；
5. APP 备案、ICP备案和应用商店隐私清单。工信部明确新开展业务的 App 应先备案再开展业务：[APP 备案通知解读](https://www.miit.gov.cn/jgsj/xgj/hlwgl/art/2023/art_564bf0759d7e41d5b4aa8ce4996b9e84.html)；
6. 医疗、诈骗、自伤、走失等高风险场景的人工升级流程和 110/120/家属紧急联系策略；
7. Android 正式签名、iOS 正式签名、崩溃监控、性能监控和灰度发布；
8. 100 人至少运行 4 周的封闭试点，再根据失败率、平均延迟、RAG 命中率、误报和授权撤回情况决定扩容。

当前合理的下一步不是直接全量商用，而是部署一套带正式域名的 50–100 人封闭测试环境，接入短信与声线服务，完成安全和授权验收后再提交应用商店。
