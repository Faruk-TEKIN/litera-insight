from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND_HEALTH_URL = os.getenv("BACKEND_HEALTH_URL", "http://backend:8000/health")
NGROK_API_URL = os.getenv("NGROK_API_URL", "http://ngrok:4040/api/tunnels")
WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/integrations/telegram/webhook")
WAIT_SECONDS = int(os.getenv("TELEGRAM_WEBHOOK_WAIT_SECONDS", "120"))


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not token:
        print("[telegram-webhook] TELEGRAM_BOT_TOKEN is required.", file=sys.stderr)
        return 1
    if not secret:
        print("[telegram-webhook] TELEGRAM_WEBHOOK_SECRET is required.", file=sys.stderr)
        return 1

    wait_for_backend()
    public_url = wait_for_ngrok_url()
    webhook_url = f"{public_url.rstrip('/')}{WEBHOOK_PATH}"

    api_base = f"https://api.telegram.org/bot{token}"
    post_form(f"{api_base}/deleteWebhook", {"drop_pending_updates": "true"})
    result = post_form(
        f"{api_base}/setWebhook",
        {
            "url": webhook_url,
            "secret_token": secret,
            "allowed_updates": '["message"]',
        },
    )
    info = get_json(f"{api_base}/getWebhookInfo")

    if not result.get("ok"):
        print(f"[telegram-webhook] setWebhook failed: {result}", file=sys.stderr)
        return 1

    print(f"[telegram-webhook] Webhook configured: {webhook_url}")
    print(f"[telegram-webhook] Telegram webhook info: {redact_token(json.dumps(info, ensure_ascii=False))}")
    return 0


def wait_for_backend() -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            get_json(BACKEND_HEALTH_URL)
            return
        except Exception as exc:
            print(f"[telegram-webhook] Waiting for backend: {exc}")
            time.sleep(2)
    raise RuntimeError("Backend did not become reachable in time.")


def wait_for_ngrok_url() -> str:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            payload = get_json(NGROK_API_URL)
            for tunnel in payload.get("tunnels", []):
                public_url = tunnel.get("public_url", "")
                if public_url.startswith("https://"):
                    return public_url
        except Exception as exc:
            print(f"[telegram-webhook] Waiting for ngrok public URL: {exc}")
        time.sleep(2)
    raise RuntimeError("Ngrok HTTPS tunnel did not become reachable in time.")


def get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_form(url: str, data: dict[str, str]) -> dict:
    encoded = urlencode(data).encode("utf-8")
    request = Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def redact_token(value: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    return value.replace(token, "<telegram-token>") if token else value


if __name__ == "__main__":
    raise SystemExit(main())
