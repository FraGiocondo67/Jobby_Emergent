import os
import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user

router = APIRouter()

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_BASE = os.environ.get("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")


class OriginIn(BaseModel):
    origin_url: str


class PaypalEmailIn(BaseModel):
    email: str


async def _access_token(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{PAYPAL_BASE}/v1/oauth2/token",
                          data={"grant_type": "client_credentials"},
                          auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET))
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="paypal_auth_failed")
    return r.json()["access_token"]


@router.put("/wallet/paypal-email")
async def set_paypal_email(body: PaypalEmailIn, user=Depends(get_current_user)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="invalid_email")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"paypal_email": email}})
    return {"paypal_email": email}


@router.post("/bookings/{booking_id}/paypal/create")
async def create_paypal_order(booking_id: str, body: OriginIn, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="booking_not_found")
    if b["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b.get("payment_status") == "paid":
        return {"already_paid": True}
    amount = round(float(b["total"]), 2)
    origin = body.origin_url.rstrip("/")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _access_token(client)
        r = await client.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": booking_id,
                    "amount": {"currency_code": "EUR", "value": f"{amount:.2f}"},
                }],
                "application_context": {
                    "brand_name": "JOBBY",
                    "user_action": "PAY_NOW",
                    "return_url": f"{origin}/booking/{booking_id}",
                    "cancel_url": f"{origin}/booking/{booking_id}",
                },
            })
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="paypal_order_failed")
    data = r.json()
    order_id = data["id"]
    approve = next((l["href"] for l in data.get("links", []) if l["rel"] in ("approve", "payer-action")), None)
    await db.payment_transactions.insert_one({
        "session_id": order_id, "provider": "paypal", "user_id": user["user_id"], "amount": amount,
        "currency": "eur", "purpose": "booking_payment", "booking_id": booking_id,
        "payment_status": "initiated", "status": "open", "credited": False, "created_at": now_utc().isoformat(),
    })
    return {"order_id": order_id, "url": approve}


@router.post("/paypal/capture/{order_id}")
async def capture_paypal_order(order_id: str, user=Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": order_id, "provider": "paypal"}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="tx_not_found")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _access_token(client)
        r = await client.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    completed = r.status_code in (200, 201) and r.json().get("status") == "COMPLETED"
    await db.payment_transactions.update_one({"session_id": order_id},
                                             {"$set": {"payment_status": "paid" if completed else "pending",
                                                       "status": "complete" if completed else "open"}})
    if completed and not tx.get("credited"):
        await db.payment_transactions.update_one({"session_id": order_id}, {"$set": {"credited": True}})
        await db.bookings.update_one({"booking_id": tx["booking_id"]},
                                     {"$set": {"payment_status": "paid", "paid_at": now_utc().isoformat()}})
        await db.transactions.insert_one({
            "tx_id": new_id("tx"), "user_id": tx["user_id"], "type": "booking_payment", "status": "paid",
            "amount": -tx["amount"], "label": f"Booking payment €{tx['amount']:.2f} (PayPal)",
            "booking_id": tx["booking_id"], "created_at": now_utc().isoformat()})
    return {"paid": completed, "amount": tx["amount"], "purpose": tx.get("purpose")}


@router.post("/bookings/{booking_id}/payout")
async def payout_provider(booking_id: str, user=Depends(get_current_user)):
    """Provider withdraws their earnings (labor_cost) to their PayPal account."""
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="booking_not_found")
    if b["provider_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b.get("payment_status") != "paid":
        raise HTTPException(status_code=400, detail="not_paid")
    if b.get("payout_status") == "paid":
        raise HTTPException(status_code=400, detail="already_paid_out")
    email = user.get("paypal_email")
    if not email:
        raise HTTPException(status_code=400, detail="no_paypal_email")
    amount = round(float(b["labor_cost"]), 2)  # provider gets labor; JOBBY keeps the commission
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _access_token(client)
        r = await client.post(
            f"{PAYPAL_BASE}/v1/payments/payouts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "sender_batch_header": {"sender_batch_id": new_id("po"), "email_subject": "JOBBY payout"},
                "items": [{
                    "recipient_type": "EMAIL",
                    "amount": {"value": f"{amount:.2f}", "currency": "EUR"},
                    "receiver": email,
                    "note": f"JOBBY earnings for {b['category']} booking",
                    "sender_item_id": booking_id,
                }],
            })
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="payout_failed")
    batch_id = r.json().get("batch_header", {}).get("payout_batch_id", "")
    await db.bookings.update_one({"booking_id": booking_id},
                                 {"$set": {"payout_status": "paid", "payout_at": now_utc().isoformat(),
                                           "payout_batch_id": batch_id}})
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": user["user_id"], "type": "payout", "status": "paid",
        "amount": amount, "label": f"Payout €{amount:.2f} (PayPal)", "booking_id": booking_id,
        "created_at": now_utc().isoformat()})
    return {"payout_status": "paid", "amount": amount, "batch_id": batch_id}
