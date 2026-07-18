from fastapi import FastAPI, APIRouter, Header, HTTPException, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import math
import uuid
import random
import asyncio
import logging
import httpx
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'change-me')

app = FastAPI()
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TREVISO = {"lat": 45.6669, "lng": 12.2433}
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


def now_utc():
    return datetime.now(timezone.utc)


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def L(it, en):
    return {"it": it, "en": en}


def haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


# =============================== Catalog =================================
def q_duration(default=2, mx=8):
    return {"id": "duration", "label": L("Durata (ore)", "Duration (hours)"), "type": "number", "min": 1, "max": mx, "default": default}


def q_note():
    return {"id": "note", "label": L("Descrivi cosa ti serve", "Describe what you need"), "type": "text",
            "placeholder": L("Dettagli", "Details")}


STANDARD_SERVICES = [
    {"cat_id": "sarta", "emoji": "🪡", "label": L("Sarta", "Seamstress"), "questions": [q_note(), q_duration(1)]},
    {"cat_id": "pulizie", "emoji": "🧹", "label": L("Pulizie", "Housekeeping"), "questions": [
        {"id": "homeType", "label": L("Tipo di abitazione", "Home type"), "type": "select",
         "options": [{"id": "apartment", "label": L("Appartamento", "Apartment")}, {"id": "house", "label": L("Casa", "House")}]},
        {"id": "rooms", "label": L("Numero di stanze", "Rooms"), "type": "number", "min": 1, "max": 12, "default": 3},
        q_duration(2)]},
    {"cat_id": "babysitting", "emoji": "👶", "label": L("Babysitting", "Babysitting"), "questions": [
        {"id": "children", "label": L("Numero di bambini", "Children"), "type": "number", "min": 1, "max": 5, "default": 1}, q_duration(3, 10)]},
    {"cat_id": "petsitting", "emoji": "🐾", "label": L("Pet Sitting", "Pet Sitting"), "questions": [
        {"id": "petType", "label": L("Tipo di animale", "Pet type"), "type": "select",
         "options": [{"id": "dog", "label": L("Cane", "Dog")}, {"id": "cat", "label": L("Gatto", "Cat")}, {"id": "other", "label": L("Altro", "Other")}]}, q_duration(2, 10)]},
    {"cat_id": "driver", "emoji": "🚗", "label": L("Driver", "Driver"), "questions": [q_note(), q_duration(2)]},
    {"cat_id": "tuttofare", "emoji": "🔧", "label": L("Tuttofare", "Handyman"), "questions": [q_note(), q_duration(2)]},
    {"cat_id": "hospitality", "emoji": "🍽️", "label": L("Hospitality", "Hospitality support"), "questions": [
        {"id": "guests", "label": L("Numero di ospiti", "Guests"), "type": "number", "min": 1, "max": 50, "default": 4}, q_duration(3, 10)]},
    {"cat_id": "assistenza", "emoji": "❤️", "label": L("Assistenza", "Home assistance"), "questions": [q_note(), q_duration(3, 10)]},
    {"cat_id": "tecnico", "emoji": "💻", "label": L("Tecnico", "Technical services"), "questions": [q_note(), q_duration(1, 6)]},
]

PROXIMITY_BUSINESS = [
    ("lavanderia", "👕", "Lavanderia", "Laundry"), ("calzolaio", "👟", "Calzolaio", "Cobbler"),
    ("noleggio_auto", "🚙", "Noleggio Auto", "Car Rental"), ("barbiere", "✂️", "Barbiere / Parrucchiere", "Barber / Hairdresser"),
    ("idraulico", "🚿", "Idraulico", "Plumber"), ("elettricista", "⚡", "Elettricista", "Electrician"),
    ("estetista", "💅", "Estetista / Centro spa", "Beauty / Spa"), ("veterinario", "🐾", "Veterinario", "Veterinarian"),
    ("ottico", "👓", "Ottico", "Optician"), ("food_delivery", "🍕", "Food Delivery", "Food Delivery"),
    ("alimentari", "🛒", "Alimentari", "Grocery"), ("fioreria", "💐", "Fioreria", "Florist"),
    ("sartoria", "🧵", "Sartoria", "Tailor"), ("farmacia", "💊", "Farmacia", "Pharmacy"),
    ("falegname", "🪵", "Falegname", "Carpenter"), ("officina", "🔩", "Riparazione / Officina", "Repair shop"),
]

