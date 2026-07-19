from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user, require_admin
from dispute_ai import ai_analyze, REASON_CODES
from routers.notifications import push_notification

router = APIRouter()

DEFAULT_WINDOW_HOURS = 8
DEFAULT_PROVIDER_HOURS = 48


class DisputeCreate(BaseModel):
    booking_id: str
    reason_code: str
    description: str = ""


class MessageIn(BaseModel):
    text: str


class ProviderRespondIn(BaseModel):
    accept: bool
    refund_pct: int = 100
    message: str = ""


class AdminResolveIn(BaseModel):
    decision: str          # refund_full | refund_partial | reject
    refund_pct: int = 100
    note: str = ""


async def _setting(key, default):
    s = await db.settings.find_one({"key": key})
    try:
        return int(s["value"]) if s else default
    except Exception:
        return default


async def _apply_refund(booking: dict, refund_pct: int):
    """Refund the client (from the provider's blocked funds when possible, otherwise JOBBY guarantees)."""
    pct = max(0, min(100, int(refund_pct)))
    refund_amount = round(float(booking["total"]) * pct / 100.0, 2)
    provider_clawback = round(float(booking["labor_cost"]) * pct / 100.0, 2)
    guaranteed = refund_amount
    hold = await db.wallet_holds.find_one({"booking_id": booking["booking_id"], "status": {"$in": ["pending", "disputed"]}}, {"_id": 0})
    if hold and provider_clawback > 0:
        claw = round(min(hold["amount"], provider_clawback), 2)
        await db.users.update_one({"user_id": booking["provider_id"]}, {"$inc": {"pending_balance": -claw}})
        await db.wallet_holds.update_one({"hold_id": hold["hold_id"]}, {"$set": {"status": "clawed_back", "clawed_at": now_utc().isoformat()}})
        await db.transactions.insert_one({"tx_id": new_id("tx"), "user_id": booking["provider_id"], "type": "clawback",
                                          "label": f"Storno per contestazione €{claw:.2f}", "amount": -claw,
                                          "booking_id": booking["booking_id"], "status": "clawed_back", "created_at": now_utc().isoformat()})
        guaranteed = round(refund_amount - claw, 2)
    if refund_amount > 0:
        await db.users.update_one({"user_id": booking["customer_id"]}, {"$inc": {"wallet_balance": refund_amount}})
        label = f"Rimborso contestazione €{refund_amount:.2f}" + (" (garantito da JOBBY)" if guaranteed > 0.005 and (not hold) else "")
        await db.transactions.insert_one({"tx_id": new_id("tx"), "user_id": booking["customer_id"], "type": "refund",
                                          "label": label, "amount": refund_amount, "booking_id": booking["booking_id"],
                                          "status": "available", "created_at": now_utc().isoformat()})
    await db.bookings.update_one({"booking_id": booking["booking_id"]},
                                 {"$set": {"escrow_status": "refunded" if pct >= 100 else "released",
                                           "status": "completed",
                                           "dispute_resolution_pct": pct}})
    return {"refund_amount": refund_amount, "jobby_guaranteed": max(0.0, guaranteed)}


@router.get("/disputes/reason-codes")
async def reason_codes():
    return [{"code": c, "label": m} for c, m in REASON_CODES.items()]


