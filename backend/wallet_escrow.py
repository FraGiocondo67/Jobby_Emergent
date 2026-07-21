"""Wallet-based escrow for richieste (pulizie / babysitting / driver / artigiani).

Model requested by the product owner:
  - At CONFIRM / ORDER the client's funds are blocked immediately (bonus first, then
    wallet_balance). If funds are not enough the action is rejected (insufficient_wallet)
    so the amount is always guaranteed.
  - At COMPLETION (provider/business declares the service done) the net (after JOBBY fee)
    is released to the earner. Professionals (role=provider) receive it in pending_balance
    with a 24h hold before it becomes available/withdrawable (dispute window). Businesses
    (role=business) receive it as available immediately.
  - Cancellation / dispute in favour of the client refunds the still-held amount.

The escrow state lives on the richiesta document under `escrow`:
  {stato: held|released|refunded, held, from_bonus, from_wallet, net_provider, gross,
   shortfall, released_at, refunded_at}

Wallet ledger fields on the user doc:
  wallet_balance  -> AVAILABLE (spendable / withdrawable)
  bonus_credit    -> in-app promotional credit (spent first)
  pending_balance -> BLOCKED provider earnings awaiting the 24h hold
"""
from datetime import timedelta

from fastapi import HTTPException

from core import db, now_utc, new_id

HOLD_HOURS = 24  # professionals: funds usable/withdrawable only after 24h


async def _tx(user_id, ttype, amount, label, rid=None, status="ok"):
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": user_id, "type": ttype, "status": status,
        "amount": round(float(amount), 2), "label": label, "richiesta_id": rid,
        "created_at": now_utc().isoformat()})


async def _reload(rid):
    return await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})


async def _deduct(client_id: str, amount: float, rid: str, label: str) -> tuple:
    """Block `amount` from the client (bonus first, then wallet). 400 if not enough.
    Returns (from_bonus, from_wallet, blocked_amount). If `partial` is allowed the caller
    must pre-check; here we always require the full amount."""
    amount = round(float(amount), 2)
    if amount <= 0:
        return 0.0, 0.0, 0.0
    u = await db.users.find_one({"user_id": client_id}, {"_id": 0})
    bonus = round(float((u or {}).get("bonus_credit", 0)), 2)
    bal = round(float((u or {}).get("wallet_balance", 0)), 2)
    if bonus + bal + 1e-6 < amount:
        raise HTTPException(status_code=400, detail="insufficient_wallet")
    from_bonus = round(min(bonus, amount), 2)
    from_wallet = round(amount - from_bonus, 2)
    inc = {}
    if from_bonus:
        inc["bonus_credit"] = -from_bonus
    if from_wallet:
        inc["wallet_balance"] = -from_wallet
    if inc:
        await db.users.update_one({"user_id": client_id}, {"$inc": inc})
    await _tx(client_id, "escrow_hold", -amount, label, rid, "held")
    return from_bonus, from_wallet, amount


async def _deduct_best_effort(client_id: str, amount: float, rid: str, label: str) -> tuple:
    """Block up to `amount` from the client (used for taxi/overtime conguaglio). Never raises.
    Returns (from_bonus, from_wallet, blocked_amount)."""
    amount = round(float(amount), 2)
    if amount <= 0:
        return 0.0, 0.0, 0.0
    u = await db.users.find_one({"user_id": client_id}, {"_id": 0})
    bonus = round(float((u or {}).get("bonus_credit", 0)), 2)
    bal = round(float((u or {}).get("wallet_balance", 0)), 2)
    blocked = round(min(amount, bonus + bal), 2)
    if blocked <= 0:
        return 0.0, 0.0, 0.0
    from_bonus = round(min(bonus, blocked), 2)
    from_wallet = round(blocked - from_bonus, 2)
    inc = {}
    if from_bonus:
        inc["bonus_credit"] = -from_bonus
    if from_wallet:
        inc["wallet_balance"] = -from_wallet
    if inc:
        await db.users.update_one({"user_id": client_id}, {"$inc": inc})
    await _tx(client_id, "escrow_hold", -blocked, label, rid, "held")
    return from_bonus, from_wallet, blocked


def _merge(esc: dict, from_bonus: float, from_wallet: float, amount: float) -> dict:
    esc = esc or {"stato": "held", "held": 0.0, "from_bonus": 0.0, "from_wallet": 0.0}
    esc["stato"] = "held"
    esc["held"] = round(float(esc.get("held", 0)) + amount, 2)
    esc["from_bonus"] = round(float(esc.get("from_bonus", 0)) + from_bonus, 2)
    esc["from_wallet"] = round(float(esc.get("from_wallet", 0)) + from_wallet, 2)
    return esc


