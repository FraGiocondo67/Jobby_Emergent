"""BLOCCO 9 (fix bug segnalato dall'utente): "le categorie non generiche non
sono selezionabili, la pagina è bianca... funziona solo artigiani della
casa, pulizie, baby sitter e driver, mentre sarta, pet sitting, hospitality,
assistenza e tecnico non funzionano" + "anche se viene selezionata una
categoria e chiesto un servizio, il servizio non viene salvato — manca
completamente la gestione dei servizi".

Causa reale (non un bug di rendering): `service_categories` ha 9 categorie
`category_type='standard'` attive, ma solo 4 (housekeeping/pulizie,
babysitting, driver, artigiani) hanno un router dedicato con motore prezzi/
matching/escrow proprio (richieste.py/babysitting.py/driver.py/
artigiani.py). Le altre 5 (seamstress/Sarta, pet-sitting, hospitality,
home-assistance/Assistenza, technical/Tecnico) cadevano nel fallback
generico `frontend/app/request/[id].tsx`, che chiamava due endpoint MAI
montati in questo backend: `GET /categories/{id}` (esisteva solo nella
versione Mongo ritirata, catalog_routes.py) e `POST /missions` (motore
generico ritirato nel Blocco 5, routers/missions.py non importato da
server.py). Risultato: fetch 404 → eccezione silenziosa (catch vuoto) →
`cat` resta null per sempre → schermo bianco permanente; e comunque anche
riuscendo a caricare la pagina, il submit sarebbe andato a un endpoint
inesistente, quindi "il servizio non viene salvato" è la stessa causa.

Non replichiamo il motore prezzi/escrow delle 4 verticali dedicate (fuori
scope per 5 categorie eterogenee in un colpo solo) — replichiamo invece il
modello già esistente in routers/business.py ("preventivo su misura", Blocco
5): nessun pagamento in piattaforma, il cliente pubblica la richiesta con le
risposte alle `service_categories.questions` (il "FIELD" richiesto
dall'utente, colonna jsonb già presente ma finora editabile solo via SQL —
vedi il nuovo endpoint admin in categories.py), i provider con quella
categoria tra le `skills` vedono la richiesta e propongono un prezzo, il
cliente conferma una proposta (`missions.provider_id` impostato → la chat
già esistente in chat.py si sblocca automaticamente, stesso meccanismo delle
altre verticali). L'incasso avviene fuori piattaforma, esattamente come già
deciso e implementato in business.py — non è una scorciatoia di questo
blocco, è lo stesso pattern prodotto già in uso.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core_pg import db, notify, now_iso, to_geography_point, parse_scheduled_at
from deps_pg import get_current_user

router = APIRouter()

# Le 4 verticali con router/motore dedicato — tutto il resto di
# category_type='standard' passa da qui.
DEDICATED_SLUGS = {"housekeeping", "babysitting", "driver", "artigiani"}


def _category(cat_id: str) -> dict:
    res = (
        db.table("service_categories")
        .select("id, slug, name_it, name_en, category_type, is_active, questions")
        .eq("slug", cat_id).limit(1).execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="category_not_found")
    return res.data[0]


def _is_generic(cat: dict) -> bool:
    return cat.get("category_type") == "standard" and cat["slug"] not in DEDICATED_SLUGS


def _cat_map(ids: List[str]) -> dict:
    if not ids:
        return {}
    res = db.table("service_categories").select("id, slug, name_it, name_en, icon").in_("id", ids).execute()
    return {r["id"]: r for r in (res.data or [])}


def _out(row: dict, cat: Optional[dict] = None) -> dict:
    brief = row.get("brief_answers") or {}
    out = dict(row)
    out["brief_answers"] = brief
    if cat:
        out["category"] = {"cat_id": cat["slug"], "name_it": cat.get("name_it"), "name_en": cat.get("name_en"), "icon": cat.get("icon")}
    return out


class GenericRequestIn(BaseModel):
    cat_id: str
    answers: dict = {}
    note: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    scheduled_at: Optional[str] = None
    photos: List[str] = []


@router.post("/requests/generic")
async def create_generic_request(body: GenericRequestIn, user=Depends(get_current_user)):
    cat = _category(body.cat_id)
    if not cat.get("is_active"):
        raise HTTPException(status_code=400, detail="category_not_active")
    if not _is_generic(cat):
        raise HTTPException(status_code=400, detail="use_dedicated_flow")

    brief = {
        "kind": "generic_request", "stato": "pubblicata",
        "answers": body.answers, "note": body.note, "photos": body.photos,
        "proposte": [], "provider_scelto": None,
        "pagamento_lavoro": {"stato": "da_definire"},
    }
    row = {
        "client_id": user["id"], "category_id": cat["id"],
        "title": cat.get("name_it") or cat["slug"], "description": body.note,
        "status": "published", "address": body.address,
        "location": to_geography_point(body.lat, body.lng),
        "scheduled_at": parse_scheduled_at(body.scheduled_at),
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="create_failed")
    created = res.data[0]

    provs = db.table("profiles_provider").select("user_id").contains("skills", [cat["slug"]]).execute()
    for p in (provs.data or []):
        await notify(p["user_id"], "nuova_richiesta", "Nuova richiesta",
                    f"Nuova richiesta {cat.get('name_it') or cat['slug']} compatibile.", "mission", created["id"])
    return _out(created, cat)


@router.get("/requests/generic/mine")
async def my_generic_requests(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*").eq("client_id", user["id"])
        .contains("brief_answers", {"kind": "generic_request"})
        .order("created_at", desc=True).limit(100).execute()
    )
    rows = res.data or []
    cats = _cat_map([r["category_id"] for r in rows])
    return [_out(r, cats.get(r["category_id"])) for r in rows]


@router.get("/requests/generic/available")
async def available_generic_requests(user=Depends(get_current_user)):
    prov = db.table("profiles_provider").select("skills").eq("user_id", user["id"]).limit(1).execute()
    skills = (prov.data[0].get("skills") or []) if prov.data else []
    generic_skills = [s for s in skills if s not in DEDICATED_SLUGS]
    if not generic_skills:
        return []
    cats_res = db.table("service_categories").select("id, slug, name_it, name_en, icon").in_("slug", generic_skills).execute()
    cats = {r["id"]: r for r in (cats_res.data or [])}
    if not cats:
        return []
    res = (
        db.table("missions").select("*")
        .eq("status", "published").in_("category_id", list(cats.keys()))
        .contains("brief_answers", {"kind": "generic_request", "stato": "pubblicata"})
        .order("created_at", desc=True).limit(100).execute()
    )
    rows = res.data or []
    out = []
    for r in rows:
        brief = r.get("brief_answers") or {}
        item = _out(r, cats.get(r["category_id"]))
        item["my_proposal"] = next((p for p in brief.get("proposte", []) if p.get("provider_id") == user["id"]), None)
        out.append(item)
    return out


def _load(rid: str, user_id: str) -> dict:
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("kind") != "generic_request":
        raise HTTPException(status_code=404, detail="not_found")
    is_owner = row["client_id"] == user_id
    is_provider = row.get("provider_id") == user_id
    is_proposer = user_id in [p.get("provider_id") for p in brief.get("proposte", [])]
    if not (is_owner or is_provider or is_proposer):
        raise HTTPException(status_code=403, detail="forbidden")
    return row


@router.get("/requests/generic/{rid}")
async def get_generic_request(rid: str, user=Depends(get_current_user)):
    row = _load(rid, user["id"])
    cat = _cat_map([row["category_id"]]).get(row["category_id"])
    return _out(row, cat)


class ProposalIn(BaseModel):
    price: float
    message: str = ""


@router.post("/requests/generic/{rid}/propose")
async def propose_generic_request(rid: str, body: ProposalIn, user=Depends(get_current_user)):
    row = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = row.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("kind") != "generic_request":
        raise HTTPException(status_code=404, detail="not_found")
    if brief.get("stato") != "pubblicata":
        raise HTTPException(status_code=400, detail="not_open")
    if body.price <= 0:
        raise HTTPException(status_code=400, detail="invalid_price")

    proposte = [p for p in brief.get("proposte", []) if p.get("provider_id") != user["id"]]
    proposte.append({"provider_id": user["id"], "price": round(body.price, 2), "message": body.message, "at": now_iso()})
    brief["proposte"] = proposte
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "nuova_proposta", "Nuova proposta ricevuta",
                f"Hai ricevuto una proposta da €{body.price:.2f}.", "mission", rid)
    return {"ok": True}


class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/requests/generic/{rid}/confirm")
async def confirm_generic_request(rid: str, body: ConfirmIn, user=Depends(get_current_user)):
    row = _load(rid, user["id"])
    if row["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "pubblicata":
        raise HTTPException(status_code=400, detail="not_open")
    proposal = next((p for p in brief.get("proposte", []) if p.get("provider_id") == body.provider_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")

    brief["stato"] = "confermata"
    brief["provider_scelto"] = body.provider_id
    db.table("missions").update({
        "provider_id": body.provider_id, "price_agreed": proposal["price"],
        "brief_answers": brief,
    }).eq("id", rid).execute()
    await notify(body.provider_id, "richiesta_confermata", "Richiesta confermata",
                "Il cliente ha accettato la tua proposta.", "mission", rid)
    return {"stato": "confermata"}


@router.post("/requests/generic/{rid}/cancel")
async def cancel_generic_request(rid: str, user=Depends(get_current_user)):
    row = _load(rid, user["id"])
    if row["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") not in ("pubblicata", "confermata"):
        raise HTTPException(status_code=400, detail="cannot_cancel")
    brief["stato"] = "annullata"
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
    if row.get("provider_id"):
        await notify(row["provider_id"], "richiesta_annullata", "Richiesta annullata",
                    "Il cliente ha annullato la richiesta.", "mission", rid)
    return {"stato": "annullata"}


@router.post("/requests/generic/{rid}/complete")
async def complete_generic_request(rid: str, user=Depends(get_current_user)):
    row = _load(rid, user["id"])
    if user["id"] not in (row["client_id"], row.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    brief["stato"] = "completata"
    db.table("missions").update({"status": "completed", "brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "completata"}
