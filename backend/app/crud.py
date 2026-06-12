from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import Document


async def get_all_documents(session: AsyncSession) -> List[Document]:
    result = await session.execute(select(Document))
    return result.scalars().all()


async def create_document(
    session: AsyncSession,
    title: str,
    content: str,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Document:
    doc = Document(title=title, content=content, source=source, metadata_json=metadata or {})
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def delete_document(session: AsyncSession, doc_id: int) -> None:
    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc:
        await session.delete(doc)
        await session.commit()


async def clear_documents(session: AsyncSession) -> None:
    result = await session.execute(select(Document))
    for doc in result.scalars().all():
        await session.delete(doc)
    await session.commit()
