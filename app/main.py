"""Точка входу FastAPI-застосунку FootballValue."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api_router
from .config import get_settings
from .database.db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Аналітичний застосунок для футбольних матчів і коефіцієнтів. "
        "Надає лише статистичний аналіз, не робить ставок і не гарантує прибутку."
    ),
    lifespan=lifespan,
)

# CORS — щоб мобільний застосунок (Flutter) міг звертатися з пристрою/емулятора.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "disclaimer": ("Лише статистичний аналіз. Ставки пов'язані з ризиком втрати "
                       "коштів. Застосунок не робить ставок автоматично."),
    }


app.include_router(api_router, prefix="/api")
