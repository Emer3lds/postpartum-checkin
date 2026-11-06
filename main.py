"""Tend: a postpartum check-in demo. Run with: python -m uvicorn main:app --port 8000"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from tend import pipeline, store  # noqa: E402
from tend.signs import FOLLOW_UPS, SIGN_NAMES, SIGNS, highest_level  # noqa: E402

ROOT = Path(__file__).resolve().parent
COOKIE = "tend_session"
DEMO_FILE = ROOT / "demo_seed.json"

app = FastAPI(title="Tend")


class Credentials(BaseModel):
    username: str
    password: str


class CheckIn(BaseModel):
    text: str


class Profile(BaseModel):
    birth_date: str


class FollowUp(BaseModel):
    sign_id: str
    answer: str


def current_user(tend_session: str | None = Cookie(default=None)) -> dict:
    with store.db() as conn:
        user = store.user_for_token(conn, tend_session)
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)


def _view(entry: dict, by_id: dict, birth_date: str | None) -> dict:
    """Add the sign names, dates, questions, and fixed script the page needs."""
    flags = [
        {**f, "name": SIGN_NAMES[f["sign_id"]], "question": FOLLOW_UPS.get(f["sign_id"])}
        for f in entry["flags"]
    ]
    patterns = [
        {
            **p,
            "evidence": [
                {**e, "date": by_id[e["entry_id"]]["created_at"][:10]}
                for e in p["evidence"]
                if e["entry_id"] in by_id
            ],
        }
        for p in entry["patterns"]
    ]
    return {
        "id": entry["id"],
        "created_at": entry["created_at"],
        "text": entry["text"],
        "ai_status": entry["ai_status"],
        "flags": flags,
        "patterns": patterns,
        "level": highest_level(entry["flags"]),
        "script": pipeline.build_script(entry["flags"], birth_date),
    }


def _state(conn, user_id: int) -> dict:
    user = conn.execute("SELECT username, birth_date FROM users WHERE id = ?", (user_id,)).fetchone()
    entries = store.list_entries(conn, user_id)
    by_id = {e["id"]: e for e in entries}
    views = [_view(e, by_id, user["birth_date"]) for e in entries]
    return {
        "username": user["username"],
        "birth_date": user["birth_date"],
        "weeks_since_birth": pipeline.weeks_since(user["birth_date"]) if user["birth_date"] else None,
        "entries": views,
        "patterns": views[-1]["patterns"] if views else [],
        "signs": SIGNS,
    }


@app.post("/api/signup")
def signup(body: Credentials, response: Response):
    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Please choose a username with at least 3 characters.")
    if len(body.password) < 8:
        raise HTTPException(400, "Please choose a password with at least 8 characters.")
    with store.db() as conn:
        user_id = store.create_user(conn, username, body.password)
        if user_id is None:
            raise HTTPException(409, "That username is taken.")
        _set_cookie(response, store.create_session(conn, user_id))
        return _state(conn, user_id)


@app.post("/api/login")
def login(body: Credentials, response: Response):
    with store.db() as conn:
        user_id = store.verify_user(conn, body.username.strip(), body.password)
        if user_id is None:
            raise HTTPException(401, "That username and password don't match.")
        _set_cookie(response, store.create_session(conn, user_id))
        return _state(conn, user_id)


@app.post("/api/demo/login")
def demo_login(response: Response):
    """Open the sample account, reset to its prepared made-up check-ins."""
    if not DEMO_FILE.exists():
        raise HTTPException(404, "The demo account isn't ready yet.")
    seed = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    now = datetime.now()
    items = [
        {
            **item,
            "created_at": (now - timedelta(days=item["days_ago"]))
            .replace(hour=item["hour"], minute=12, second=0, microsecond=0)
            .isoformat(),
        }
        for item in seed["entries"]
    ]
    birth_date = (now - timedelta(days=seed["birth_days_ago"])).date().isoformat()
    with store.db() as conn:
        user_id = store.get_or_create_demo_user(conn)
        store.replace_demo_entries(conn, user_id, birth_date, items)
        _set_cookie(response, store.create_session(conn, user_id))
        return _state(conn, user_id)


@app.post("/api/logout")
def logout(response: Response, tend_session: str | None = Cookie(default=None)):
    if tend_session:
        with store.db() as conn:
            store.end_session(conn, tend_session)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/state")
def get_state(user: dict = Depends(current_user)):
    with store.db() as conn:
        return _state(conn, user["id"])


@app.post("/api/profile")
def set_profile(profile: Profile, user: dict = Depends(current_user)):
    try:
        parsed = date.fromisoformat(profile.birth_date)
    except ValueError:
        raise HTTPException(400, "Please enter a valid date.")
    if parsed > date.today():
        raise HTTPException(400, "The birth date can't be in the future.")
    with store.db() as conn:
        store.set_birth_date(conn, user["id"], profile.birth_date)
        return _state(conn, user["id"])


@app.post("/api/checkin")
def check_in(body: CheckIn, user: dict = Depends(current_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Please write or say something first.")
    with store.db() as conn:
        history = store.list_entries(conn, user["id"])
        current = store.add_entry(conn, user["id"], datetime.now().isoformat(timespec="seconds"), text)
        result = pipeline.analyze(current, history, user["birth_date"])
        store.save_result(conn, user["id"], current["id"], result)
        state = _state(conn, user["id"])
    return {"entry": state["entries"][-1], "state": state}


@app.post("/api/entries/{entry_id}/follow-up")
def follow_up(entry_id: int, body: FollowUp, user: dict = Depends(current_user)):
    if body.answer not in {"yes", "no", "unsure"}:
        raise HTTPException(400, "Unknown answer.")
    with store.db() as conn:
        entry = store.get_entry(conn, user["id"], entry_id)
        if entry is None:
            raise HTTPException(404, "Entry not found.")
        flags = pipeline.apply_follow_up(entry["flags"], body.sign_id, body.answer)
        store.update_flags(conn, user["id"], entry_id, flags)
        state = _state(conn, user["id"])
    updated = next(e for e in state["entries"] if e["id"] == entry_id)
    return {"entry": updated, "state": state}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
