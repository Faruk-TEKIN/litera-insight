from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from database.db import Base


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_key = Column(String(160), nullable=False, unique=True, index=True)
    payload_json = Column(JSONB, nullable=False)
    metadata_json = Column(JSONB, nullable=True)
    generated_at = Column(DateTime, nullable=False)
