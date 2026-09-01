from __future__ import annotations

import base64

from app.config import Settings
from app.voice_provider import DashScopeQwenVoiceProvider


class _Response:
    def __init__(self, payload=None, *, content=b"", content_type="application/json"):
        self._payload = payload or {}
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_dashscope_voice_enroll_synthesize_and_revoke(monkeypatch):
    settings = Settings(
        app_env="test",
        dashscope_api_key="test-key",
        dashscope_voice_model="qwen3-tts-vc-2026-01-22",
    )
    provider = DashScopeQwenVoiceProvider(settings)
    posted = []

    def fake_post(url, **kwargs):
        posted.append((url, kwargs["json"]))
        action = kwargs["json"]["input"].get("action")
        if action == "create":
            encoded = kwargs["json"]["input"]["audio"]["data"].split(",", 1)[1]
            assert base64.b64decode(encoded) == b"voice-sample"
            return _Response({"output": {"voice": "voice-123"}})
        if action == "delete":
            return _Response({"output": {}})
        return _Response({"output": {"audio": {"url": "https://audio.test/result.mp3"}}})

    def fake_get(url, **kwargs):
        assert url == "https://audio.test/result.mp3"
        return _Response(content=b"mp3-data", content_type="audio/mpeg")

    monkeypatch.setattr("app.voice_provider.httpx.post", fake_post)
    monkeypatch.setattr("app.voice_provider.httpx.get", fake_get)

    enrolled = provider.enroll(
        profile_id="abc-def",
        mime_type="audio/mpeg",
        sample=b"voice-sample",
    )
    assert enrolled.voice_id == "voice-123"

    audio = provider.synthesize(voice_id=enrolled.voice_id, text="你好")
    assert audio.payload == b"mp3-data"
    assert audio.mime_type == "audio/mpeg"

    provider.revoke(enrolled.voice_id)
    assert [request[1]["input"].get("action") for request in posted] == [
        "create",
        None,
        "delete",
    ]
