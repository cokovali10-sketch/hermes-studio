"""IP-based rate limiting."""
import time

from hermes.storage.db import get_db


async def check_rate_limit(ip: str, max_requests: int = 30, window_seconds: int = 60) -> bool:
    """Return True if request is allowed, False if rate limited."""
    db = await get_db()
    now = time.time()
    window_start = now - (now % window_seconds)

    cursor = await db.execute(
        "SELECT request_count FROM rate_limits WHERE ip = ? AND window_start = ?",
        (ip, window_start),
    )
    row = await cursor.fetchone()

    if row is None:
        await db.execute(
            "INSERT INTO rate_limits (ip, window_start, request_count) VALUES (?, ?, 1)",
            (ip, window_start),
        )
        await db.commit()
        return True

    if row["request_count"] >= max_requests:
        return False

    await db.execute(
        "UPDATE rate_limits SET request_count = request_count + 1 WHERE ip = ? AND window_start = ?",
        (ip, window_start),
    )
    await db.commit()
    return True


async def cleanup_old_entries(max_age_seconds: int = 600):
    db = await get_db()
    cutoff = time.time() - max_age_seconds
    await db.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
    await db.commit()
