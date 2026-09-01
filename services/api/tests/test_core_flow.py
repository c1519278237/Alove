from conftest import auth, login


def bootstrap_family(client):
    child_token, child_id = login(client, "+8613800000001", "小林")
    elder_token, elder_id = login(client, "+8613800000002", "林奶奶")

    family_response = client.post(
        "/api/v1/families",
        headers=auth(child_token),
        json={"name": "林家", "my_role": "admin", "relationship_label": "女儿"},
    )
    assert family_response.status_code == 201, family_response.text
    family_id = family_response.json()["id"]

    invite_response = client.post(
        f"/api/v1/families/{family_id}/invites",
        headers=auth(child_token),
        json={"role": "elder", "relationship_label": "母亲"},
    )
    assert invite_response.status_code == 201, invite_response.text
    code = invite_response.json()["code"]
    accepted = client.post(
        f"/api/v1/family-invites/{code}/accept",
        headers=auth(elder_token),
        json={"code": code},
    )
    assert accepted.status_code == 200, accepted.text
    return child_token, child_id, elder_token, elder_id, family_id


def create_consent(client, elder_token, elder_id, child_id, family_id, consent_type):
    response = client.post(
        "/api/v1/consents",
        headers=auth(elder_token),
        json={
            "subject_user_id": elder_id,
            "grantee_user_id": child_id,
            "family_id": family_id,
            "consent_type": consent_type,
            "scope": {"summary_only": True},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_structured_error(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "environment": "test", "ai_provider": "demo"}

    missing_auth = client.get("/api/v1/me")
    assert missing_auth.status_code == 401
    assert missing_auth.json()["error"]["code"] == "UNAUTHORIZED"
    assert missing_auth.headers["X-Trace-ID"]


def test_admin_can_list_and_reuse_invite_page_for_more_elders(client):
    child_token, _, _, _, family_id = bootstrap_family(client)
    second_elder_token, _ = login(client, "+8613800000003", "林爷爷")

    created = client.post(
        f"/api/v1/families/{family_id}/invites",
        headers=auth(child_token),
        json={"role": "elder", "relationship_label": "父亲"},
    )
    assert created.status_code == 201, created.text
    code = created.json()["code"]

    active = client.get(
        f"/api/v1/families/{family_id}/invites", headers=auth(child_token)
    )
    assert active.status_code == 200, active.text
    assert code in {item["code"] for item in active.json()}

    accepted = client.post(
        f"/api/v1/family-invites/{code}/accept",
        headers=auth(second_elder_token),
        json={"code": code},
    )
    assert accepted.status_code == 200, accepted.text

    active_after_use = client.get(
        f"/api/v1/families/{family_id}/invites", headers=auth(child_token)
    )
    assert active_after_use.status_code == 200, active_after_use.text
    assert code not in {item["code"] for item in active_after_use.json()}

    members = client.get(
        f"/api/v1/families/{family_id}/members", headers=auth(child_token)
    )
    assert sum(item["role"] == "elder" for item in members.json()) == 2


def test_family_consent_ai_need_and_report_flow(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)

    report_consent = create_consent(
        client,
        elder_token,
        elder_id,
        child_id,
        family_id,
        "conversation_summary",
    )
    need_consent = create_consent(
        client, elder_token, elder_id, child_id, family_id, "care_need_sharing"
    )

    knowledge = client.post(
        f"/api/v1/families/{family_id}/knowledge",
        headers=auth(child_token),
        json={
            "title": "家庭称呼",
            "content": "小林是林奶奶的女儿，每周日晚通常会打电话。",
            "visibility_scope": "family",
        },
    )
    assert knowledge.status_code == 201, knowledge.text

    conversation_response = client.post(
        "/api/v1/conversations",
        headers=auth(elder_token),
        json={"family_id": family_id, "sharing_level": "family_summary"},
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation_id = conversation_response.json()["id"]

    turn = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth(elder_token),
        json={"text": "我今天有点孤单，想女儿了。"},
    )
    assert turn.status_code == 200, turn.text
    assert "AI助手" in turn.json()["assistant_message"]["text"]
    assert turn.json()["safety_level"] == "low"

    scam_turn = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth(elder_token),
        json={"text": "有人让我把验证码告诉他，再转账到安全账户。"},
    )
    assert scam_turn.status_code == 200, scam_turn.text
    assert scam_turn.json()["safety_level"] == "high"
    assert "不要转账" in scam_turn.json()["assistant_message"]["text"]

    raw_conversation = client.get(
        f"/api/v1/conversations/{conversation_id}", headers=auth(child_token)
    )
    assert raw_conversation.status_code == 404

    need_response = client.post(
        "/api/v1/care-needs",
        headers=auth(elder_token),
        json={
            "elder_user_id": elder_id,
            "title": "帮忙买菜",
            "description": "周六帮我买一些青菜。",
            "priority": "normal",
            "consent_id": need_consent["id"],
        },
    )
    assert need_response.status_code == 201, need_response.text
    need_id = need_response.json()["id"]

    child_needs = client.get(
        f"/api/v1/elders/{elder_id}/needs", headers=auth(child_token)
    )
    assert child_needs.status_code == 200, child_needs.text
    assert child_needs.json()[0]["title"] == "帮忙买菜"

    accepted = client.post(
        f"/api/v1/care-needs/{need_id}/accept", headers=auth(child_token)
    )
    assert accepted.status_code == 200
    completed = client.post(
        f"/api/v1/care-needs/{need_id}/complete", headers=auth(child_token)
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    generated = client.post(
        f"/api/v1/elders/{elder_id}/care-reports/generate",
        headers=auth(child_token),
        json={"period_days": 7},
    )
    assert generated.status_code == 200, generated.text
    report = generated.json()
    assert report["report"]["title"] == "生活状态与关怀摘要"
    assert report["report"]["shared_message_count"] == 2
    assert len(report["evidence_message_ids"]) == 2
    assert report_consent["revoked_at"] is None


def test_consent_cannot_be_granted_by_someone_else(client):
    child_token, child_id, elder_token, elder_id, family_id = bootstrap_family(client)
    response = client.post(
        "/api/v1/consents",
        headers=auth(child_token),
        json={
            "subject_user_id": elder_id,
            "grantee_user_id": child_id,
            "family_id": family_id,
            "consent_type": "conversation_summary",
            "scope": {},
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_family_isolation(client):
    child_token, _, _, _, family_id = bootstrap_family(client)
    outsider_token, _ = login(client, "+8613800000099", "陌生人")

    hidden = client.get(
        f"/api/v1/families/{family_id}/knowledge", headers=auth(outsider_token)
    )
    assert hidden.status_code == 404

    visible = client.get(f"/api/v1/families/{family_id}", headers=auth(child_token))
    assert visible.status_code == 200
