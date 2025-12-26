import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Iterable, Tuple

from config import DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_admin INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                is_blocked INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                post_link TEXT NOT NULL,
                from_chat TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                recipients_count INTEGER NOT NULL DEFAULT 0,
                delivered_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        # Индексы для ускорения выборок по часто используемым полям
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mailings_created_at ON mailings (created_at DESC)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mailing_type TEXT NOT NULL,
                post_link TEXT NOT NULL,
                from_chat TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                admin_chat_id INTEGER NOT NULL,
                scheduled_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduled_mailings_status_time ON scheduled_mailings (status, scheduled_at)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS webview_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                text_preview TEXT
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_posts_chat_created ON channel_posts (chat_id, created_at DESC)"
        )


def upsert_user(user_id: int, is_admin: bool = False) -> None:
    now = datetime.utcnow().isoformat()
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO users (user_id, is_admin, first_seen, last_seen, is_blocked)
                VALUES (?, ?, ?, ?, 0)
                """,
                (user_id, int(is_admin), now, now),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET last_seen = ?, is_admin = MAX(is_admin, ?)
                WHERE user_id = ?
                """,
                (now, int(is_admin), user_id),
            )


def mark_user_blocked(user_id: int) -> None:
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        conn.execute(
            "UPDATE users SET is_blocked = 1 WHERE user_id = ?",
            (user_id,),
        )


def get_active_users(include_admins: bool = True):
    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        if include_admins:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE is_blocked = 0",
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT user_id FROM users WHERE is_blocked = 0 AND is_admin = 0",
            ).fetchall()
    return [int(r["user_id"]) for r in rows]


def get_admin_users():
    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        rows = conn.execute(
            "SELECT user_id FROM users WHERE is_blocked = 0 AND is_admin = 1",
        ).fetchall()
    return [int(r["user_id"]) for r in rows]


def create_mailing(
    mailing_type: str,
    post_link: str,
    from_chat: str,
    message_id: int,
    recipients_count: int,
) -> int:
    now = datetime.utcnow().isoformat()
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        cur = conn.execute(
            """
            INSERT INTO mailings (type, created_at, post_link, from_chat, message_id, recipients_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mailing_type, now, post_link, from_chat, message_id, recipients_count),
        )
        return int(cur.lastrowid)


def update_mailing_counters(
    mailing_id: int,
    delivered_delta: int,
    error_delta: int,
) -> None:
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        conn.execute(
            """
            UPDATE mailings
            SET delivered_count = delivered_count + ?,
                error_count = error_count + ?
            WHERE id = ?
            """,
            (delivered_delta, error_delta, mailing_id),
        )


def add_webview_event(user_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        conn.execute(
            "INSERT INTO webview_events (user_id, created_at) VALUES (?, ?)",
            (user_id, now),
        )


def get_user_stats() -> Tuple[int, int, int, int, int, int]:
    now = datetime.utcnow()
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        new_24h = conn.execute(
            "SELECT COUNT(*) FROM users WHERE first_seen >= ?",
            (day_ago,),
        ).fetchone()[0]
        active_24h = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_seen >= ? AND is_blocked = 0",
            (day_ago,),
        ).fetchone()[0]
        active_7d = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_seen >= ? AND is_blocked = 0",
            (week_ago,),
        ).fetchone()[0]
        active_30d = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_seen >= ? AND is_blocked = 0",
            (month_ago,),
        ).fetchone()[0]
        blocked = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_blocked = 1",
        ).fetchone()[0]

    return int(total), int(new_24h), int(active_24h), int(active_7d), int(active_30d), int(blocked)


def get_recent_mailings(limit: int = 5) -> Iterable[sqlite3.Row]:
    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        rows = conn.execute(
            """
            SELECT id, type, created_at, recipients_count, delivered_count, error_count
            FROM mailings
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


def create_scheduled_mailing(
    mailing_type: str,
    post_link: str,
    from_chat: str,
    message_id: int,
    admin_chat_id: int,
    scheduled_at_iso: str,
) -> int:
    now = datetime.utcnow().isoformat()
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        cur = conn.execute(
            """
            INSERT INTO scheduled_mailings (
                mailing_type, post_link, from_chat, message_id,
                admin_chat_id, scheduled_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mailing_type, post_link, from_chat, message_id, admin_chat_id, scheduled_at_iso, now),
        )
        return int(cur.lastrowid)


def get_due_scheduled_mailings(now_iso: str) -> Iterable[sqlite3.Row]:
    """Возвращает запланированные рассылки, время которых уже наступило."""

    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        rows = conn.execute(
            """
            SELECT id, mailing_type, post_link, from_chat, message_id, admin_chat_id, scheduled_at
            FROM scheduled_mailings
            WHERE status = 'pending' AND scheduled_at <= ?
            ORDER BY scheduled_at ASC, id ASC
            """,
            (now_iso,),
        ).fetchall()
    return rows


def update_scheduled_mailing_status(mailing_id: int, status: str) -> None:
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        conn.execute(
            "UPDATE scheduled_mailings SET status = ? WHERE id = ?",
            (status, mailing_id),
        )


def get_scheduled_mailings(limit: int = 10) -> Iterable[sqlite3.Row]:
    """Возвращает последние запланированные рассылки (любого статуса)."""

    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        rows = conn.execute(
            """
            SELECT id, mailing_type, post_link, from_chat, message_id,
                   admin_chat_id, scheduled_at, created_at, status
            FROM scheduled_mailings
            ORDER BY scheduled_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


def save_channel_post(chat_id: str, message_id: int, text_preview: str | None) -> None:
    now = datetime.utcnow().isoformat()
    with closing(_get_conn()) as conn, conn:  # type: ignore[call-arg]
        conn.execute(
            """
            INSERT INTO channel_posts (chat_id, message_id, created_at, text_preview)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, message_id, now, text_preview),
        )


def get_recent_channel_posts(limit: int = 10) -> Iterable[sqlite3.Row]:
    with closing(_get_conn()) as conn:  # type: ignore[call-arg]
        rows = conn.execute(
            """
            SELECT id, chat_id, message_id, created_at, text_preview
            FROM channel_posts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows
