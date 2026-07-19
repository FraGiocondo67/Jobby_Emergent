"""Stripe Connect (Express) — real provider onboarding + payouts (test mode).

Uses a dedicated raw Stripe secret key (STRIPE_CONNECT_SECRET_KEY) separate from the
Emergent-proxied Checkout key used for wallet top-ups.
"""
import os
import time
import logging

import stripe
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

CONNECT_KEY = os.environ.get("STRIPE_CONNECT_SECRET_KEY", "")
IS_TEST = CONNECT_KEY.startswith("sk_test")


class OriginIn(BaseModel):
    origin_url: str


class StripeWithdrawIn(BaseModel):
    amount: float


def _require_key():
    if not CONNECT_KEY:
        raise HTTPException(status_code=503, detail="stripe_connect_not_configured")
    stripe.api_key = CONNECT_KEY


async def _get_or_create_account(user: dict) -> str:
    acct_id = user.get("stripe_connect_account_id")
    if acct_id:
        return acct_id
    acct = stripe.Account.create(
        type="express",
        country="IT",
        email=user.get("email") or None,
        business_type="individual",
        capabilities={"transfers": {"requested": True}},
        metadata={"jobby_user_id": user["user_id"]},
    )
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"stripe_connect_account_id": acct["id"]}})
    return acct["id"]


@router.post("/connect/onboarding-link")
async def onboarding_link(body: OriginIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    _require_key()
    try:
        acct_id = await _get_or_create_account(user)
        origin = body.origin_url.rstrip("/")
        link = stripe.AccountLink.create(
            account=acct_id,
            refresh_url=f"{origin}/payments-settings?stripe_connect=refresh",
            return_url=f"{origin}/payments-settings?stripe_connect=return",
            type="account_onboarding",
        )
        return {"url": link["url"], "account_id": acct_id}
    except stripe.error.StripeError as e:
        logger.warning("connect onboarding failed: %s", e)
        raise HTTPException(status_code=502, detail=str(getattr(e, "user_message", "") or e))


@router.get("/connect/status")
async def connect_status(user=Depends(get_current_user)):
    acct_id = user.get("stripe_connect_account_id")
    if not acct_id:
        return {"connected": False, "details_submitted": False, "payouts_enabled": False}
    _require_key()
    try:
        acct = stripe.Account.retrieve(acct_id)
        details = bool(acct.get("details_submitted"))
        payouts = bool(acct.get("payouts_enabled"))
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"stripe_onboarding_completed": details, "stripe_payouts_enabled": payouts}})
        return {"connected": True, "account_id": acct_id, "details_submitted": details, "payouts_enabled": payouts}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(getattr(e, "user_message", "") or e))


@router.post("/wallet/withdraw/stripe")
async def withdraw_stripe(body: StripeWithdrawIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    amount = round(float(body.amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    available = round(user.get("wallet_balance", 0), 2)
    if amount > available:
        raise HTTPException(status_code=400, detail="insufficient_available")
    acct_id = user.get("stripe_connect_account_id")
    if not acct_id:
        raise HTTPException(status_code=400, detail="no_connect_account")
    _require_key()
    # Confirm payouts are enabled on the connected account.
    try:
        acct = stripe.Account.retrieve(acct_id)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not acct.get("payouts_enabled"):
        raise HTTPException(status_code=400, detail="payouts_not_enabled")

    cents = int(round(amount * 100))
    # In test mode the platform balance is usually 0, so fund it with an
    # immediately-available test charge before transferring to the provider.
    if IS_TEST:
        try:
            stripe.Charge.create(amount=cents, currency="eur", source="tok_bypassPending",
                                 description=f"JOBBY test balance for payout {user['user_id']}")
        except stripe.error.StripeError as e:
            logger.info("test balance top-up skipped: %s", e)

    try:
        transfer = stripe.Transfer.create(
            amount=cents, currency="eur", destination=acct_id,
            metadata={"jobby_user_id": user["user_id"]},
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(getattr(e, "user_message", "") or e))

    new_balance = round(available - amount, 2)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": user["user_id"], "type": "payout", "status": "paid",
        "label": f"Payout Stripe €{amount:.2f}", "amount": -amount,
        "stripe_transfer_id": transfer["id"], "created_at": now_utc().isoformat(),
    })
    return {"status": "paid", "amount": amount, "transfer_id": transfer["id"], "balance": new_balance}
