from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from database.models.TelegramLinkToken import TelegramLinkToken
from database.models.UserTelegramAccount import UserTelegramAccount


class TelegramLinkService:
    def __init__(self, db: Session):
        self.db = db

    def create_link_token(self, user_id: int) -> dict:
        if not settings.TELEGRAM_BOT_USERNAME:
            raise ValueError("TELEGRAM_BOT_USERNAME is not configured.")

        raw_token = secrets.token_urlsafe(32)
        now = _utcnow_naive()
        expires_at = now + timedelta(minutes=settings.TELEGRAM_LINK_TOKEN_TTL_MINUTES)
        token = TelegramLinkToken(
            user_id=user_id,
            token_hash=self._hash_token(raw_token),
            expires_at=expires_at,
            created_at=now,
        )
        self.db.add(token)
        self.db.commit()
        return {
            "bot_username": settings.TELEGRAM_BOT_USERNAME,
            "link_url": f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={raw_token}",
            "expires_at": expires_at.isoformat(),
        }

    def get_status(self, user_id: int) -> dict:
        account = self._get_account(user_id)
        if account is None:
            return {"linked": False, "telegram_username": None, "is_enabled": False, "last_error": None}
        return {
            "linked": True,
            "telegram_username": account.telegram_username,
            "is_enabled": account.is_enabled,
            "linked_at": account.linked_at.isoformat() if account.linked_at else None,
            "last_error": account.last_error,
        }

    def unlink(self, user_id: int) -> None:
        account = self._get_account(user_id)
        if account is not None:
            self.db.delete(account)
            self.db.commit()

    def consume_start_token(self, raw_token: str, update: dict) -> dict:
        token_hash = self._hash_token(raw_token)
        now = _utcnow_naive()
        token = (
            self.db.query(TelegramLinkToken)
            .filter(TelegramLinkToken.token_hash == token_hash)
            .first()
        )
        if token is None or token.used_at is not None or token.expires_at < now:
            return {"linked": False, "reason": "invalid_or_expired_token"}

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return {"linked": False, "reason": "missing_chat_id"}

        account = self._get_account(token.user_id)
        existing_chat_account = (
            self.db.query(UserTelegramAccount)
            .filter(UserTelegramAccount.telegram_chat_id == str(chat_id))
            .first()
        )
        if existing_chat_account is not None and existing_chat_account.user_id != token.user_id:
            self.db.delete(existing_chat_account)
            self.db.flush()

        if account is None:
            account = UserTelegramAccount(user_id=token.user_id, linked_at=now, created_at=now)
            self.db.add(account)

        account.telegram_chat_id = str(chat_id)
        account.telegram_user_id = str(from_user.get("id")) if from_user.get("id") is not None else None
        account.telegram_username = from_user.get("username")
        account.is_enabled = True
        account.linked_at = now
        account.last_error = None
        account.updated_at = now
        token.used_at = now
        self.db.commit()
        return {"linked": True, "user_id": token.user_id}

    def _get_account(self, user_id: int) -> UserTelegramAccount | None:
        return (
            self.db.query(UserTelegramAccount)
            .filter(UserTelegramAccount.user_id == user_id)
            .first()
        )

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
