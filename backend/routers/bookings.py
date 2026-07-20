from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id
from deps import get_current_user
from models import ReviewIn, ClientRatingIn, DisputeIn
from trust import recalc_provider_trust, recalc_client_trust, log_trust_event, PROVIDER_WEIGHTS, CLIENT_WEIGHTS
from escrow import release_escrow, refund_escrow

router = APIRouter()


@router.post("/bookings/{booking_id}/pay-escrow")
async def pay_escrow(booking_id: str, user=Depends(get_current_user)):
    """Client blocks the estimated total in escrow (from available wallet balance)."""
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b.get("escrow_status") == "held" or b.get("payment_status") == "paid":
        return {"already_paid": True, "booking": b}
    amount = round(float(b["total"]), 2)
    available = round(user.get("wallet_balance", 0), 2)
    if amount > available:
        raise HTTPException(status_code=400, detail="insufficient_funds")
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"wallet_balance": -amount}})
    await db.transactions.insert_one({"tx_id": new_id("tx"), "user_id": user["user_id"], "type": "escrow_hold",
                                      "label": f"Importo bloccato in garanzia €{amount:.2f}", "amount": -amount,
                                      "booking_id": booking_id, "status": "held", "created_at": now_utc().isoformat()})
    await db.bookings.update_one({"booking_id": booking_id},
                                 {"$set": {"escrow_status": "held", "escrow_amount": amount, "payment_status": "paid",
                                           "escrow_held_at": now_utc().isoformat()}})
    return {"paid": True, "booking": await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})}


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
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "completed", "completed_at": now_utc().isoformat()}})
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    # Release the held escrow to the provider (client confirmation of execution).
    if b.get("escrow_status") == "held":
        await release_escrow(b)
        b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    await recalc_provider_trust(b["provider_id"])
    return b


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, user=Depends(get_current_user)):
    """Client cancels a booking before completion; any held escrow is refunded."""
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    if b["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b["status"] in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="cannot_cancel")
    if b.get("escrow_status") == "held":
        await refund_escrow(b)
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "cancelled"}})
    return await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})


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
    # A dispute by the client on a held escrow refunds the blocked amount.
    if against == "provider" and b.get("escrow_status") == "held":
        await refund_escrow(b)
    ps = await recalc_provider_trust(b["provider_id"])
    cs = await recalc_client_trust(b["customer_id"])
    await log_trust_event("trust_events", b["provider_id"], "dispute", ps, {"booking_id": booking_id})
    await log_trust_event("client_trust_events", b["customer_id"], "dispute", cs, {"booking_id": booking_id})
    return {"ok": True}


@router.get("/earnings")
async def earnings(user=Depends(get_current_user)):
    uid = user["user_id"]
    bs = await db.bookings.find({"provider_id": uid}, {"_id": 0}).to_list(500)
    rq = await db.richieste.find({"provider_scelto": uid}, {"_id": 0}).to_list(1000)

    def rnet(r):
        pl = r.get("pagamento_lavoro") or r.get("pagamento") or {}
        v = pl.get("net_provider") or pl.get("importo") or pl.get("provider_net")
        if v:
            return round(float(v), 2)
        p = r.get("prezzo_finale") or r.get("importo_totale") or 0
        return round(float(p), 2)

    DONE = ("completata", "recensita")
    ACTIVE = ("confermata", "in_corso")
    PAID = ("released", "settled")
    total_earned = 0.0
    pending = 0.0
    jobs_count = 0
    completed_count = 0
    for r in rq:
        jobs_count += 1
        pl = (r.get("pagamento_lavoro") or r.get("pagamento") or {})
        if r["stato"] in DONE:
            completed_count += 1
            if pl.get("stato") in PAID or pl.get("credited"):
                total_earned += rnet(r)
            else:
                pending += rnet(r)
        elif r["stato"] in ACTIVE:
            pending += rnet(r)
    for b in bs:
        jobs_count += 1
        if b.get("status") == "completed":
            completed_count += 1
            total_earned += b.get("labor_cost", 0)
        else:
            pending += b.get("labor_cost", 0)
    return {"total_earned": round(total_earned, 2), "jobs_count": jobs_count,
            "completed_count": completed_count, "pending": round(pending, 2)}


@router.get("/trust")
async def get_trust(user=Depends(get_current_user)):
    events = await db.trust_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    cevents = await db.client_trust_events.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"provider_score": user.get("trust_score", 0), "provider_subscores": user.get("trust_subscores", {}),
            "client_score": user.get("client_trust_score", 0), "client_subscores": user.get("client_trust_subscores", {}),
            "provider_weights": PROVIDER_WEIGHTS, "client_weights": CLIENT_WEIGHTS,
            "events": events, "client_events": cevents}
