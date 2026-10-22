"""OpenAI-compatible chat client. The key, base URL, and model are env vars."""

from __future__ import annotations

import httpx

from backend.app.config import get_settings


class LLMError(RuntimeError):
    """The upstream model call failed. Safe to show a generic Persian message."""


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.boxapi_api_key.strip()
        self.base_url = settings.boxapi_base_url.strip()
        self.model = settings.boxapi_model.strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def complete(self, messages: list[dict], tools: list[dict] | None, tool_choice: str | None) -> dict:
        if not self.configured:
            raise LLMError("مدل زبانی تنظیم نشده است.")
        token = self.api_key
        if token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1].strip()
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 700,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        try:
            with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                response = client.post(
                    self.endpoint(),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMError("ارتباط با مدل زبانی برقرار نشد.") from exc
        if response.status_code >= 400:
            body = response.text[:300].replace(token, "***")
            raise LLMError(f"مدل زبانی پاسخ {response.status_code} داد: {body}")
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("پاسخ مدل زبانی قابل خواندن نبود.") from exc
        if not data.get("choices"):
            raise LLMError("پاسخ مدل زبانی ناقص بود.")
        return data
