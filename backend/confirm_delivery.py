"""RITIRATO nel Blocco 10 — non più importato/esposto da server.py.

Mongo-based (from core import db — MONGO_URL non configurato su questo
deploy Render, vedi core.py): ogni query di questo modulo si bloccava o
falliva, pur essendo montato. Sostituito da delivery_pg.py +
routers/delivery.py (stesso design, layer dati Postgres, rilascio
delegato alle funzioni già esistenti di ciascuna verticale invece di
wallet_escrow.py). File lasciato nel repo come riferimento storico.

QR / 6-digit "consegna verificata" confirmation layer.

Optional guarantee the CLIENT enables in the profile (users.qr_confirm_enabled). When on, the
release of a completed service / delivered order is ARMED instead of executed: the client shows
a QR (encoding a secret token) + a 6-digit code; the EARNER (provider/business) scans the QR or
types the code to release the payment. Auto-releases 24h after arming if never confirmed.

A single collection `delivery_confirmations` backs both richieste and business orders:
  {confirm_id, token, code, kind: richiesta|order, ref_id, categoria, client_id, earner_id,
   net, label, verified, released, created_at, deadline}
"""
import random
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user
import wallet_escrow as we
from routers.notifications import push_notification

router = APIRouter()

CONFIRM_TTL_HOURS = 24


async def _qr_enabled(client_id: str) -> bool:
    u = await db.users.find_one({"user_id": client_id}, {"_id": 0, "qr_confirm_enabled": 1})
    return bool(u and u.get("qr_confirm_enabled"))


async def _active_conf(ref_id: str):
    return await db.delivery_confirmations.find_one(
        {"ref_id": ref_id, "released": False}, {"_id": 0})


async def _arm(kind: str, ref_id: str, categoria: str, client_id: str, earner_id: str,
               net: float, label: str) -> dict:
    existing = await _active_conf(ref_id)
    if existing:
        return existing
    conf = {
        "confirm_id": new_id("cfm"), "token": new_id("tok") + new_id("tok"),
        "code": f"{random.randint(0, 999999):06d}", "kind": kind, "ref_id": ref_id,
        "categoria": categoria, "client_id": client_id, "earner_id": earner_id,
        "net": round(float(net), 2), "label": label, "verified": False, "released": False,
        "created_at": now_utc().isoformat(),
        "deadline": (now_utc() + timedelta(hours=CONFIRM_TTL_HOURS)).isoformat(),
    }
    await db.delivery_confirmations.insert_one(dict(conf))
    await push_notification(client_id, "consegna_conferma", "Conferma consegna",
                            "Mostra il tuo QR/codice al professionista per liberare il pagamento.",
                            "delivery", ref_id)
    return conf


async def arm_or_release_richiesta(r: dict, net: float, label: str) -> dict:
    """If the client enabled QR confirmation -> arm and wait; else release immediately."""
    esc = r.get("escrow")
    if not esc or esc.get("stato") != "held":
        return {"released": 0.0}
    if await _qr_enabled(r["cliente_id"]):
        conf = await _arm("richiesta", r["richiesta_id"], r.get("categoria", ""),
                          r["cliente_id"], r.get("provider_scelto"), net, label)
        await db.richieste.update_one({"richiesta_id": r["richiesta_id"]},
                                      {"$set": {"conferma_pending": True}})
        return {"awaiting_confirmation": True, "deadline": conf["deadline"]}
    released = await we.release_richiesta(r, net, label)
    return {"released": released}


async def arm_or_release_order(o: dict, net: float, label: str) -> dict:
    """Business product order: arm QR confirmation (client shows) or release to business now."""
    ref_id = o["request_id"]
    if await _qr_enabled(o["client_id"]):
        conf = await _arm("order", ref_id, o.get("category", ""), o["client_id"],
                          o["business_id"], net, label)
        await db.business_requests.update_one({"request_id": ref_id},
                                              {"$set": {"conferma_pending": True}})
        return {"awaiting_confirmation": True, "deadline": conf["deadline"]}
    await _release_order(o, net, label)
    return {"released": net}


async def _release_order(o: dict, net: float, label: str):
    await we.credit_earner(o["business_id"], net, o["request_id"], label)
    await db.business_requests.update_one(
        {"request_id": o["request_id"]},
        {"$set": {"status": "completed", "payment_status": "released",
                  "conferma_pending": False, "updated_at": now_utc().isoformat()}})


