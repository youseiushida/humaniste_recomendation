from __future__ import annotations

from typing import List, Optional, Any
from datetime import datetime, timezone
from sqlalchemy import select, text, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .microcms import MicroCMSClient
from .normalizer import normalize_article
from .embeddings import embed_text
from .models import ArticleEmbedding

REQUIRED_FIELDS = "id,title,contents,content,body,text,html,description,publishedAt,createdAt"

def _pick_title_and_body(payload: dict[str, Any]) -> tuple[str, str]:
    title = str(payload.get("title") or payload.get("name") or "")
    # Try common body fields by priority
    for key in ("contents", "content", "body", "text", "html", "description"):
        val = payload.get(key)
        if isinstance(val, str) and len(val) > 0:
            return title, val
    # Fallback: serialize whole json
    import json

    return title, json.dumps(payload, ensure_ascii=False)


def _as_vector_param(vec: Any) -> list[float]:
    """Convert possible numpy arrays or other list-likes to a Python list[float]."""
    try:
        to_list = getattr(vec, "tolist", None)
        if callable(to_list):
            return [float(x) for x in to_list()]
    except Exception:
        pass
    if isinstance(vec, (list, tuple)):
        return [float(x) for x in vec]
    # As a last resort, try to iterate
    try:
        return [float(x) for x in list(vec)]  # type: ignore[arg-type]
    except Exception as exc:
        raise TypeError("embedding vector must be list-like") from exc


async def upsert_article(
    session: AsyncSession,
    content_id: str,
    title: str,
    normalized_text: str,
    embedding: list[float],
) -> None:
    now = datetime.now(timezone.utc)
    stmt = pg_insert(ArticleEmbedding).values(
        id=content_id,
        title=title,
        normalized_text=normalized_text,
        embedding=embedding,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=[ArticleEmbedding.id],
        set_={
            ArticleEmbedding.title.key: title,
            ArticleEmbedding.normalized_text.key: normalized_text,
            ArticleEmbedding.embedding.key: embedding,
            ArticleEmbedding.updated_at.key: now,
        },
    )
    await session.execute(stmt)


async def neighbors(session: AsyncSession, vec: list[float], self_id: str, k: int = 4) -> List[str]:
    # Use raw SQL for ORDER BY vector distance for performance
    q = text(
        """
        SELECT id
        FROM article_embeddings
        WHERE id <> :self_id
        ORDER BY embedding <=> :query
        LIMIT :k
        """
    )
    vec_param = _as_vector_param(vec)
    res = await session.execute(q, {"self_id": self_id, "query": vec_param, "k": k})
    return [row[0] for row in res.fetchall()]


async def process_one(session: AsyncSession, endpoint: str, content_id: str) -> List[str]:
    cms = MicroCMSClient(settings.MICROCMS_API_KEY, endpoint)
    # fetch single via list(ids=...) to allow draft without draftKey (API key must allow draft-all)
    lst = await cms.list_contents(limit=1, offset=0, fields=REQUIRED_FIELDS, ids=[content_id])
    items = lst.get("contents", [])
    if not items:
        return []
    detail = items[0]
    title, raw_body = _pick_title_and_body(detail)
    normalized, _summary, _full = await normalize_article(
        title=title,
        raw_html_or_text=raw_body,
        published_at=str(detail.get("publishedAt") or detail.get("createdAt") or ""),
        authors=None,
        type_hint=None,
    )
    vec = await embed_text(normalized)
    await upsert_article(session, content_id, title, normalized, vec)
    await session.commit()
    # compute neighbors
    ids = await neighbors(session, vec, self_id=content_id, k=4)
    # update relations
    if ids:
        await cms.patch_relations(content_id, ids)
    return ids


async def propagate_update(session: AsyncSession, endpoint: str, neighbor_ids: List[str]) -> None:
    cms = MicroCMSClient(settings.MICROCMS_API_KEY, endpoint)
    for nid in neighbor_ids:
        # we already have embedding in DB; reuse if exists to avoid re-LLM
        row = (await session.execute(select(ArticleEmbedding).where(ArticleEmbedding.id == nid))).scalar_one_or_none()
        if row:
            vec = row.embedding  # type: ignore[assignment]
        else:
            # fetch & compute
            lst = await cms.list_contents(limit=1, offset=0, fields=REQUIRED_FIELDS, ids=[nid])
            items = lst.get("contents", [])
            if not items:
                continue
            detail = items[0]
            title, raw_body = _pick_title_and_body(detail)
            normalized, _s, _f = await normalize_article(title, raw_body)
            vec = await embed_text(normalized)
            await upsert_article(session, nid, title, normalized, vec)
            await session.commit()
        ids = await neighbors(session, vec, self_id=nid, k=4)
        if ids:
            await cms.patch_relations(nid, ids)


async def initial_batch(session: AsyncSession, endpoint: str) -> None:
    cms = MicroCMSClient(settings.MICROCMS_API_KEY, endpoint)
    # 1) ingest all -> normalized + embed upsert
    offset = 0
    page = 0
    while True:
        lst = await cms.list_contents(limit=100, offset=offset, fields=REQUIRED_FIELDS)
        contents = lst.get("contents", [])
        if not contents:
            break
        for item in contents:
            cid = str(item.get("id"))
            # Use list() response directly (no detail fetch)
            title, raw_body = _pick_title_and_body(item)
            normalized, _s, _f = await normalize_article(title, raw_body)
            vec = await embed_text(normalized)
            await upsert_article(session, cid, title, normalized, vec)
        await session.commit()
        offset += len(contents)
        page += 1
    # 2) for each, compute neighbors and patch
    all_ids_res = await session.execute(select(ArticleEmbedding.id))
    all_ids = [r[0] for r in all_ids_res.fetchall()]
    for cid in all_ids:
        row = (await session.execute(select(ArticleEmbedding).where(ArticleEmbedding.id == cid))).scalar_one()
        vec = row.embedding  # type: ignore[assignment]
        ids = await neighbors(session, vec, self_id=cid, k=4)
        if ids:
            await cms.patch_relations(cid, ids)


