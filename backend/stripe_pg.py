"""Blocco 3 (Wallet/pagamenti/escrow) — layer Stripe Connect per il backend
Postgres. Decisione presa con l'utente (dopo ricognizione, vedi
`JOBBY_blocco3_proposta_wallet_escrow.md` nel progetto Claude): Stripe Connect
come gateway reale per questo blocco (PayPal a seguire in un secondo giro),
NESSUN fallback a wallet interno — un provider deve completare l'onboarding
Stripe Connect (Express, `stripe_payouts_enabled=true`) prima di poter essere
confermato su una richiesta con binario impresa/piva.

Pattern usato (diverso dal "destination charge" istantaneo di
`payments_split.py` nel sistema Emergent — vedi il docstring di quel file e
l'analisi nel progetto): un vero escrow ha bisogno che i soldi restino sul
saldo della piattaforma al momento dell'addebito e vengano trasferiti al
provider solo più tardi, al completamento del lavoro. Quindi:

  1. CONFIRM  -> `charge_hold()`: PaymentIntent *senza* `transfer_data` (i
     soldi restano sul saldo Stripe di JOBBY) sulla carta salvata dal cliente
     (`users.default_payment_method_id`, impostata via `/pay/setup-card`,
     stesso SetupIntent già presente nel sistema Emergent). Poi
     `create_escrow_hold()` (RPC Postgres) registra il ledger.
  2. COMPLETE -> `release_escrow()` (RPC Postgres, ledger) + `transfer_to_provider()`
     (vero `stripe.Transfer.create(destination=..., amount=...)`, sposta
     davvero il netto sul connected account del provider — stesso codice già
     dimostrato in `payments_connect.py` nel sistema Emergent, qui reso
     automatico invece che azionato manualmente dall'utente).
  3. CANCEL/REFUND -> `refund_escrow()` (RPC, ledger) + `refund_payment_intent()`
     (`stripe.Refund.create(payment_intent=...)`, senza `reverse_transfer`
     perché non c'è stato alcun transfer al momento dell'addebito).

Il binario `persona_lf` (Libretto Famiglia) NON passa da qui: nessun gateway
di pagamento reale, solo il registro `public.lf_ledger` (vedi lf_pg.py).
"""
import os
from typing import Optional

import stripe
from fastapi import HTTPException

CONNECT_KEY = os.environ.get("STRIPE_CONNECT_SECRET_KEY", "")


def _require_key():
    if not CONNECT_KEY:
        raise HTTPException(status_code=503, detail="stripe_connect_not_configured")
    stripe.api_key = CONNECT_KEY


# ---------------- customer (payer) ----------------
def get_or_create_customer(user: dict) -> str:
    """user è la riga public.users del cliente (payer)."""
    cust = user.get("stripe_customer_id")
    if cust:
        return cust
    _require_key()
    c = stripe.Customer.create(email=user.get("email") or None,
                               metadata={"jobby_user_id": user["id"]})
    return c["id"]


def create_setup_session(customer_id: str, origin_url: str) -> dict:
    """Checkout mode=setup — salva una carta per addebiti off_session futuri
    (stesso pattern del `setup-card` Emergent, portato qui)."""
    _require_key()
    origin = (origin_url or "").rstrip("/")
    session = stripe.checkout.Session.create(
        mode="setup", customer=customer_id, payment_method_types=["card"],
        setup_intent_data={"usage": "off_session", "metadata": {"jobby_customer_id": customer_id}},
        success_url=f"{origin}/portafoglio?setup=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/portafoglio?setup=cancel",
    )
    return {"url": session["url"], "session_id": session["id"]}


def get_setup_session_payment_method(session_id: str) -> Optional[str]:
    _require_key()
    sess = stripe.checkout.Session.retrieve(session_id, expand=["setup_intent"])
    si = sess.get("setup_intent")
    return si.get("payment_method") if isinstance(si, dict) else None


# ---------------- provider (connected account) ----------------
def create_connect_account(user: dict) -> str:
    """user è la riga public.users del provider."""
    _require_key()
    acct = stripe.Account.create(
        type="express", country="IT", email=user.get("email") or None,
        business_type="individual", capabilities={"transfers": {"requested": True}},
        metadata={"jobby_user_id": user["id"]},
    )
    return acct["id"]


def create_onboarding_link(account_id: str, origin_url: str) -> str:
    _require_key()
    origin = (origin_url or "").rstrip("/")
    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=f"{origin}/payments-settings?stripe_connect=refresh",
        return_url=f"{origin}/payments-settings?stripe_connect=return",
        type="account_onboarding",
    )
    return link["url"]


def get_account_status(account_id: str) -> dict:
    _require_key()
    acct = stripe.Account.retrieve(account_id)
    return {"details_submitted": bool(acct.get("details_submitted")),
            "payouts_enabled": bool(acct.get("payouts_enabled"))}


# ---------------- escrow: hold / release / refund ----------------
def charge_hold(customer_id: str, payment_method_id: str, amount_eur: float, metadata: dict) -> dict:
    """Addebita `amount_eur` sulla carta salvata del cliente, SENZA
    transfer_data — i soldi restano sul saldo Stripe di JOBBY finché non
    viene chiamato transfer_to_provider() al completamento. Ritorna
    {payment_intent_id, status}. Solleva HTTPException su carta rifiutata o
    altro errore Stripe."""
    _require_key()
    cents = int(round(amount_eur * 100))
    try:
        pi = stripe.PaymentIntent.create(
            amount=cents, currency="eur", customer=customer_id,
            payment_method=payment_method_id, off_session=True, confirm=True,
            metadata=metadata,
        )
    except stripe.error.CardError as e:
        raise HTTPException(status_code=402, detail=f"card_declined: {getattr(e, 'user_message', '') or e}")
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
    return {"payment_intent_id": pi["id"], "status": pi["status"], "raw": pi}


def transfer_to_provider(account_id: str, amount_eur: float, metadata: dict) -> dict:
    """Trasferimento reale del netto al connected account del provider (al
    completamento del lavoro). Stesso `stripe.Transfer.create` già usato in
    payments_connect.py per i prelievi manuali, qui automatico."""
    _require_key()
    cents = int(round(amount_eur * 100))
    try:
        transfer = stripe.Transfer.create(amount=cents, currency="eur", destination=account_id, metadata=metadata)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
    return {"transfer_id": transfer["id"], "raw": transfer}


def refund_payment_intent(payment_intent_id: str, amount_eur: Optional[float] = None) -> dict:
    """Rimborso (parziale o totale) di un hold. Nessun reverse_transfer:
    l'addebito non ha mai avuto transfer_data (vedi charge_hold)."""
    _require_key()
    kwargs = {"payment_intent": payment_intent_id}
    if amount_eur is not None:
        kwargs["amount"] = int(round(amount_eur * 100))
    try:
        refund = stripe.Refund.create(**kwargs)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"stripe_error: {getattr(e, 'user_message', '') or e}")
    return {"refund_id": refund["id"], "raw": refund}
