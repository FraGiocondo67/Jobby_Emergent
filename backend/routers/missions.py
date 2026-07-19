import random
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id, haversine, TREVISO
from deps import get_current_user
from models import MissionIn, AcceptIn, SelectIn

router = APIRouter()


@router.get("/providers/nearby")
async def providers_nearby(lat: float, lng: float, category: Optional[str] = None, user=Depends(get_current_user)):
    # Real registered providers/businesses only (exclude demo bots).
    providers = await db.users.find(
        {"role": {"$in": ["provider", "business"]}, "online": True, "is_bot": {"$ne": True},
         "approval_status": {"$nin": ["rejected", "suspended"]}},
        {"_id": 0}).to_list(300)
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
            "trust_score": p.get("trust_score", 0), "bio": p.get("bio", ""), "distance_km": dist,
            "services": p.get("services", []), "lat": p.get("lat"), "lng": p.get("lng"),
            "role": p.get("role"), "service_mode": p.get("service_mode", "both"),
            "business_name": p.get("business_name", ""),
            "approval_status": p.get("approval_status", "approved"),
        })
    result.sort(key=lambda x: x["distance_km"])
    return result


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


@router.post("/missions")
async def create_mission(body: MissionIn, user=Depends(get_current_user)):
    mission_id = new_id("msn")
    providers = await db.users.find({"role": {"$in": ["provider", "business"]}, "online": True}, {"_id": 0}).to_list(300)
    invited = []
    for p in providers:
        if not p.get("is_bot") and body.category not in p.get("services", []):
            continue
        # In-shop-only providers/businesses don't travel to the client → not invited.
        if not p.get("is_bot") and p.get("service_mode") == "in_shop":
            continue
        if haversine(body.lat, body.lng, p.get("lat", TREVISO["lat"]), p.get("lng", TREVISO["lng"])) <= p.get("radius_km", 10):
            invited.append(p)
    doc = {"mission_id": mission_id, "customer_id": user["user_id"], "customer_name": user["name"],
           "category": body.category, "service_type": body.service_type, "config": body.config,
           "address": body.address, "lat": body.lat, "lng": body.lng, "date": body.date, "time": body.time,
           "duration_hours": body.duration_hours, "recurrence": body.recurrence, "status": "pending",
           "budget": body.budget,
           "invited_provider_ids": [p["user_id"] for p in invited], "accepted": [], "chosen_provider_id": None,
           "created_at": now_utc().isoformat()}
    await db.missions.insert_one(doc)
    for p in invited:
        if p.get("is_bot"):
            asyncio.create_task(simulate_accept(mission_id, p["user_id"], random.uniform(2, 9), round(p.get("hourly_rate", 13) * body.duration_hours, 2)))
    return await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})


@router.get("/missions")
async def my_missions(user=Depends(get_current_user)):
    return await db.missions.find({"customer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/missions/incoming/list")
async def incoming_missions(user=Depends(get_current_user)):
    ms = await db.missions.find({"invited_provider_ids": user["user_id"], "status": {"$in": ["pending", "matched"]}}, {"_id": 0}).sort("created_at", -1).to_list(50)
    for m in ms:
        m["already_accepted"] = any(a["provider_id"] == user["user_id"] for a in m.get("accepted", []))
    return ms


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    return m


@router.post("/missions/{mission_id}/select")
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
    cat = await db.categories.find_one({"cat_id": m["category"]}, {"_id": 0})
    commission_pct = float(cat.get("commission_pct", 10.0)) if cat else 10.0
    jobby_fee = round(labor * commission_pct / 100.0, 2)
    booking_id = new_id("bkg")
    await db.bookings.insert_one({
        "booking_id": booking_id, "mission_id": mission_id, "customer_id": user["user_id"],
        "customer_name": user["name"], "provider_id": body.provider_id, "provider_name": accept["name"],
        "provider_picture": accept.get("picture", ""), "category": m["category"], "service_type": m["service_type"],
        "address": m["address"], "date": m["date"], "time": m["time"], "duration_hours": m["duration_hours"],
        "labor_cost": labor, "jobby_fee": jobby_fee, "commission_pct": commission_pct, "total": round(labor + jobby_fee, 2),
        "status": "confirmed", "payment_status": "unpaid", "check_in_on_time": False, "reviewed": False, "client_rated": False,
        "created_at": now_utc().isoformat()})
    await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "booked", "chosen_provider_id": body.provider_id}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


@router.post("/missions/{mission_id}/accept")
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


@router.post("/missions/{mission_id}/decline")
async def decline_mission(mission_id: str, user=Depends(get_current_user)):
    await db.missions.update_one({"mission_id": mission_id}, {"$pull": {"invited_provider_ids": user["user_id"]}})
    return {"ok": True}


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str, user=Depends(get_current_user)):
    """Client cancels their own service request before it is booked."""
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="not_found")
    if m["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if m["status"] in ("booked", "cancelled"):
        raise HTTPException(status_code=400, detail="cannot_cancel")
    await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "cancelled"}})
    return {"status": "cancelled"}


@router.get("/providers/{provider_id}/reviews")
async def provider_reviews(provider_id: str, user=Depends(get_current_user)):
    return await db.reviews.find({"provider_id": provider_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
