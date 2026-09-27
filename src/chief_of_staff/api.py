"""HTTP API: ``POST /v1/digest``, ``POST /v1/extract`` and ``GET /healthz``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel, Field

from chief_of_staff import __version__
from chief_of_staff.config import Settings
from chief_of_staff.extraction.factory import build_prioritizer, build_service
from chief_of_staff.extraction.service import ExtractionService
from chief_of_staff.models import ActionItem, Digest, Message
from chief_of_staff.pipeline import Pipeline


class DigestRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=5000)
    as_of: datetime | None = None


class Health(BaseModel):
    status: str
    version: str
    backend: str


def create_app(
    settings: Settings | None = None, service: ExtractionService | None = None
) -> FastAPI:
    settings = settings or Settings()
    extraction = service or build_service(settings)
    pipeline = Pipeline(extraction, build_prioritizer(settings), prefilter=settings.prefilter)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        extraction.close()

    app = FastAPI(title="Chief-of-Staff AI", version=__version__, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> Health:
        return Health(status="ok", version=__version__, backend=extraction.primary_label)

    @app.post("/v1/digest")
    async def digest(request: DigestRequest) -> Digest:
        return await pipeline.run(request.messages, as_of=request.as_of)

    @app.post("/v1/extract")
    async def extract(message: Message) -> list[ActionItem]:
        return (await extraction.extract_message(message)).items

    return app
