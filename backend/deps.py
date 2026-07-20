from typing import Optional
from datetime import timezone
from fastapi import Header, HTTPException, Request
from core import db, ADMIN_TOKEN, now_utc


async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    exp = session["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc():
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(request: Request, x_admin_token: Optional[str] = Header(None)):
    # 1) Web backoffice session cookie
    sid = request.cookies.get("jobby_admin")
    if sid:
        sess = await db.admin_sessions.find_one({"sid": sid})
        if sess:
            exp = sess["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp >= now_utc():
                return True
    # 2) Legacy static token (automated tests / curl)
    if x_admin_token and x_admin_token == ADMIN_TOKEN:
        return True
    raise HTTPException(status_code=403, detail="Admin auth required")
