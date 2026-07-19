"""JOBBY — Richiesta object + Pulizie configurator subsystem (Spec 1).

Deterministic price engine, provider listino, manual admin matching, dual-track
(IMPRESA / PERSONA_LF), full state machine and (simulated) Libretto Famiglia flow.
"""
from datetime import timedelta, datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id, haversine
from deps import get_current_user, require_admin
from routers.notifications import push_notification
import richieste_config as C

router = APIRouter()

STATES_OPEN = ("pubblicata", "in_matching", "con_proposte")


# ---------------- models ----------------
class Listino(BaseModel):
    binario: str = "impresa"
    tariffa_ordinaria: float = 16.0
    tariffa_afondo: float = 19.0
    tariffa_posttrasloco: float = 22.0
    prodotti_propri: bool = True
    supplemento_prodotti: float = 5.0     # flat per intervento
    extra: dict = {}                       # {forno: 10, frigo: 8, finestre: 15, balconi: 12}
    stiro_ora: float = C.STIRO_DEFAULT_PRICE
    sconto_ricorrenza_pct: float = 10.0
    raggio_km: float = 15.0
    minimo_ore: int = 2


class Config(BaseModel):
    home_type: str = "appartamento"
    mq_band: str = "80_120"
    tipo_pulizia: str = "ordinaria"
    extra: List[str] = []
    stiro_ore: int = 0
    prodotti: str = "cliente"              # cliente | provider
    durata_ore: float = 3
    animali: bool = False


class RichiestaIn(BaseModel):
    binario: str = "impresa"
    config: Config
    indirizzo: str = ""
    lat: float
    lng: float
    data_ora: str = ""
    flessibilita: str = "fascia"
    ricorrenza: str = "una_tantum"
    giorni_preferiti: List[str] = []
    note: str = ""
    foto: List[str] = []
    parcheggio: str = ""
    publish: bool = True


class ProposeIn(BaseModel):
    accept: bool
    variation_reason: Optional[str] = None
    variation_price: Optional[float] = None
    message: str = ""


class ConfirmIn(BaseModel):
    provider_id: str


class InviteIn(BaseModel):
    provider_ids: List[str]


# ---------------- settings ----------------
async def fee_pct() -> float:
    s = await db.settings.find_one({"key": "pulizie_fee_pct"})
    try:
        return float(s["value"]) if s else C.DEFAULT_FEE_PCT
    except Exception:
        return C.DEFAULT_FEE_PCT


# ---------------- price engine ----------------
def _extra_price(listino: dict, key: str) -> float:
    ov = (listino.get("extra") or {}).get(key)
    if ov is not None:
        return float(ov)
    for e in C.EXTRA_ITEMS:
        if e["id"] == key:
            return float(e["default_price"])
    return 0.0


def compute_work_total(listino: dict, config: dict) -> float:
    tipo = config.get("tipo_pulizia", "ordinaria")
    tariffa = {
        "ordinaria": listino.get("tariffa_ordinaria", 16.0),
        "afondo": listino.get("tariffa_afondo", 19.0),
        "posttrasloco": listino.get("tariffa_posttrasloco", 22.0),
    }.get(tipo, listino.get("tariffa_ordinaria", 16.0))
    ore = float(config.get("durata_ore", 3) or 0)
    total = float(tariffa) * ore
    if config.get("prodotti") == "provider":
        total += float(listino.get("supplemento_prodotti", 0))
    for ex in config.get("extra", []):
        if ex == "stiro":
            continue
        total += _extra_price(listino, ex)
    if "stiro" in config.get("extra", []):
        total += float(listino.get("stiro_ora", C.STIRO_DEFAULT_PRICE)) * int(config.get("stiro_ore", 0) or 0)
    ric = config.get("_ricorrenza", "una_tantum")
    if ric in ("settimanale", "quindicinale"):
        total *= (1 - float(listino.get("sconto_ricorrenza_pct", 0)) / 100.0)
    return round(total, 2)


