"""Wallet-based escrow for richieste (pulizie / babysitting / driver / artigiani).

Product model:
  - At CONFIRM the client's funds are blocked immediately (bonus first, then wallet_balance).
    If funds are not enough the action is rejected (insufficient_wallet) so the amount is
    always guaranteed.
  - At COMPLETION the net (after JOBBY fee) is released to the earner. Professionals
    (role=provider) receive it in pending_balance with a 24h hold before it becomes
    available/withdrawable (dispute window). Businesses (role=business) receive it as
    available immediately.
  - Cancellation / dispute in favour of the client refunds the still-held amount.

Optional "QR / codice consegna" guarantee (client preference qr_confirm_enabled): the release
is armed instead of executed — the client shows a QR/6-digit code, the earner scans/enters it
(see confirm_delivery.py) to release. Auto-releases after 24h if never confirmed.

Escrow state on the richiesta doc under `escrow`:
  {stato: held|released|refunded, held, from_bonus, from_wallet, net_provider, gross,
   shortfall, released_at, refunded_at}
"""
from datetime import timedelta

from fastapi import HTTPException

from core import db, now_utc, new_id

HOLD_HOURS = 24  # professionals: earnings usable/withdrawable only after 24h


async def _tx(user_id, ttype, amount, label, ref=None, status="ok"):
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": user_id, "type": ttype, "status": status,
        "amount": round(float(amount), 2), "label": label, "richiesta_id": ref,
        "created_at": now_utc().isoformat()})


async def credit_earner(earner_id: str, net: float, ref_id: str, label: str = "Compenso"):
    """Credit the net to the earner. Professionals -> pending_balance + 24h hold;
    businesses -> available immediately."""
    net = round(float(net), 2)
    if net <= 0 or not earner_id:
        return
    prov = await db.users.find_one({"user_id": earner_id}, {"_id": 0})
    is_business = bool(prov and prov.get("role") == "business")
    if is_business:
        await db.users.update_one({"user_id": earner_id}, {"$inc": {"wallet_balance": net}})
        await _tx(earner_id, "earning", net, f"{label} €{net:.2f} (disponibile)", ref_id, "available")
    else:
        release_at = (now_utc() + timedelta(hours=HOLD_HOURS)).isoformat()
        await db.users.update_one({"user_id": earner_id}, {"$inc": {"pending_balance": net}})
        await db.wallet_holds.insert_one({
            "hold_id": new_id("hold"), "user_id": earner_id, "richiesta_id": ref_id,
            "amount": net, "status": "pending", "release_at": release_at,
            "created_at": now_utc().isoformat()})
        await _tx(earner_id, "earning", net, f"{label} €{net:.2f} (disponibile tra 24h)", ref_id, "pending")


# ---------------- client-side blocking ----------------
async def _deduct(client_id: str, amount: float, ref: str, label: str, best_effort: bool = False):
    amount = round(float(amount), 2)
    if amount <= 0:
        return 0.0, 0.0, 0.0
    u = await db.users.find_one({"user_id": client_id}, {"_id": 0})
    bonus = round(float((u or {}).get("bonus_credit", 0)), 2)
    bal = round(float((u or {}).get("wallet_balance", 0)), 2)
    if bonus + bal + 1e-6 < amount:
        if not best_effort:
            raise HTTPException(status_code=400, detail="insufficient_wallet")
        amount = round(bonus + bal, 2)
        if amount <= 0:
            return 0.0, 0.0, 0.0
    from_bonus = round(min(bonus, amount), 2)
    from_wallet = round(amount - from_bonus, 2)
    inc = {}
    if from_bonus:
        inc["bonus_credit"] = -from_bonus
    if from_wallet:
        inc["wallet_balance"] = -from_wallet
    if inc:
        await db.users.update_one({"user_id": client_id}, {"$inc": inc})
    await _tx(client_id, "escrow_hold", -amount, label, ref, "held")
    return from_bonus, from_wallet, amount


