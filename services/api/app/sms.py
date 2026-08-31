import httpx

from .config import Settings
from .errors import AppError


def deliver_sms_code(settings: Settings, *, phone: str, code: str) -> None:
    if settings.sms_provider == "console" and settings.is_local:
        return
    if settings.sms_provider != "webhook" or not settings.sms_webhook_url:
        raise AppError(
            "SMS_PROVIDER_NOT_CONFIGURED",
            "短信服务尚未配置，请联系管理员",
            503,
        )
    headers = {"Content-Type": "application/json"}
    if settings.sms_webhook_token:
        headers["Authorization"] = f"Bearer {settings.sms_webhook_token}"
    try:
        response = httpx.post(
            settings.sms_webhook_url,
            headers=headers,
            json={
                "phone": phone,
                "code": code,
                "purpose": "guiyin_login",
                "expires_in": settings.sms_code_ttl_seconds,
            },
            timeout=settings.sms_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AppError("SMS_PROVIDER_UNAVAILABLE", "短信发送暂时失败，请稍后重试", 503) from exc