PAYMENT_SERVICES = [
    {"cat_id": "estero", "emoji": "🌍", "label": L("Manda soldi all'estero", "Send money abroad"), "questions": [
        {"id": "country", "label": L("Paese di destinazione", "Destination country"), "type": "text", "placeholder": L("Es. Marocco", "e.g. Morocco")},
        {"id": "recipient", "label": L("Destinatario", "Recipient"), "type": "text", "placeholder": L("Nome", "Name")},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 5, "max": 2000, "default": 50}]},
    {"cat_id": "ricarica", "emoji": "📱", "label": L("Ricarica Telefonica", "Mobile top-up"), "questions": [
        {"id": "phone", "label": L("Numero di telefono", "Phone number"), "type": "text", "placeholder": "+39 ..."},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 5, "max": 100, "default": 10}]},
    {"cat_id": "bollette", "emoji": "🧾", "label": L("Paga Bollette", "Pay bills"), "questions": [
        {"id": "biller", "label": L("Ente/Bolletta", "Biller"), "type": "text", "placeholder": L("Es. Enel", "e.g. Enel")},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 5, "max": 2000, "default": 60}]},
    {"cat_id": "locale", "emoji": "🔄", "label": L("Manda e Richiedi Soldi localmente", "Send & request money locally"), "questions": [
        {"id": "recipient", "label": L("Destinatario", "Recipient"), "type": "text", "placeholder": L("Nome o telefono", "Name or phone")},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 1, "max": 1000, "default": 25}]},
]

MANIFESTO = [
    L("Il lavoro si adatta alla vita, non la vita al lavoro.", "Work should adapt to life, not life to work."),
    L("Ogni persona ha tempo, competenze e valore.", "Every person has time, skills and value."),
    L("La tecnologia deve dare più libertà, non meno.", "Technology should give people more freedom, not less."),
    L("La reputazione conta più della gerarchia.", "Reputation matters more than hierarchy."),
    L("Il reddito non deve dipendere da un solo datore di lavoro.", "Income should not depend on a single employer."),
    L("Il tempo disponibile può diventare opportunità.", "Available time can become opportunity."),
]


# =============================== Models =================================
class SessionIn(BaseModel):
    session_token: str


class ProfileUpdate(BaseModel):
    role: Optional[str] = None            # client | provider | business
    language: Optional[str] = None
    bio: Optional[str] = None
    business_name: Optional[str] = None
    hourly_rate: Optional[float] = None
    radius_km: Optional[float] = None
    services: Optional[List[str]] = None  # candidate activities
    online: Optional[bool] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class MissionIn(BaseModel):
    category: str
    service_type: str
    config: Dict[str, Any] = {}
    address: str
    lat: float
    lng: float
    date: str
    time: str
    duration_hours: float
    recurrence: str = "once"


class AcceptIn(BaseModel):
    price: Optional[float] = None


class SelectIn(BaseModel):
    provider_id: str


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


class ClientRatingIn(BaseModel):
    rating: int
    brief_accuracy: int = 5
    tip: float = 0.0


class WalletIn(BaseModel):
    amount: float


class PaymentIn(BaseModel):
    service_id: str
    label: str
    amount: float
    answers: Dict[str, Any] = {}


class PaymentMethodIn(BaseModel):
    card_holder: str
    card_last4: str
    card_brand: str = "visa"
    expiry: str


class BankAccountIn(BaseModel):
    account_holder: str
    iban: str


class DisputeIn(BaseModel):
    reason: str


class MessageIn(BaseModel):
    text: str


# =============================== Auth ===================================
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
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin token required")
    return True


# =========================== Trust Score engine ==========================
PROVIDER_WEIGHTS = {"kyc": .20, "punctuality": .20, "quality": .20, "communication": .10,
                    "cancellation": .10, "completed": .10, "dispute": .05, "tenure": .05}
CLIENT_WEIGHTS = {"identity": .20, "education": .20, "brief": .20, "payment": .15,
                  "cancellation": .15, "tips": .05, "reviews": .05}


