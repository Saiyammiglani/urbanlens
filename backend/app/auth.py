"""Token auth as a dependency — runs BEFORE body validation (401 not 422)."""
from fastapi import Header, HTTPException

from .config import settings


async def require_token(x_api_token: str = Header(default="")) -> None:
    if x_api_token != settings.API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
