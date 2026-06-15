from pydantic import BaseModel
from typing import Optional, List


class ChatRequest(BaseModel):
    question: str


class DocumentRead(BaseModel):
    id: int
    title: str
    content: str
    metadata: Optional[dict] = None


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
