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


def haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


# ---------------- Models ----------------
class SessionIn(BaseModel):
    session_token: str


class ProfileUpdate(BaseModel):
    role: Optional[str] = None
    language: Optional[str] = None
    bio: Optional[str] = None
    hourly_rate: Optional[float] = None
    radius_km: Optional[float] = None
    services: Optional[List[str]] = None
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


# ---------------- Auth helpers ----------------
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


# ---------------- Auth routes ----------------
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
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "picture": data.get("picture", ""),
            "role": "customer",
            "language": "it",
            "bio": "",
            "hourly_rate": 13.0,
            "radius_km": 10.0,
            "services": ["cleaning", "ironing"],
            "online": False,
            "rating": 0.0,
            "reviews_count": 0,
            "verified": False,
            "lat": TREVISO["lat"],
            "lng": TREVISO["lng"],
            "created_at": now_utc().isoformat(),
        }
        await db.users.insert_one(user_doc)
    session_token = data["session_token"]
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": user, "session_token": session_token}


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


@api_router.put("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in body.dict().items() if v is not None}
    if update.get("role") == "provider":
        update["verified"] = True
    if update:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    return await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})


# ---------------- Providers ----------------
@api_router.get("/providers/nearby")
async def providers_nearby(lat: float, lng: float, category: Optional[str] = None):
    providers = await db.users.find({"role": "provider", "online": True}, {"_id": 0}).to_list(200)
    result = []
    for p in providers:
        if category and category not in p.get("services", []):
            continue
        dist = haversine(lat, lng, p.get("lat", TREVISO["lat"]), p.get("lng", TREVISO["lng"]))
        if dist > p.get("radius_km", 10):
            continue
        result.append({
            "user_id": p["user_id"], "name": p["name"], "picture": p.get("picture", ""),
            "rating": p.get("rating", 0), "reviews_count": p.get("reviews_count", 0),
            "hourly_rate": p.get("hourly_rate", 13), "verified": p.get("verified", False),
            "bio": p.get("bio", ""), "distance_km": dist, "services": p.get("services", []),
            "lat": p.get("lat"), "lng": p.get("lng"),
        })
    result.sort(key=lambda x: x["distance_km"])
    return result


# ---------------- Missions ----------------
async def simulate_accept(mission_id: str, provider_id: str, delay: float, price: float):
    await asyncio.sleep(delay)
    mission = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not mission or mission["status"] != "broadcasting":
        return
    if any(a["provider_id"] == provider_id for a in mission.get("accepted", [])):
        return
    prov = await db.users.find_one({"user_id": provider_id}, {"_id": 0})
    if not prov:
        return
    accept = {
        "provider_id": provider_id,
        "name": prov["name"],
        "picture": prov.get("picture", ""),
        "rating": prov.get("rating", 0),
        "reviews_count": prov.get("reviews_count", 0),
        "distance_km": haversine(mission["lat"], mission["lng"], prov.get("lat"), prov.get("lng")),
        "price": price,
        "eta_min": random.randint(10, 40),
        "verified": prov.get("verified", True),
        "accepted_at": now_utc().isoformat(),
    }
    await db.missions.update_one({"mission_id": mission_id}, {"$push": {"accepted": accept}})


@api_router.post("/missions")
async def create_mission(body: MissionIn, user=Depends(get_current_user)):
    mission_id = new_id("msn")
    providers = await db.users.find({"role": "provider", "online": True}, {"_id": 0}).to_list(200)
    invited = []
    for p in providers:
        if body.category not in p.get("services", []):
            continue
        dist = haversine(body.lat, body.lng, p.get("lat", TREVISO["lat"]), p.get("lng", TREVISO["lng"]))
        if dist <= p.get("radius_km", 10):
            invited.append(p)
    doc = {
        "mission_id": mission_id,
        "customer_id": user["user_id"],
        "customer_name": user["name"],
        "category": body.category,
        "service_type": body.service_type,
        "config": body.config,
        "address": body.address,
        "lat": body.lat,
        "lng": body.lng,
        "date": body.date,
        "time": body.time,
        "duration_hours": body.duration_hours,
        "recurrence": body.recurrence,
        "status": "broadcasting",
        "invited_provider_ids": [p["user_id"] for p in invited],
        "accepted": [],
        "chosen_provider_id": None,
        "created_at": now_utc().isoformat(),
    }
    await db.missions.insert_one(doc)
    for p in invited:
        if p.get("is_bot"):
            price = round(p.get("hourly_rate", 13) * body.duration_hours, 2)
            asyncio.create_task(simulate_accept(mission_id, p["user_id"], random.uniform(2, 9), price))
    return await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})


