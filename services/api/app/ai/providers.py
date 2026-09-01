from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..config import Settings


@dataclass(slots=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    async def chat(self, messages: list[dict[str, Any]]) -> LLMResult: ...


class DemoLLMProvider:
    """Safe deterministic provider used when no external key is configured."""

    async def chat(self, messages: list[dict[str, Any]]) -> LLMResult:
        def text_content(item: dict[str, Any]) -> str:
            content = item.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            return ""

        user_text = next(
            (text_content(item) for item in reversed(messages) if item["role"] == "user"), ""
        )
        if any(word in user_text for word in ("孤单", "想孩子", "没人说话", "闷")):
            answer = (
                "我是归音AI助手，不是真实家人。听起来您这会儿有些孤单，我愿意陪您聊一会儿。"
                "您更想聊聊今天发生的事，还是让我帮您给家人留句话？"
            )
        elif any(word in user_text for word in ("提醒", "记得", "别忘")):
            answer = (
                "我是归音AI助手。我可以先帮您整理一个提醒草稿；在真正保存前，"
                "还需要您再确认时间和内容。"
            )
        elif any(word in user_text for word in ("孩子", "女儿", "儿子", "家人")):
            answer = (
                "我是归音AI助手。涉及转告家人的内容，我会先说清楚准备分享什么，"
                "只有得到您的确认才会发送。您希望我帮您整理哪件事？"
            )
        else:
            answer = (
                "我是归音AI助手，不是真实家人。我听见您说：“"
                + user_text[:80]
                + "”。您可以继续讲，我会尽量用简单、清楚的方式陪您一起处理。"
            )
        return LLMResult(
            text=answer,
            provider="demo",
            model="safe-rules-v1",
            latency_ms=5,
        )


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def chat(self, messages: list[dict[str, Any]]) -> LLMResult:
        started = time.perf_counter()
        url = self.settings.ai_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.settings.ai_model,
            "messages": messages,
            "temperature": self.settings.ai_temperature,
            "max_tokens": self.settings.ai_max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        content = payload["choices"][0]["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("AI provider returned no user-visible content")
        text = content.strip()
        latency_ms = round((time.perf_counter() - started) * 1000)
        return LLMResult(
            text=text,
            provider=self.settings.ai_provider,
            model=payload.get("model", self.settings.ai_model),
            latency_ms=latency_ms,
            usage=payload.get("usage", {}),
        )


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.ai_provider in {"deepseek", "openai_compatible"} and settings.ai_api_key:
        return OpenAICompatibleProvider(settings)
    return DemoLLMProvider()
