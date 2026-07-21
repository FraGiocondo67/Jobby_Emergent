"""JOBBY — Spec 8 DRIVER subsystem (NCC + TAXI).

Reuses the richieste engine. NCC = firm parametric quote per vehicle class with
motivated upward tweaks + free discount, prepaid in app. TAXI = dispatch only,
fare regulated by official taximeter (app shows an estimate, settled at the end).
Payer/passenger separation, unaccompanied minors 16+ with double consent,
shared-ride tracking, 4h/30min cancellation schema, per-class onboarding.
"""
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id, haversine
from deps import get_current_user, require_admin
from routers.notifications import push_notification
import driver_config as D
import wallet_escrow as we
import confirm_delivery as cd

router = APIRouter()

STATES_OPEN = ("pubblicata", "in_matching", "con_proposte")
CAT = {"categoria": "MOBILITA", "servizio": "DRIVER"}


async def fee_pct() -> float:
    s = await db.settings.find_one({"key": "driver_fee_pct"})
    try:
        return float(s["value"]) if s else D.DEFAULT_FEE_PCT
    except Exception:
        return D.DEFAULT_FEE_PCT


async def _credit_provider(rid: str, provider_id: str, totale: float):
    """Accredita il netto (dopo fee JOBBY) sul wallet del provider al saldo corsa.
    Idempotente: usa pagamento.credited."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or (r.get("pagamento") or {}).get("credited"):
        return
    fee = await fee_pct()
    net = round(float(totale) * (1 - fee / 100.0), 2)
    await db.users.update_one({"user_id": provider_id}, {"$inc": {"wallet_balance": net}})
    await db.transactions.insert_one({
        "tx_id": new_id("tx"), "user_id": provider_id, "type": "earning", "status": "available",
        "amount": net, "label": f"Corsa completata €{net:.2f} (netto)",
        "richiesta_id": rid, "created_at": now_utc().isoformat()})
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"pagamento.net_provider": net, "pagamento.credited": True}})


def _parse(dt: str) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def estimate_route(a_lat, a_lng, b_lat, b_lng) -> dict:
    geo = haversine(a_lat, a_lng, b_lat, b_lng)
    km = round(geo * D.ROAD_FACTOR, 1)
    minutes = int(round(km / D.AVG_SPEED_KMH * 60)) if km else 0
    return {"distance_km": km, "duration_min": minutes}


def _is_notturno(pickup: Optional[datetime]) -> bool:
    if not pickup:
        return False
    return pickup.hour >= 22 or pickup.hour < 6


def _is_festivo(pickup: Optional[datetime]) -> bool:
    return bool(pickup) and pickup.weekday() == 6   # Sunday (holidays approximated)


def ncc_price(listino: dict, classe: str, route: dict, pickup: Optional[datetime], ritorno: Optional[dict]) -> float:
    cl = (listino.get("classi") or {}).get(classe) or D.DEFAULT_LISTINO.get(classe, D.DEFAULT_LISTINO["standard"])
    base = float(cl.get("base", 8)) + float(cl.get("per_km", 1.4)) * float(route.get("distance_km", 0))
    if ritorno and ritorno.get("distance_km"):
        leg2 = float(cl.get("base", 8)) + float(cl.get("per_km", 1.4)) * float(ritorno.get("distance_km", 0))
        base += leg2 * (1 - float(listino.get("sconto_ar_pct", 0)) / 100.0)
    if _is_notturno(pickup):
        base *= (1 + float(listino.get("notturno_pct", 0)) / 100.0)
    if _is_festivo(pickup):
        base *= (1 + float(listino.get("festivo_pct", 0)) / 100.0)
    return round(base, 2)


def taxi_estimate(route: dict, pickup: Optional[datetime]) -> float:
    tf = D.TAXI_TARIFFA
    amt = tf["scatto"] + tf["per_km"] * float(route.get("distance_km", 0))
    if _is_notturno(pickup):
        amt *= (1 + tf["notturno_pct"] / 100.0)
    if _is_festivo(pickup):
        amt *= (1 + tf["festivo_pct"] / 100.0)
    return round(max(amt, tf["min_corsa"]), 2)


async def compatible_drivers(tipo: str, classe: str, lat: float, lng: float) -> list:
    q = {"role": {"$in": ["provider", "business"]}, "services": "driver",
         "approval_status": {"$nin": ["rejected", "suspended", "waitlist", "pending"]},
         "driver_tipo": tipo, "driver_listino": {"$exists": True}}
    out = []
    for p in await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(200):
        lst = p.get("driver_listino") or {}
        if classe not in (lst.get("classi") or {}):
            continue
        dist = haversine(lat, lng, p.get("lat", 0), p.get("lng", 0))
        if dist > float(lst.get("raggio_km", 30)):
            continue
        out.append({"provider": p, "distance": round(dist, 1), "listino": lst})
    return out


# ---------------- config / geocode / estimate ----------------
@router.get("/driver/config")
async def get_config(user=Depends(get_current_user)):
    return {
        "vehicle_classes": D.VEHICLE_CLASSES, "shortcuts": D.SHORTCUTS, "ritocco_motivi": D.RITOCCO_MOTIVI,
        "special_needs": D.SPECIAL_NEEDS, "cancellation": D.CANCELLATION, "min_age": D.MIN_UNACCOMPANIED_AGE,
        "included_wait_min": D.INCLUDED_WAIT_MIN, "taxi_tariffa": D.TAXI_TARIFFA, "fee_pct": await fee_pct(),
    }


class GeocodeIn(BaseModel):
    query: str


@router.post("/driver/geocode")
async def geocode(body: GeocodeIn, user=Depends(get_current_user)):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": body.query, "format": "json", "limit": 1, "countrycodes": "it"},
                         headers={"User-Agent": "JOBBY-app/1.0"}, timeout=8)
        js = r.json()
        if js:
            return {"lat": float(js[0]["lat"]), "lng": float(js[0]["lon"]),
                    "label": js[0].get("display_name", body.query)[:80]}
    except Exception:
        pass
    return {"lat": 45.6669, "lng": 12.2433, "label": body.query, "fallback": True}


class EstimateIn(BaseModel):
    tipo: str = "ncc"
    classe: str = "standard"
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    pickup_at: str = ""
    ritorno: Optional[dict] = None


@router.post("/driver/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    route = estimate_route(body.from_lat, body.from_lng, body.to_lat, body.to_lng)
    pickup = _parse(body.pickup_at)
    ritorno_route = None
    if body.ritorno:
        ritorno_route = estimate_route(body.to_lat, body.to_lng, body.from_lat, body.from_lng)
    if body.tipo == "taxi":
        est = taxi_estimate(route, pickup)
        drivers = await compatible_drivers("taxi", body.classe, body.from_lat, body.from_lng)
        return {"route": route, "tipo": "taxi", "estimate": est, "providers": len(drivers),
                "note": "Tariffa regolata dal tassametro ufficiale. Importo finale a fine corsa."}
    provs = await compatible_drivers("ncc", body.classe, body.from_lat, body.from_lng)
    prices = [ncc_price(pp["listino"], body.classe, route, pickup, ritorno_route) for pp in provs]
    return {"route": route, "ritorno_route": ritorno_route, "tipo": "ncc", "providers": len(provs),
            "min": round(min(prices), 2) if prices else None, "max": round(max(prices), 2) if prices else None}


# ---------------- driver listino + vehicles + authorization ----------------
class ListinoIn(BaseModel):
    tipo: str = "ncc"
    classi: dict = {}                # {standard: {base, per_km, per_hour, attesa_per_hour}, ...}
    notturno_pct: float = 0.0
    festivo_pct: float = 0.0
    sconto_ar_pct: float = 0.0
    raggio_km: float = 30.0
    trasporto_minori: bool = False
    animali: bool = False
    fasce: List[str] = []


@router.get("/driver/listino")
async def get_listino(user=Depends(get_current_user)):
    return {"driver_tipo": user.get("driver_tipo", "ncc"), "listino": user.get("driver_listino"),
            "vehicles": user.get("driver_vehicles", []),
            "authorization": {"numero": user.get("driver_auth_numero"),
                              "verified": bool(user.get("driver_auth_verified")),
                              "uploaded": bool(user.get("driver_auth_doc"))}}


@router.put("/driver/listino")
async def set_listino(body: ListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    lst = body.dict()
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"driver_tipo": body.tipo, "driver_listino": lst,
                                        "services": list(set((user.get("services") or []) + ["driver"]))}})
    return {"driver_tipo": body.tipo, "listino": lst}


class VehicleIn(BaseModel):
    classe: str
    targa: str
    posti: int = 4
    foto: str = ""
    assicurazione: bool = False
    modello: str = ""


@router.post("/driver/vehicles")
async def add_vehicle(body: VehicleIn, user=Depends(get_current_user)):
    v = {"vehicle_id": new_id("veh"), **body.dict()}
    await db.users.update_one({"user_id": user["user_id"]}, {"$push": {"driver_vehicles": v}})
    return v


@router.delete("/driver/vehicles/{vid}")
async def del_vehicle(vid: str, user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$pull": {"driver_vehicles": {"vehicle_id": vid}}})
    return {"deleted": True}


class AuthIn(BaseModel):
    tipo: str = "ncc"           # ncc autorizzazione | taxi licenza
    numero: str
    image: str


@router.post("/driver/authorization")
async def upload_auth(body: AuthIn, user=Depends(get_current_user)):
    if not body.image.strip() or not body.numero.strip():
        raise HTTPException(status_code=400, detail="invalid_authorization")
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"driver_tipo": body.tipo, "driver_auth_numero": body.numero,
                                        "driver_auth_doc": body.image, "driver_auth_verified": False,
                                        "driver_auth_uploaded_at": now_utc().isoformat()}})
    return {"uploaded": True}


# ---------------- richiesta CRUD ----------------
class Waypoint(BaseModel):
    label: str = ""
    lat: float
    lng: float


class RichiestaIn(BaseModel):
    tipo: str = "ncc"                 # ncc | taxi
    classe: str = "standard"
    partenza: Waypoint
    destinazione: Waypoint
    pickup_at: str
    flight_number: str = ""
    passeggeri: int = 1
    bagagli: int = 0
    passeggero_nome: str = ""         # if different from payer
    passeggero_tel: str = ""
    minore: bool = False
    minore_consenso: bool = False
    special: List[str] = []
    ritorno: Optional[dict] = None    # {pickup_at}
    note: str = ""
    target_provider_id: str = ""      # richiesta diretta a un driver specifico


@router.post("/driver/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    if body.tipo not in ("ncc", "taxi"):
        raise HTTPException(status_code=400, detail="invalid_tipo")
    if body.minore and not body.minore_consenso:
        raise HTTPException(status_code=400, detail="minor_consent_required")
    route = estimate_route(body.partenza.lat, body.partenza.lng, body.destinazione.lat, body.destinazione.lng)
    pickup = _parse(body.pickup_at)
    ritorno = None
    if body.ritorno:
        rr = estimate_route(body.destinazione.lat, body.destinazione.lng, body.partenza.lat, body.partenza.lng)
        ritorno = {**rr, "pickup_at": body.ritorno.get("pickup_at", "")}
    est = taxi_estimate(route, pickup) if body.tipo == "taxi" else None
    rid = new_id("drv")
    config = {"tipo": body.tipo, "classe": body.classe, "route": route, "ritorno": ritorno,
              "flight_number": body.flight_number, "passeggeri": body.passeggeri, "bagagli": body.bagagli,
              "special": body.special, "minore": body.minore, "taxi_estimate": est}
    doc = {
        "richiesta_id": rid, "cliente_id": user["user_id"], "cliente_nome": user.get("name", ""),
        **CAT, "binario": "piva", "config": config,
        "partenza": body.partenza.dict(), "destinazione": body.destinazione.dict(),
        "lat": body.partenza.lat, "lng": body.partenza.lng,
        "pickup_at": body.pickup_at, "note": body.note,
        "passeggero": {"nome": body.passeggero_nome, "tel": body.passeggero_tel} if body.passeggero_nome else None,
        "minore_consenso": body.minore_consenso,
        "stato": "pubblicata", "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "extra": [], "tracking": None, "pagamento": {"stato": "none"},
        "recensione": None, "created_at": now_utc().isoformat(), "updated_at": now_utc().isoformat(),
        "scade_at": (now_utc() + timedelta(hours=D.PROPOSAL_WINDOW_HOURS)).isoformat(),
    }
    # ---- Auto-matching: invita i driver compatibili nel raggio (+ eventuale diretta) ----
    invited: list = []
    seen = set()
    if body.target_provider_id:
        tp = await db.users.find_one({"user_id": body.target_provider_id}, {"_id": 0})
        if tp and "driver" in (tp.get("services") or []):
            invited.append({"provider_id": tp["user_id"], "status": "invited", "direct": True})
            seen.add(tp["user_id"])
    try:
        provs = await compatible_drivers(body.tipo, body.classe, body.partenza.lat, body.partenza.lng)
    except Exception:
        provs = []
    for p in provs[:25]:
        pid = p["provider"]["user_id"]
        if pid in seen:
            continue
        seen.add(pid)
        invited.append({"provider_id": pid, "status": "invited"})
    if invited:
        doc["provider_invitati"] = invited
        doc["stato"] = "in_matching"
    await db.richieste.insert_one(doc)
    for inv in invited:
        await push_notification(inv["provider_id"], "driver_invito", "🚘 Nuova richiesta corsa",
                                f"{body.partenza.label} → {body.destinazione.label}", "driver", rid)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/driver/richieste")
async def my_richieste(user=Depends(get_current_user)):
    return await db.richieste.find({"cliente_id": user["user_id"], **CAT}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/driver/richieste/{rid}")
async def get_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    is_owner = r["cliente_id"] == user["user_id"]
    is_confirmed = r.get("provider_scelto") == user["user_id"]
    is_invited = user["user_id"] in [p.get("provider_id") for p in r.get("provider_invitati", [])]
    if not (is_owner or is_invited or is_confirmed):
        raise HTTPException(status_code=403, detail="forbidden")
    r["role"] = "client" if is_owner else "provider"
    return r


def _cancellation_outcome(pickup: Optional[datetime], prezzo: float) -> dict:
    if not pickup:
        return {"charge": 0.0, "refund_pct": 100}
    delta = (pickup - now_utc()).total_seconds() / 60.0
    if delta >= D.CANCELLATION["full_refund_hours"] * 60:
        return {"charge": 0.0, "refund_pct": 100, "band": ">4h"}
    if delta >= D.CANCELLATION["full_charge_under_min"]:
        return {"charge": round(prezzo * 0.5, 2), "refund_pct": 50, "band": "<4h"}
    return {"charge": round(prezzo, 2), "refund_pct": 0, "band": "<30min"}


@router.post("/driver/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] in ("completata", "recensita", "annullata"):
        raise HTTPException(status_code=400, detail="already_closed")
    prezzo = float(r.get("prezzo_finale", 0))
    outcome = _cancellation_outcome(_parse(r.get("pickup_at", "")), prezzo)
    # Escrow: rilascia la penale al driver (se dovuta) e rimborsa il resto al cliente.
    if (r.get("escrow") or {}).get("stato") == "held":
        charge = round(float(outcome.get("charge", 0)), 2)
        if charge > 0 and r.get("provider_scelto"):
            await we.conguaglio(r, charge)
            r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
            feev = await fee_pct()
            await we.release_richiesta(r, round(charge * (1 - feev / 100.0), 2), "Penale cancellazione")
        else:
            await we.refund(r, "Rimborso corsa annullata")
    upd = {"stato": "annullata", "cancellazione": outcome, "updated_at": now_utc().isoformat()}
    if r.get("provider_scelto") and outcome["charge"] > 0:
        await push_notification(r["provider_scelto"], "driver_annullata", "Corsa annullata",
                                f"Il cliente ha annullato. Ti spetta €{outcome['charge']:.2f}.", "driver", rid)
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": upd})
    return outcome


# ---------------- provider side ----------------
@router.get("/driver/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        return []
    uid = user["user_id"]
    items = await db.richieste.find(
        {**CAT, "$or": [
            {"provider_invitati": {"$elemMatch": {"provider_id": uid, "status": {"$ne": "declined"}}}, "stato": {"$in": list(STATES_OPEN)}},
            {"provider_scelto": uid, "stato": {"$in": ["confermata", "in_corso"]}},
        ]},
        {"_id": 0}).sort("created_at", -1).to_list(100)
    lst = user.get("driver_listino") or {}
    for r in items:
        cfg = r["config"]
        pickup = _parse(r.get("pickup_at", ""))
        if cfg["tipo"] == "ncc":
            r["suggested_price"] = ncc_price(lst, cfg["classe"], cfg["route"], pickup, cfg.get("ritorno"))
        else:
            r["taxi_estimate"] = cfg.get("taxi_estimate")
        r["my_proposal"] = next((p for p in r.get("proposte", []) if p.get("provider_id") == user["user_id"]), None)
    return items


class ProposeIn(BaseModel):
    accept: bool
    prezzo: Optional[float] = None
    ritocco_motivo: str = ""
    message: str = ""


@router.post("/driver/richieste/{rid}/propose")
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
    cfg = r["config"]; lst = user.get("driver_listino") or {}
    pickup = _parse(r.get("pickup_at", ""))
    vehicle = next((v for v in (user.get("driver_vehicles") or []) if v.get("classe") == cfg["classe"]), {})
    if cfg["tipo"] == "ncc":
        base = ncc_price(lst, cfg["classe"], cfg["route"], pickup, cfg.get("ritorno"))
        prezzo = round(float(body.prezzo), 2) if body.prezzo is not None else base
        ritocco = None
        if prezzo > base:
            if body.ritocco_motivo not in [m["id"] for m in D.RITOCCO_MOTIVI]:
                raise HTTPException(status_code=400, detail="ritocco_requires_reason")
            ritocco = {"delta": round(prezzo - base, 2), "motivo": body.ritocco_motivo}
    else:
        prezzo = cfg.get("taxi_estimate")
        ritocco = None
    proposal = {
        "provider_id": user["user_id"], "provider_nome": user.get("business_name") or user.get("name", ""),
        "provider_rating": user.get("rating", 0), "provider_affidabilita": user.get("affidabilita", 100),
        "provider_foto": user.get("presentation_photo") or user.get("selfie_document"),
        "vehicle": vehicle, "classe": cfg["classe"], "prezzo": prezzo, "ritocco": ritocco,
        "is_estimate": cfg["tipo"] == "taxi", "message": body.message, "at": now_utc().isoformat(),
    }
    await db.richieste.update_one({"richiesta_id": rid}, {"$pull": {"proposte": {"provider_id": user["user_id"]}}})
    # Richiesta DIRETTA + accettazione al prezzo di listino → conferma automatica
    # (il cliente ha già scelto questo driver). Con contro-prezzo resta in attesa.
    inv = next((p for p in r.get("provider_invitati", []) if p.get("provider_id") == user["user_id"]), {})
    is_direct = bool(inv.get("direct"))
    has_counter = ritocco is not None
    if is_direct and not has_counter:
        try:
            await we.hold(r, prezzo, f"Blocco garanzia corsa €{prezzo:.2f}")
        except HTTPException:
            # Cliente senza fondi sufficienti: niente conferma automatica, resta da confermare.
            await db.richieste.update_one({"richiesta_id": rid},
                                          {"$push": {"proposte": proposal},
                                           "$set": {"stato": "con_proposte", "updated_at": now_utc().isoformat()}})
            await push_notification(r["cliente_id"], "driver_proposta", "Nuova proposta corsa",
                                    f"{proposal['provider_nome']}: €{prezzo:.2f} — ricarica il portafoglio per confermare.", "driver", rid)
            return {**proposal, "auto_confirmed": False, "needs_topup": True}
        fee = await fee_pct()
        jobby_fee = round(prezzo * fee / 100.0, 2)
        await db.richieste.update_one({"richiesta_id": rid}, {
            "$push": {"proposte": proposal},
            "$set": {"stato": "confermata", "provider_scelto": user["user_id"], "prezzo_finale": prezzo,
                     "jobby_fee": jobby_fee,
                     "pagamento": {"stato": "meter_pending" if cfg["tipo"] == "taxi" else "prepaid",
                                   "importo": prezzo, "fee": jobby_fee, "at": now_utc().isoformat()},
                     "updated_at": now_utc().isoformat()}})
        await push_notification(r["cliente_id"], "driver_confermata", "🚘 Corsa confermata",
                                f"{proposal['provider_nome']} ha accettato la tua richiesta (€{prezzo:.2f}).", "driver", rid)
        return {**proposal, "auto_confirmed": True}
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$push": {"proposte": proposal},
                                   "$set": {"stato": "con_proposte", "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "driver_proposta", "Nuova proposta corsa",
                            f"{proposal['provider_nome']}: €{prezzo:.2f}", "driver", rid)
    return proposal


class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/driver/richieste/{rid}/confirm")
async def confirm(rid: str, body: ConfirmIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "con_proposte":
        raise HTTPException(status_code=400, detail="no_proposals")
    prop = next((p for p in r.get("proposte", []) if p.get("provider_id") == body.provider_id), None)
    if not prop:
        raise HTTPException(status_code=400, detail="proposal_not_found")
    is_taxi = r["config"]["tipo"] == "taxi"
    fee = await fee_pct()
    jobby_fee = round(prop["prezzo"] * fee / 100.0, 2)
    # Blocca subito l'importo (stima per il taxi) dal portafoglio del cliente.
    await we.hold(r, prop["prezzo"], f"Blocco garanzia corsa €{prop['prezzo']:.2f}")
    upd = {"stato": "confermata", "provider_scelto": body.provider_id, "prezzo_finale": prop["prezzo"],
           "jobby_fee": jobby_fee,
           "pagamento": {"stato": "meter_pending" if is_taxi else "prepaid",
                         "importo": prop["prezzo"], "fee": jobby_fee, "at": now_utc().isoformat()},
           "updated_at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": upd})
    await push_notification(body.provider_id, "driver_confermata", "Corsa confermata",
                            "Un cliente ti ha scelto. Trovi i dettagli nella tua area.", "driver", rid)
    return {**r, **upd}


# ---------------- execution ----------------
@router.post("/driver/richieste/{rid}/depart")
async def depart(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    tracking = {"started_at": now_utc().isoformat(), "lat": user.get("lat"), "lng": user.get("lng")}
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"stato": "in_corso", "tracking": tracking, "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "driver_in_arrivo", "Il driver è in arrivo",
                            "Puoi seguire la corsa in tempo reale.", "driver", rid)
    if (r.get("passeggero") or {}).get("tel"):
        await push_notification(r["cliente_id"], "driver_passeggero", "Driver in arrivo",
                                f"{user.get('name','')} sta arrivando.", "driver", rid)
    return tracking


class TrackIn(BaseModel):
    lat: float
    lng: float


@router.post("/driver/richieste/{rid}/track")
async def track(rid: str, body: TrackIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"tracking.lat": body.lat, "tracking.lng": body.lng,
                                            "tracking.updated_at": now_utc().isoformat()}})
    return {"ok": True}


class ExtraIn(BaseModel):
    tipo: str            # attesa | fermata | cambio
    importo: float
    motivo: str = ""


@router.post("/driver/richieste/{rid}/extra")
async def add_extra(rid: str, body: ExtraIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    extra = {"extra_id": new_id("ex"), "tipo": body.tipo, "importo": round(body.importo, 2),
             "motivo": body.motivo, "stato": "pending", "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$push": {"extra": extra}})
    await push_notification(r["cliente_id"], "driver_extra", "Extra da approvare",
                            f"{body.tipo}: €{body.importo:.2f}", "driver", rid)
    return extra


class ExtraApprove(BaseModel):
    extra_id: str
    approve: bool


@router.post("/driver/richieste/{rid}/extra/approve")
async def approve_extra(rid: str, body: ExtraApprove, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    st = "approved" if body.approve else "rejected"
    if body.approve:
        ex = next((e for e in r.get("extra", []) if e.get("extra_id") == body.extra_id), None)
        if ex and ex.get("stato") == "pending":
            # Blocca l'importo extra dal portafoglio del cliente (garanzia).
            await we.hold(r, float(ex.get("importo", 0)), f"Extra corsa €{float(ex.get('importo', 0)):.2f}")
    await db.richieste.update_one({"richiesta_id": rid, "extra.extra_id": body.extra_id},
                                  {"$set": {"extra.$.stato": st}})
    return {"extra_id": body.extra_id, "stato": st}


@router.post("/driver/richieste/{rid}/noshow")
async def noshow(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="invalid_state")
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"stato": "completata", "no_show": True,
                                            "importo_dovuto": r.get("prezzo_finale", 0),
                                            "completed_at": now_utc().isoformat(), "updated_at": now_utc().isoformat()}})
    # No-show: la corsa è dovuta per intero → rilascio diretto al driver (niente QR: cliente assente).
    feev = await fee_pct()
    r2 = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    held = float((r2.get("escrow") or {}).get("held", 0))
    if held > 0:
        await we.release_richiesta(r2, round(held * (1 - feev / 100.0), 2), "No-show corsa")
    await push_notification(r["cliente_id"], "driver_noshow", "Mancata presentazione",
                            "La corsa è dovuta per intero.", "driver", rid)
    return {"stato": "completata", "no_show": True}


class CompleteIn(BaseModel):
    meter_amount: Optional[float] = None       # taxi: final taximeter amount


@router.post("/driver/richieste/{rid}/complete")
async def complete(rid: str, body: CompleteIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    extras = sum(e["importo"] for e in r.get("extra", []) if e.get("stato") == "approved")
    is_taxi = r["config"]["tipo"] == "taxi"
    if is_taxi:
        if body.meter_amount is None:
            raise HTTPException(status_code=400, detail="meter_amount_required")
        totale = round(float(body.meter_amount) + extras, 2)
    else:
        totale = round(float(r.get("prezzo_finale", 0)) + extras, 2)
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"stato": "completata", "importo_totale": totale, "extra_totale": extras,
                                            "pagamento.stato": "settled", "completed_at": now_utc().isoformat(),
                                            "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "driver_completata", "Corsa completata",
                            (f"Importo tassametro: €{totale:.2f}." if is_taxi else "Grazie! Lascia una recensione."),
                            "driver", rid)
    # Conguaglio (taxi) + rilascio/arma conferma verso il driver.
    feev = await fee_pct()
    r2 = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if is_taxi:
        collectable = await we.conguaglio(r2, totale)
        r2 = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    else:
        collectable = float((r2.get("escrow") or {}).get("held", totale))
    net = round(collectable * (1 - feev / 100.0), 2)
    await cd.arm_or_release_richiesta(r2, net, "Compenso corsa")
    return {"stato": "completata", "importo_totale": totale}


@router.post("/driver/richieste/{rid}/pay")
async def pay_taxi(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if (r.get("pagamento") or {}).get("stato") != "meter_to_settle":
        raise HTTPException(status_code=400, detail="nothing_to_settle")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"pagamento.stato": "settled",
                                                                    "pagamento.settled_at": now_utc().isoformat()}})
    await _credit_provider(rid, r["provider_scelto"], r.get("importo_totale", 0))
    return {"stato": "settled", "importo": r.get("importo_totale")}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/driver/richieste/{rid}/review")
async def review(rid: str, body: ReviewIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "completata":
        raise HTTPException(status_code=400, detail="not_completed")
    rev = {"rating": max(1, min(5, body.rating)), "comment": body.comment, "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"recensione": rev, "stato": "recensita", "updated_at": now_utc().isoformat()}})
    return rev


# ---------------- admin ----------------
@router.get("/admin/driver/richieste")
async def admin_richieste(_=Depends(require_admin)):
    items = await db.richieste.find({"stato": {"$in": list(STATES_OPEN)}, **CAT}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for r in items:
        cfg = r.get("config") or {}
        r["compatible"] = []
        try:
            provs = await compatible_drivers(cfg.get("tipo"), cfg.get("classe"), r.get("lat"), r.get("lng"))
            pickup = _parse(r.get("pickup_at", ""))
            for pp in provs:
                p = pp["provider"]
                inv = next((i for i in r.get("provider_invitati", []) if i.get("provider_id") == p["user_id"]), None)
                r["compatible"].append({
                    "provider_id": p["user_id"], "nome": p.get("business_name") or p.get("name"),
                    "distance": pp["distance"], "rating": p.get("rating", 0), "affidabilita": p.get("affidabilita", 100),
                    "auth_ok": bool(p.get("driver_auth_verified")),
                    "price": (ncc_price(pp["listino"], cfg.get("classe"), cfg.get("route"), pickup, cfg.get("ritorno"))
                              if cfg.get("tipo") == "ncc" else cfg.get("taxi_estimate")),
                    "invited": bool(inv),
                    "invite_status": (inv.get("status") if inv else None),
                    "confirmed": r.get("provider_scelto") == p["user_id"],
                })
        except Exception:
            r["compatible"] = []
    return items


class InviteIn(BaseModel):
    provider_ids: List[str]


@router.post("/admin/driver/richieste/{rid}/invite")
async def admin_invite(rid: str, body: InviteIn, _=Depends(require_admin)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    already = [i.get("provider_id") for i in r.get("provider_invitati", [])]
    new_invites = []
    reset = 0
    for pid in body.provider_ids:
        if pid in already:
            res = await db.richieste.update_one(
                {"richiesta_id": rid, "provider_invitati": {"$elemMatch": {"provider_id": pid, "status": "declined"}}},
                {"$set": {"provider_invitati.$.status": "invited", "provider_invitati.$.reinvited_at": now_utc().isoformat()}})
            if res.modified_count:
                reset += 1
                await push_notification(pid, "driver_invito", "Nuova richiesta corsa",
                                        "Hai ricevuto di nuovo una richiesta di corsa.", "driver", rid)
            continue
        new_invites.append({"provider_id": pid, "at": now_utc().isoformat(), "status": "invited"})
        await push_notification(pid, "driver_invito", "Nuova richiesta corsa",
                                "Hai ricevuto una richiesta di corsa compatibile.", "driver", rid)
    if new_invites or reset:
        upd = {"$set": {"stato": "in_matching", "updated_at": now_utc().isoformat()}}
        if new_invites:
            upd["$push"] = {"provider_invitati": {"$each": new_invites}}
        await db.richieste.update_one({"richiesta_id": rid}, upd)
    return {"invited": len(new_invites)}


class AuthDecisionIn(BaseModel):
    verified: bool


@router.post("/admin/driver/{user_id}/authorization")
async def admin_auth(user_id: str, body: AuthDecisionIn, _=Depends(require_admin)):
    await db.users.update_one({"user_id": user_id}, {"$set": {"driver_auth_verified": body.verified}})
    msg = "Autorizzazione/licenza verificata (badge attivo)." if body.verified else "Autorizzazione non validata. Ricaricala."
    await push_notification(user_id, "driver_auth", "Verifica autorizzazione", msg, "profile", user_id)
    return {"user_id": user_id, "driver_auth_verified": body.verified}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/driver/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "driver_fee_pct"}, {"$set": {"value": float(body.fee_pct)}}, upsert=True)
    return {"fee_pct": body.fee_pct}
