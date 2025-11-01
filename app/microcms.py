from __future__ import annotations

from typing import Any, Dict, List, Optional
import httpx

from .config import settings


BASE_CONTENT_URL = f"https://{settings.MICROCMS_SERVICE_ID}.microcms.io/api/v1"


class MicroCMSClient:
    def __init__(self, api_key: str, endpoint: str) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.headers = {"X-MICROCMS-API-KEY": api_key, "Content-Type": "application/json"}

    async def get_content(self, content_id: str, depth: int = 1) -> Dict[str, Any]:
        url = f"{BASE_CONTENT_URL}/{self.endpoint}/{content_id}?depth={depth}"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def list_contents(
        self,
        limit: int = 100,
        offset: int = 0,
        fields: Optional[str] = None,
        ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields
        if ids:
            params["ids"] = ",".join(ids)
        url = f"{BASE_CONTENT_URL}/{self.endpoint}"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url, headers=self.headers, params=params)
            r.raise_for_status()
            return r.json()

    async def patch_relations(self, content_id: str, related_ids: List[str]) -> None:
        url = f"{BASE_CONTENT_URL}/{self.endpoint}/{content_id}"
        body = {settings.MICROCMS_RELATION_FIELD: related_ids}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(url, headers=self.headers, json=body)
            r.raise_for_status()


