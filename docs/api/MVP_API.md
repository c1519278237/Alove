# MVP API 使用说明

API 前缀为 `/api/v1`，完整交互契约可在服务启动后通过 `/docs` 查看。

## 最短演示链路

1. 子女和老人分别调用 `POST /auth/sms/request`、`POST /auth/sms/verify` 登录。
2. 子女调用 `POST /families` 创建家庭，再调用 `/families/{id}/invites` 生成老人邀请码。
3. 老人调用 `POST /family-invites/{code}/accept` 加入家庭。
4. 老人调用 `POST /consents` 授予 `conversation_summary` 或 `care_need_sharing`。
5. 老人创建对话，并调用 `/conversations/{id}/messages` 与 AI 交互。
6. 老人将对话分享级别设为 `family_summary`，子女才能基于有效授权生成关怀摘要。

## 主要能力分组

- `/consents`：摘要、需求、提醒、家庭知识、表达习惯、声线和录音的分项授权与撤回。
- `/families/{family_id}/knowledge`：家庭 RAG 资料上传、分块和可见范围隔离。
- `/memories`：候选记忆确认、纠正、拒绝与删除；只有已确认记忆参与检索。
- `/family-messages`、`/media/audio`：文字或加密音频留言、播放状态闭环。
- `/reminders`：提醒创建、修改以及 played/confirmed/skipped/expired 事件。
- `/elders/{elder_id}/care-reports`：授权周报生成、列表和准确度反馈。
- `/families/{family_id}/style-profile`：经老人授权的家人表达风格档案。
- `/voice-profiles`：声线供应商接入前的授权、对象限制、核验和撤回状态机。
- `/admin/families/{family_id}`：用量、风险、审计和家庭概览。
- `/me/export`、`DELETE /me`：个人数据副本和账号数据清理。

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
- 音频文件在本地存储前同样使用 Fernet 加密，下载同时校验发送者/接收者。
- 家庭成员添加的 RAG 资料和表达习惯只有在老人单独授权后才能影响老人对话。