def price_breakdown(listino: dict, config: dict, binario: str, fee: float) -> dict:
    work = compute_work_total(listino, config)
    jobby_fee = round(work * fee / 100.0, 2)
    out = {"work_total": work, "jobby_fee": jobby_fee, "fee_pct": fee, "total_client": round(work + jobby_fee, 2)}
    if binario == "persona_lf":
        nominale = C.lf_round_nominale(work)
        out.update({
            "lf_nominale": nominale, "lf_voucher": int(nominale / 10),
            "lf_netto_lavoratrice": round(nominale * C.LF_VOUCHER_NET_RATE, 2),
            "total_client": round(nominale + jobby_fee, 2),
        })
    return out


async def compatible_providers(binario: str, config: dict, lat: float, lng: float) -> list:
    q = {"role": {"$in": ["provider", "business"]}, "services": "pulizie",
         "approval_status": {"$nin": ["rejected", "suspended", "waitlist", "pending"]},
         "pulizie_binario": binario, "pulizie_listino": {"$exists": True}}
    out = []
    for p in await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(200):
        # Persona LF providers cannot receive requests until INPS registration is confirmed.
        if binario == "persona_lf" and p.get("lf_inps_registered") is False:
            continue
        lst = p.get("pulizie_listino") or {}
        dist = haversine(lat, lng, p.get("lat", 0), p.get("lng", 0))
        if dist > float(lst.get("raggio_km", 15)):
            continue
        if config.get("prodotti") == "provider" and not lst.get("prodotti_propri"):
            continue
        if float(config.get("durata_ore", 0)) < float(lst.get("minimo_ore", 0)):
            continue
        out.append({"provider": p, "distance": round(dist, 1), "listino": lst})
    return out


# ---------------- config / estimate ----------------
@router.get("/pulizie/config")
async def get_pulizie_config(user=Depends(get_current_user)):
    return {
        "home_types": C.HOME_TYPES, "mq_bands": C.MQ_BANDS, "tipi_pulizia": C.TIPI_PULIZIA,
        "extra_items": C.EXTRA_ITEMS, "stiro_default_price": C.STIRO_DEFAULT_PRICE,
        "ricorrenze": C.RICORRENZE, "flessibilita": C.FLESSIBILITA, "binari": C.BINARI,
        "variation_reasons": C.VARIATION_REASONS, "ore_table": C.ORE_TABLE, "fee_pct": await fee_pct(),
    }


class EstimateIn(BaseModel):
    binario: str = "impresa"
    config: Config
    lat: float = 45.6669
    lng: float = 12.2433
    ricorrenza: str = "una_tantum"


