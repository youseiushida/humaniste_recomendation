from __future__ import annotations

from typing import List
from openai import OpenAI
from .config import settings


async def embed_text(text: str) -> List[float]:
    # Truncate to first 8,000 characters to avoid exceeding embedding model context
    truncated_text = text[:8000]
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.embeddings.create(
        model=settings.OPENAI_EMBED_MODEL,
        input=truncated_text,
    )
    return resp.data[0].embedding  # type: ignore[no-any-return]


