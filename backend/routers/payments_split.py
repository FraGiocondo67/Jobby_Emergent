"""JOBBY — Pagamenti reali con split marketplace (Spec 3, punto 1).

Aggancia il pagamento REALE alla conferma di una richiesta (tutte le categorie,
collection condivisa `db.richieste`) sul binario `impresa`/`piva`:

  • Stripe Connect **destination charge**: il cliente paga l'intero importo,
    JOBBY trattiene la fee intera come `application_fee_amount`, il provider
    (connected account Express) riceve il netto tramite `transfer_data.destination`.
  • PayPal **Orders v2 multiparty**: `payee` = provider, `platform_fees` = fee JOBBY.
  • Rimborsi con `reverse_transfer` + `refund_application_fee` (Stripe) e
    `platform_fees` (PayPal), usati da annulli/contestazioni.
  • Ricorrenti: SetupIntent `off_session` (via Checkout mode=setup) + addebito
    automatico su carta salvata prima di ogni visita.

Il binario `persona_lf` (Libretto Famiglia) NON passa dal PSP: usa i voucher INPS
(borsellino) gestiti altrove.

Fallback: se il provider non è ancora onboardato su Stripe Connect / PayPal, si usa
un escrow **simulato** sul wallet (così i flussi demo restano testabili E2E).
"""
import os
import logging

import stripe
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user, require_admin
from routers.notifications import push_notification

router = APIRouter()
logger = logging.getLogger(__name__)

CONNECT_KEY = os.environ.get("STRIPE_CONNECT_SECRET_KEY", "")
IS_TEST = CONNECT_KEY.startswith("sk_test")

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_BASE = os.environ.get("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")

PSP_STATES_PAYABLE = ("psp_pending", "none", "authorized")


# ---------------- models ----------------
class CheckoutIn(BaseModel):
    method: str = "stripe"          # stripe | paypal | wallet
    origin_url: str = ""


class OriginIn(BaseModel):
    origin_url: str = ""


class RefundIn(BaseModel):
    amount: float | None = None     # None => rimborso integrale
    reason: str = ""


# ---------------- helpers ----------------
def _require_stripe():
    if not CONNECT_KEY:
        raise HTTPException(status_code=503, detail="stripe_connect_not_configured")
    stripe.api_key = CONNECT_KEY


async def _paypal_token(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{PAYPAL_BASE}/v1/oauth2/token",
                          data={"grant_type": "client_credentials"},
                          auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET))
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="paypal_auth_failed")
    return r.json()["access_token"]