@router.post("/pulizie/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    cfg = body.config.dict()
    cfg["_ricorrenza"] = body.ricorrenza
    fee = await fee_pct()
    result = {}
    for binario in ("impresa", "persona_lf"):
        provs = await compatible_providers(binario, cfg, body.lat, body.lng)
        prices = [price_breakdown(pp["listino"], cfg, binario, fee)["total_client"] for pp in provs]
        result[binario] = {
            "providers": len(provs),
            "min": round(min(prices), 2) if prices else None,
            "max": round(max(prices), 2) if prices else None,
        }
    return {"recommended_hours": C.recommended_hours(cfg.get("mq_band"), cfg.get("tipo_pulizia")),
            "fee_pct": fee, "ranges": result}


# ---------------- richiesta CRUD ----------------
@router.post("/pulizie/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    if body.binario not in ("impresa", "persona_lf"):
        raise HTTPException(status_code=400, detail="invalid_binario")
    cfg = body.config.dict()
    cfg["_ricorrenza"] = body.ricorrenza
    rid = new_id("req")
    doc = {
        "richiesta_id": rid, "cliente_id": user["user_id"], "cliente_nome": user.get("name", ""),
        "categoria": "CASA", "servizio": "PULIZIA", "binario": body.binario, "config": cfg,
        "indirizzo": body.indirizzo, "lat": body.lat, "lng": body.lng,
        "data_ora": body.data_ora, "flessibilita": body.flessibilita,
        "ricorrenza": body.ricorrenza, "giorni_preferiti": body.giorni_preferiti,
        "durata_ore": cfg.get("durata_ore"), "note": body.note, "foto": body.foto, "parcheggio": body.parcheggio,
        "stato": "pubblicata" if body.publish else "bozza",
        "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "pagamento_fee": {"stato": "authorized" if body.publish else "none"},
        "pagamento_lavoro": {"stato": "none"},
        "recensione": None, "created_at": now_utc().isoformat(), "updated_at": now_utc().isoformat(),
    }
    if body.publish:
        doc["scade_at"] = (now_utc() + timedelta(hours=C.PROPOSAL_WINDOW_HOURS)).isoformat()
    await db.richieste.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/pulizie/richieste")
async def my_richieste(user=Depends(get_current_user)):
    items = await db.richieste.find({"cliente_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return items


@router.get("/pulizie/richieste/{rid}")
async def get_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    is_owner = r["cliente_id"] == user["user_id"]
    is_invited = user["user_id"] in [p.get("provider_id") for p in r.get("provider_invitati", [])]
    if not (is_owner or is_invited):
        raise HTTPException(status_code=403, detail="forbidden")
    r["role"] = "client" if is_owner else "provider"
    if not is_owner:
        r.pop("indirizzo", None)  # exact address hidden until confirmed
    return r


@router.post("/pulizie/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] in ("completata", "recensita"):
        raise HTTPException(status_code=400, detail="already_done")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"stato": "annullata", "updated_at": now_utc().isoformat()}})
    return {"stato": "annullata"}


# ---------------- provider side ----------------
@router.get("/pulizie/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        return []
    items = await db.richieste.find(
        {"provider_invitati.provider_id": user["user_id"], "stato": {"$in": list(STATES_OPEN)}},
        {"_id": 0}).sort("created_at", -1).to_list(100)
    fee = await fee_pct()
    out = []
    for r in items:
        lst = user.get("pulizie_listino") or {}
        r.pop("indirizzo", None)
        r["price"] = price_breakdown(lst, r["config"], r["binario"], fee)
        r["my_proposal"] = next((p for p in r.get("proposte", []) if p.get("provider_id") == user["user_id"]), None)
        out.append(r)
    return out


@router.post("/pulizie/richieste/{rid}/propose")
async def propose(rid: str, body: ProposeIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    if user["user_id"] not in [p.get("provider_id") for p in r.get("provider_invitati", [])]:
        raise HTTPException(status_code=403, detail="not_invited")
    if r["stato"] not in STATES_OPEN:
        raise HTTPException(status_code=400, detail="not_open")
    if not body.accept:
        await db.richieste.update_one({"richiesta_id": rid, "provider_invitati.provider_id": user["user_id"]},
                                      {"$set": {"provider_invitati.$.status": "declined"}})
        return {"declined": True}
    if body.variation_price is not None and body.variation_reason not in [v["id"] for v in C.VARIATION_REASONS]:
        raise HTTPException(status_code=400, detail="invalid_variation_reason")
    lst = user.get("pulizie_listino") or {}
    fee = await fee_pct()
    pb = price_breakdown(lst, r["config"], r["binario"], fee)
    price = round(float(body.variation_price), 2) if body.variation_price is not None else pb["total_client"]
    proposal = {
        "provider_id": user["user_id"], "provider_nome": user.get("business_name") or user.get("name", ""),
        "provider_rating": user.get("rating", 0), "provider_trust": user.get("trust_score", 0),
        "listino_price": pb["total_client"], "price": price, "breakdown": pb,
        "variation_reason": body.variation_reason, "message": body.message,
        "at": now_utc().isoformat(),
    }
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$pull": {"proposte": {"provider_id": user["user_id"]}}})
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$push": {"proposte": proposal},
                                   "$set": {"stato": "con_proposte", "updated_at": now_utc().isoformat()},
                                   })
    await push_notification(r["cliente_id"], "richiesta_proposta", "Nuova proposta Pulizie",
                            f"{proposal['provider_nome']} ha proposto €{price:.2f}.", "richiesta", rid)
    return proposal


# ---------------- client confirm + lifecycle ----------------
@router.post("/pulizie/richieste/{rid}/confirm")
async def confirm(rid: str, body: ConfirmIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "con_proposte":
        raise HTTPException(status_code=400, detail="no_proposals")
    prop = next((p for p in r.get("proposte", []) if p.get("provider_id") == body.provider_id), None)
    if not prop:
        raise HTTPException(status_code=400, detail="proposal_not_found")
    lf = {}
    if r["binario"] == "persona_lf":
        nominale = prop["breakdown"].get("lf_nominale", prop["price"])
        bors = round(user.get("lf_borsellino", 0), 2)
        if bors < nominale:
            raise HTTPException(status_code=400, detail="lf_insufficient_borsellino")
        await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"lf_borsellino": -nominale,
                                                                          "lf_year_total": nominale,
                                                                          "lf_year_hours": float(r["config"].get("durata_ore", 0))}})
        lf = {"nominale": nominale, "voucher": prop["breakdown"].get("lf_voucher"),
              "netto_lavoratrice": prop["breakdown"].get("lf_netto_lavoratrice"), "stato": "coperto"}
    upd = {
        "stato": "confermata", "provider_scelto": body.provider_id,
        "pagamento_fee": {"stato": "charged", "importo": prop["breakdown"]["jobby_fee"], "at": now_utc().isoformat()},
        "pagamento_lavoro": ({"stato": "psp_pending", "importo": prop["price"]} if r["binario"] == "impresa"
                             else {**lf, "stato": "lf"}),
        "prezzo_finale": prop["price"], "updated_at": now_utc().isoformat(),
    }
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": upd})
    await push_notification(body.provider_id, "richiesta_confermata", "Richiesta confermata",
                            f"Il cliente ti ha scelto per una pulizia (€{prop['price']:.2f}).", "richiesta", rid)
    return {**r, **upd}


