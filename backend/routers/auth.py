import os
from typing import Optional
from datetime import timedelta
import httpx
import bcrypt
import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id, TREVISO, EMERGENT_SESSION_URL
from deps import get_current_user
from models import SessionIn, ProfileUpdate, RegisterIn, LoginIn, AppleIn
from trust import recalc_provider_trust, recalc_client_trust

router = APIRouter()

APPLE_AUDIENCES = [a.strip() for a in os.environ.get("APPLE_AUDIENCES", "").split(",") if a.strip()]
_apple_jwks = PyJWKClient("https://appleid.apple.com/auth/keys")
DEMO_EMAIL = "demo@jobby.app"


# ---- shared helpers ----
def default_user_doc(user_id, email, name, picture="", onboarding_completed=False):
    return {
        "user_id": user_id, "email": email, "name": name, "picture": picture,
        "role": "client", "roles": ["client"], "language": "it", "bio": "", "business_name": "",
        "hourly_rate": 13.0, "radius_km": 10.0, "services": [], "online": False, "service_mode": "both",
        "rating": 0.0, "reviews_count": 0, "verified": False, "verification_status": "unverified",
        "wallet_balance": 0.0, "bonus_credit": 0.0, "bonus_granted": False, "email_verified": True,
        "payment_method": None, "bank_account": None,
        "trust_score": 0.0, "trust_subscores": {}, "client_trust_score": 0.0, "client_trust_subscores": {},
        "is_admin": False, "lat": TREVISO["lat"], "lng": TREVISO["lng"], "created_at": now_utc().isoformat(),
        "approval_status": "approved", "provider_approved": False, "onboarding_completed": onboarding_completed,
    }


async def issue_session(user_id):
    token = new_id("sess")
    await db.user_sessions.insert_one({
        "session_token": token, "user_id": user_id,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7)})
    await db.users.update_one({"user_id": user_id}, {"$set": {"last_login": now_utc().isoformat()}})
    return token


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], h.encode())
    except Exception:
        return False


async def _public_user(user_id):
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


# ---- Email / password ----
@router.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="invalid_email")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="weak_password")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="email_exists")
    user_id = new_id("user")
    doc = default_user_doc(user_id, email, body.name.strip() or email.split("@")[0], onboarding_completed=False)
    doc["password_hash"] = hash_pw(body.password)
    doc["auth_provider"] = "password"
    await db.users.insert_one(doc)
    token = await issue_session(user_id)
    return {"user": await _public_user(user_id), "session_token": token}


@router.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    u = await db.users.find_one({"email": email})
    if not u or not u.get("password_hash") or not verify_pw(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    token = await issue_session(u["user_id"])
    return {"user": await _public_user(u["user_id"]), "session_token": token}


# ---- Sign in with Apple ----
@router.post("/auth/apple")
async def apple_login(body: AppleIn):
    try:
        signing_key = _apple_jwks.get_signing_key_from_jwt(body.identity_token)
        data = jwt.decode(body.identity_token, signing_key.key, algorithms=["RS256"],
                          audience=APPLE_AUDIENCES, issuer="https://appleid.apple.com")
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_apple_token")
    apple_sub = data["sub"]
    u = await db.users.find_one({"apple_sub": apple_sub})
    if u:
        user_id = u["user_id"]
    else:
        user_id = new_id("user")
        email = (body.email or data.get("email") or f"{apple_sub}@privaterelay.apple").strip().lower()
        name = body.name or email.split("@")[0]
        doc = default_user_doc(user_id, email, name, onboarding_completed=False)
        doc["apple_sub"] = apple_sub
        doc["auth_provider"] = "apple"
        await db.users.insert_one(doc)
    token = await issue_session(user_id)
    return {"user": await _public_user(user_id), "session_token": token}


# ---- Demo (read-only) ----
@router.post("/auth/demo")
async def demo_login():
    u = await db.users.find_one({"email": DEMO_EMAIL})
    if not u:
        user_id = new_id("user")
        doc = default_user_doc(user_id, DEMO_EMAIL, "Demo User", onboarding_completed=True)
        doc["is_demo"] = True
        doc["auth_provider"] = "demo"
        doc["wallet_balance"] = 0.0
        await db.users.insert_one(doc)
    else:
        user_id = u["user_id"]
        if not u.get("is_demo"):
            await db.users.update_one({"user_id": user_id}, {"$set": {"is_demo": True}})
    token = await issue_session(user_id)
    return {"user": await _public_user(user_id), "session_token": token}


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
        # #2 — l'Accesso (signin) non deve creare l'account: serve prima la registrazione.
        if (body.mode or "signup") == "signin":
            raise HTTPException(status_code=404, detail="not_registered")
        user_id = new_id("user")
        doc = default_user_doc(user_id, email, data.get("name", email.split("@")[0]),
                               picture=data.get("picture", ""), onboarding_completed=False)
        doc["auth_provider"] = "google"
        await db.users.insert_one(doc)
    session_token = data["session_token"]
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user_id,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7)})
    await db.users.update_one({"user_id": user_id}, {"$set": {"last_login": now_utc().isoformat()}})
    return {"user": await _public_user(user_id), "session_token": session_token}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    from routers.provider_onboarding import provider_state
    user["provider_state"] = provider_state(user)
    return user


@router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        await db.user_sessions.delete_one({"session_token": authorization.split(" ", 1)[1]})
    return {"ok": True}


@router.put("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in body.dict().items() if v is not None}
    if "role" in update:
        new_role = update["role"]
        if new_role == "client":
            update["approval_status"] = "approved"
        else:
            # Providers/Businesses require admin approval (unless previously approved).
            update["approval_status"] = "approved" if user.get("provider_approved") else "pending"
    if update:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    if "role" in update:
        await recalc_provider_trust(user["user_id"])
    return await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})


class QrPrefIn(BaseModel):
    enabled: bool


@router.post("/profile/qr-confirm")
async def set_qr_confirm(body: QrPrefIn, user=Depends(get_current_user)):
    """Client preference: require a QR/6-digit confirmation from the earner before the
    escrow payment is released (extra 'consegna verificata' guarantee)."""
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"qr_confirm_enabled": bool(body.enabled)}})
    return {"qr_confirm_enabled": bool(body.enabled)}



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
