"""Tool call statistics tracking."""
import hashlib
import json
import time

from hermes.storage.db import get_db


def _hash_args(args: dict) -> str:
    raw = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


async def log_tool_call(
    tool_name: str,
    args: dict,
    success: bool,
    elapsed_ms: float,
    conversation_id: str = "",
):
    db = await get_db()
    await db.execute(
        "INSERT INTO tool_stats (tool_name, args_hash, success, elapsed_ms, conversation_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (tool_name, _hash_args(args), 1 if success else 0, elapsed_ms, conversation_id, time.time()),
    )
    await db.commit()


async def get_tool_stats() -> dict:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as total FROM tool_stats")
    total = (await cursor.fetchone())["total"]

    cursor = await db.execute(
        "SELECT tool_name, COUNT(*) as count, AVG(elapsed_ms) as avg_ms FROM tool_stats GROUP BY tool_name"
    )
    by_name = {}
    for row in await cursor.fetchall():
        by_name[row["tool_name"]] = {"count": row["count"], "avg_ms": round(row["avg_ms"], 2)}

    return {"total_calls": total, "by_name": by_name}


async def get_historical_stats(days: int = 7) -> list[dict]:
    db = await get_db()
    cutoff = time.time() - days * 86400
    cursor = await db.execute(
        """SELECT
            date(created_at, 'unixepoch') as day,
            COUNT(*) as total,
            SUM(success) as successes,
            AVG(elapsed_ms) as avg_ms
        FROM tool_stats
        WHERE created_at > ?
        GROUP BY day
        ORDER BY day DESC""",
        (cutoff,),
    )
    return [dict(r) for r in await cursor.fetchall()]
