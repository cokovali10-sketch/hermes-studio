"""Conversation CRUD operations."""
import time
import uuid

from hermes.storage.db import get_db


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


async def create_conversation(title: str = "Untitled", model: str = "", mode: str = "chat") -> str:
    db = await get_db()
    conv_id = _new_id()
    now = time.time()
    await db.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at, model, mode) VALUES (?, ?, ?, ?, ?, ?)",
        (conv_id, title, now, now, model, mode),
    )
    await db.commit()
    return conv_id


async def get_conversation(conv_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    conv = dict(row)
    msg_cursor = await db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conv_id,),
    )
    conv["messages"] = [dict(r) for r in await msg_cursor.fetchall()]
    return conv


async def list_conversations() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
    return [dict(r) for r in await cursor.fetchall()]


async def add_message(
    conversation_id: str,
    role: str,
    content: str,
    model: str = "",
    route: str = "",
    metadata: str = "",
) -> int:
    db = await get_db()
    now = time.time()
    cursor = await db.execute(
        "INSERT INTO messages (conversation_id, role, content, model, route, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (conversation_id, role, content, model, route, metadata, now),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    await db.commit()
    return cursor.lastrowid


async def delete_conversation(conv_id: str) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    await db.commit()
    return cursor.rowcount > 0


async def update_conversation_title(conv_id: str, title: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, time.time(), conv_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_recent_conversations(limit: int = 20) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in await cursor.fetchall()]