async def _load_payable_richiesta(rid: str, user: dict) -> dict:
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    if r.get("cliente_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if not r.get("provider_scelto"):
        raise HTTPException(status_code=400, detail="not_confirmed")
    if r.get("binario") == "persona_lf":
        raise HTTPException(status_code=400, detail="lf_uses_voucher_not_psp")
    pl = r.get("pagamento_lavoro", {}) or {}
    if pl.get("stato") in ("held", "charged", "released"):
        raise HTTPException(status_code=400, detail="already_paid")
    return r


def _amounts(r: dict) -> dict:
    """Ricava gli importi dello split dalla proposta scelta.
    charge = prezzo_finale (quanto paga il cliente)
    jobby_fee = fee JOBBY intera (application_fee)
    provider_net = charge - jobby_fee (quanto riceve il provider)."""
    prop = next((p for p in r.get("proposte", []) if p.get("provider_id") == r.get("provider_scelto")), None)
    bd = (prop or {}).get("breakdown", {}) if prop else {}
    charge = round(float(r.get("prezzo_finale") or (prop or {}).get("price") or bd.get("total_client", 0)), 2)
    jobby_fee = round(float(bd.get("jobby_fee", 0)), 2)
    if jobby_fee <= 0 or jobby_fee >= charge:
        # difesa: fee non valida -> ricava dalla differenza col netto se presente
        provider_net = round(float(bd.get("provider_net", 0)), 2)
        if provider_net and provider_net < charge:
            jobby_fee = round(charge - provider_net, 2)
    provider_net = round(charge - jobby_fee, 2)
    return {"charge": charge, "jobby_fee": jobby_fee, "provider_net": provider_net}


async def _provider(r: dict) -> dict:
    p = await db.users.find_one({"user_id": r["provider_scelto"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=400, detail="provider_not_found")
    return p


async def _set_pagamento(rid: str, patch: dict):
    fields = {f"pagamento_lavoro.{k}": v for k, v in patch.items()}
    fields["updated_at"] = now_utc().isoformat()
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": fields})


# ==================================================================
# 1) CHECKOUT — avvia il pagamento reale (o simulato) alla conferma
# ==================================================================
@router.post("/pay/richiesta/{rid}/checkout")
async def start_checkout(rid: str, body: CheckoutIn, user=Depends(get_current_user)):
    r = await _load_payable_richiesta(rid, user)
    amt = _amounts(r)
    if amt["charge"] <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    prov = await _provider(r)
    origin = (body.origin_url or "").rstrip("/")

    # ---- Stripe destination charge (Checkout hosted) ----
    if body.method == "stripe":
        acct = prov.get("stripe_connect_account_id")
        if not acct or not prov.get("stripe_payouts_enabled"):
            raise HTTPException(status_code=400, detail="provider_not_onboarded_stripe")
        _require_stripe()
        cents = int(round(amt["charge"] * 100))
        fee_cents = int(round(amt["jobby_fee"] * 100))
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {"currency": "eur",
                                   "product_data": {"name": f"JOBBY · {r.get('category_label', r.get('category', 'Servizio'))}"},
                                   "unit_amount": cents},
                    "quantity": 1,
                }],
                payment_intent_data={
                    "application_fee_amount": fee_cents,
                    "transfer_data": {"destination": acct},
                    "metadata": {"richiesta_id": rid, "purpose": "richiesta_split"},
                },
                success_url=f"{origin}/richiesta/{rid}?pay=success&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{origin}/richiesta/{rid}?pay=cancel",
                metadata={"richiesta_id": rid, "user_id": user["user_id"], "purpose": "richiesta_split"},
            )
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
        await db.payment_transactions.insert_one({
            "session_id": session["id"], "provider": "stripe", "kind": "richiesta_split",
            "richiesta_id": rid, "user_id": user["user_id"], "provider_id": r["provider_scelto"],
            "amount": amt["charge"], "jobby_fee": amt["jobby_fee"], "provider_net": amt["provider_net"],
            "currency": "eur", "payment_status": "initiated", "status": "open", "credited": False,
            "created_at": now_utc().isoformat(),
        })
        await _set_pagamento(rid, {"stato": "psp_pending", "psp": "stripe", "stripe_session_id": session["id"],
                                   "importo": amt["provider_net"], "jobby_fee_total": amt["jobby_fee"]})
        return {"url": session["url"], "session_id": session["id"], "method": "stripe"}

    # ---- PayPal Orders v2 multiparty (payee + platform_fees) ----
    if body.method == "paypal":
        payee_email = prov.get("paypal_email")
        payee_merchant = prov.get("paypal_merchant_id")
        if not payee_email and not payee_merchant:
            raise HTTPException(status_code=400, detail="provider_not_onboarded_paypal")
        payee = {"merchant_id": payee_merchant} if payee_merchant else {"email_address": payee_email}
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _paypal_token(client)
            r_ord = await client.post(
                f"{PAYPAL_BASE}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "reference_id": rid,
                        "amount": {"currency_code": "EUR", "value": f"{amt['charge']:.2f}"},
                        "payee": payee,
                        "payment_instruction": {
                            "disbursement_mode": "INSTANT",
                            "platform_fees": [{
                                "amount": {"currency_code": "EUR", "value": f"{amt['jobby_fee']:.2f}"}
                            }],
                        },
                    }],
                    "application_context": {
                        "brand_name": "JOBBY", "user_action": "PAY_NOW",
                        "return_url": f"{origin}/richiesta/{rid}?pay=success",
                        "cancel_url": f"{origin}/richiesta/{rid}?pay=cancel",
                    },
                })
        if r_ord.status_code not in (200, 201):
            logger.warning("paypal order failed: %s", r_ord.text)
            raise HTTPException(status_code=502, detail="paypal_order_failed")
        data = r_ord.json()
        order_id = data["id"]
        approve = next((l["href"] for l in data.get("links", []) if l["rel"] in ("approve", "payer-action")), None)
        await db.payment_transactions.insert_one({
            "session_id": order_id, "provider": "paypal", "kind": "richiesta_split",
            "richiesta_id": rid, "user_id": user["user_id"], "provider_id": r["provider_scelto"],
            "amount": amt["charge"], "jobby_fee": amt["jobby_fee"], "provider_net": amt["provider_net"],
            "currency": "eur", "payment_status": "initiated", "status": "open", "credited": False,
            "created_at": now_utc().isoformat(),
        })
        await _set_pagamento(rid, {"stato": "psp_pending", "psp": "paypal", "paypal_order_id": order_id,
                                   "importo": amt["provider_net"], "jobby_fee_total": amt["jobby_fee"]})
        return {"url": approve, "order_id": order_id, "method": "paypal"}

    # ---- Fallback simulato su wallet (escrow) ----
    if body.method == "wallet":
        bal = round(float(user.get("wallet_balance", 0)), 2)
        if bal < amt["charge"]:
            raise HTTPException(status_code=400, detail="insufficient_wallet")
        await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"wallet_balance": -amt["charge"]}})
        await db.transactions.insert_one({
            "tx_id": new_id("tx"), "user_id": user["user_id"], "type": "booking_payment", "status": "held",
            "amount": -amt["charge"], "label": f"Pagamento servizio €{amt['charge']:.2f} (in garanzia)",
            "richiesta_id": rid, "created_at": now_utc().isoformat()})
        await _set_pagamento(rid, {"stato": "held", "psp": "simulato", "importo": amt["provider_net"],
                                   "jobby_fee_total": amt["jobby_fee"], "charge": amt["charge"],
                                   "held_at": now_utc().isoformat()})
        await push_notification(r["provider_scelto"], "pagamento_garanzia", "Pagamento in garanzia",
                                f"Il cliente ha versato €{amt['charge']:.2f} in garanzia.", "richiesta", rid)
        return {"status": "held", "simulated": True, "provider_net": amt["provider_net"]}

    raise HTTPException(status_code=400, detail="invalid_method")


