"""Local SQLite storage with simple accounts. Every entry query is limited to one user."""

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tend.db"
DEMO_USERNAME = "demo-mother"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    birth_date TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    flags TEXT NOT NULL DEFAULT '[]',
    patterns TEXT NOT NULL DEFAULT '[]',
    ai_status TEXT NOT NULL DEFAULT 'pending',
    notices TEXT NOT NULL DEFAULT '[]'
);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(entries)")}
    if "notices" not in columns:  # databases made before notices existed
        conn.execute("ALTER TABLE entries ADD COLUMN notices TEXT NOT NULL DEFAULT '[]'")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(conn, username: str, password: str) -> int | None:
    """Return the new user's id, or None if the username is taken."""
    salt = secrets.token_hex(16)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_salt, password_hash) VALUES (?, ?, ?)",
            (username, salt, _hash_password(password, salt)),
        )
    except sqlite3.IntegrityError:
        return None
    conn.commit()
    return cur.lastrowid


def verify_user(conn, username: str, password: str) -> int | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        return None
    candidate = _hash_password(password, row["password_salt"])
    return row["id"] if secrets.compare_digest(candidate, row["password_hash"]) else None


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)", (_hash_token(token), user_id)
    )
    conn.commit()
    return token


def user_for_token(conn, token: str | None) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        "SELECT u.id, u.username, u.birth_date FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ?",
        (_hash_token(token),),
    ).fetchone()
    return dict(row) if row else None


def end_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
    conn.commit()


def set_birth_date(conn, user_id: int, value: str) -> None:
    conn.execute("UPDATE users SET birth_date = ? WHERE id = ?", (value, user_id))
    conn.commit()


def _to_entry(row: sqlite3.Row) -> dict:
    entry = dict(row)
    entry["flags"] = json.loads(entry["flags"])
    entry["patterns"] = json.loads(entry["patterns"])
    entry["notices"] = json.loads(entry["notices"])
    return entry


def add_entry(conn, user_id: int, created_at: str, text: str) -> dict:
    """Save her words first, so nothing she wrote is lost if a later step fails."""
    cur = conn.execute(
        "INSERT INTO entries (user_id, created_at, text) VALUES (?, ?, ?)",
        (user_id, created_at, text),
    )
    conn.commit()
    return {"id": cur.lastrowid, "user_id": user_id, "created_at": created_at, "text": text,
            "flags": [], "patterns": []}


def save_result(conn, user_id: int, entry_id: int, result: dict) -> None:
    conn.execute(
        "UPDATE entries SET flags = ?, patterns = ?, notices = ?, ai_status = ? WHERE id = ? AND user_id = ?",
        (
            json.dumps(result["flags"], ensure_ascii=False),
            json.dumps(result["patterns"], ensure_ascii=False),
            json.dumps(result.get("notices", [])),
            result["ai_status"],
            entry_id,
            user_id,
        ),
    )
    conn.commit()


def get_entry(conn, user_id: int, entry_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM entries WHERE id = ? AND user_id = ?", (entry_id, user_id)
    ).fetchone()
    return _to_entry(row) if row else None


def update_flags(conn, user_id: int, entry_id: int, flags: list[dict]) -> None:
    conn.execute(
        "UPDATE entries SET flags = ? WHERE id = ? AND user_id = ?",
        (json.dumps(flags, ensure_ascii=False), entry_id, user_id),
    )
    conn.commit()


def get_or_create_demo_user(conn) -> int:
    """The sample account holds made-up entries only and has an unusable random password."""
    row = conn.execute("SELECT id FROM users WHERE username = ?", (DEMO_USERNAME,)).fetchone()
    return row["id"] if row else create_user(conn, DEMO_USERNAME, secrets.token_urlsafe(32))


def replace_demo_entries(conn, user_id: int, birth_date: str, items: list[dict]) -> None:
    """Reset only the sample account, mapping saved ids to the new entry ids."""
    conn.execute("DELETE FROM entries WHERE user_id = ?", (user_id,))
    set_birth_date(conn, user_id, birth_date)
    id_map: dict[int, int] = {}
    for item in items:
        id_map[item["id"]] = add_entry(conn, user_id, item["created_at"], item["text"])["id"]
    for item in items:
        patterns = [
            {**p, "evidence": [{**e, "entry_id": id_map[e["entry_id"]]} for e in p["evidence"]]}
            for p in item["patterns"]
        ]
        save_result(
            conn, user_id, id_map[item["id"]],
            {"flags": item["flags"], "patterns": patterns, "notices": item.get("notices", []), "ai_status": item["ai_status"]},
        )


def list_entries(conn, user_id: int) -> list[dict]:
    """This user's entries, oldest first."""
    rows = conn.execute(
        "SELECT * FROM entries WHERE user_id = ? ORDER BY created_at, id", (user_id,)
    ).fetchall()
    return [_to_entry(r) for r in rows]
