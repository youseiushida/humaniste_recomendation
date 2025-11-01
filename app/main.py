from __future__ import annotations

import hmac
import hashlib
from typing import Any, Dict
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import settings
from .db import lifespan_session, ensure_extensions
from .service import process_one, propagate_update


app = FastAPI(title="microCMS Related Updater")


def verify_signature(secret: str | None, body: bytes, signature: str | None) -> bool:
    if not secret:
        return True  # no verification configured
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


@app.on_event("startup")
async def on_startup() -> None:
    await ensure_extensions()


@app.post("/webhook/microcms")
async def webhook_microcms(
    request: Request,
    x_microcms_signature: str | None = Header(default=None, alias="x-microcms-signature"),
) -> JSONResponse:
    body = await request.body()
    if not verify_signature(settings.MICROCMS_WEBHOOK_SECRET, body, x_microcms_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload: Dict[str, Any] = await request.json()
    endpoint = str(payload.get("api") or settings.MICROCMS_ENDPOINT)
    content_id = payload.get("id")
    if not content_id:
        return JSONResponse({"ok": True, "skipped": "no content id"})
    async with lifespan_session() as session:
        neighbors = await process_one(session, endpoint=endpoint, content_id=str(content_id))
        if neighbors:
            await propagate_update(session, endpoint=endpoint, neighbor_ids=neighbors)
    return JSONResponse({"ok": True, "id": content_id, "endpoint": endpoint})

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})