@router.post("/disputes")
async def create_dispute(body: DisputeCreate, user=Depends(get_current_user)):
    if body.reason_code not in REASON_CODES:
        raise HTTPException(status_code=400, detail="invalid_reason")
    b = await db.bookings.find_one({"booking_id": body.booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="booking_not_found")
    if b["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b.get("status") != "completed":
        raise HTTPException(status_code=400, detail="not_completed")
    window = await _setting("dispute_window_hours", DEFAULT_WINDOW_HOURS)
    completed_at = b.get("completed_at")
    if completed_at:
        try:
            from datetime import datetime
            ca = datetime.fromisoformat(completed_at)
            if (now_utc() - ca) > timedelta(hours=window):
                raise HTTPException(status_code=400, detail="window_expired")
        except HTTPException:
            raise
        except Exception:
            pass
    if await db.disputes.find_one({"booking_id": body.booking_id, "status": {"$nin": ["resolved_mutual", "resolved_jobby", "rejected"]}}):
        raise HTTPException(status_code=400, detail="dispute_exists")
    prov_hours = await _setting("provider_response_hours", DEFAULT_PROVIDER_HOURS)
    dispute = {
        "dispute_id": new_id("dsp"), "booking_id": body.booking_id, "customer_id": user["user_id"],
        "provider_id": b["provider_id"], "reason_code": body.reason_code, "description": body.description,
        "status": "open", "provider_response": "", "amount": b["total"],
        "messages": [{"from": "client", "text": body.description, "at": now_utc().isoformat()}],
        "provider_deadline": (now_utc() + timedelta(hours=prov_hours)).isoformat(),
        "ai_recommendation": None, "resolution": None, "created_at": now_utc().isoformat(),
    }
    await db.disputes.insert_one(dispute)
    # Freeze the provider's blocked funds for this booking so they can't mature during the dispute.
    await db.wallet_holds.update_many({"booking_id": body.booking_id, "status": "pending"}, {"$set": {"status": "disputed"}})
    await db.bookings.update_one({"booking_id": body.booking_id}, {"$set": {"status": "disputed"}})
    # AI produces a (non-binding) recommendation immediately.
    rec = await ai_analyze(dispute, b)
    await db.disputes.update_one({"dispute_id": dispute["dispute_id"]}, {"$set": {"ai_recommendation": rec}})
    dispute["ai_recommendation"] = rec
    await push_notification(
        b["provider_id"], "dispute_opened", "Nuova contestazione",
        f"Un cliente ha aperto una contestazione ({REASON_CODES.get(body.reason_code, 'Altro')}). Hai 48h per rispondere.",
        "dispute", dispute["dispute_id"],
    )
    return {k: v for k, v in dispute.items() if k != "_id"}


@router.get("/disputes")
async def my_disputes(user=Depends(get_current_user)):
    q = {"$or": [{"customer_id": user["user_id"]}, {"provider_id": user["user_id"]}]}
    items = await db.disputes.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    for d in items:
        d["role"] = "client" if d["customer_id"] == user["user_id"] else "provider"
    return items


@router.get("/disputes/{dispute_id}")
async def get_dispute(dispute_id: str, user=Depends(get_current_user)):
    d = await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="not_found")
    if user["user_id"] not in (d["customer_id"], d["provider_id"]):
        raise HTTPException(status_code=403, detail="forbidden")
    d["role"] = "client" if d["customer_id"] == user["user_id"] else "provider"
    return d


@router.post("/disputes/{dispute_id}/message")
async def add_message(dispute_id: str, body: MessageIn, user=Depends(get_current_user)):
    d = await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})
    if not d or user["user_id"] not in (d["customer_id"], d["provider_id"]):
        raise HTTPException(status_code=404, detail="not_found")
    sender = "client" if d["customer_id"] == user["user_id"] else "provider"
    msg = {"from": sender, "text": body.text, "at": now_utc().isoformat()}
    await db.disputes.update_one({"dispute_id": dispute_id}, {"$push": {"messages": msg}})
    recipient = d["provider_id"] if sender == "client" else d["customer_id"]
    await push_notification(recipient, "dispute_message", "Nuovo messaggio contestazione",
                            body.text[:120], "dispute", dispute_id)
    return msg


