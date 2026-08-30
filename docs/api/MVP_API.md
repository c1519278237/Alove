# MVP API 使用说明

API 前缀为 `/api/v1`，完整交互契约可在服务启动后通过 `/docs` 查看。

## 最短演示链路

1. 子女和老人分别调用 `POST /auth/sms/request`、`POST /auth/sms/verify` 登录。
2. 子女调用 `POST /families` 创建家庭，再调用 `/families/{id}/invites` 生成老人邀请码。
3. 老人调用 `POST /family-invites/{code}/accept` 加入家庭。
4. 老人调用 `POST /consents` 授予 `conversation_summary` 或 `care_need_sharing`。
5. 老人创建对话，并调用 `/conversations/{id}/messages` 与 AI 交互。
6. 老人将对话分享级别设为 `family_summary`，子女才能基于有效授权生成关怀摘要。

## WebSocket

连接：

```text
ws://127.0.0.1:8000/api/v1/realtime/conversations/{conversation_id}?token={access_token}
```

当前可用事件：

```json
{"type":"transcript.commit","text":"今天有点闷。"}
{"type":"session.end"}
```

音频事件会返回接收确认，但 `audio.commit` 在尚未配置 ASR 供应商时返回
`ASR_NOT_CONFIGURED`，不会伪装成已识别成功。

## 隐私约束

- 子女无法通过对话接口读取老人的原始对话；越权时统一返回 404。
- 摘要只使用分享级别为 `family_summary` 或 `selected` 的对话。
- 查看需求与摘要时同时校验共同家庭关系和未过期、未撤回的分项授权。
- 数据库敏感文本字段使用 Fernet 加密；非本地环境必须设置独立密钥。
