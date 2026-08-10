"""RITIRATO nel Blocco 7 (migrazione Emergent -> Supabase/Render) — non più
importato/esposto da server.py, su conferma esplicita dell'utente. Wrapper
Stripe per il top-up wallet (via `emergentintegrations`, già rimosso nel
Blocco 1) — superato dal vero escrow Stripe Connect (`stripe_pg.py` +
`routers/stripe_connect.py`, Blocco 3) che copre tutti i pagamenti reali
delle 4 verticali + business/listino. File lasciato nel repo come
riferimento storico (Mongo, non funzionante senza MONGO_URL)."""
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user

router = APIRouter()

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")

# Server-defined top-up packages (never trust client-sent amounts).
TOPUP_PACKAGES = {"p10": 10.0, "p25": 25.0, "p50": 50.0, "p100": 100.0}


class CheckoutIn(BaseModel):
    package_id: str
    origin_url: str


class OriginIn(BaseModel):
    origin_url: str


def _stripe(request: Request):
    """Import differito (non a livello di modulo): `emergentintegrations` non è
    su PyPI pubblico e non viene più installato (vedi requirements.txt). Blocco 1
    lascia questo router così com'è (è Mongo-based, non ancora migrato — la
    sostituzione con l'SDK `stripe` diretto è pianificata per il Blocco 3, vedi
    punto 3 della tabella "legami da rimuovere" nel piano di migrazione). Fino ad
    allora il modulo si importa senza errori; solo queste route (checkout/webhook
    Stripe via wrapper Emergent) falliscono se effettivamente chiamate.
    Ritorna (client, classe CheckoutSessionRequest) — serve entrambi ai chiamanti."""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    client = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    return client, CheckoutSessionRequest


@router.post("/wallet/topup/checkout")
async def create_topup_checkout(body: CheckoutIn, request: Request, user=Depends(get_current_user)):
    if body.package_id not in TOPUP_PACKAGES:
        raise HTTPException(status_code=400, detail="invalid_package")
    amount = TOPUP_PACKAGES[body.package_id]
    origin = body.origin_url.rstrip("/")
    stripe, CheckoutSessionRequest = _stripe(request)
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
        "purpose": "wallet_topup", "package_id": body.package_id,
        "payment_status": "initiated", "status": "open", "credited": False,
        "created_at": now_utc().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}


@router.post("/bookings/{booking_id}/pay")
async def pay_booking(booking_id: str, body: OriginIn, request: Request, user=Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="booking_not_found")
    if b["customer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if b.get("payment_status") == "paid":
        return {"already_paid": True}
    amount = round(float(b["total"]), 2)  # server-side amount from DB
    origin = body.origin_url.rstrip("/")
    stripe, CheckoutSessionRequest = _stripe(request)
    req = CheckoutSessionRequest(
        amount=amount,
        currency="eur",
        success_url=f"{origin}/booking/{booking_id}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/booking/{booking_id}",
        metadata={"user_id": user["user_id"], "booking_id": booking_id, "purpose": "booking_payment"},
    )
    session = await stripe.create_checkout_session(req)
    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "user_id": user["user_id"], "amount": amount, "currency": "eur",
        "purpose": "booking_payment", "booking_id": booking_id,
        "payment_status": "initiated", "status": "open", "credited": False,
        "created_at": now_utc().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}


async def _settle_if_paid(session_id: str, status) -> dict:
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="tx_not_found")
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"payment_status": status.payment_status, "status": status.status}})
    paid = status.payment_status == "paid"
    # Idempotent settlement: only once, only when paid.
    if paid and not tx.get("credited"):
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"credited": True}})
        purpose = tx.get("purpose", "wallet_topup")
        if purpose == "wallet_topup":
            await db.users.update_one({"user_id": tx["user_id"]}, {"$inc": {"wallet_balance": tx["amount"]}})
            await db.transactions.insert_one({
                "tx_id": new_id("tx"), "user_id": tx["user_id"], "type": "topup", "status": "paid",
                "amount": tx["amount"], "label": f"Wallet top-up €{tx['amount']:.0f} (Stripe)",
                "created_at": now_utc().isoformat()})
        elif purpose == "booking_payment":
            await db.bookings.update_one({"booking_id": tx["booking_id"]},
                                         {"$set": {"payment_status": "paid", "paid_at": now_utc().isoformat()}})
            await db.transactions.insert_one({
                "tx_id": new_id("tx"), "user_id": tx["user_id"], "type": "booking_payment", "status": "paid",
                "amount": -tx["amount"], "label": f"Booking payment €{tx['amount']:.2f} (Stripe)",
                "booking_id": tx["booking_id"], "created_at": now_utc().isoformat()})
    return {"payment_status": status.payment_status, "status": status.status,
            "amount": tx["amount"], "purpose": tx.get("purpose"), "paid": paid}


@router.get("/payments/status/{session_id}")
async def payment_status(session_id: str, request: Request, user=Depends(get_current_user)):
    stripe, _ = _stripe(request)
    status = await stripe.get_checkout_status(session_id)
    return await _settle_if_paid(session_id, status)


@router.get("/wallet/topup/status/{session_id}")
async def topup_status(session_id: str, request: Request, user=Depends(get_current_user)):
    stripe, _ = _stripe(request)
    status = await stripe.get_checkout_status(session_id)
    return await _settle_if_paid(session_id, status)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe, _ = _stripe(request)
    try:
        event = await stripe.handle_webhook(body, sig)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_webhook")
    if getattr(event, "session_id", None):
        try:
            status = await stripe.get_checkout_status(event.session_id)
            await _settle_if_paid(event.session_id, status)
        except Exception:
            pass
    return {"received": True}