async def _do_release(conf: dict):
    """Release a confirmed/expired arming to the earner and close it."""
    if conf.get("released"):
        return
    if conf["kind"] == "richiesta":
        r = await db.richieste.find_one({"richiesta_id": conf["ref_id"]}, {"_id": 0})
        if r:
            await we.release_richiesta(r, conf["net"], conf["label"])
            await db.richieste.update_one({"richiesta_id": conf["ref_id"]},
                                          {"$set": {"conferma_pending": False}})
    else:
        o = await db.business_requests.find_one({"request_id": conf["ref_id"]}, {"_id": 0})
        if o and o.get("payment_status") != "released":
            await _release_order(o, conf["net"], conf["label"])
    await db.delivery_confirmations.update_one({"confirm_id": conf["confirm_id"]},
                                               {"$set": {"released": True, "released_at": now_utc().isoformat()}})


async def auto_release_expired():
    """Release any arming whose 24h deadline elapsed without confirmation. Called lazily."""
    now_iso = now_utc().isoformat()
    expired = await db.delivery_confirmations.find(
        {"released": False, "deadline": {"$lte": now_iso}}, {"_id": 0}).to_list(200)
    for c in expired:
        await _do_release(c)
    return len(expired)


# ---------------- endpoints ----------------
@router.get("/delivery/mine")
async def my_confirmations(user=Depends(get_current_user)):
    """QR/codes the client must show to earners (active, not yet confirmed)."""
    await auto_release_expired()
    items = await db.delivery_confirmations.find(
        {"client_id": user["user_id"], "released": False}, {"_id": 0}).to_list(100)
    return items


@router.get("/delivery/ref/{ref_id}")
async def confirmation_for_ref(ref_id: str, user=Depends(get_current_user)):
    conf = await db.delivery_confirmations.find_one(
        {"ref_id": ref_id, "released": False}, {"_id": 0})
    if not conf or conf["client_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    return {"token": conf["token"], "code": conf["code"], "deadline": conf["deadline"],
            "label": conf["label"], "net": conf["net"]}


class TokenIn(BaseModel):
    token: str


class CodeIn(BaseModel):
    ref_id: str
    code: str


@router.post("/delivery/confirm")
async def confirm_by_token(body: TokenIn, user=Depends(get_current_user)):
    """Earner scanned the client's QR (token)."""
    conf = await db.delivery_confirmations.find_one({"token": body.token, "released": False}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="not_found")
    if conf["earner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="not_your_delivery")
    await db.delivery_confirmations.update_one({"confirm_id": conf["confirm_id"]},
                                               {"$set": {"verified": True, "verified_at": now_utc().isoformat()}})
    await _do_release(conf)
    await push_notification(conf["client_id"], "consegna_confermata", "Consegna confermata",
                            "Il pagamento è stato liberato. Grazie!", "delivery", conf["ref_id"])
    return {"confirmed": True, "released": conf["net"]}


@router.post("/delivery/confirm-code")
async def confirm_by_code(body: CodeIn, user=Depends(get_current_user)):
    """Earner typed the 6-digit code shown by the client (fallback when no camera)."""
    conf = await db.delivery_confirmations.find_one({"ref_id": body.ref_id, "released": False}, {"_id": 0})
    if not conf:
        raise HTTPException(status_code=404, detail="not_found")
    if conf["earner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="not_your_delivery")
    if body.code.strip() != conf["code"]:
        raise HTTPException(status_code=400, detail="invalid_code")
    await db.delivery_confirmations.update_one({"confirm_id": conf["confirm_id"]},
                                               {"$set": {"verified": True, "verified_at": now_utc().isoformat()}})
    await _do_release(conf)
    await push_notification(conf["client_id"], "consegna_confermata", "Consegna confermata",
                            "Il pagamento è stato liberato. Grazie!", "delivery", conf["ref_id"])
    return {"confirmed": True, "released": conf["net"]}


@router.get("/delivery/status/{ref_id}")
async def confirmation_status(ref_id: str, user=Depends(get_current_user)):
    """Earner polls whether a confirmation is pending / done for a ref."""
    await auto_release_expired()
    conf = await db.delivery_confirmations.find_one({"ref_id": ref_id}, {"_id": 0})
    if not conf:
        return {"pending": False}
    return {"pending": not conf.get("released"), "verified": conf.get("verified", False),
            "released": conf.get("released", False), "deadline": conf.get("deadline")}
