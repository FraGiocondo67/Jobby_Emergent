"""Blocco 3 (Wallet/pagamenti/escrow) — onboarding Stripe Connect (provider) +
salvataggio carta (cliente), riscrittura Postgres di
routers/payments_connect.py e della parte "setup-card" di
routers/payments_split.py (sistema Emergent/Mongo). Fondamenta condivise da
tutte e quattro le verticali (Artigiani/Pulizie/Babysitting/Driver) per il
binario impresa/piva — vedi stripe_pg.py per il resto del flusso
(hold/release/refund) e il docstring di quel modulo per il perché del design.

Decisione presa con l'utente: nessun fallback a wallet interno — un provider
deve completare questo onboarding (stripe_payouts_enabled=true) prima di
poter essere confermato su una richiesta con binario impresa/piva.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core_pg import db
from deps_pg import get_current_user
import stripe_pg as SP

router = APIRouter()


class OriginIn(BaseModel):
    origin_url: str = ""


# ---------------- provider: onboarding Stripe Connect ----------------
@router.post("/connect/onboarding-link")
async def onboarding_link(body: OriginIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    acct_id = row.data[0].get("stripe_connect_account_id")
    if not acct_id:
        acct_id = SP.create_connect_account(user)
        db.table("profiles_provider").update({"stripe_connect_account_id": acct_id}).eq("user_id", user["id"]).execute()
    url = SP.create_onboarding_link(acct_id, body.origin_url)
    return {"url": url, "account_id": acct_id}


@router.get("/connect/status")
async def connect_status(user=Depends(get_current_user)):
    row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", user["id"]).limit(1).execute()
    acct_id = row.data[0].get("stripe_connect_account_id") if row.data else None
    if not acct_id:
        return {"connected": False, "details_submitted": False, "payouts_enabled": False}
    status = SP.get_account_status(acct_id)
    db.table("profiles_provider").update({
        "stripe_onboarding_completed": status["details_submitted"],
        "stripe_payouts_enabled": status["payouts_enabled"],
    }).eq("user_id", user["id"]).execute()
    return {"connected": True, "account_id": acct_id, **status}


# ---------------- cliente: salvataggio carta per addebiti off_session ----------------
@router.post("/pay/setup-card")
async def setup_card(body: OriginIn, user=Depends(get_current_user)):
    row = db.table("users").select("stripe_customer_id").eq("id", user["id"]).limit(1).execute()
    cust = row.data[0].get("stripe_customer_id") if row.data else None
    if not cust:
        cust = SP.get_or_create_customer(user)
        db.table("users").update({"stripe_customer_id": cust}).eq("id", user["id"]).execute()
    return SP.create_setup_session(cust, body.origin_url)


@router.get("/pay/setup-card/status/{session_id}")
async def setup_card_status(session_id: str, user=Depends(get_current_user)):
    pm = SP.get_setup_session_payment_method(session_id)
    saved = bool(pm)
    if saved:
        db.table("users").update({"default_payment_method_id": pm}).eq("id", user["id"]).execute()
    return {"saved": saved, "payment_method": pm}