async def hold(r: dict, amount: float, label: str) -> dict:
    """Block `amount` from the client and merge it into the richiesta escrow. Raises 400
    insufficient_wallet if the client cannot cover it. Returns the updated escrow dict."""
    rid = r["richiesta_id"]
    fb, fw, amt = await _deduct(r["cliente_id"], amount, rid, label)
    esc = _merge(r.get("escrow"), fb, fw, amt)
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"escrow": esc}})
    return esc


async def _refund_surplus(r: dict, surplus: float):
    """Give `surplus` back to the client (wallet_balance) and shrink the escrow held pool."""
    rid = r["richiesta_id"]
    surplus = round(float(surplus), 2)
    if surplus <= 0:
        return
    await db.users.update_one({"user_id": r["cliente_id"]}, {"$inc": {"wallet_balance": surplus}})
    await _tx(r["cliente_id"], "refund", surplus, f"Conguaglio rimborso €{surplus:.2f}", rid, "available")
    esc = r.get("escrow") or {}
    new_held = round(max(0.0, float(esc.get("held", 0)) - surplus), 2)
    # surplus comes back to the wallet side of the ledger
    esc["held"] = new_held
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


async def _credit_provider(r: dict, net: float, label: str):
    provider_id = r.get("provider_scelto")
    rid = r["richiesta_id"]
    net = round(float(net), 2)
    prov = await db.users.find_one({"user_id": provider_id}, {"_id": 0})
    is_business = bool(prov and prov.get("role") == "business")
    if is_business:
        await db.users.update_one({"user_id": provider_id}, {"$inc": {"wallet_balance": net}})
        await _tx(provider_id, "earning", net, f"{label} €{net:.2f} (disponibile)", rid, "available")
    else:
        release_at = (now_utc() + timedelta(hours=HOLD_HOURS)).isoformat()
        await db.users.update_one({"user_id": provider_id}, {"$inc": {"pending_balance": net}})
        await db.wallet_holds.insert_one({
            "hold_id": new_id("hold"), "user_id": provider_id, "richiesta_id": rid,
            "amount": net, "status": "pending", "release_at": release_at,
            "created_at": now_utc().isoformat()})
        await _tx(provider_id, "earning", net, f"{label} €{net:.2f} (disponibile tra 24h)", rid, "pending")


async def release_fixed(r: dict, net: float, label: str = "Compenso") -> float:
    """Release an exact net amount to the earner. Idempotent via escrow.stato."""
    esc = r.get("escrow")
    if not esc or esc.get("stato") != "held":
        return 0.0
    net = round(float(net), 2)
    await _credit_provider(r, net, label)
    await db.richieste.update_one({"richiesta_id": r["richiesta_id"]},
                                  {"$set": {"escrow.stato": "released",
                                            "escrow.released_at": now_utc().isoformat(),
                                            "escrow.net_provider": net}})
    return net


async def settle_and_release(r: dict, final_gross: float, fee_pct_val: float,
                             label: str = "Compenso") -> float:
    """Conguaglio for variable-price services (taxi meter, babysitting overtime):
    adjust the held pool to the final gross (refund surplus / best-effort block the
    difference), then release the collectable net (after fee) to the earner."""
    esc = r.get("escrow")
    if not esc or esc.get("stato") != "held":
        return 0.0
    rid = r["richiesta_id"]
    final_gross = round(float(final_gross), 2)
    held = round(float(esc.get("held", 0)), 2)
    if final_gross < held:
        await _refund_surplus(r, round(held - final_gross, 2))
        r = await _reload(rid)
    elif final_gross > held:
        diff = round(final_gross - held, 2)
        fb, fw, blocked = await _deduct_best_effort(r["cliente_id"], diff, rid, "Conguaglio corsa")
        esc = _merge(r.get("escrow"), fb, fw, blocked)
        if blocked < diff:
            esc["shortfall"] = round(float(esc.get("shortfall", 0)) + (diff - blocked), 2)
        await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"escrow": esc}})
        r = await _reload(rid)
    esc = r.get("escrow") or {}
    collectable = round(float(esc.get("held", 0)), 2)
    net = round(collectable * (1 - float(fee_pct_val) / 100.0), 2)
    await _credit_provider(r, net, label)
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"escrow.stato": "released",
                                            "escrow.released_at": now_utc().isoformat(),
                                            "escrow.net_provider": net,
                                            "escrow.gross": final_gross}})
    return net