# ==================================================================
# 2) SETTLEMENT — verifica esito e registra escrow
# ==================================================================
async def _settle_stripe(session_id: str) -> dict:
    tx = await db.payment_transactions.find_one({"session_id": session_id, "provider": "stripe"}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="tx_not_found")
    _require_stripe()
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
    paid = sess.get("payment_status") == "paid"
    await db.payment_transactions.update_one({"session_id": session_id},
                                             {"$set": {"payment_status": sess.get("payment_status"),
                                                       "status": sess.get("status"),
                                                       "payment_intent": sess.get("payment_intent")}})
    if paid and not tx.get("credited"):
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"credited": True}})
        await _set_pagamento(tx["richiesta_id"], {"stato": "held", "stripe_payment_intent": sess.get("payment_intent"),
                                                  "held_at": now_utc().isoformat()})
        await push_notification(tx["provider_id"], "pagamento_ok", "Pagamento ricevuto",
                                f"Il cliente ha pagato €{tx['amount']:.2f}. Netto per te €{tx['provider_net']:.2f}.",
                                "richiesta", tx["richiesta_id"])
    return {"paid": paid, "payment_status": sess.get("payment_status"), "richiesta_id": tx["richiesta_id"]}


@router.get("/pay/stripe/status/{session_id}")
async def stripe_status(session_id: str, user=Depends(get_current_user)):
    return await _settle_stripe(session_id)


