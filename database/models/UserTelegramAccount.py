from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from database.db import Base


class UserTelegramAccount(Base):
    __tablename__ = "user_telegram_accounts"
    __table_args__ = (
        UniqueConstraint("telegram_chat_id"),
        UniqueConstraint("user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    telegram_chat_id = Column(String(80), nullable=False)
    telegram_user_id = Column(String(80), nullable=True)
    telegram_username = Column(String(120), nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    linked_at = Column(DateTime, nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
