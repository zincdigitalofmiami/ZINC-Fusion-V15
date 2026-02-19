"""FastAPI server exposing read-only endpoints for Fusion."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fusion.api.routers import (
    db_explorer_router,
    market_drivers_router,
    market_router,
    overview_router,
    pulse_router,
    sentiment_strategy_router,
)

app = FastAPI(title="Fusion API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.environ.get("FUSION_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

app.include_router(overview_router)
app.include_router(market_router)
app.include_router(sentiment_strategy_router)
app.include_router(pulse_router)
app.include_router(market_drivers_router)
app.include_router(db_explorer_router)
