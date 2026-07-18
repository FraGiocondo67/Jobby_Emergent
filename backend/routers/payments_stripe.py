import os
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

from core import db, now_utc, new_id
from deps import get_current_user

router = APIRouter()

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")

# Server-defined top-up packages (never trust client-sent amounts).
TOPUP_PACKAGES = {"p10": 10.0, "p25": 25.0, "p50": 50.0, "p100": 100.0}


class CheckoutIn(BaseModel):
    package_id: str
    origin_url: str


def _client(request: Request) -> StripeCheckout:
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)


@router.post("/wallet/topup/checkout")
async def create_topup_checkout(body: CheckoutIn, request: Request, user=Depends(get_current_user)):
    if body.package_id not in TOPUP_PACKAGES:
        raise HTTPException(status_code=400, detail="invalid_package")
    amount = TOPUP_PACKAGES[body.package_id]
    origin = body.origin_url.rstrip("/")
    stripe = _client(request)
    req = CheckoutSessionRequest(
        amount=amount,
        currency="eur",
        success_url=f"{origin}/wallet?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/wallet",
        metadata={"user_id": user["user_id"], "package_id": body.package_id, "purpose": "wallet_topup"},
    )
    session = await stripe.create_checkout_session(req)
    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "user_id": user["user_id"], "amount": amount, "currency": "eur",
        "package_id": body.package_id, "payment_status": "initiated", "status": "open", "credited": False,
        "created_at": now_utc().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}


async def _credit_if_paid(session_id: str, status) -> dict:
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="tx_not_found")
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"payment_status": status.payment_status, "status": status.status}})
    # Idempotent credit: only once, only when paid.
    if status.payment_status == "paid" and not tx.get("credited"):
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"credited": True}})
        await db.users.update_one({"user_id": tx["user_id"]}, {"$inc": {"wallet_balance": tx["amount"]}})
        await db.transactions.insert_one({
            "tx_id": new_id("tx"), "user_id": tx["user_id"], "type": "topup", "status": "paid",
            "amount": tx["amount"], "label": f"Wallet top-up €{tx['amount']:.0f} (Stripe)",
            "created_at": now_utc().isoformat(),
        })
    return {"payment_status": status.payment_status, "status": status.status,
            "amount": tx["amount"], "credited": status.payment_status == "paid"}


@router.get("/wallet/topup/status/{session_id}")
async def topup_status(session_id: str, request: Request, user=Depends(get_current_user)):
    stripe = _client(request)
    status = await stripe.get_checkout_status(session_id)
    return await _credit_if_paid(session_id, status)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe = _client(request)
    try:
        event = await stripe.handle_webhook(body, sig)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_webhook")
    if getattr(event, "session_id", None):
        try:
            status = await stripe.get_checkout_status(event.session_id)
            await _credit_if_paid(event.session_id, status)
        except Exception:
            pass
    return {"received": True}
