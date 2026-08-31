from conftest import auth, login
from test_core_flow import bootstrap_family, create_consent


def test_style_memory_admin_risk_and_reminder_flow(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)

    create_consent(
        client, elder_token, elder_id, child_id, family_id, "style_personalization"
    )

    style = client.put(
        f"/api/v1/families/{family_id}/style-profile",
        headers=auth(child_token),
        json={
            "target_user_id": elder_id,
            "preferred_calling_name": "妈妈",
            "common_greetings": ["妈，今天感觉怎么样"],
            "sentence_style": "短句、温和",
            "comfort_style": "先表示理解，再建议联系家人",
            "reminder_style": "像日常聊天一样提醒",
            "dialect_preference": "普通话",
            "banned_phrases": ["你怎么又忘了"],
        },
    )
    assert style.status_code == 200, style.text
    assert style.json()["preferred_calling_name"] == "妈妈"

    knowledge = client.post(
        f"/api/v1/families/{family_id}/knowledge",
        headers=auth(child_token),
        json={
            "title": "家庭日程",
            "content": "每周日晚八点，小林通常会给妈妈打电话。" * 80,
            "visibility_scope": "family",
        },
    )
    assert knowledge.status_code == 201, knowledge.text

    conversation = client.post(
        "/api/v1/conversations",
        headers=auth(elder_token),
        json={"family_id": family_id, "sharing_level": "private"},
    )
    conversation_id = conversation.json()["id"]
    routine = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth(elder_token),
        json={"text": "我每天早上七点去公园散步。"},
    )
    assert routine.status_code == 200, routine.text
    assert routine.json()["evidence"] == []

    memories = client.get("/api/v1/memories", headers=auth(elder_token))
    assert memories.status_code == 200
    assert memories.json()[0]["confirmation_status"] == "pending"
    memory_id = memories.json()[0]["id"]
    confirmed = client.post(
        f"/api/v1/memories/{memory_id}/confirm", headers=auth(elder_token)
    )
    assert confirmed.json()["confirmation_status"] == "confirmed"

    risk_turn = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth(elder_token),
        json={"text": "陌生人让我提供验证码并转账到安全账户。"},
    )
    assert risk_turn.json()["safety_level"] == "high"

    risks = client.get(
        f"/api/v1/admin/families/{family_id}/risk-events",
        headers=auth(child_token),
    )
    assert risks.status_code == 200, risks.text
    assert risks.json()[0]["status"] == "open"
    assert "scam_or_transfer" in risks.json()[0]["labels"]

    overview = client.get(
        f"/api/v1/admin/families/{family_id}/overview",
        headers=auth(child_token),
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["open_risk_events"] == 1
    assert overview.json()["conversations_7d"] == 1

    create_consent(
        client, elder_token, elder_id, child_id, family_id, "reminder_management"
    )
    reminder = client.post(
        "/api/v1/reminders",
        headers=auth(child_token),
        json={
            "owner_user_id": elder_id,
            "content": "晚上八点和女儿通电话",
            "schedule_rule": "once:2026-09-01T20:00:00+08:00",
            "category": "family",
        },
    )
    assert reminder.status_code == 201, reminder.text
    reminder_id = reminder.json()["id"]
    action = client.post(
        f"/api/v1/reminders/{reminder_id}/actions",
        headers=auth(elder_token),
        json={"action": "confirmed", "note": "已经完成"},
    )
    assert action.status_code == 200, action.text
    assert action.json()["action"] == "confirmed"


def test_encrypted_voice_message_access_is_limited_to_sender_and_recipient(client):
    child_token, _, elder_token, elder_id, _ = bootstrap_family(client)
    outsider_token, _ = login(client, "+8613800000088", "无关用户")
    audio_bytes = b"ID3-local-demo-audio"
    upload = client.post(
        "/api/v1/media/audio",
        headers=auth(child_token),
        files={"file": ("message.mp3", audio_bytes, "audio/mpeg")},
    )
    assert upload.status_code == 201, upload.text
    media_id = upload.json()["id"]

    sent = client.post(
        "/api/v1/family-messages",
        headers=auth(child_token),
        json={
            "recipient_user_id": elder_id,
            "type": "audio",
            "content": "一条家人语音留言",
            "audio_object_key": media_id,
        },
    )
    assert sent.status_code == 201, sent.text

    download = client.get(f"/api/v1/media/{media_id}", headers=auth(elder_token))
    assert download.status_code == 200
    assert download.content == audio_bytes
    denied = client.get(f"/api/v1/media/{media_id}", headers=auth(outsider_token))
    assert denied.status_code == 404


def test_rag_and_style_are_blocked_until_elder_grants_them(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)
    created = client.post(
        f"/api/v1/families/{family_id}/knowledge",
        headers=auth(child_token),
        json={
            "title": "家庭联系时间",
            "content": "女儿每周日晚八点给妈妈打电话。",
            "visibility_scope": "family",
        },
    )
    assert created.status_code == 201
    denied_style = client.put(
        f"/api/v1/families/{family_id}/style-profile",
        headers=auth(child_token),
        json={"target_user_id": elder_id, "preferred_calling_name": "妈妈"},
    )
    assert denied_style.status_code == 403
    assert denied_style.json()["error"]["code"] == "CONSENT_REQUIRED"

    conversation = client.post(
        "/api/v1/conversations",
        headers=auth(elder_token),
        json={"family_id": family_id, "sharing_level": "private"},
    ).json()
    before = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth(elder_token),
        json={"text": "女儿通常什么时候打电话？"},
    )
    assert before.json()["evidence"] == []

    create_consent(
        client, elder_token, elder_id, child_id, family_id, "family_knowledge"
    )
    create_consent(
        client, elder_token, elder_id, child_id, family_id, "style_personalization"
    )
    after = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth(elder_token),
        json={"text": "女儿通常什么时候打电话？"},
    )
    assert after.status_code == 200
    assert after.json()["evidence"][0]["title"] == "家庭联系时间"

    exported = client.get("/api/v1/me/export", headers=auth(elder_token))
    assert exported.status_code == 200
    assert exported.json()["user"]["id"] == elder_id
    assert len(exported.json()["messages"]) == 4