@router.post("/pulizie/richieste/{rid}/start")
async def start(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or user["user_id"] not in (r["cliente_id"], r.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"stato": "in_corso", "updated_at": now_utc().isoformat()}})
    return {"stato": "in_corso"}


@router.post("/pulizie/richieste/{rid}/complete")
async def complete(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or user["user_id"] not in (r["cliente_id"], r.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="not_in_progress")
    extra = {}
    if r["binario"] == "persona_lf":
        # generate the (simulated) INPS communication for the intermediary
        extra["lf_comunicazione"] = {
            "prestatrice_id": r.get("provider_scelto"), "committente_id": r["cliente_id"],
            "nominale": r.get("pagamento_lavoro", {}).get("nominale"),
            "voucher": r.get("pagamento_lavoro", {}).get("voucher"),
            "ore": r["config"].get("durata_ore"), "generata_at": now_utc().isoformat(), "stato": "da_trasmettere",
        }
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"stato": "completata", "completed_at": now_utc().isoformat(), **extra, "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "richiesta_completata", "Servizio completato",
                            "Puoi lasciare una recensione.", "richiesta", rid)
    return {"stato": "completata", **extra}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/pulizie/richieste/{rid}/review")
async def review(rid: str, body: ReviewIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "completata":
        raise HTTPException(status_code=400, detail="not_completed")
    rev = {"rating": max(1, min(5, body.rating)), "comment": body.comment, "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"recensione": rev, "stato": "recensita", "updated_at": now_utc().isoformat()}})
    return rev


# ---------------- Libretto Famiglia borsellino (simulated) ----------------
class LfTopupIn(BaseModel):
    amount: float


@router.get("/pulizie/lf/borsellino")
async def lf_borsellino(user=Depends(get_current_user)):
    return {
        "borsellino": round(user.get("lf_borsellino", 0), 2),
        "year_total": round(user.get("lf_year_total", 0), 2),
        "year_hours": round(user.get("lf_year_hours", 0), 1),
        "ceiling_eur": C.LF_YEAR_CEILING_EUR, "ceiling_hours": C.LF_YEAR_CEILING_HOURS,
        "alert": round(user.get("lf_year_total", 0), 2) >= C.LF_YEAR_CEILING_EUR * 0.7,
    }


@router.post("/pulizie/lf/topup")
async def lf_topup(body: LfTopupIn, user=Depends(get_current_user)):
    amt = round(float(body.amount), 2)
    if amt <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"lf_borsellino": amt}})
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "lf_borsellino": 1})
    return {"borsellino": round(u.get("lf_borsellino", 0), 2)}