def months_since(iso):
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (now_utc() - d).days / 30.0
    except Exception:
        return 0


async def recalc_provider_trust(user_id: str):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return
    bookings = await db.bookings.find({"provider_id": user_id}, {"_id": 0}).to_list(1000)
    completed = [b for b in bookings if b.get("status") == "completed"]
    reviews = await db.reviews.find({"provider_id": user_id}, {"_id": 0}).to_list(1000)
    disputes = await db.disputes.find({"provider_id": user_id, "against": "provider"}, {"_id": 0}).to_list(1000)
    on_time = [b for b in bookings if b.get("check_in_on_time")]

    sub = {}
    sub["kyc"] = 100 if user.get("verification_status") == "verified" else 0
    sub["punctuality"] = round(len(on_time) / len(bookings) * 100) if bookings else 90
    sub["quality"] = round(sum(r["rating"] for r in reviews) / len(reviews) / 5 * 100) if reviews else 80
    sub["communication"] = 85
    accepted = max(len(bookings), 1)
    cancelled = len([b for b in bookings if b.get("status") == "cancelled"])
    sub["cancellation"] = round(100 - cancelled / accepted * 100)
    sub["completed"] = round(min(len(completed) / 10, 1) * 100)
    sub["dispute"] = round(max(0, 100 - len(disputes) * 20))
    sub["tenure"] = round(min(months_since(user.get("created_at", now_utc().isoformat())) / 12, 1) * 100)

    score = round(sum(sub[k] * PROVIDER_WEIGHTS[k] for k in PROVIDER_WEIGHTS), 1)
    await db.users.update_one({"user_id": user_id}, {"$set": {"trust_score": score, "trust_subscores": sub}})
    return score


async def recalc_client_trust(user_id: str):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return
    events = await db.client_trust_events.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    ratings = [e["meta"].get("rating") for e in events if e.get("type") == "client_rated" and e.get("meta")]
    briefs = [e["meta"].get("brief_accuracy") for e in events if e.get("type") == "client_rated" and e.get("meta")]
    tips = [e for e in events if e.get("type") == "client_rated" and e.get("meta", {}).get("tip", 0) > 0]
    bookings = await db.bookings.find({"customer_id": user_id}, {"_id": 0}).to_list(1000)
    missions = await db.missions.find({"customer_id": user_id}, {"_id": 0}).to_list(1000)
    disputes = await db.disputes.find({"customer_id": user_id, "against": "client"}, {"_id": 0}).to_list(1000)

    sub = {}
    sub["identity"] = 100 if user.get("verification_status") == "verified" else 60
    sub["education"] = round(sum(ratings) / len(ratings) / 5 * 100) if ratings else 80
    sub["brief"] = round(sum(briefs) / len(briefs) / 5 * 100) if briefs else 80
    sub["payment"] = round(max(0, 100 - len(disputes) * 25))
    total_req = max(len(missions), 1)
    cancelled = len([m for m in missions if m.get("status") == "cancelled"])
    sub["cancellation"] = round(100 - cancelled / total_req * 100)
    sub["tips"] = round(min(len(tips) * 20, 100))
    sub["reviews"] = round(sum(ratings) / len(ratings) / 5 * 100) if ratings else 80

    score = round(sum(sub[k] * CLIENT_WEIGHTS[k] for k in CLIENT_WEIGHTS), 1)
    await db.users.update_one({"user_id": user_id}, {"$set": {"client_trust_score": score, "client_trust_subscores": sub}})
    return score


async def log_trust_event(collection, user_id, event_type, score_after, meta=None):
    await db[collection].insert_one({
        "event_id": new_id("te"), "user_id": user_id, "type": event_type,
        "score_after": score_after, "meta": meta or {}, "created_at": now_utc().isoformat(),
    })


# =============================== Auth routes =============================
@api_router.post("/auth/session")
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


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        await db.user_sessions.delete_one({"session_token": authorization.split(" ", 1)[1]})
    return {"ok": True}


@api_router.put("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in body.dict().items() if v is not None}
    if update:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    if "role" in update:
        await recalc_provider_trust(user["user_id"])
    return await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})


