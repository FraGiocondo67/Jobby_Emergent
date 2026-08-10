"""BLOCCO 5 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent.

"Business" qui è un `profiles_provider` con `is_proximity_business = true`
(colonna già esistente nello schema storico) — non un `role` separato: lo
schema Postgres ha un enum `role` chiuso (client/provider/both/admin, senza
"business", gap già segnalato nel Blocco 1) e questa è la soluzione più
semplice che non richiede toccarlo, coerente con come `is_proximity_business`
è già usata altrove nello schema.

Flusso "preventivo su misura": il cliente descrive un bisogno direttamente a
un business specifico (non un catalogo prodotti — per quello vedi
routers/listino.py), il business risponde con prezzo/tempi. **Nessun
pagamento qui**: esattamente come nel sistema Emergent originale, questo
endpoint non tocca mai denaro (l'accordo economico avviene fuori piattaforma
o via consegna diretta) — solo `listino.py` (ordini da catalogo, con importi
noti lato server) usa l'escrow Stripe Connect del Blocco 3. Non è
un'omissione: il vecchio `business.py` non aveva mai un passo di pagamento.

Ogni richiesta è una riga `public.missions` (categoria proximity,
`brief_answers` per il dettaglio) — stesso modello delle 4 verticali. La
chat si attiva automaticamente appena `provider_id` è impostato (vedi
routers/chat.py, Blocco 4): niente più `open_thread()` dedicato.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core_pg import db, notify, haversine, TREVISO, to_geography_point, parse_scheduled_at
from deps_pg import get_current_user

router = APIRouter()


def _business_out(p: dict, u: dict, lat: float, lng: float) -> dict:
    bd = p.get("business_data") or {}
    blat, blng = bd.get("last_lat"), bd.get("last_lng")
    dist = haversine(lat, lng, blat, blng) if blat is not None and blng is not None else None
    return {
        "user_id": u["id"], "name": bd.get("business_name") or u.get("full_name", ""),
        "avatar_url": u.get("avatar_url", ""), "rating": p.get("avg_rating") or 0,
        "trust_score": p.get("trust_score") or 0, "bio": p.get("bio", ""),
        "service_mode": bd.get("service_mode", "both"), "distance_km": dist,
        "skills": p.get("skills") or [], "business_photos": p.get("business_photos") or [],
    }


@router.get("/businesses")
async def list_businesses(category: str, lat: float = TREVISO["lat"], lng: float = TREVISO["lng"],
                          user=Depends(get_current_user)):
    res = (
        db.table("profiles_provider").select("*, users!inner(id, full_name, avatar_url)")
        .eq("is_proximity_business", True).contains("skills", [category]).execute()
    )
    out = []
    for p in (res.data or []):
        u = p.get("users") or {}
        out.append(_business_out(p, {"id": u.get("id"), "full_name": u.get("full_name"), "avatar_url": u.get("avatar_url")}, lat, lng))
    out.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 999999)
    return out


@router.get("/businesses/detail/{business_id}")
async def business_detail(business_id: str, user=Depends(get_current_user)):
    res = (
        db.table("profiles_provider").select("*, users!inner(id, full_name, avatar_url)")
        .eq("user_id", business_id).eq("is_proximity_business", True).limit(1).execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="business_not_found")
    p = res.data[0]
    u = p.get("users") or {}
    out = _business_out(p, {"id": u.get("id"), "full_name": u.get("full_name"), "avatar_url": u.get("avatar_url")},
                        TREVISO["lat"], TREVISO["lng"])
    bd = p.get("business_data") or {}
    out["address"] = bd.get("address", "")
    return out


def _category_id(slug: str) -> str:
    res = db.table("service_categories").select("id").eq("slug", slug).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="invalid_category")
    return res.data[0]["id"]


class BusinessRequestIn(BaseModel):
    business_id: str
    category: str
    note: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    budget: Optional[float] = None


@router.post("/business-requests")
async def create_business_request(body: BusinessRequestIn, user=Depends(get_current_user)):
    prov = (
        db.table("profiles_provider").select("skills")
        .eq("user_id", body.business_id).eq("is_proximity_business", True).limit(1).execute()
    )
    if not prov.data or body.category not in (prov.data[0].get("skills") or []):
        raise HTTPException(status_code=404, detail="business_not_found")

    brief = {
        "kind": "quote_request", "stato": "in_attesa_preventivo", "note": body.note,
        "budget": body.budget, "response": None,
    }
    row = {
        "client_id": user["id"], "provider_id": body.business_id, "category_id": _category_id(body.category),
        "title": "Richiesta preventivo", "description": body.note,
        "status": "published", "address": body.address,
        "location": to_geography_point(body.lat, body.lng),
        "scheduled_at": parse_scheduled_at(None),
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    created = res.data[0]
    await notify(body.business_id, "richiesta_invito", "Nuova richiesta di preventivo",
                body.note[:120] or "Un cliente ha richiesto un preventivo.", "mission", created["id"])
    return created


@router.get("/business-requests")
async def my_business_requests(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*").eq("client_id", user["id"])
        .contains("brief_answers", {"kind": "quote_request"}).order("created_at", desc=True).limit(100).execute()
    )
    return res.data or []


@router.get("/business-requests/incoming")
async def incoming_business_requests(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*").eq("provider_id", user["id"])
        .contains("brief_answers", {"kind": "quote_request"}).order("created_at", desc=True).limit(100).execute()
    )
    return res.data or []


def _load(request_id: str, user_id: str) -> dict:
    res = db.table("missions").select("*").eq("id", request_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    if (row.get("brief_answers") or {}).get("kind") != "quote_request":
        raise HTTPException(status_code=404, detail="not_found")
    if user_id not in (row["client_id"], row.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    return row


@router.get("/business-requests/{request_id}")
async def get_business_request(request_id: str, user=Depends(get_current_user)):
    return _load(request_id, user["id"])


@router.post("/business-requests/{request_id}/cancel")
async def cancel_business_request(request_id: str, user=Depends(get_current_user)):
    row = _load(request_id, user["id"])
    if row["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "in_attesa_preventivo":
        raise HTTPException(status_code=400, detail="cannot_cancel")
    brief["stato"] = "annullata"
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", request_id).execute()
    return {"stato": "annullata"}


class BusinessResponseIn(BaseModel):
    accept: bool
    eta: str = ""
    mode: str = "pickup"          # pickup | delivery
    price: float = 0.0
    delivery_cost: float = 0.0
    note: str = ""


@router.post("/business-requests/{request_id}/respond")
async def respond_business_request(request_id: str, body: BusinessResponseIn, user=Depends(get_current_user)):
    row = _load(request_id, user["id"])
    if row["provider_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "in_attesa_preventivo":
        raise HTTPException(status_code=400, detail="already_handled")

    if not body.accept:
        brief["stato"] = "rifiutata"
        db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", request_id).execute()
        await notify(row["client_id"], "richiesta_annullata", "Preventivo rifiutato",
                    "Il business non può soddisfare la richiesta.", "mission", request_id)
        return {"stato": "rifiutata"}

    # Nessun pagamento qui (vedi docstring modulo) — solo l'accordo su
    # prezzo/tempi/modalità, l'incasso avviene fuori piattaforma.
    response = {"eta": body.eta, "mode": body.mode, "delivery_cost": round(body.delivery_cost, 2),
                "price": round(body.price, 2), "note": body.note}
    brief["response"] = response
    brief["stato"] = "confermata"
    db.table("missions").update({"brief_answers": brief}).eq("id", request_id).execute()
    await notify(row["client_id"], "richiesta_confermata", "Preventivo confermato",
                f"{('Consegna a domicilio' if body.mode == 'delivery' else 'Ritiro in sede')} — "
                f"€{response['price']:.2f}" + (f" + consegna €{response['delivery_cost']:.2f}" if body.mode == "delivery" else ""),
                "mission", request_id)
    return {"stato": "confermata", "response": response}
