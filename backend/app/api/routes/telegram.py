from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.services.telegram_bot_service import TelegramBotService
from backend.app.services.telegram_link_service import TelegramLinkService
from database.models.User import User


router = APIRouter()


@router.get("/telegram/status")
def telegram_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return TelegramLinkService(db).get_status(user.id)


@router.post("/telegram/link-token")
def create_telegram_link_token(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return TelegramLinkService(db).create_link_token(user.id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/telegram/link")
def unlink_telegram(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    TelegramLinkService(db).unlink(user.id)
    return {"linked": False}


@router.post("/integrations/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
    db: Session = Depends(get_db),
):
    if settings.TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret.")

    update = await request.json()
    text = ((update.get("message") or {}).get("text") or "").strip()
    if not text.startswith("/start"):
        return {"ok": True, "ignored": True}

    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return {"ok": True, "linked": False, "reason": "missing_token"}

    result = TelegramLinkService(db).consume_start_token(parts[1].strip(), update)
    if result.get("linked"):
        try:
            chat_id = str(((update.get("message") or {}).get("chat") or {}).get("id"))
            TelegramBotService().send_message(chat_id, "Telegram notifications are now connected.")
        except Exception:
            pass
    return {"ok": True, **result}
