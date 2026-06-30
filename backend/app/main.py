from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.logging_config import setup_logging
from app.utils.qdrant_service import get_qdrant_service
from app.routers.chat import router as chat_router
from app.routers.documents import router as documents_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_qdrant_service().ensure_ready()
    yield


app = FastAPI(title="Big 4 Audit RAG Chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(documents_router)
