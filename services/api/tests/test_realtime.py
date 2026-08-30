from conftest import auth
from test_core_flow import bootstrap_family


def test_realtime_text_protocol(client):
    _, _, elder_token, _, family_id = bootstrap_family(client)
    created = client.post(
        "/api/v1/conversations",
        headers=auth(elder_token),
        json={"family_id": family_id, "sharing_level": "private"},
    )
    conversation_id = created.json()["id"]

    with client.websocket_connect(
        f"/api/v1/realtime/conversations/{conversation_id}?token={elder_token}"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "session.ready"
        assert ready["audio_supported"] is False

        websocket.send_json({"type": "transcript.commit", "text": "今天想聊聊天。"})
        assert websocket.receive_json()["type"] == "asr.final"
        delta = websocket.receive_json()
        assert delta["type"] == "assistant.text.delta"
        assert "AI助手" in delta["text"]
        completed = websocket.receive_json()
        assert completed["type"] == "response.completed"

        websocket.send_json({"type": "audio.commit"})
        error = websocket.receive_json()
        assert error["code"] == "ASR_NOT_CONFIGURED"
