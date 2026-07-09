from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from database.db import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "related_snapshot_key", name="uq_notifications_user_type_snapshot"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    type = Column(String(60), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    payload_json = Column(JSONB, nullable=True)
    related_snapshot_key = Column(String(200), nullable=True, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