# ---- Simulated KYC verification (Sumsub-ready, MOCK) ----
@api_router.post("/verification/start")
async def verification_start(user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"verification_status": "pending", "kyc_provider": "sumsub_mock"}})
    return {"status": "pending", "provider": "sumsub_mock", "mock": True}


@api_router.post("/verification/complete")
async def verification_complete(user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"verification_status": "verified", "verified": True}})
    await recalc_provider_trust(user["user_id"])
    await recalc_client_trust(user["user_id"])
    return {"status": "verified", "mock": True}


# =============================== Categories =============================
@api_router.get("/categories")
async def get_categories(user=Depends(get_current_user)):
    online = await db.users.count_documents({"role": {"$in": ["provider", "business"]}, "online": True})
    cats = await db.categories.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(200)
    grouped = {"standard": [], "proximity": [], "payment": []}
    for c in cats:
        grouped.get(c["kind"], grouped["standard"]).append(c)
    return {"standard": grouped["standard"], "proximity": grouped["proximity"], "payment": grouped["payment"],
            "providers_online": online, "manifesto": MANIFESTO}


@api_router.get("/categories/{cat_id}")
async def get_category(cat_id: str, user=Depends(get_current_user)):
    c = await db.categories.find_one({"cat_id": cat_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")
    return c


# ---- Admin (backend only, X-Admin-Token) ----
@api_router.get("/admin/categories")
async def admin_list_categories(_=Depends(require_admin)):
    return await db.categories.find({}, {"_id": 0}).sort("order", 1).to_list(300)


@api_router.post("/admin/categories/{cat_id}/toggle")
async def admin_toggle_category(cat_id: str, _=Depends(require_admin)):
    c = await db.categories.find_one({"cat_id": cat_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    new_active = not c.get("active", True)
    await db.categories.update_one({"cat_id": cat_id}, {"$set": {"active": new_active}})
    return {"cat_id": cat_id, "active": new_active}


@api_router.post("/admin/trust/recalc")
async def admin_trust_recalc(_=Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "role": 1}).to_list(1000)
    for u in users:
        await recalc_provider_trust(u["user_id"])
        await recalc_client_trust(u["user_id"])
    return {"recalculated": len(users)}


# =============================== Providers ==============================
@api_router.get("/providers/nearby")
async def providers_nearby(lat: float, lng: float, category: Optional[str] = None, user=Depends(get_current_user)):
    providers = await db.users.find({"role": {"$in": ["provider", "business"]}, "online": True}, {"_id": 0}).to_list(300)
    result = []
    for p in providers:
        if category and not p.get("is_bot") and category not in p.get("services", []):
            continue
        dist = haversine(lat, lng, p.get("lat", TREVISO["lat"]), p.get("lng", TREVISO["lng"]))
        if dist > p.get("radius_km", 10):
            continue
        result.append({
            "user_id": p["user_id"], "name": p["name"], "picture": p.get("picture", ""),
            "rating": p.get("rating", 0), "reviews_count": p.get("reviews_count", 0),
            "hourly_rate": p.get("hourly_rate", 13), "verified": p.get("verified", False),
            "trust_score": p.get("trust_score", 0), "bio": p.get("bio", ""), "distance_km": dist,
            "services": p.get("services", []), "lat": p.get("lat"), "lng": p.get("lng"),
        })
    result.sort(key=lambda x: x["distance_km"])
    return result


# =============================== Missions ===============================
async def simulate_accept(mission_id, provider_id, delay, price):
    await asyncio.sleep(delay)
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["status"] not in ("pending", "matched"):
        return
    if any(a["provider_id"] == provider_id for a in m.get("accepted", [])):
        return
    p = await db.users.find_one({"user_id": provider_id}, {"_id": 0})
    if not p:
        return
    accept = {"provider_id": provider_id, "name": p["name"], "picture": p.get("picture", ""),
              "rating": p.get("rating", 0), "reviews_count": p.get("reviews_count", 0),
              "trust_score": p.get("trust_score", 0),
              "distance_km": haversine(m["lat"], m["lng"], p.get("lat"), p.get("lng")),
              "price": price, "eta_min": random.randint(10, 40), "verified": p.get("verified", True),
              "accepted_at": now_utc().isoformat()}
    await db.missions.update_one({"mission_id": mission_id}, {"$push": {"accepted": accept}, "$set": {"status": "matched"}})


@api_router.post("/missions")
async def create_mission(body: MissionIn, user=Depends(get_current_user)):
    mission_id = new_id("msn")
    providers = await db.users.find({"role": {"$in": ["provider", "business"]}, "online": True}, {"_id": 0}).to_list(300)
    invited = []
    for p in providers:
        if not p.get("is_bot") and body.category not in p.get("services", []):
            continue
        if haversine(body.lat, body.lng, p.get("lat", TREVISO["lat"]), p.get("lng", TREVISO["lng"])) <= p.get("radius_km", 10):
            invited.append(p)
    doc = {"mission_id": mission_id, "customer_id": user["user_id"], "customer_name": user["name"],
           "category": body.category, "service_type": body.service_type, "config": body.config,
           "address": body.address, "lat": body.lat, "lng": body.lng, "date": body.date, "time": body.time,
           "duration_hours": body.duration_hours, "recurrence": body.recurrence, "status": "pending",
           "invited_provider_ids": [p["user_id"] for p in invited], "accepted": [], "chosen_provider_id": None,
           "created_at": now_utc().isoformat()}
    await db.missions.insert_one(doc)
    for p in invited:
        if p.get("is_bot"):
            asyncio.create_task(simulate_accept(mission_id, p["user_id"], random.uniform(2, 9), round(p.get("hourly_rate", 13) * body.duration_hours, 2)))
    return await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})


@api_router.get("/missions")
async def my_missions(user=Depends(get_current_user)):
    return await db.missions.find({"customer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api_router.get("/missions/incoming/list")
async def incoming_missions(user=Depends(get_current_user)):
    ms = await db.missions.find({"invited_provider_ids": user["user_id"], "status": {"$in": ["pending", "matched"]}}, {"_id": 0}).sort("created_at", -1).to_list(50)
    for m in ms:
        m["already_accepted"] = any(a["provider_id"] == user["user_id"] for a in m.get("accepted", []))
    return ms


@api_router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    return m


@api_router.post("/missions/{mission_id}/select")
async def select_provider(mission_id: str, body: SelectIn, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    if m["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    accept = next((a for a in m.get("accepted", []) if a["provider_id"] == body.provider_id), None)
    if not accept:
        raise HTTPException(status_code=400, detail="Provider has not accepted")
    labor = round(accept["price"], 2)
    jobby_fee = round(labor * 0.15, 2)
    booking_id = new_id("bkg")
    await db.bookings.insert_one({
        "booking_id": booking_id, "mission_id": mission_id, "customer_id": user["user_id"],
        "customer_name": user["name"], "provider_id": body.provider_id, "provider_name": accept["name"],
        "provider_picture": accept.get("picture", ""), "category": m["category"], "service_type": m["service_type"],
        "address": m["address"], "date": m["date"], "time": m["time"], "duration_hours": m["duration_hours"],
        "labor_cost": labor, "jobby_fee": jobby_fee, "total": round(labor + jobby_fee, 2),
        "status": "confirmed", "check_in_on_time": False, "reviewed": False, "client_rated": False,
        "created_at": now_utc().isoformat()})
    await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "booked", "chosen_provider_id": body.provider_id}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


@api_router.post("/missions/{mission_id}/accept")
async def accept_mission(mission_id: str, body: AcceptIn, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["status"] not in ("pending", "matched"):
        raise HTTPException(status_code=400, detail="Mission not available")
    if any(a["provider_id"] == user["user_id"] for a in m.get("accepted", [])):
        return {"ok": True}
    price = body.price if body.price is not None else round(user.get("hourly_rate", 13) * m["duration_hours"], 2)
    accept = {"provider_id": user["user_id"], "name": user["name"], "picture": user.get("picture", ""),
              "rating": user.get("rating", 0), "reviews_count": user.get("reviews_count", 0),
              "trust_score": user.get("trust_score", 0),
              "distance_km": haversine(m["lat"], m["lng"], user.get("lat", TREVISO["lat"]), user.get("lng", TREVISO["lng"])),
              "price": price, "eta_min": random.randint(10, 40), "verified": user.get("verified", True),
              "accepted_at": now_utc().isoformat()}
    await db.missions.update_one({"mission_id": mission_id}, {"$push": {"accepted": accept}, "$set": {"status": "matched"}})
    return {"ok": True}


@api_router.post("/missions/{mission_id}/decline")
async def decline_mission(mission_id: str, user=Depends(get_current_user)):
    await db.missions.update_one({"mission_id": mission_id}, {"$pull": {"invited_provider_ids": user["user_id"]}})
    return {"ok": True}


# =============================== Bookings ===============================
@api_router.get("/bookings")
async def list_bookings(user=Depends(get_current_user)):
    key = "provider_id" if user["role"] in ("provider", "business") else "customer_id"
    return await db.bookings.find({key: user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api_router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    return b


@api_router.post("/bookings/{booking_id}/start")
async def start_booking(booking_id: str, user=Depends(get_current_user)):
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "in_progress", "check_in_on_time": True}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


@api_router.post("/bookings/{booking_id}/complete")
async def complete_booking(booking_id: str, user=Depends(get_current_user)):
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "completed"}})
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    await recalc_provider_trust(b["provider_id"])
    return b


@api_router.post("/bookings/{booking_id}/review")
async def review_booking(booking_id: str, body: ReviewIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b.get("reviewed"):
        return {"ok": True}
    await db.reviews.insert_one({"review_id": new_id("rev"), "booking_id": booking_id, "provider_id": b["provider_id"],
                                 "customer_id": user["user_id"], "customer_name": user["name"],
                                 "rating": body.rating, "comment": body.comment, "certified": True,
                                 "created_at": now_utc().isoformat()})
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"reviewed": True, "status": "completed"}})
    revs = await db.reviews.find({"provider_id": b["provider_id"]}, {"_id": 0}).to_list(1000)
    avg = round(sum(r["rating"] for r in revs) / len(revs), 1) if revs else 0
    await db.users.update_one({"user_id": b["provider_id"]}, {"$set": {"rating": avg, "reviews_count": len(revs)}})
    score = await recalc_provider_trust(b["provider_id"])
    await log_trust_event("trust_events", b["provider_id"], "review", score, {"rating": body.rating, "booking_id": booking_id})
    return {"ok": True}


@api_router.post("/bookings/{booking_id}/rate-client")
async def rate_client(booking_id: str, body: ClientRatingIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b.get("client_rated"):
        return {"ok": True}
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"client_rated": True}})
    score = await recalc_client_trust(b["customer_id"])
    await log_trust_event("client_trust_events", b["customer_id"], "client_rated", score,
                          {"rating": body.rating, "brief_accuracy": body.brief_accuracy, "tip": body.tip, "booking_id": booking_id})
    score = await recalc_client_trust(b["customer_id"])
    await db.users.update_one({"user_id": b["customer_id"]}, {"$set": {"client_trust_score": score}})
    return {"ok": True}


