from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id
from deps import get_current_user
from models import ReviewIn, ClientRatingIn, DisputeIn
from trust import recalc_provider_trust, recalc_client_trust, log_trust_event, PROVIDER_WEIGHTS, CLIENT_WEIGHTS

router = APIRouter()


@router.get("/bookings")
async def list_bookings(user=Depends(get_current_user)):
    key = "provider_id" if user["role"] in ("provider", "business") else "customer_id"
    return await db.bookings.find({key: user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    return b


def _member(b, user):
    return user["user_id"] in (b["provider_id"], b["customer_id"])


@router.post("/bookings/{booking_id}/start")
async def start_booking(booking_id: str, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if not _member(b, user):
        raise HTTPException(status_code=403, detail="forbidden")
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "in_progress", "check_in_on_time": True}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


@router.post("/bookings/{booking_id}/complete")
async def complete_booking(booking_id: str, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if not _member(b, user):
        raise HTTPException(status_code=403, detail="forbidden")
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "completed"}})
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    await recalc_provider_trust(b["provider_id"])
    return b


@router.post("/bookings/{booking_id}/review")
async def review_booking(booking_id: str, body: ReviewIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if user["user_id"] != b["customer_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
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


@router.post("/bookings/{booking_id}/rate-client")
async def rate_client(booking_id: str, body: ClientRatingIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if user["user_id"] != b["provider_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b.get("client_rated"):
        return {"ok": True}
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"client_rated": True}})
    await log_trust_event("client_trust_events", b["customer_id"], "client_rated", 0,
                          {"rating": body.rating, "brief_accuracy": body.brief_accuracy, "tip": body.tip, "booking_id": booking_id})
    score = await recalc_client_trust(b["customer_id"])
    return {"ok": True, "client_trust_score": score}


@router.post("/bookings/{booking_id}/dispute")
async def dispute_booking(booking_id: str, body: DisputeIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if not _member(b, user):
        raise HTTPException(status_code=403, detail="forbidden")
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


@router.get("/earnings")
async def earnings(user=Depends(get_current_user)):
    bs = await db.bookings.find({"provider_id": user["user_id"]}, {"_id": 0}).to_list(500)
    return {"total_earned": round(sum(b["labor_cost"] for b in bs), 2), "jobs_count": len(bs),
            "completed_count": len([b for b in bs if b["status"] == "completed"]),
            "pending": round(sum(b["labor_cost"] for b in bs if b["status"] != "completed"), 2)}


@router.get("/trust")
async def get_trust(user=Depends(get_current_user)):
    events = await db.trust_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    cevents = await db.client_trust_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"provider_score": user.get("trust_score", 0), "provider_subscores": user.get("trust_subscores", {}),
            "client_score": user.get("client_trust_score", 0), "client_subscores": user.get("client_trust_subscores", {}),
            "provider_weights": PROVIDER_WEIGHTS, "client_weights": CLIENT_WEIGHTS,
            "events": events, "client_events": cevents}
