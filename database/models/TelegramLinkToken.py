from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from database.db import Base


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