# ---------------- provider listino ----------------
@router.get("/pulizie/listino")
async def get_listino(user=Depends(get_current_user)):
    return {"pulizie_binario": user.get("pulizie_binario", "impresa" if user.get("role") == "business" else "persona_lf"),
            "listino": user.get("pulizie_listino")}


class ListinoIn(BaseModel):
    binario: str = "impresa"
    listino: Listino


@router.put("/pulizie/listino")
async def set_listino(body: ListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    lst = body.listino.dict()
    lst["binario"] = body.binario
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"pulizie_binario": body.binario, "pulizie_listino": lst,
                                        "services": list(set((user.get("services") or []) + ["pulizie"]))}})
    return {"pulizie_binario": body.binario, "listino": lst}


# ---------------- admin manual matching ----------------
@router.get("/admin/pulizie/richieste")
async def admin_richieste(_=Depends(require_admin)):
    items = await db.richieste.find({"stato": {"$in": list(STATES_OPEN)}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    fee = await fee_pct()
    for r in items:
        provs = await compatible_providers(r["binario"], r["config"], r["lat"], r["lng"])
        r["compatible"] = [{
            "provider_id": pp["provider"]["user_id"],
            "nome": pp["provider"].get("business_name") or pp["provider"].get("name"),
            "distance": pp["distance"], "rating": pp["provider"].get("rating", 0),
            "trust": pp["provider"].get("trust_score", 0),
            "price": price_breakdown(pp["listino"], r["config"], r["binario"], fee)["total_client"],
            "invited": pp["provider"]["user_id"] in [i.get("provider_id") for i in r.get("provider_invitati", [])],
        } for pp in provs]
    return items


@router.post("/admin/pulizie/richieste/{rid}/invite")
async def admin_invite(rid: str, body: InviteIn, _=Depends(require_admin)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    already = [i.get("provider_id") for i in r.get("provider_invitati", [])]
    new_invites = []
    for pid in body.provider_ids:
        if pid in already:
            continue
        new_invites.append({"provider_id": pid, "at": now_utc().isoformat(), "status": "invited"})
        await push_notification(pid, "richiesta_invito", "Nuova richiesta di pulizia",
                                "Hai ricevuto una richiesta compatibile. Rispondi entro 24h.", "richiesta", rid)
    if new_invites:
        upd = {"$push": {"provider_invitati": {"$each": new_invites}}, "$set": {"stato": "in_matching", "updated_at": now_utc().isoformat()}}
        await db.richieste.update_one({"richiesta_id": rid}, upd)
    return {"invited": len(new_invites)}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/pulizie/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "pulizie_fee_pct"}, {"$set": {"value": float(body.fee_pct)}}, upsert=True)
    return {"fee_pct": body.fee_pct}