@router.post("/disputes/{dispute_id}/respond")
async def provider_respond(dispute_id: str, body: ProviderRespondIn, user=Depends(get_current_user)):
    d = await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="not_found")
    if d["provider_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if d["status"] not in ("open", "provider_responded"):
        raise HTTPException(status_code=400, detail="not_open")
    upd = {"provider_response": body.message}
    if body.message:
        await db.disputes.update_one({"dispute_id": dispute_id}, {"$push": {"messages": {"from": "provider", "text": body.message, "at": now_utc().isoformat()}}})
    if body.accept:
        b = await db.bookings.find_one({"booking_id": d["booking_id"]}, {"_id": 0})
        res = await _apply_refund(b, body.refund_pct)
        upd.update({"status": "resolved_mutual", "resolution": {"by": "provider_accept", "refund_pct": max(0, min(100, body.refund_pct)), **res}})
    else:
        upd["status"] = "provider_responded"
    await db.disputes.update_one({"dispute_id": dispute_id}, {"$set": upd})
    if body.accept:
        await push_notification(d["customer_id"], "dispute_resolved", "Contestazione risolta",
                                f"Il fornitore ha accettato un rimborso del {max(0, min(100, body.refund_pct))}%.", "dispute", dispute_id)
    else:
        await push_notification(d["customer_id"], "dispute_update", "Risposta del fornitore",
                                "Il fornitore ha risposto alla tua contestazione.", "dispute", dispute_id)
    return await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})


@router.post("/disputes/{dispute_id}/escalate")
async def escalate(dispute_id: str, user=Depends(get_current_user)):
    d = await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})
    if not d or user["user_id"] not in (d["customer_id"], d["provider_id"]):
        raise HTTPException(status_code=404, detail="not_found")
    if d["status"] in ("resolved_mutual", "resolved_jobby", "rejected"):
        raise HTTPException(status_code=400, detail="already_resolved")
    await db.disputes.update_one({"dispute_id": dispute_id}, {"$set": {"status": "escalated", "escalated_at": now_utc().isoformat()}})
    return {"status": "escalated"}


# ---- Admin ----
@router.get("/admin/disputes")
async def admin_list_disputes(_=Depends(require_admin)):
    return await db.disputes.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/admin/disputes/{dispute_id}/resolve")
async def admin_resolve(dispute_id: str, body: AdminResolveIn, _=Depends(require_admin)):
    d = await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="not_found")
    if body.decision not in ("refund_full", "refund_partial", "reject"):
        raise HTTPException(status_code=400, detail="invalid_decision")
    pct = 100 if body.decision == "refund_full" else (0 if body.decision == "reject" else max(0, min(100, body.refund_pct)))
    b = await db.bookings.find_one({"booking_id": d["booking_id"]}, {"_id": 0})
    res = {}
    if pct > 0:
        res = await _apply_refund(b, pct)
    else:
        # No refund: release the frozen hold back to normal pending so it can mature.
        await db.wallet_holds.update_many({"booking_id": d["booking_id"], "status": "disputed"}, {"$set": {"status": "pending"}})
        await db.bookings.update_one({"booking_id": d["booking_id"]}, {"$set": {"status": "completed"}})
    await db.disputes.update_one({"dispute_id": dispute_id},
                                 {"$set": {"status": "resolved_jobby",
                                           "resolution": {"by": "jobby_admin", "decision": body.decision, "refund_pct": pct, "note": body.note, **res},
                                           "resolved_at": now_utc().isoformat()}})
    for uid in (d["customer_id"], d["provider_id"]):
        await push_notification(uid, "dispute_resolved", "Contestazione risolta da JOBBY",
                                f"Decisione: {body.decision.replace('_', ' ')} ({pct}%).", "dispute", dispute_id)
    return await db.disputes.find_one({"dispute_id": dispute_id}, {"_id": 0})


class DisputeSettingsIn(BaseModel):
    window_hours: int = 8
    provider_hours: int = 48


@router.post("/admin/settings/dispute")
async def set_dispute_settings(body: DisputeSettingsIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "dispute_window_hours"}, {"$set": {"value": int(body.window_hours)}}, upsert=True)
    await db.settings.update_one({"key": "provider_response_hours"}, {"$set": {"value": int(body.provider_hours)}}, upsert=True)
    return {"window_hours": body.window_hours, "provider_hours": body.provider_hours}
