from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass(slots=True)
class VoiceEnrollmentResult:
    voice_id: str
    status: str = "active"


@dataclass(slots=True)
class VoiceAudio:
    payload: bytes
    mime_type: str


class WebhookVoiceProvider:
    """Vendor-neutral adapter for a reviewed voice-cloning/TTS service.

    The configured service is expected to expose /enroll, /synthesize and
    /voices/{voice_id}. This keeps vendor credentials server-side and allows a
    China-region provider to be selected before the pilot without changing App code.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.voice_webhook_url:
            raise ValueError("VOICE_WEBHOOK_URL is required")
        self.settings = settings
        self.base_url = settings.voice_webhook_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.voice_webhook_token:
            headers["Authorization"] = f"Bearer {self.settings.voice_webhook_token}"
        return headers

    def enroll(
        self, *, profile_id: str, mime_type: str, sample: bytes
    ) -> VoiceEnrollmentResult:
        response = httpx.post(
            self.base_url + "/enroll",
            headers=self._headers(),
            json={
                "profile_id": profile_id,
                "mime_type": mime_type,
                "audio_base64": base64.b64encode(sample).decode("ascii"),
                "consent_verified": True,
                "watermark_required": True,
            },
            timeout=self.settings.voice_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        voice_id = str(payload.get("voice_id", "")).strip()
        if not voice_id:
            raise ValueError("voice provider did not return voice_id")
        return VoiceEnrollmentResult(
            voice_id=voice_id,
            status=str(payload.get("status", "active")),
        )

    def synthesize(self, *, voice_id: str, text: str) -> VoiceAudio:
        response = httpx.post(
            self.base_url + "/synthesize",
            headers=self._headers(),
            json={
                "voice_id": voice_id,
                "text": text,
                "watermark": True,
                "ai_identity_notice": True,
            },
            timeout=self.settings.voice_timeout_seconds,
        )
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("audio/"):
            return VoiceAudio(response.content, response.headers["content-type"].split(";")[0])
        payload = response.json()
        return VoiceAudio(
            base64.b64decode(payload["audio_base64"]),
            str(payload.get("mime_type", "audio/mpeg")),
        )

    def revoke(self, voice_id: str) -> None:
        response = httpx.delete(
            self.base_url + f"/voices/{voice_id}",
            headers=self._headers(),
            timeout=self.settings.voice_timeout_seconds,
        )
        response.raise_for_status()


class DashScopeQwenVoiceProvider:
    """Direct adapter for Alibaba Cloud Model Studio Qwen voice cloning.

    The API key never leaves the backend. The source sample is sent as a data
    URL only during enrollment; the returned provider voice id is what we keep.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY is required")
        self.settings = settings
        self.base_url = settings.dashscope_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

    def enroll(
        self, *, profile_id: str, mime_type: str, sample: bytes
    ) -> VoiceEnrollmentResult:
        encoded = base64.b64encode(sample).decode("ascii")
        response = httpx.post(
            self.base_url + "/services/audio/tts/customization",
            headers=self._headers(),
            json={
                "model": "qwen-voice-enrollment",
                "input": {
                    "action": "create",
                    "target_model": self.settings.dashscope_voice_model,
                    "preferred_name": f"gy_{profile_id.replace('-', '')[:10]}",
                    "audio": {"data": f"data:{mime_type};base64,{encoded}"},
                },
            },
            timeout=self.settings.voice_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        voice_id = str(payload.get("output", {}).get("voice", "")).strip()
        if not voice_id:
            raise ValueError("DashScope did not return output.voice")
        return VoiceEnrollmentResult(voice_id=voice_id, status="active")

    def synthesize(self, *, voice_id: str, text: str) -> VoiceAudio:
        response = httpx.post(
            self.base_url + "/services/aigc/multimodal-generation/generation",
            headers=self._headers(),
            json={
                "model": self.settings.dashscope_voice_model,
                "input": {"text": text, "voice": voice_id},
            },
            timeout=self.settings.voice_timeout_seconds,
        )
        response.raise_for_status()
        output = response.json().get("output", {})
        audio = output.get("audio", {})
        audio_url = audio.get("url") if isinstance(audio, dict) else audio
        if not isinstance(audio_url, str) or not audio_url.startswith("http"):
            raise ValueError("DashScope did not return output.audio.url")
        audio_response = httpx.get(
            audio_url,
            timeout=self.settings.voice_timeout_seconds,
            follow_redirects=True,
        )
        audio_response.raise_for_status()
        mime_type = audio_response.headers.get("content-type", "audio/mpeg").split(";")[0]
        if not mime_type.startswith("audio/"):
            mime_type = "audio/mpeg"
        return VoiceAudio(audio_response.content, mime_type)

    def revoke(self, voice_id: str) -> None:
        response = httpx.post(
            self.base_url + "/services/audio/tts/customization",
            headers=self._headers(),
            json={
                "model": "qwen-voice-enrollment",
                "input": {"action": "delete", "voice": voice_id},
            },
            timeout=self.settings.voice_timeout_seconds,
        )
        response.raise_for_status()