@router.post("/pay/paypal/capture/{order_id}")
async def paypal_capture(order_id: str, user=Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": order_id, "provider": "paypal"}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="tx_not_found")
    if tx["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _paypal_token(client)
        r = await client.post(f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
                              headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    data = r.json() if r.content else {}
    completed = r.status_code in (200, 201) and data.get("status") == "COMPLETED"
    capture_id = None
    try:
        capture_id = data["purchase_units"][0]["payments"]["captures"][0]["id"]
    except Exception:
        pass
    await db.payment_transactions.update_one({"session_id": order_id},
                                             {"$set": {"payment_status": "paid" if completed else "pending",
                                                       "status": "complete" if completed else "open",
                                                       "capture_id": capture_id}})
    if completed and not tx.get("credited"):
        await db.payment_transactions.update_one({"session_id": order_id}, {"$set": {"credited": True}})
        await _set_pagamento(tx["richiesta_id"], {"stato": "held", "paypal_capture_id": capture_id,
                                                  "held_at": now_utc().isoformat()})
        await push_notification(tx["provider_id"], "pagamento_ok", "Pagamento ricevuto",
                                f"Il cliente ha pagato €{tx['amount']:.2f} (PayPal).", "richiesta", tx["richiesta_id"])
    return {"paid": completed, "richiesta_id": tx["richiesta_id"]}


# ==================================================================
# 3) RELEASE (solo escrow simulato) — accredita il netto al provider
# ==================================================================
@router.post("/pay/richiesta/{rid}/release")
async def release_simulated(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    if user["user_id"] not in (r.get("cliente_id"), r.get("provider_scelto")):
        raise HTTPException(status_code=403, detail="forbidden")
    pl = r.get("pagamento_lavoro", {}) or {}
    if pl.get("psp") != "simulato" or pl.get("stato") != "held":
        raise HTTPException(status_code=400, detail="not_releasable")
    net = round(float(pl.get("importo", 0)), 2)
    await db.users.update_one({"user_id": r["provider_scelto"]}, {"$inc": {"wallet_balance": net}})
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": r["provider_scelto"], "type": "earning", "status": "available",
        "amount": net, "label": f"Compenso €{net:.2f} (accreditato)", "richiesta_id": rid,
        "created_at": now_utc().isoformat()})
    await _set_pagamento(rid, {"stato": "released", "released_at": now_utc().isoformat()})
    return {"stato": "released", "importo": net}


# ==================================================================
# 4) REFUND — annulli / contestazioni (reverse_transfer + fee refund)
# ==================================================================
@router.post("/pay/richiesta/{rid}/refund")
async def refund_richiesta(rid: str, body: RefundIn, _=Depends(require_admin)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    pl = r.get("pagamento_lavoro", {}) or {}
    if pl.get("stato") not in ("held", "charged", "released"):
        raise HTTPException(status_code=400, detail="nothing_to_refund")
    psp = pl.get("psp")

    if psp == "stripe":
        _require_stripe()
        pi = pl.get("stripe_payment_intent")
        if not pi:
            raise HTTPException(status_code=400, detail="no_payment_intent")
        kwargs = {"payment_intent": pi, "reverse_transfer": True, "refund_application_fee": True,
                  "metadata": {"richiesta_id": rid}}
        if body.amount is not None:
            kwargs["amount"] = int(round(float(body.amount) * 100))
        try:
            refund = stripe.Refund.create(**kwargs)
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
        await _set_pagamento(rid, {"stato": "refunded", "refund_id": refund["id"], "refunded_at": now_utc().isoformat()})
        return {"refunded": True, "refund_id": refund["id"], "psp": "stripe"}

    if psp == "paypal":
        capture_id = pl.get("paypal_capture_id")
        if not capture_id:
            raise HTTPException(status_code=400, detail="no_capture")
        refund_body = {}
        if body.amount is not None:
            refund_body["amount"] = {"value": f"{float(body.amount):.2f}", "currency_code": "EUR"}
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _paypal_token(client)
            rr = await client.post(f"{PAYPAL_BASE}/v2/payments/captures/{capture_id}/refund",
                                   headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                   json=refund_body)
        if rr.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="paypal_refund_failed")
        await _set_pagamento(rid, {"stato": "refunded", "refund_id": rr.json().get("id"),
                                   "refunded_at": now_utc().isoformat()})
        return {"refunded": True, "psp": "paypal"}

    # simulato: riaccredita al cliente l'importo trattenuto
    amount = round(float(body.amount if body.amount is not None else pl.get("charge", 0)), 2)
    await db.users.update_one({"user_id": r["cliente_id"]}, {"$inc": {"wallet_balance": amount}})
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": r["cliente_id"], "type": "refund", "status": "available",
        "amount": amount, "label": f"Rimborso €{amount:.2f}", "richiesta_id": rid,
        "created_at": now_utc().isoformat()})
    await _set_pagamento(rid, {"stato": "refunded", "refunded_at": now_utc().isoformat()})
    return {"refunded": True, "psp": "simulato", "amount": amount}


