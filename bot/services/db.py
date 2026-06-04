"""Хранилище на SQLite: паки, участники совместных паков, токены приглашений."""
from __future__ import annotations

import secrets
import time
from typing import Optional

import aiosqlite

from bot.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS packs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL,
    name        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    pack_type   TEXT NOT NULL,      -- 'sticker' | 'emoji'
    media_kind  TEXT NOT NULL,      -- 'static' | 'video' | 'unified'
    is_shared   INTEGER NOT NULL DEFAULT 0,
    join_token  TEXT,               -- токен для ссылки-приглашения
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_packs_owner ON packs(owner_id);
CREATE INDEX IF NOT EXISTS idx_packs_token ON packs(join_token);

CREATE TABLE IF NOT EXISTS members (
    pack_name   TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    username    TEXT,
    joined_at   INTEGER NOT NULL,
    PRIMARY KEY (pack_name, user_id)
);
CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def add_pack(owner_id: int, name: str, title: str, pack_type: str,
                   media_kind: str, is_shared: bool = False) -> str | None:
    """Создаёт запись пака. Для совместного генерирует join_token."""
    token = secrets.token_urlsafe(8) if is_shared else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO packs"
            "(owner_id,name,title,pack_type,media_kind,is_shared,join_token,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (owner_id, name, title, pack_type, media_kind,
             int(is_shared), token, int(time.time())),
        )
        await db.commit()
    if is_shared:
        # владелец — тоже участник
        await add_member(name, owner_id, None)
    return token


async def get_pack(name: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM packs WHERE name=?", (name,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_pack_by_token(token: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM packs WHERE join_token=?", (token,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_packs(owner_id: int) -> list[dict]:
    """Паки, где пользователь владелец ИЛИ участник."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT DISTINCT p.* FROM packs p "
            "LEFT JOIN members m ON m.pack_name = p.name "
            "WHERE p.owner_id=? OR m.user_id=? "
            "ORDER BY p.created_at DESC",
            (owner_id, owner_id),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# --- участники совместных паков ---
async def add_member(pack_name: str, user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO members(pack_name,user_id,username,joined_at)"
            " VALUES(?,?,?,?)",
            (pack_name, user_id, username, int(time.time())),
        )
        await db.commit()


async def remove_member(pack_name: str, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM members WHERE pack_name=? AND user_id=?",
            (pack_name, user_id),
        )
        await db.commit()


async def is_member(pack_name: str, user_id: int) -> bool:
    pack = await get_pack(pack_name)
    if pack and pack["owner_id"] == user_id:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM members WHERE pack_name=? AND user_id=?",
            (pack_name, user_id),
        ) as cur:
            return await cur.fetchone() is not None


async def list_members(pack_name: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM members WHERE pack_name=? ORDER BY joined_at",
            (pack_name,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
