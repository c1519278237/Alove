from conftest import auth
from test_core_flow import bootstrap_family, create_consent


def test_uploaded_knowledge_is_chunked_embedded_and_searchable(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)
    create_consent(client, elder_token, elder_id, child_id, family_id, "family_knowledge")

    uploaded = client.post(
        f"/api/v1/families/{family_id}/knowledge/upload",
        headers=auth(child_token),
        data={"title": "家庭日程", "visibility_scope": "family"},
        files={
            "file": (
                "schedule.txt",
                "女儿每周日晚上八点会给妈妈打电话。端午节一起包粽子。".encode(),
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["source_type"] == "upload"

    searched = client.get(
        f"/api/v1/families/{family_id}/knowledge/search",
        headers=auth(elder_token),
        params={"query": "女儿什么时候打电话"},
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()[0]["title"] == "家庭日程"
    assert searched.json()[0]["score"] > 0


def test_style_sample_learns_profile_only_after_elder_consent(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)
    payload = {
        "target_user_id": elder_id,
        "title": "聊天样本",
    }
    files = {
        "file": (
            "chat.txt",
            "妈妈，今天感觉怎么样？别担心，我在呢。记得早点休息，明天我再打电话。".encode(),
            "text/plain",
        )
    }
    denied = client.post(
        f"/api/v1/families/{family_id}/style-samples/upload",
        headers=auth(child_token),
        data=payload,
        files=files,
    )
    assert denied.status_code == 403

    create_consent(client, elder_token, elder_id, child_id, family_id, "style_personalization")
    uploaded = client.post(
        f"/api/v1/families/{family_id}/style-samples/upload",
        headers=auth(child_token),
        data=payload,
        files=files,
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["metrics"]["sentence_count"] >= 2

    profiles = client.get(
        f"/api/v1/families/{family_id}/style-profiles",
        headers=auth(child_token),
    )
    assert profiles.status_code == 200
    assert profiles.json()[0]["target_user_id"] == elder_id
    assert profiles.json()[0]["common_greetings"]


def test_voice_sample_consent_and_device_fallback(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)
    consent = client.post(
        "/api/v1/consents",
        headers=auth(child_token),
        json={
            "subject_user_id": child_id,
            "grantee_user_id": elder_id,
            "family_id": family_id,
            "consent_type": "voice_use",
            "scope": {"watermark_required": True},
        },
    )
    assert consent.status_code == 201, consent.text
    media = client.post(
        "/api/v1/media/audio",
        headers=auth(child_token),
        files={"file": ("voice.mp3", b"ID3-voice-sample", "audio/mpeg")},
    )
    assert media.status_code == 201
    enrolled = client.post(
        "/api/v1/voice-profiles/enrollment",
        headers=auth(child_token),
        json={
            "consent_id": consent.json()["id"],
            "allowed_recipient_ids": [elder_id],
            "sample_media_id": media.json()["id"],
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    verified = client.post(
        f"/api/v1/voice-profiles/{enrolled.json()['id']}/verify-consent",
        headers=auth(child_token),
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "ready_device_fallback"
    fallback = client.post(
        f"/api/v1/voice-profiles/{enrolled.json()['id']}/synthesize",
        headers=auth(elder_token),
        json={"text": "妈妈，我是归音 AI 助手。"},
    )
    assert fallback.status_code == 409
    assert fallback.json()["error"]["code"] == "VOICE_DEVICE_FALLBACK"


def test_quick_call_contacts_and_app_call_history(client):
    child_token, child_id, elder_token, _, family_id = bootstrap_family(client)
    contacts = client.get(
        f"/api/v1/families/{family_id}/contacts",
        headers=auth(elder_token),
    )
    assert contacts.status_code == 200, contacts.text
    child = next(item for item in contacts.json() if item["user_id"] == child_id)
    assert child["phone"].endswith("0001")

    created = client.post(
        f"/api/v1/families/{family_id}/call-events",
        headers=auth(elder_token),
        json={"callee_user_id": child_id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "initiated"
    completed = client.patch(
        f"/api/v1/call-events/{created.json()['id']}",
        headers=auth(elder_token),
        json={"status": "completed", "duration_seconds": 20},
    )
    assert completed.status_code == 200
    assert completed.json()["duration_seconds"] == 20

    history = client.get(
        f"/api/v1/families/{family_id}/call-events",
        headers=auth(child_token),
    )
    assert history.status_code == 200
    assert history.json()[0]["callee_user_id"] == child_id