# ==================================================================
# 5) RICORRENTI — SetupIntent off_session + addebito automatico
# ==================================================================
@router.post("/pay/setup-card")
async def setup_card(body: OriginIn, user=Depends(get_current_user)):
    """Avvia il salvataggio carta per addebiti off_session (ricorrenze).
    Usa Checkout mode=setup così funziona anche su web/Expo Go via redirect."""
    _require_stripe()
    origin = (body.origin_url or "").rstrip("/")
    cust = user.get("stripe_customer_id")
    if not cust:
        c = stripe.Customer.create(email=user.get("email") or None,
                                   metadata={"jobby_user_id": user["user_id"]})
        cust = c["id"]
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"stripe_customer_id": cust}})
    session = stripe.checkout.Session.create(
        mode="setup", customer=cust, payment_method_types=["card"],
        setup_intent_data={"usage": "off_session", "metadata": {"jobby_user_id": user["user_id"]}},
        success_url=f"{origin}/portafoglio?setup=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/portafoglio?setup=cancel",
    )
    await db.payment_transactions.insert_one({
        "session_id": session["id"], "provider": "stripe", "kind": "setup_card",
        "user_id": user["user_id"], "status": "open", "created_at": now_utc().isoformat()})
    return {"url": session["url"], "session_id": session["id"]}


@router.get("/pay/setup-card/status/{session_id}")
async def setup_card_status(session_id: str, user=Depends(get_current_user)):
    _require_stripe()
    sess = stripe.checkout.Session.retrieve(session_id, expand=["setup_intent"])
    si = sess.get("setup_intent")
    pm = si.get("payment_method") if isinstance(si, dict) else None
    saved = bool(pm)
    if saved:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"default_payment_method_id": pm,
                                            "stripe_customer_id": sess.get("customer")}})
    return {"saved": saved, "payment_method": pm}


@router.post("/pay/richiesta/{rid}/charge-recurring")
async def charge_recurring(rid: str, user=Depends(get_current_user)):
    """Addebito automatico off_session per la visita ricorrente successiva
    (destination charge su carta salvata). Chiamato dallo scheduler 48h prima."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("cliente_id") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r.get("binario") == "persona_lf":
        raise HTTPException(status_code=400, detail="lf_uses_voucher_not_psp")
    cust = user.get("stripe_customer_id")
    pm = user.get("default_payment_method_id")
    if not cust or not pm:
        raise HTTPException(status_code=400, detail="no_saved_card")
    prov = await _provider(r)
    acct = prov.get("stripe_connect_account_id")
    if not acct or not prov.get("stripe_payouts_enabled"):
        raise HTTPException(status_code=400, detail="provider_not_onboarded_stripe")
    amt = _amounts(r)
    _require_stripe()
    try:
        pi = stripe.PaymentIntent.create(
            amount=int(round(amt["charge"] * 100)), currency="eur",
            customer=cust, payment_method=pm, off_session=True, confirm=True,
            application_fee_amount=int(round(amt["jobby_fee"] * 100)),
            transfer_data={"destination": acct},
            metadata={"richiesta_id": rid, "purpose": "richiesta_recurring"},
        )
    except stripe.error.CardError as e:
        raise HTTPException(status_code=402, detail=f"card_declined: {getattr(e, 'user_message', '') or e}")
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
    await _set_pagamento(rid, {"stato": "held", "psp": "stripe", "stripe_payment_intent": pi["id"],
                               "importo": amt["provider_net"], "jobby_fee_total": amt["jobby_fee"],
                               "held_at": now_utc().isoformat(), "recurring": True})
    return {"paid": pi["status"] == "succeeded", "payment_intent": pi["id"], "status": pi["status"]}
