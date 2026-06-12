from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(1000), nullable=True)
    metadata_json = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
