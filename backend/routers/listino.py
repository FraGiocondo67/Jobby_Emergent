"""BLOCCO 5 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent.

Controparte "che tocca denaro" di routers/business.py (leggere il suo
docstring per il modello business = `profiles_provider` con
`is_proximity_business = true`): lì il cliente descrive un bisogno e
l'accordo economico avviene fuori piattaforma; qui invece il cliente sceglie
prodotti da un catalogo con prezzi noti lato server e paga subito — stessa
distinzione già presente nel sistema Emergent originale (solo
`business_requests` con `order=True`, cioè questo router, toccava mai il
wallet).

Catalogo: `public.marketplace_products` (Blocco 5), di proprietà del
business (`owner_id`) — non un catalogo condiviso admin-editabile come
`artigiani_paniere`/`pulizie_extra`, ma un modello di ownership come
`child_cards` (Blocco 2 babysitting): ogni business gestisce il proprio
listino, solo per le categorie proximity che ha in `skills`.

Pagamento: stesso pattern "vero escrow Stripe Connect" del Blocco 3
(`stripe_pg.py`) e stessa fee JOBBY split cliente/provider delle 4 verticali
(vedi `price_breakdown` in richieste.py) — qui niente binario `persona_lf`
(un ordine da catalogo non è mai Libretto Famiglia). L'hold avviene subito
alla creazione dell'ordine, non in un "confirm" separato: qui il business è
già noto (niente fase di proposte come nelle 4 verticali).

  1. CREATE ORDER -> `charge_hold()` + `create_escrow_hold()` (RPC) subito,
     riga `public.missions` con `provider_id` già impostato al business.
  2. RESPOND (rifiuto)  -> `refund_payment_intent()` + `refund_escrow()` (RPC).
     RESPOND (accetto)  -> nessuna azione gateway, il denaro resta held.
  3. COMPLETE (il business segna consegnato) -> `transfer_to_provider()` +
     `release_escrow()` (RPC) — netto del provider (fee già dedotta).
  4. CANCEL (cliente, mentre ancora pending) -> `refund_payment_intent()` +
     `refund_escrow()` (RPC).

Semplificazione deliberata rispetto al vecchio `confirm_delivery.py`
(`arm_or_release_order`, finestra di conferma differita prima del rilascio):
qui `complete` rilascia subito, stesso pattern immediato già usato nelle 4
verticali del Blocco 3 — nessuna finestra d'attesa aggiuntiva.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import stripe_pg as SP
from core_pg import db, notify, to_geography_point, parse_scheduled_at
from deps_pg import get_current_user, require_admin

router = APIRouter()

UNITS = ("pz", "nr", "hr", "kg", "bulk")
_FEE_SETTING_KEY = "marketplace_fee_pct"
DEFAULT_FEE_PCT = 15.0


async def fee_pct() -> float:
    res = db.table("app_settings").select("value").eq("key", _FEE_SETTING_KEY).limit(1).execute()
    if res.data:
        try:
            return float(res.data[0]["value"])
        except Exception:
            pass
    return DEFAULT_FEE_PCT


def price_breakdown(work: float, fee: float) -> dict:
    """Stessa formula di richieste.py's price_breakdown: fee JOBBY divisa a
    metà tra cliente (aggiunta al totale) e provider (dedotta dal netto)."""
    work = round(float(work), 2)
    jobby_fee = round(work * fee / 100.0, 2)
    fee_client = round(jobby_fee / 2.0, 2)
    fee_provider = round(jobby_fee - fee_client, 2)
    provider_net = round(work - fee_provider, 2)
    return {"work_total": work, "jobby_fee": jobby_fee, "fee_pct": fee,
            "fee_client": fee_client, "fee_provider": fee_provider,
            "provider_net": provider_net, "total_client": round(work + fee_client, 2)}


def _category_id(slug: str) -> str:
    res = db.table("service_categories").select("id").eq("slug", slug).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="invalid_category")
    return res.data[0]["id"]


def _category_slug(category_id: str) -> str:
    res = db.table("service_categories").select("slug").eq("id", category_id).limit(1).execute()
    return res.data[0]["slug"] if res.data else ""


def _pub(p: dict) -> dict:
    return {"item_id": p["id"], "category": _category_slug(p["category_id"]),
            "descrizione": p["descrizione"], "unita": p.get("unita", "pz"),
            "prezzo": round(float(p.get("prezzo", 0)), 2), "foto": p.get("foto"),
            "active": p.get("active", True)}


def _require_business_skill(business_id: str, category: str) -> dict:
    prov = (
        db.table("profiles_provider").select("skills, stripe_payouts_enabled, stripe_connect_account_id")
        .eq("user_id", business_id).eq("is_proximity_business", True).limit(1).execute()
    )
    if not prov.data or category not in (prov.data[0].get("skills") or []):
        raise HTTPException(status_code=404, detail="business_not_found")
    return prov.data[0]


class ProductIn(BaseModel):
    category: str
    descrizione: str
    unita: str = "pz"
    prezzo: float
    foto: Optional[str] = None          # data URI base64 (opzionale)


# ---------------- Business: gestione catalogo ----------------
@router.get("/listino/mine")
async def my_listino(category: Optional[str] = None, user=Depends(get_current_user)):
    q = db.table("marketplace_products").select("*").eq("owner_id", user["id"])
    if category:
        q = q.eq("category_id", _category_id(category))
    res = q.order("created_at").execute()
    return [_pub(p) for p in (res.data or [])]


@router.post("/listino")
async def create_product(body: ProductIn, user=Depends(get_current_user)):
    if body.unita not in UNITS:
        raise HTTPException(status_code=400, detail="invalid_unit")
    if body.prezzo <= 0:
        raise HTTPException(status_code=400, detail="invalid_price")
    _require_business_skill(user["id"], body.category)
    row = {"owner_id": user["id"], "category_id": _category_id(body.category),
           "descrizione": body.descrizione.strip(), "unita": body.unita,
           "prezzo": round(float(body.prezzo), 2), "foto": body.foto, "active": True}
    res = db.table("marketplace_products").insert(row).execute()
    return _pub(res.data[0])


@router.put("/listino/{item_id}")
async def update_product(item_id: str, body: ProductIn, user=Depends(get_current_user)):
    res = db.table("marketplace_products").select("*").eq("id", item_id).eq("owner_id", user["id"]).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    if body.unita not in UNITS:
        raise HTTPException(status_code=400, detail="invalid_unit")
    if body.prezzo <= 0:
        raise HTTPException(status_code=400, detail="invalid_price")
    upd = {"descrizione": body.descrizione.strip(), "unita": body.unita,
           "prezzo": round(float(body.prezzo), 2), "category_id": _category_id(body.category)}
    if body.foto is not None:
        upd["foto"] = body.foto
    res2 = db.table("marketplace_products").update(upd).eq("id", item_id).execute()
    return _pub(res2.data[0])


@router.delete("/listino/{item_id}")
async def delete_product(item_id: str, user=Depends(get_current_user)):
    res = db.table("marketplace_products").delete().eq("id", item_id).eq("owner_id", user["id"]).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True}


# ---------------- Cliente: consulta catalogo + ordina ----------------
@router.get("/listino/business/{business_id}")
async def business_listino(business_id: str, category: Optional[str] = None, user=Depends(get_current_user)):
    q = db.table("marketplace_products").select("*").eq("owner_id", business_id).eq("active", True)
    if category:
        q = q.eq("category_id", _category_id(category))
    res = q.order("created_at").execute()
    return [_pub(p) for p in (res.data or [])]


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


@router.post("/listino/order")
async def create_order(body: OrderIn, user=Depends(get_current_user)):
    prov = _require_business_skill(body.business_id, body.category)
    if not prov.get("stripe_payouts_enabled"):
        raise HTTPException(status_code=400, detail="provider_not_onboarded")
    if not body.items:
        raise HTTPException(status_code=400, detail="empty_order")

    customer_id = user.get("stripe_customer_id")
    pm_id = user.get("default_payment_method_id")
    if not customer_id or not pm_id:
        raise HTTPException(status_code=400, detail="client_payment_method_missing")

    # Totale calcolato lato server dai prezzi in marketplace_products — mai fidarsi del client.
    lines, work = [], 0.0
    for it in body.items:
        if it.qty <= 0:
            continue
        pres = (
            db.table("marketplace_products").select("*")
            .eq("id", it.item_id).eq("owner_id", body.business_id).eq("active", True).limit(1).execute()
        )
        if not pres.data:
            raise HTTPException(status_code=400, detail=f"item_not_found:{it.item_id}")
        p = pres.data[0]
        line_total = round(float(p["prezzo"]) * float(it.qty), 2)
        work += line_total
        lines.append({"item_id": p["id"], "descrizione": p["descrizione"], "unita": p.get("unita", "pz"),
                      "prezzo": round(float(p["prezzo"]), 2), "qty": it.qty, "line_total": line_total})
    if work <= 0:
        raise HTTPException(status_code=400, detail="empty_order")

    fee = await fee_pct()
    pb = price_breakdown(work, fee)
    total_client = pb["total_client"]

    brief = {"kind": "catalog_order", "stato": "pending", "note": body.note,
             "items": lines, "breakdown": pb, "response": None}
    row = {
        "client_id": user["id"], "provider_id": body.business_id, "category_id": _category_id(body.category),
        "title": "Ordine da listino", "description": body.note or "; ".join(f"{l['qty']}x {l['descrizione']}" for l in lines),
        "status": "published", "address": body.address,
        "location": to_geography_point(body.lat, body.lng),
        "scheduled_at": parse_scheduled_at(None),
        "price_agreed": total_client, "platform_fee": pb["jobby_fee"], "provider_payout": pb["provider_net"],
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    created = res.data[0]

    charge = SP.charge_hold(customer_id, pm_id, total_client, {"mission_id": created["id"], "category": "marketplace"})
    db.rpc("create_escrow_hold", {
        "p_mission_id": created["id"], "p_gateway_transaction_id": charge["payment_intent_id"],
        "p_gateway_response": {"status": charge["status"]}, "p_gateway_name": "stripe",
    }).execute()
    brief["pagamento_lavoro"] = {"stato": "held", "payment_intent_id": charge["payment_intent_id"], "amount": total_client}
    upd = db.table("missions").update({"brief_answers": brief}).eq("id", created["id"]).execute()
    created = upd.data[0]

    await notify(body.business_id, "richiesta_invito", "Nuovo ordine",
                f"€{total_client:.2f} — {len(lines)} articoli.", "mission", created["id"])
    return created


def _load_order(request_id: str, user_id: str) -> dict:
    res = db.table("missions").select("*").eq("id", request_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="order_not_found")
    row = res.data[0]
    if (row.get("brief_answers") or {}).get("kind") != "catalog_order":
        raise HTTPException(status_code=404, detail="order_not_found")
    if user_id not in (row["client_id"], row.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    return row


@router.get("/listino/order")
async def my_orders(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*").eq("client_id", user["id"])
        .contains("brief_answers", {"kind": "catalog_order"}).order("created_at", desc=True).limit(100).execute()
    )
    return res.data or []


@router.get("/listino/order/incoming")
async def incoming_orders(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*").eq("provider_id", user["id"])
        .contains("brief_answers", {"kind": "catalog_order"}).order("created_at", desc=True).limit(100).execute()
    )
    return res.data or []


@router.get("/listino/order/{rid}")
async def get_order(rid: str, user=Depends(get_current_user)):
    return _load_order(rid, user["id"])


class OrderRespondIn(BaseModel):
    accept: bool
    eta: str = ""
    mode: str = "pickup"          # pickup | delivery
    note: str = ""


@router.post("/listino/order/{rid}/respond")
async def order_respond(rid: str, body: OrderRespondIn, user=Depends(get_current_user)):
    """Il Business accetta o rifiuta un ordine. Rifiuto -> rimborso dell'hold."""
    row = _load_order(rid, user["id"])
    if row["provider_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "pending":
        raise HTTPException(status_code=400, detail="already_handled")

    if not body.accept:
        pagamento = brief.get("pagamento_lavoro") or {}
        if pagamento.get("stato") == "held":
            refund = SP.refund_payment_intent(pagamento["payment_intent_id"])
            db.rpc("refund_escrow", {
                "p_mission_id": rid, "p_reason": "ordine_rifiutato",
                "p_gateway_transaction_id": refund["refund_id"],
                "p_gateway_response": {}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["stato"] = "refunded"
            pagamento["refund_id"] = refund["refund_id"]
            brief["pagamento_lavoro"] = pagamento
        brief["stato"] = "declined"
        db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
        await notify(row["client_id"], "richiesta_annullata", "Ordine rifiutato",
                    "Il business non può soddisfare l'ordine — importo rimborsato.", "mission", rid)
        return {"stato": "declined"}

    response = {"eta": body.eta, "mode": body.mode, "note": body.note}
    brief["response"] = response
    brief["stato"] = "confirmed"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    total = float((brief.get("breakdown") or {}).get("total_client") or 0)
    mode_txt = "Consegna a domicilio" if body.mode == "delivery" else "Ritiro in sede"
    await notify(row["client_id"], "richiesta_confermata", "Ordine confermato",
                f"{mode_txt} — Tempo: {body.eta or 'da concordare'} — €{total:.2f}", "mission", rid)
    return {"stato": "confirmed", "response": response}


@router.post("/listino/order/{rid}/complete")
async def order_complete(rid: str, user=Depends(get_current_user)):
    """Il Business marca l'ordine come consegnato -> trasferisce il netto al business."""
    row = _load_order(rid, user["id"])
    if row["provider_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "confirmed":
        raise HTTPException(status_code=400, detail="not_confirmed")
    pagamento = brief.get("pagamento_lavoro") or {}
    if pagamento.get("stato") != "held":
        raise HTTPException(status_code=400, detail="payment_not_held")

    prov_row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", user["id"]).limit(1).execute()
    acct_id = prov_row.data[0].get("stripe_connect_account_id") if prov_row.data else None
    if not acct_id:
        raise HTTPException(status_code=400, detail="provider_not_onboarded")
    payout = float(row.get("provider_payout") or 0)
    transfer = SP.transfer_to_provider(acct_id, payout, {"mission_id": rid, "category": "marketplace"})
    db.rpc("release_escrow", {
        "p_mission_id": rid, "p_gateway_transaction_id": transfer["transfer_id"],
        "p_gateway_response": {}, "p_gateway_name": "stripe",
    }).execute()
    pagamento["stato"] = "released"
    pagamento["transfer_id"] = transfer["transfer_id"]
    brief["pagamento_lavoro"] = pagamento
    brief["stato"] = "completed"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(row["client_id"], "richiesta_completata", "Ordine consegnato",
                "Il tuo ordine è stato consegnato.", "mission", rid)
    return {"stato": "completed", "released": payout}


@router.post("/listino/order/{rid}/cancel")
async def order_cancel(rid: str, user=Depends(get_current_user)):
    """Il Cliente annulla il proprio ordine finché è ancora in attesa -> rimborso."""
    row = _load_order(rid, user["id"])
    if row["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "pending":
        raise HTTPException(status_code=400, detail="cannot_cancel")

    pagamento = brief.get("pagamento_lavoro") or {}
    if pagamento.get("stato") == "held":
        refund = SP.refund_payment_intent(pagamento["payment_intent_id"])
        db.rpc("refund_escrow", {
            "p_mission_id": rid, "p_reason": "cancellazione_cliente",
            "p_gateway_transaction_id": refund["refund_id"],
            "p_gateway_response": {}, "p_gateway_name": "stripe",
        }).execute()
        pagamento["stato"] = "refunded"
        pagamento["refund_id"] = refund["refund_id"]
        brief["pagamento_lavoro"] = pagamento
    brief["stato"] = "cancelled"
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "cancelled"}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/listino/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    db.table("app_settings").upsert({"key": _FEE_SETTING_KEY, "value": float(body.fee_pct)}).execute()
    return {"fee_pct": body.fee_pct}
