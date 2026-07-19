"""Escrow + wallet ledger helpers.

Wallet model:
  wallet_balance  -> AVAILABLE (spendable/withdrawable)
  pending_balance -> BLOCKED (held, awaiting release date)
  total           -> available + pending

Booking escrow (funds held by the platform):
  escrow_status: none | held | released | refunded
"""
from datetime import timedelta

from core import db, now_utc, new_id

DEFAULT_HOLD_DAYS = 2


async def get_hold_days() -> int:
    s = await db.settings.find_one({"key": "provider_hold_days"})
    try:
        return int(s["value"]) if s else DEFAULT_HOLD_DAYS
    except Exception:
        return DEFAULT_HOLD_DAYS


async def _tx(user_id, ttype, amount, label, booking_id=None, status="ok"):
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": user_id, "type": ttype, "status": status,
        "amount": amount, "label": label, "booking_id": booking_id,
        "created_at": now_utc().isoformat()})


async def mature_holds(user_id: str) -> int:
    """Move any matured pending holds into the available balance. Called lazily on wallet reads."""
    now_iso = now_utc().isoformat()
    holds = await db.wallet_holds.find({"user_id": user_id, "status": "pending"}, {"_id": 0}).to_list(500)
    moved = 0
    for h in holds:
        if h.get("release_at") and now_iso >= h["release_at"]:
            await db.wallet_holds.update_one({"hold_id": h["hold_id"]},
                                             {"$set": {"status": "released", "released_at": now_iso}})
            await db.users.update_one({"user_id": user_id},
                                      {"$inc": {"pending_balance": -h["amount"], "wallet_balance": h["amount"]}})
            await _tx(user_id, "release", h["amount"], f"Compenso reso disponibile €{h['amount']:.2f}", h.get("booking_id"), "available")
            moved += 1
    return moved


async def release_escrow(booking: dict) -> bool:
    """Release a held booking escrow to the provider (platform keeps the commission).
    Generic providers -> pending (matures after hold days); businesses -> available immediately."""
    if booking.get("escrow_status") != "held":
        return False
    provider_id = booking["provider_id"]
    labor = round(float(booking["labor_cost"]), 2)
    prov = await db.users.find_one({"user_id": provider_id}, {"_id": 0})
    is_business = prov and prov.get("role") == "business"
    if is_business:
        await db.users.update_one({"user_id": provider_id}, {"$inc": {"wallet_balance": labor}})
        await _tx(provider_id, "earning", labor, f"Compenso €{labor:.2f} (disponibile)", booking["booking_id"], "available")
    else:
        days = await get_hold_days()
        release_at = (now_utc() + timedelta(days=days)).isoformat()
        await db.users.update_one({"user_id": provider_id}, {"$inc": {"pending_balance": labor}})
        await db.wallet_holds.insert_one({
            "hold_id": new_id("hold"), "user_id": provider_id, "booking_id": booking["booking_id"],
            "amount": labor, "status": "pending", "release_at": release_at, "created_at": now_utc().isoformat()})
        await _tx(provider_id, "earning", labor, f"Compenso €{labor:.2f} (in attesa di accredito)", booking["booking_id"], "pending")
    await db.bookings.update_one({"booking_id": booking["booking_id"]},
                                 {"$set": {"escrow_status": "released", "escrow_released_at": now_utc().isoformat()}})
    return True


async def refund_escrow(booking: dict) -> bool:
    """Return a held booking escrow to the client (service not performed / cancelled / disputed)."""
    if booking.get("escrow_status") != "held":
        return False
    amount = round(float(booking.get("escrow_amount", booking.get("total", 0))), 2)
    await db.users.update_one({"user_id": booking["customer_id"]}, {"$inc": {"wallet_balance": amount}})
    await _tx(booking["customer_id"], "refund", amount, f"Rimborso garanzia €{amount:.2f}", booking["booking_id"], "available")
    await db.bookings.update_one({"booking_id": booking["booking_id"]},
                                 {"$set": {"escrow_status": "refunded", "escrow_refunded_at": now_utc().isoformat(),
                                           "payment_status": "refunded"}})
    return True
