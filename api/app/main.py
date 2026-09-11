"""ASGI application factory.

Caddy proxies ``/api/*`` without stripping the prefix (build plan §5), so routes
carry ``/api`` themselves.
"""

from fastapi import FastAPI

from app.routers import health


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(title="Indoor 360 Tour API", docs_url=None, redoc_url=None)
    app.include_router(health.router)
    return app


app = create_app()
