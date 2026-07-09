from __future__ import annotations

from io import BytesIO
import logging

import httpx

from backend.app.core.config import settings


logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramBotService:
    def __init__(self, token: str | None = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        if not self.token:
            raise TelegramConfigurationError("TELEGRAM_BOT_TOKEN is not configured.")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send_message(self, chat_id: str, text: str) -> dict:
        return self._post_json(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4096],
                "disable_web_page_preview": True,
            },
        )

    def send_document(
        self,
        chat_id: str,
        filename: str,
        content: bytes | str,
        mime_type: str = "application/octet-stream",
        caption: str | None = None,
    ) -> dict:
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        file_obj = BytesIO(content_bytes)
        files = {"document": (filename, file_obj, mime_type)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]
        return self._post_multipart("sendDocument", data=data, files=files)

    def _post_json(self, method: str, payload: dict) -> dict:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(f"{self.base_url}/{method}", json=payload)
        return self._parse_response(response)

    def _post_multipart(self, method: str, data: dict, files: dict) -> dict:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self.base_url}/{method}", data=data, files=files)
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Telegram returned non-JSON response: HTTP {response.status_code}") from exc

        if response.status_code >= 400 or not payload.get("ok"):
            description = payload.get("description") or f"HTTP {response.status_code}"
            raise RuntimeError(description)
        return payload.get("result") or {}