def _merge(esc, from_bonus, from_wallet, amount):
    esc = esc or {"stato": "held", "held": 0.0, "from_bonus": 0.0, "from_wallet": 0.0}
    esc["stato"] = "held"
    esc["held"] = round(float(esc.get("held", 0)) + amount, 2)
    esc["from_bonus"] = round(float(esc.get("from_bonus", 0)) + from_bonus, 2)
    esc["from_wallet"] = round(float(esc.get("from_wallet", 0)) + from_wallet, 2)
    return esc


async def hold(r: dict, amount: float, label: str) -> dict:
    """Block `amount` from the client and merge into the richiesta escrow. Raises 400
    insufficient_wallet if the client cannot cover it."""
    rid = r["richiesta_id"]
    fb, fw, amt = await _deduct(r["cliente_id"], amount, rid, label)
    esc = _merge(r.get("escrow"), fb, fw, amt)
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"escrow": esc}})
    return esc


async def _refund_surplus(r: dict, surplus: float):
    rid = r["richiesta_id"]
    surplus = round(float(surplus), 2)
    if surplus <= 0:
        return
    await db.users.update_one({"user_id": r["cliente_id"]}, {"$inc": {"wallet_balance": surplus}})
    await _tx(r["cliente_id"], "refund", surplus, f"Conguaglio rimborso €{surplus:.2f}", rid, "available")
    esc = r.get("escrow") or {}
    esc["held"] = round(max(0.0, float(esc.get("held", 0)) - surplus), 2)
    esc["from_wallet"] = round(max(0.0, float(esc.get("from_wallet", 0)) - surplus), 2)
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"escrow": esc}})


async def refund(r: dict, label: str = "Rimborso garanzia") -> bool:
    """Refund the entire still-held escrow to the client (cancel / dispute won)."""
    esc = r.get("escrow")
    if not esc or esc.get("stato") != "held":
        return False
    rid = r["richiesta_id"]
    inc = {}
    if esc.get("from_bonus"):
        inc["bonus_credit"] = round(float(esc["from_bonus"]), 2)
    if esc.get("from_wallet"):
        inc["wallet_balance"] = round(float(esc["from_wallet"]), 2)
    if inc:
        await db.users.update_one({"user_id": r["cliente_id"]}, {"$inc": inc})
    await _tx(r["cliente_id"], "refund", round(float(esc.get("held", 0)), 2),
              f"{label} €{float(esc.get('held', 0)):.2f}", rid, "available")
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"escrow.stato": "refunded",
                                            "escrow.refunded_at": now_utc().isoformat()}})
    return True


async def conguaglio(r: dict, final_gross: float) -> float:
    """Adjust the held pool to `final_gross` (refund surplus / best-effort block the extra).
    Returns the collectable gross actually held after adjustment."""
    esc = r.get("escrow") or {}
    rid = r["richiesta_id"]
    final_gross = round(float(final_gross), 2)
    held = round(float(esc.get("held", 0)), 2)
    if final_gross < held:
        await _refund_surplus(r, round(held - final_gross, 2))
    elif final_gross > held:
        diff = round(final_gross - held, 2)
        fb, fw, blocked = await _deduct(r["cliente_id"], diff, rid, "Conguaglio corsa", best_effort=True)
        esc = _merge(r.get("escrow"), fb, fw, blocked)
        if blocked < diff:
            esc["shortfall"] = round(float(esc.get("shortfall", 0)) + (diff - blocked), 2)
        await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"escrow": esc}})
    r2 = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    return round(float((r2.get("escrow") or {}).get("held", 0)), 2)


async def release_richiesta(r: dict, net: float, label: str = "Compenso") -> float:
    """Release an exact net amount to the earner and mark the escrow released. Idempotent."""
    esc = r.get("escrow")
    if not esc or esc.get("stato") != "held":
        return 0.0
    net = round(float(net), 2)
    await credit_earner(r.get("provider_scelto"), net, r["richiesta_id"], label)
    await db.richieste.update_one({"richiesta_id": r["richiesta_id"]},
                                  {"$set": {"escrow.stato": "released",
                                            "escrow.released_at": now_utc().isoformat(),
                                            "escrow.net_provider": net}})
    return net