@api_router.get("/missions")
async def my_missions(user=Depends(get_current_user)):
    return await db.missions.find({"customer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api_router.get("/missions/incoming/list")
async def incoming_missions(user=Depends(get_current_user)):
    ms = await db.missions.find({
        "invited_provider_ids": user["user_id"],
        "status": "broadcasting",
    }, {"_id": 0}).sort("created_at", -1).to_list(50)
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
    accept = next((a for a in m.get("accepted", []) if a["provider_id"] == body.provider_id), None)
    if not accept:
        raise HTTPException(status_code=400, detail="Provider has not accepted")
    labor = round(accept["price"], 2)
    jobby_fee = round(labor * 0.15, 2)
    booking_id = new_id("bkg")
    booking = {
        "booking_id": booking_id,
        "mission_id": mission_id,
        "customer_id": user["user_id"],
        "customer_name": user["name"],
        "provider_id": body.provider_id,
        "provider_name": accept["name"],
        "provider_picture": accept.get("picture", ""),
        "category": m["category"],
        "service_type": m["service_type"],
        "address": m["address"],
        "date": m["date"],
        "time": m["time"],
        "duration_hours": m["duration_hours"],
        "labor_cost": labor,
        "jobby_fee": jobby_fee,
        "total": round(labor + jobby_fee, 2),
        "status": "confirmed",
        "reviewed": False,
        "created_at": now_utc().isoformat(),
    }
    await db.bookings.insert_one(booking)
    await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "booked", "chosen_provider_id": body.provider_id}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


@api_router.post("/missions/{mission_id}/accept")
async def accept_mission(mission_id: str, body: AcceptIn, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["status"] != "broadcasting":
        raise HTTPException(status_code=400, detail="Mission not available")
    if any(a["provider_id"] == user["user_id"] for a in m.get("accepted", [])):
        return {"ok": True}
    price = body.price if body.price is not None else round(user.get("hourly_rate", 13) * m["duration_hours"], 2)
    accept = {
        "provider_id": user["user_id"],
        "name": user["name"],
        "picture": user.get("picture", ""),
        "rating": user.get("rating", 0),
        "reviews_count": user.get("reviews_count", 0),
        "distance_km": haversine(m["lat"], m["lng"], user.get("lat", TREVISO["lat"]), user.get("lng", TREVISO["lng"])),
        "price": price,
        "eta_min": random.randint(10, 40),
        "verified": user.get("verified", True),
        "accepted_at": now_utc().isoformat(),
    }
    await db.missions.update_one({"mission_id": mission_id}, {"$push": {"accepted": accept}})
    return {"ok": True}


@api_router.post("/missions/{mission_id}/decline")
async def decline_mission(mission_id: str, user=Depends(get_current_user)):
    await db.missions.update_one({"mission_id": mission_id}, {"$pull": {"invited_provider_ids": user["user_id"]}})
    return {"ok": True}


# ---------------- Bookings ----------------
@api_router.get("/bookings")
async def list_bookings(user=Depends(get_current_user)):
    key = "provider_id" if user["role"] == "provider" else "customer_id"
    return await db.bookings.find({key: user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api_router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    return b


@api_router.post("/bookings/{booking_id}/complete")
async def complete_booking(booking_id: str, user=Depends(get_current_user)):
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "completed"}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


@api_router.post("/bookings/{booking_id}/review")
async def review_booking(booking_id: str, body: ReviewIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b.get("reviewed"):
        return {"ok": True}
    await db.reviews.insert_one({
        "review_id": new_id("rev"),
        "booking_id": booking_id,
        "provider_id": b["provider_id"],
        "customer_id": user["user_id"],
        "customer_name": user["name"],
        "rating": body.rating,
        "comment": body.comment,
        "created_at": now_utc().isoformat(),
    })
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"reviewed": True, "status": "completed"}})
    revs = await db.reviews.find({"provider_id": b["provider_id"]}, {"_id": 0}).to_list(1000)
    avg = round(sum(r["rating"] for r in revs) / len(revs), 1) if revs else 0
    await db.users.update_one({"user_id": b["provider_id"]}, {"$set": {"rating": avg, "reviews_count": len(revs)}})
    return {"ok": True}


@api_router.get("/providers/{provider_id}/reviews")
async def provider_reviews(provider_id: str):
    return await db.reviews.find({"provider_id": provider_id}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api_router.get("/earnings")
async def earnings(user=Depends(get_current_user)):
    bs = await db.bookings.find({"provider_id": user["user_id"]}, {"_id": 0}).to_list(500)
    return {
        "total_earned": round(sum(b["labor_cost"] for b in bs), 2),
        "jobs_count": len(bs),
        "completed_count": len([b for b in bs if b["status"] == "completed"]),
        "pending": round(sum(b["labor_cost"] for b in bs if b["status"] != "completed"), 2),
    }


# ---------------- Seed ----------------
BOT_PROVIDERS = [
    ("Giulia Bianchi", "cleaning", 14.0, 4.9, 128, 45.668, 12.245),
    ("Marco Rossi", "cleaning", 13.0, 4.7, 86, 45.662, 12.240),
    ("Elena Ferrari", "ironing", 12.0, 4.8, 64, 45.670, 12.250),
    ("Sara Conti", "cleaning", 15.0, 5.0, 203, 45.665, 12.238),
    ("Luca Moretti", "ironing", 13.5, 4.6, 51, 45.660, 12.255),
    ("Anna Greco", "cleaning", 14.5, 4.9, 174, 45.672, 12.230),
    ("Paolo Riva", "cleaning", 13.0, 4.5, 39, 45.658, 12.248),
    ("Chiara Esposito", "ironing", 12.5, 4.8, 92, 45.669, 12.235),
]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    if await db.users.count_documents({"is_bot": True}) == 0:
        for i, (name, svc, rate, rating, reviews, lat, lng) in enumerate(BOT_PROVIDERS):
            services = ["cleaning", "ironing"] if random.random() > 0.5 else [svc]
            await db.users.insert_one({
                "user_id": new_id("prov"),
                "email": f"provider{i}@jobby.demo",
                "name": name,
                "picture": f"https://i.pravatar.cc/200?u=jobby{i}",
                "role": "provider",
                "language": "it",
                "bio": "Professionista verificato, con esperienza e assicurazione inclusa.",
                "hourly_rate": rate,
                "radius_km": 15.0,
                "services": services,
                "online": True,
                "rating": rating,
                "reviews_count": reviews,
                "verified": True,
                "is_bot": True,
                "lat": lat,
                "lng": lng,
                "created_at": now_utc().isoformat(),
            })
        logger.info("Seeded bot providers")


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
