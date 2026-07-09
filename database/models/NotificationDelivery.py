from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from database.db import Base


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_notification_delivery_channel"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(Integer, nullable=False, index=True)
    channel = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    external_message_id = Column(String(120), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
