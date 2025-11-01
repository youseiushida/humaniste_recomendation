import asyncio
import sys
import asyncio
from .config import settings
from .db import lifespan_session, ensure_extensions
from .service import initial_batch


async def main() -> None:
    await ensure_extensions()
    async with lifespan_session() as session:
        await initial_batch(session, endpoint=settings.MICROCMS_ENDPOINT)


if __name__ == "__main__":
    # Windows: psycopg async requires SelectorEventLoop
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    asyncio.run(main())


