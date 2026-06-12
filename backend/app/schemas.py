from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    question: str


class DocumentRead(BaseModel):
    id: int
    title: str
    content: str
    metadata: Optional[dict] = None

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    answer: str
    sources: List[DocumentRead] = []


class DocumentCreate(BaseModel):
    title: str
    content: str
    source: Optional[str] = None
    metadata: Optional[dict] = None


class DocumentReadFull(BaseModel):
    id: int
    title: str
    content: str
    source: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