@api_router.post("/bookings/{booking_id}/dispute")
async def dispute_booking(booking_id: str, body: DisputeIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    against = "provider" if user["user_id"] == b["customer_id"] else "client"
    await db.disputes.insert_one({"dispute_id": new_id("dsp"), "booking_id": booking_id,
                                  "provider_id": b["provider_id"], "customer_id": b["customer_id"],
                                  "against": against, "reason": body.reason, "status": "open",
                                  "created_at": now_utc().isoformat()})
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "disputed"}})
    ps = await recalc_provider_trust(b["provider_id"])
    cs = await recalc_client_trust(b["customer_id"])
    await log_trust_event("trust_events", b["provider_id"], "dispute", ps, {"booking_id": booking_id})
    await log_trust_event("client_trust_events", b["customer_id"], "dispute", cs, {"booking_id": booking_id})
    return {"ok": True}


@api_router.get("/providers/{provider_id}/reviews")
async def provider_reviews(provider_id: str, user=Depends(get_current_user)):
    return await db.reviews.find({"provider_id": provider_id}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api_router.get("/earnings")
async def earnings(user=Depends(get_current_user)):
    bs = await db.bookings.find({"provider_id": user["user_id"]}, {"_id": 0}).to_list(500)
    return {"total_earned": round(sum(b["labor_cost"] for b in bs), 2), "jobs_count": len(bs),
            "completed_count": len([b for b in bs if b["status"] == "completed"]),
            "pending": round(sum(b["labor_cost"] for b in bs if b["status"] != "completed"), 2)}


# =============================== Trust API ==============================
@api_router.get("/trust")
async def get_trust(user=Depends(get_current_user)):
    events = await db.trust_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    cevents = await db.client_trust_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"provider_score": user.get("trust_score", 0), "provider_subscores": user.get("trust_subscores", {}),
            "client_score": user.get("client_trust_score", 0), "client_subscores": user.get("client_trust_subscores", {}),
            "provider_weights": PROVIDER_WEIGHTS, "client_weights": CLIENT_WEIGHTS,
            "events": events, "client_events": cevents}


