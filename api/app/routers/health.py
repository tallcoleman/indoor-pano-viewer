"""Liveness endpoint used by the compose healthcheck."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz")
def healthz(
    response: Response, db: Annotated[Session, Depends(get_db)]
) -> dict[str, str]:
    """200 when the database answers, 503 otherwise."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error"}
    return {"status": "ok"}
