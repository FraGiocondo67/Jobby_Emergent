from typing import Optional
from datetime import timedelta
import httpx
from fastapi import APIRouter, Header, HTTPException, Depends

from core import db, now_utc, new_id, TREVISO, EMERGENT_SESSION_URL
from deps import get_current_user
from models import SessionIn, ProfileUpdate
from trust import recalc_provider_trust, recalc_client_trust

router = APIRouter()


@router.post("/auth/session")
async def create_session(body: SessionIn):
    async with httpx.AsyncClient() as http:
        r = await http.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_token})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session token")
    data = r.json()
    email = data["email"]
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
    else:
        user_id = new_id("user")
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": data.get("name", email.split("@")[0]),
            "picture": data.get("picture", ""), "role": "client", "language": "it", "bio": "",
            "business_name": "", "hourly_rate": 13.0, "radius_km": 10.0, "services": [], "online": False,
            "service_mode": "both",
            "rating": 0.0, "reviews_count": 0, "verified": False, "verification_status": "unverified",
            "wallet_balance": 92.29, "payment_method": None, "bank_account": None,
            "trust_score": 0.0, "trust_subscores": {}, "client_trust_score": 0.0, "client_trust_subscores": {},
            "is_admin": False, "lat": TREVISO["lat"], "lng": TREVISO["lng"], "created_at": now_utc().isoformat(),
        })
    session_token = data["session_token"]
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user_id,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7)})
    return {"user": await db.users.find_one({"user_id": user_id}, {"_id": 0}), "session_token": session_token}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        await db.user_sessions.delete_one({"session_token": authorization.split(" ", 1)[1]})
    return {"ok": True}


@router.put("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in body.dict().items() if v is not None}
    if update:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    if "role" in update:
        await recalc_provider_trust(user["user_id"])
    return await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})


@router.post("/verification/start")
async def verification_start(user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"verification_status": "pending", "kyc_provider": "sumsub_mock"}})
    return {"status": "pending", "provider": "sumsub_mock", "mock": True}


@router.post("/verification/complete")
async def verification_complete(user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"verification_status": "verified", "verified": True}})
    await recalc_provider_trust(user["user_id"])
    await recalc_client_trust(user["user_id"])
    return {"status": "verified", "mock": True}
