"""JOBBY — Listino prodotti per attività di PROSSIMITÀ (Business) — Spec #6/#7.

Struttura prodotto semplice ed efficace:
  item_id · descrizione · unita (pz|nr|hr|kg|bulk) · prezzo · foto (base64, opzionale)

Il Business gestisce il proprio listino SOLO per le categorie che ha selezionato.
Il Cliente sceglie i prodotti + quantità → totale → importo BLOCCATO nel wallet
(usando prima l'eventuale Credito Bonus, poi il saldo).
"""
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id
from deps import get_current_user

router = APIRouter()

UNITS = ("pz", "nr", "hr", "kg", "bulk")


class ProductIn(BaseModel):
    category: str
    descrizione: str
    unita: str = "pz"
    prezzo: float
    foto: Optional[str] = None          # data URI base64 (opzionale)


class OrderItemIn(BaseModel):
    item_id: str
    qty: float


class OrderIn(BaseModel):
    business_id: str
    category: str
    items: List[OrderItemIn]
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    note: str = ""


def _pub(p: dict) -> dict:
    return {"item_id": p["item_id"], "category": p["category"], "descrizione": p["descrizione"],
            "unita": p.get("unita", "pz"), "prezzo": round(float(p.get("prezzo", 0)), 2),
            "foto": p.get("foto"), "active": p.get("active", True)}


# ---------------- Business: gestione listino ----------------
@router.get("/listino/mine")
async def my_listino(category: Optional[str] = None, user=Depends(get_current_user)):
    q = {"owner_id": user["user_id"]}
    if category:
        q["category"] = category
    items = await db.listino_prodotti.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [_pub(p) for p in items]


@router.post("/listino")
async def create_product(body: ProductIn, user=Depends(get_current_user)):
    if body.unita not in UNITS:
        raise HTTPException(status_code=400, detail="invalid_unit")
    if body.prezzo <= 0:
        raise HTTPException(status_code=400, detail="invalid_price")
    if body.category not in (user.get("services") or []):
        raise HTTPException(status_code=400, detail="category_not_selected")
    doc = {"item_id": new_id("prod"), "owner_id": user["user_id"], "category": body.category,
           "descrizione": body.descrizione.strip(), "unita": body.unita, "prezzo": round(float(body.prezzo), 2),
           "foto": body.foto, "active": True, "created_at": now_utc().isoformat()}
    await db.listino_prodotti.insert_one(doc)
    return _pub(doc)


@router.put("/listino/{item_id}")
async def update_product(item_id: str, body: ProductIn, user=Depends(get_current_user)):
    p = await db.listino_prodotti.find_one({"item_id": item_id, "owner_id": user["user_id"]})
    if not p:
        raise HTTPException(status_code=404, detail="not_found")
    if body.unita not in UNITS:
        raise HTTPException(status_code=400, detail="invalid_unit")
    upd = {"descrizione": body.descrizione.strip(), "unita": body.unita,
           "prezzo": round(float(body.prezzo), 2), "category": body.category}
    if body.foto is not None:
        upd["foto"] = body.foto
    await db.listino_prodotti.update_one({"item_id": item_id}, {"$set": upd})
    return {"ok": True}


@router.delete("/listino/{item_id}")
async def delete_product(item_id: str, user=Depends(get_current_user)):
    r = await db.listino_prodotti.delete_one({"item_id": item_id, "owner_id": user["user_id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True}


# ---------------- Cliente: consulta listino + ordina ----------------
@router.get("/listino/business/{business_id}")
async def business_listino(business_id: str, category: Optional[str] = None, user=Depends(get_current_user)):
    q = {"owner_id": business_id, "active": True}
    if category:
        q["category"] = category
    items = await db.listino_prodotti.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [_pub(p) for p in items]


@router.post("/listino/order")
async def create_order(body: OrderIn, user=Depends(get_current_user)):
    biz = await db.users.find_one({"user_id": body.business_id, "role": "business"}, {"_id": 0})
    if not biz:
        raise HTTPException(status_code=404, detail="business_not_found")
    if not body.items:
        raise HTTPException(status_code=400, detail="empty_order")

    # Calcolo totale dai prezzi lato server (non ci si fida del client)
    lines, total = [], 0.0
    for it in body.items:
        if it.qty <= 0:
            continue
        p = await db.listino_prodotti.find_one({"item_id": it.item_id, "owner_id": body.business_id, "active": True}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=400, detail=f"item_not_found:{it.item_id}")
        line_total = round(float(p["prezzo"]) * float(it.qty), 2)
        total += line_total
        lines.append({"item_id": p["item_id"], "descrizione": p["descrizione"], "unita": p.get("unita", "pz"),
                      "prezzo": round(float(p["prezzo"]), 2), "qty": it.qty, "line_total": line_total})
    total = round(total, 2)
    if total <= 0:
        raise HTTPException(status_code=400, detail="empty_order")

    # Blocco importo nel wallet: prima Credito Bonus, poi saldo
    bonus = round(float(user.get("bonus_credit", 0)), 2)
    bal = round(float(user.get("wallet_balance", 0)), 2)
    if bonus + bal < total:
        raise HTTPException(status_code=400, detail="insufficient_wallet")
    from_bonus = round(min(bonus, total), 2)
    from_wallet = round(total - from_bonus, 2)
    inc = {}
    if from_bonus:
        inc["bonus_credit"] = -from_bonus
    if from_wallet:
        inc["wallet_balance"] = -from_wallet
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": inc})

    cat = await db.categories.find_one({"cat_id": body.category}, {"_id": 0})
    label = cat["label"] if cat else {"it": body.category, "en": body.category}
    note = body.note.strip() or "; ".join(f"{l['qty']}x {l['descrizione']}" for l in lines)
    rid = new_id("breq")
    doc = {
        "request_id": rid, "kind": "business_request", "order": True,
        "client_id": user["user_id"], "client_name": user["name"],
        "business_id": body.business_id, "business_name": biz.get("business_name") or biz["name"],
        "business_picture": biz.get("picture", ""), "category": body.category, "category_label": label,
        "note": note, "items": lines, "total": total, "held": total,
        "held_from_bonus": from_bonus, "held_from_wallet": from_wallet, "payment_status": "held",
        "address": body.address, "lat": body.lat, "lng": body.lng, "budget": total,
        "status": "pending", "response": None,
        "created_at": now_utc().isoformat(), "updated_at": now_utc().isoformat(),
    }
    await db.business_requests.insert_one(doc)
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": user["user_id"], "type": "order_payment", "status": "held",
        "amount": -total, "label": f"Ordine {biz.get('business_name') or biz['name']} €{total:.2f} (in garanzia)",
        "request_id": rid, "created_at": now_utc().isoformat()})
    return {"request_id": rid, "total": total, "held_from_bonus": from_bonus, "held_from_wallet": from_wallet}
