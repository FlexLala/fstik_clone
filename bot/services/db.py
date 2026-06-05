"""Хранилище на SQLite."""
from __future__ import annotations

import secrets
import time
from typing import Optional

import aiosqlite

from bot.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS packs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL,
    name         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    pack_type    TEXT NOT NULL,
    media_kind   TEXT NOT NULL,
    is_shared    INTEGER NOT NULL DEFAULT 0,
    join_token   TEXT,
    max_members  INTEGER NOT NULL DEFAULT 0,   -- 0 = без лимита
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_packs_owner ON packs(owner_id);
CREATE INDEX IF NOT EXISTS idx_packs_token ON packs(join_token);

CREATE TABLE IF NOT EXISTS members (
    pack_name    TEXT NOT NULL,
    user_id      INTEGER NOT NULL,
    username     TEXT,
    notify       INTEGER NOT NULL DEFAULT 1,   -- уведомления вкл/выкл
    joined_at    INTEGER NOT NULL,
    PRIMARY KEY (pack_name, user_id)
);
CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id      INTEGER PRIMARY KEY,
    max_side     INTEGER NOT NULL DEFAULT 512,
    fit_mode     TEXT    NOT NULL DEFAULT 'fit',
    sharpen      INTEGER NOT NULL DEFAULT 1
);
"""

# --- миграции для существующих БД ---
_MIGRATIONS = [
    "ALTER TABLE packs ADD COLUMN max_members INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE members ADD COLUMN notify INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE user_settings ADD COLUMN fit_mode TEXT NOT NULL DEFAULT 'fit'",
    "ALTER TABLE user_settings ADD COLUMN sharpen INTEGER NOT NULL DEFAULT 1",
]


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        # применяем миграции — ошибки игнорируем (колонка уже есть)
        for sql in _MIGRATIONS:
            try:
                await db.execute(sql)
            except Exception:
                pass
        await db.commit()


# ─── паки ────────────────────────────────────────────────
async def add_pack(owner_id: int, name: str, title: str, pack_type: str,
                   media_kind: str, is_shared: bool = False,
                   max_members: int = 0) -> str | None:
    token = secrets.token_urlsafe(8) if is_shared else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO packs"
            "(owner_id,name,title,pack_type,media_kind,is_shared,join_token,max_members,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (owner_id, name, title, pack_type, media_kind,
             int(is_shared), token, max_members, int(time.time())),
        )
        await db.commit()
    if is_shared:
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


async def rename_pack(name: str, new_title: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packs SET title=? WHERE name=?", (new_title, name)
        )
        await db.commit()


async def set_pack_max_members(name: str, max_members: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE packs SET max_members=? WHERE name=?", (max_members, name)
        )
        await db.commit()


# ─── участники ───────────────────────────────────────────
async def add_member(pack_name: str, user_id: int,
                     username: str | None) -> bool:
    """Добавляет участника. Возвращает False если достигнут лимит."""
    pack = await get_pack(pack_name)
    if pack and pack.get("max_members", 0) > 0:
        members = await list_members(pack_name)
        if len(members) >= pack["max_members"]:
            return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO members(pack_name,user_id,username,notify,joined_at)"
            " VALUES(?,?,?,1,?)",
            (pack_name, user_id, username, int(time.time())),
        )
        await db.commit()
    return True


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


async def set_member_notify(pack_name: str, user_id: int, notify: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE members SET notify=? WHERE pack_name=? AND user_id=?",
            (int(notify), pack_name, user_id),
        )
        await db.commit()


async def get_notifiable_members(pack_name: str,
                                  exclude_user_id: int) -> list[dict]:
    """Участники с включёнными уведомлениями (кроме того, кто добавил)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM members WHERE pack_name=? AND notify=1 AND user_id!=?",
            (pack_name, exclude_user_id),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ─── настройки пользователя ──────────────────────────────
async def get_user_settings(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_settings WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return {"user_id": user_id, "max_side": 512,
                    "fit_mode": "fit", "sharpen": 1}


async def get_user_max_side(user_id: int) -> int:
    s = await get_user_settings(user_id)
    return s["max_side"]


async def set_user_settings(user_id: int, **kwargs) -> None:
    current = await get_user_settings(user_id)
    current.update(kwargs)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_settings(user_id,max_side,fit_mode,sharpen)"
            " VALUES(?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            "  max_side=excluded.max_side,"
            "  fit_mode=excluded.fit_mode,"
            "  sharpen=excluded.sharpen",
            (user_id, current["max_side"], current["fit_mode"], current["sharpen"]),
        )
        await db.commit()


async def set_user_max_side(user_id: int, max_side: int) -> None:
    await set_user_settings(user_id, max_side=max_side)