# =============================== Wallet =================================
@api_router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    txs = await db.transactions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"balance": round(user.get("wallet_balance", 0), 2), "transactions": txs,
            "payment_method": user.get("payment_method"), "bank_account": user.get("bank_account"), "mock": True}


@api_router.post("/wallet/add")
async def add_funds(body: WalletIn, user=Depends(get_current_user)):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    new_balance = round(user.get("wallet_balance", 0) + body.amount, 2)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    await db.transactions.insert_one({"tx_id": new_id("tx"), "user_id": user["user_id"], "type": "topup",
                                      "label": "Wallet top-up (simulated)", "amount": body.amount, "created_at": now_utc().isoformat()})
    return {"balance": new_balance}


@api_router.put("/wallet/payment-method")
async def set_payment_method(body: PaymentMethodIn, user=Depends(get_current_user)):
    pm = body.dict()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"payment_method": pm}})
    return {"payment_method": pm}


@api_router.put("/wallet/bank-account")
async def set_bank_account(body: BankAccountIn, user=Depends(get_current_user)):
    ba = {"account_holder": body.account_holder, "iban": body.iban[-6:].rjust(len(body.iban), "*") if len(body.iban) > 6 else body.iban}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"bank_account": ba}})
    return {"bank_account": ba}


# =============================== Payments ===============================
@api_router.post("/payments")
async def make_payment(body: PaymentIn, user=Depends(get_current_user)):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    balance = user.get("wallet_balance", 0)
    if body.amount > balance:
        raise HTTPException(status_code=400, detail="insufficient_funds")
    new_balance = round(balance - body.amount, 2)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    tx = {"tx_id": new_id("tx"), "user_id": user["user_id"], "type": "payment", "service_id": body.service_id,
          "label": body.label, "amount": -body.amount, "answers": body.answers, "created_at": now_utc().isoformat()}
    await db.transactions.insert_one(tx)
    await db.service_requests.insert_one({"request_id": new_id("req"), "user_id": user["user_id"], "kind": "payment",
                                          "category_id": body.service_id, "label": body.label, "amount": body.amount,
                                          "answers": body.answers, "status": "completed", "created_at": now_utc().isoformat()})
    return {"balance": new_balance, "tx": {k: v for k, v in tx.items() if k != "_id"}}


@api_router.get("/requests")
async def list_requests(user=Depends(get_current_user)):
    reqs = await db.service_requests.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    missions = await db.missions.find({"customer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"payments": [r for r in reqs if r.get("kind") == "payment"], "missions": missions}


# =============================== Chat ===================================
async def ensure_conversation(user_id, other_id, other_name, other_picture=""):
    convo = await db.conversations.find_one({"user_id": user_id, "other_id": other_id}, {"_id": 0})
    if convo:
        return convo["conversation_id"]
    cid = new_id("conv")
    await db.conversations.insert_one({"conversation_id": cid, "user_id": user_id, "other_id": other_id,
                                       "other_name": other_name, "other_picture": other_picture,
                                       "last_message": "", "updated_at": now_utc().isoformat()})
    return cid


@api_router.get("/chat/conversations")
async def conversations(user=Depends(get_current_user)):
    key = "provider_id" if user["role"] in ("provider", "business") else "customer_id"
    bookings = await db.bookings.find({key: user["user_id"]}, {"_id": 0}).to_list(100)
    for b in bookings:
        if user["role"] in ("provider", "business"):
            await ensure_conversation(user["user_id"], b["customer_id"], b["customer_name"], "")
        else:
            await ensure_conversation(user["user_id"], b["provider_id"], b["provider_name"], b.get("provider_picture", ""))
    return await db.conversations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)


@api_router.get("/chat/{conversation_id}")
async def get_messages(conversation_id: str, user=Depends(get_current_user)):
    convo = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Not found")
    if convo["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    msgs = await db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"conversation": convo, "messages": msgs}


@api_router.post("/chat/{conversation_id}")
async def send_message(conversation_id: str, body: MessageIn, user=Depends(get_current_user)):
    convo = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Not found")
    if convo["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    msg = {"message_id": new_id("msg"), "conversation_id": conversation_id, "sender_id": user["user_id"],
           "text": body.text, "created_at": now_utc().isoformat()}
    await db.messages.insert_one(msg)
    await db.conversations.update_one({"conversation_id": conversation_id},
                                      {"$set": {"last_message": body.text, "updated_at": now_utc().isoformat()}})
    return {k: v for k, v in msg.items() if k != "_id"}


# =============================== Seed ===================================
BOT_PROVIDERS = [
    ("Giulia Bianchi", ["pulizie", "sarta"], 14.0, 4.9, 128, 45.668, 12.245),
    ("Marco Rossi", ["tuttofare", "driver"], 13.0, 4.7, 86, 45.662, 12.240),
    ("Elena Ferrari", ["babysitting", "assistenza"], 12.0, 4.8, 64, 45.670, 12.250),
    ("Sara Conti", ["pulizie", "hospitality"], 15.0, 5.0, 203, 45.665, 12.238),
    ("Luca Moretti", ["tecnico", "driver"], 13.5, 4.6, 51, 45.660, 12.255),
    ("Anna Greco", ["petsitting", "babysitting"], 14.5, 4.9, 174, 45.672, 12.230),
    ("Paolo Riva", ["tuttofare", "tecnico"], 13.0, 4.5, 39, 45.658, 12.248),
    ("Chiara Esposito", ["sarta", "hospitality"], 12.5, 4.8, 92, 45.669, 12.235),
]


async def seed_categories():
    order = 0
    for s in STANDARD_SERVICES:
        order += 1
        await db.categories.update_one({"cat_id": s["cat_id"]},
            {"$setOnInsert": {**s, "kind": "standard", "active": True, "order": order}}, upsert=True)
    for pid, emoji, it, en in PROXIMITY_BUSINESS:
        order += 1
        await db.categories.update_one({"cat_id": pid},
            {"$setOnInsert": {"cat_id": pid, "emoji": emoji, "label": L(it, en), "kind": "proximity",
                              "active": True, "order": order, "questions": [q_note()]}}, upsert=True)
    for p in PAYMENT_SERVICES:
        order += 1
        await db.categories.update_one({"cat_id": p["cat_id"]},
            {"$setOnInsert": {**p, "kind": "payment", "active": True, "order": order}}, upsert=True)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.categories.create_index("cat_id", unique=True)
    await seed_categories()
    if await db.users.count_documents({"is_bot": True}) == 0:
        for i, (name, services, rate, rating, reviews, lat, lng) in enumerate(BOT_PROVIDERS):
            await db.users.insert_one({
                "user_id": new_id("prov"), "email": f"provider{i}@jobby.demo", "name": name,
                "picture": f"https://i.pravatar.cc/200?u=jobby{i}", "role": "provider", "language": "it",
                "bio": "Professionista verificato, con esperienza e assicurazione inclusa.", "business_name": "",
                "hourly_rate": rate, "radius_km": 15.0, "services": services, "online": True, "rating": rating,
                "reviews_count": reviews, "verified": True, "verification_status": "verified", "wallet_balance": 0.0,
                "payment_method": None, "bank_account": None, "trust_score": 0.0, "trust_subscores": {},
                "client_trust_score": 0.0, "client_trust_subscores": {}, "is_admin": False, "is_bot": True,
                "lat": lat, "lng": lng, "created_at": (now_utc() - timedelta(days=random.randint(60, 400))).isoformat()})
        logger.info("Seeded bot providers")
    for p in await db.users.find({"is_bot": True}, {"_id": 0, "user_id": 1}).to_list(100):
        await recalc_provider_trust(p["user_id"])


app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
