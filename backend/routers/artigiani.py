"""JOBBY — Spec 7 ARTIGIANI subsystem (two-stage flow).

Stage 1 (paniere): fixed-price standard interventions like pulizie.
Stage 2 (chiamata-diagnosi): paid diagnosis call, then in-app structured quote
(valid 7 days, one-tap accept, call fee deducted/scomputo), extras need approval,
mandatory close with outcome, 30-day platform guarantee. Tuttofare also on Libretto.
"""
from datetime import timedelta, datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id, haversine
from deps import get_current_user, require_admin
from routers.notifications import push_notification
import artigiani_config as A

router = APIRouter()

STATES_OPEN = ("pubblicata", "in_matching", "con_proposte")
CAT = {"categoria": "ARTIGIANI", "servizio": "ARTIGIANI"}


async def fee_pct() -> float:
    s = await db.settings.find_one({"key": "artigiani_fee_pct"})
    try:
        return float(s["value"]) if s else A.DEFAULT_FEE_PCT
    except Exception:
        return A.DEFAULT_FEE_PCT


def _parse(dt: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


def _mestiere(mid: str) -> Optional[dict]:
    return next((m for m in A.MESTIERI if m["id"] == mid), None)


def compute_chiamata_fee(lst: dict, distance_km: float, urgente: bool) -> float:
    """Diritto di chiamata (Ispezione): base + €/km oltre i km inclusi, +% urgenza, minimo garantito.
    Fallback al vecchio campo flat 'chiamata_fee' se i nuovi parametri non sono impostati."""
    d = A.DEFAULT_CHIAMATA
    base = float(lst.get("chiamata_base", lst.get("chiamata_fee", d["chiamata_base"])) or 0)
    per_km = float(lst.get("chiamata_per_km", d["chiamata_per_km"]) or 0)
    incl = float(lst.get("chiamata_km_inclusi", d["chiamata_km_inclusi"]) or 0)
    minimo = float(lst.get("chiamata_minimo", 0) or 0)
    urg_pct = float(lst.get("chiamata_urgenza_pct", 0) or 0)
    extra_km = max(0.0, float(distance_km or 0) - incl)
    fee = base + per_km * extra_km
    if urgente and urg_pct:
        fee = fee * (1 + urg_pct / 100.0)
    return round(max(fee, minimo), 2)


def route_tuttofare(descrizione: str) -> Optional[str]:
    """If a handyman request touches impianti, suggest the abilitato mestiere."""
    d = (descrizione or "").lower()
    for mid, kws in A.IMPIANTI_ROUTING.items():
        if any(k in d for k in kws):
            return mid
    return None


async def compatible_providers(mestiere: str, binario: str, lat: float, lng: float, urgente: bool) -> list:
    q = {"role": {"$in": ["provider", "business"]}, "services": "artigiani",
         "approval_status": {"$nin": ["rejected", "suspended", "waitlist", "pending"]},
         "art_listini." + mestiere: {"$exists": True}}
    out = []
    for p in await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(200):
        lst = (p.get("art_listini") or {}).get(mestiere) or {}
        if binario == "persona_lf" and lst.get("binario") != "persona_lf":
            continue
        if binario == "impresa" and lst.get("binario") == "persona_lf":
            continue
        if urgente and not lst.get("urgenze"):
            continue
        dist = haversine(lat, lng, p.get("lat", 0), p.get("lng", 0))
        if dist > float(lst.get("raggio_km", 20)):
            continue
        out.append({"provider": p, "distance": round(dist, 1), "listino": lst})
    return out


# ---------------- config / paniere / estimate ----------------
@router.get("/artigiani/config")
async def get_config(user=Depends(get_current_user)):
    return {"mestieri": A.MESTIERI, "paniere": A.PANIERE, "esiti": A.ESITI, "binari": A.BINARI,
            "parametri": A.PARAMETRI, "fasce_orarie": A.FASCE_ORARIE, "chiamata_default": A.DEFAULT_CHIAMATA,
            "fasce_urgenza": A.FASCE_URGENZA, "garanzia_giorni": A.GARANZIA_DAYS,
            "preventivo_giorni": A.PREVENTIVO_VALIDITY_DAYS, "fee_pct": await fee_pct()}


class RouteCheck(BaseModel):
    descrizione: str


@router.post("/artigiani/route-check")
async def route_check(body: RouteCheck, user=Depends(get_current_user)):
    mid = route_tuttofare(body.descrizione)
    return {"suggested_mestiere": mid, "mestiere_label": (_mestiere(mid) or {}).get("it") if mid else None}


class EstimateIn(BaseModel):
    mestiere: str
    modalita: str = "diagnosi"     # paniere | diagnosi
    intervento_id: str = ""
    binario: str = "impresa"
    urgente: bool = False
    lat: float = 45.6669
    lng: float = 12.2433


@router.post("/artigiani/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    provs = await compatible_providers(body.mestiere, body.binario, body.lat, body.lng, body.urgente)
    prices = []
    for pp in provs:
        lst = pp["listino"]
        if body.modalita == "paniere":
            pr = next((x["prezzo"] for x in (lst.get("paniere") or []) if x["id"] == body.intervento_id), None)
            if pr is None:
                default = next((x for x in A.PANIERE.get(body.mestiere, []) if x["id"] == body.intervento_id), None)
                pr = default["prezzo"] if default else None
            if pr is None:
                continue
            if body.urgente:
                pr = pr * (1 + float(lst.get("urgenze_pct", 0)) / 100.0)
        else:
            pr = compute_chiamata_fee(lst, pp["distance"], body.urgente)
        prices.append(round(pr, 2))
    return {"providers": len(provs), "modalita": body.modalita,
            "min": round(min(prices), 2) if prices else None, "max": round(max(prices), 2) if prices else None}


# ---------------- provider listino (per mestiere) ----------------
class MestiereListino(BaseModel):
    binario: str = "impresa"
    chiamata_fee: float = 50.0        # legacy flat fee (fallback)
    chiamata_base: float = 40.0       # diritto di chiamata: base fissa
    chiamata_per_km: float = 1.5      # €/km oltre i km inclusi
    chiamata_km_inclusi: float = 5.0  # km inclusi nella base
    chiamata_urgenza_pct: float = 20.0
    chiamata_minimo: float = 40.0
    tariffa_oraria: float = 35.0
    paniere: List[dict] = []          # [{id,prezzo}]
    urgenze: bool = False
    urgenze_pct: float = 0.0
    fasce_urgenza: List[str] = []
    raggio_km: float = 20.0
    tempi_tipici: str = ""
    abilitazione_numero: str = ""


@router.get("/artigiani/listino")
async def get_listino(user=Depends(get_current_user)):
    return {"art_listini": user.get("art_listini", {}),
            "abilitazioni": {"verified": bool(user.get("art_abilitazione_verified")),
                             "fgas": bool(user.get("art_fgas_doc")),
                             "uploaded": bool(user.get("art_abilitazione_doc"))}}


class ListinoIn(BaseModel):
    mestiere: str
    listino: MestiereListino


@router.put("/artigiani/listino")
async def set_listino(body: ListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    if not _mestiere(body.mestiere):
        raise HTTPException(status_code=400, detail="invalid_mestiere")
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {f"art_listini.{body.mestiere}": body.listino.dict(),
                                        "services": list(set((user.get("services") or []) + ["artigiani"]))}})
    return {"mestiere": body.mestiere, "listino": body.listino.dict()}


class AbilitazioneIn(BaseModel):
    kind: str = "abilitazione"        # abilitazione | fgas
    image: str


@router.post("/artigiani/abilitazione")
async def upload_abilitazione(body: AbilitazioneIn, user=Depends(get_current_user)):
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="invalid_document")
    field = "art_fgas_doc" if body.kind == "fgas" else "art_abilitazione_doc"
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {field: body.image, "art_abilitazione_verified": False,
                                        "art_abilitazione_uploaded_at": now_utc().isoformat()}})
    return {"uploaded": True}


# ---------------- richiesta CRUD ----------------
class RichiestaIn(BaseModel):
    mestiere: str
    modalita: str = "diagnosi"        # paniere | diagnosi (Ispezione)
    intervento_id: str = ""
    parametri: dict = {}              # risposte ai parametri per mestiere
    descrizione: str = ""
    foto: List[str] = []
    binario: str = "impresa"
    urgente: bool = False
    fascia_urgenza: str = ""
    fascia_oraria: str = ""           # mattina | pomeriggio | sera (intervento programmato)
    indirizzo: str = ""
    accesso: str = ""
    lat: float
    lng: float
    data_ora: str = ""


@router.post("/artigiani/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    m = _mestiere(body.mestiere)
    if not m:
        raise HTTPException(status_code=400, detail="invalid_mestiere")
    if body.binario == "persona_lf" and not m["libretto"]:
        raise HTTPException(status_code=400, detail="binario_not_allowed")
    if body.modalita not in ("paniere", "diagnosi"):
        raise HTTPException(status_code=400, detail="invalid_modalita")
    rid = new_id("art")
    intervento = None
    if body.modalita == "paniere":
        intervento = next((x for x in A.PANIERE.get(body.mestiere, []) if x["id"] == body.intervento_id), None)
    config = {"mestiere": body.mestiere, "modalita": body.modalita, "intervento_id": body.intervento_id,
              "intervento": intervento, "parametri": body.parametri, "descrizione": body.descrizione,
              "foto": body.foto, "urgente": body.urgente, "fascia_urgenza": body.fascia_urgenza,
              "fascia_oraria": body.fascia_oraria}
    doc = {
        "richiesta_id": rid, "cliente_id": user["user_id"], "cliente_nome": user.get("name", ""),
        **CAT, "binario": body.binario, "config": config,
        "indirizzo": body.indirizzo, "accesso": body.accesso, "lat": body.lat, "lng": body.lng,
        "data_ora": body.data_ora, "urgente": body.urgente,
        "stato": "pubblicata", "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "chiamata_pagata": False, "preventivo": None, "esito": None, "extra": [],
        "pagamento": {"stato": "none"}, "recensione": None, "garanzia_fino": None,
        "created_at": now_utc().isoformat(), "updated_at": now_utc().isoformat(),
        "scade_at": (now_utc() + timedelta(hours=A.PROPOSAL_WINDOW_HOURS)).isoformat(),
    }
    await db.richieste.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/artigiani/richieste")
async def my_richieste(user=Depends(get_current_user)):
    return await db.richieste.find({"cliente_id": user["user_id"], **CAT}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/artigiani/richieste/{rid}")
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
    if not (is_owner or is_confirmed):
        r.pop("indirizzo", None); r.pop("accesso", None)
    return r


@router.post("/artigiani/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] in ("completata", "recensita", "annullata"):
        raise HTTPException(status_code=400, detail="already_closed")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"stato": "annullata", "updated_at": now_utc().isoformat()}})
    return {"stato": "annullata"}


# ---------------- provider side ----------------
@router.get("/artigiani/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        return []
    items = await db.richieste.find(
        {"provider_invitati.provider_id": user["user_id"], "stato": {"$in": list(STATES_OPEN)}, **CAT},
        {"_id": 0}).sort([("urgente", -1), ("created_at", -1)]).to_list(100)
    for r in items:
        cfg = r["config"]
        lst = (user.get("art_listini") or {}).get(cfg["mestiere"]) or {}
        if cfg["modalita"] == "paniere":
            pr = next((x["prezzo"] for x in (lst.get("paniere") or []) if x["id"] == cfg["intervento_id"]),
                      (cfg.get("intervento") or {}).get("prezzo"))
            if pr is not None and r.get("urgente"):
                pr = round(pr * (1 + float(lst.get("urgenze_pct", 0)) / 100.0), 2)
        else:
            dist = haversine(r.get("lat", 0), r.get("lng", 0), user.get("lat", 0), user.get("lng", 0))
            pr = compute_chiamata_fee(lst, dist, r.get("urgente", False))
        r["my_price"] = pr
        r["my_proposal"] = next((p for p in r.get("proposte", []) if p.get("provider_id") == user["user_id"]), None)
        r.pop("indirizzo", None); r.pop("accesso", None)
    return items


class ProposeIn(BaseModel):
    accept: bool
    message: str = ""


@router.post("/artigiani/richieste/{rid}/propose")
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
    cfg = r["config"]; lst = (user.get("art_listini") or {}).get(cfg["mestiere"]) or {}
    if cfg["modalita"] == "paniere":
        prezzo = next((x["prezzo"] for x in (lst.get("paniere") or []) if x["id"] == cfg["intervento_id"]),
                      (cfg.get("intervento") or {}).get("prezzo", 0))
        if r.get("urgente"):
            prezzo = round(prezzo * (1 + float(lst.get("urgenze_pct", 0)) / 100.0), 2)
    else:
        dist = haversine(r.get("lat", 0), r.get("lng", 0), user.get("lat", 0), user.get("lng", 0))
        prezzo = compute_chiamata_fee(lst, dist, r.get("urgente", False))
    proposal = {
        "provider_id": user["user_id"], "provider_nome": user.get("business_name") or user.get("name", ""),
        "provider_rating": user.get("rating", 0), "provider_trust": user.get("trust_score", 0),
        "abilitazione_ok": bool(user.get("art_abilitazione_verified")),
        "tariffa_oraria": lst.get("tariffa_oraria"), "tempi_tipici": lst.get("tempi_tipici"),
        "prezzo": round(prezzo, 2), "modalita": cfg["modalita"], "message": body.message, "at": now_utc().isoformat(),
    }
    await db.richieste.update_one({"richiesta_id": rid}, {"$pull": {"proposte": {"provider_id": user["user_id"]}}})
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$push": {"proposte": proposal},
                                   "$set": {"stato": "con_proposte", "updated_at": now_utc().isoformat()}})
    label = "chiamata-diagnosi" if cfg["modalita"] == "diagnosi" else "intervento"
    await push_notification(r["cliente_id"], "artigiani_proposta", "Nuova proposta artigiano",
                            f"{proposal['provider_nome']}: €{prezzo:.2f} ({label})", "artigiani", rid)
    return proposal


class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/artigiani/richieste/{rid}/confirm")
async def confirm(rid: str, body: ConfirmIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "con_proposte":
        raise HTTPException(status_code=400, detail="no_proposals")
    prop = next((p for p in r.get("proposte", []) if p.get("provider_id") == body.provider_id), None)
    if not prop:
        raise HTTPException(status_code=400, detail="proposal_not_found")
    is_diagnosi = r["config"]["modalita"] == "diagnosi"
    fee = await fee_pct()
    jobby_fee = round(prop["prezzo"] * fee / 100.0, 2)
    upd = {"stato": "confermata", "provider_scelto": body.provider_id, "prezzo_iniziale": prop["prezzo"],
           "chiamata_fee": prop["prezzo"] if is_diagnosi else 0, "chiamata_pagata": True,
           "jobby_fee": jobby_fee,
           "pagamento": {"stato": "chiamata_pagata" if is_diagnosi else "intervento_pagato",
                         "importo": prop["prezzo"], "at": now_utc().isoformat()},
           "updated_at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": upd})
    await push_notification(body.provider_id, "artigiani_confermata", "Sei stato scelto!",
                            "Un cliente ti ha scelto. Organizza l'intervento.", "artigiani", rid)
    return {**r, **upd}


# ---------------- stage 2: preventivo + esito ----------------
class PreventivoVoce(BaseModel):
    descrizione: str
    tipo: str = "manodopera"     # manodopera | materiale
    qta: float = 1
    prezzo_unit: float = 0


class PreventivoIn(BaseModel):
    esito: str                    # preventivo | risolto_diagnosi | non_riparabile
    voci: List[PreventivoVoce] = []
    descrizione_lavoro: str = ""
    tempi: str = ""
    secondo_appuntamento: str = ""
    scomputo_chiamata: bool = True   # l'artigiano decide se scomputare il diritto di chiamata


@router.post("/artigiani/richieste/{rid}/preventivo")
async def compose_preventivo(rid: str, body: PreventivoIn, user=Depends(get_current_user)):
    """Mandatory close: provider composes a quote OR declares an outcome."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="invalid_state")
    if body.esito not in [e["id"] for e in A.ESITI]:
        raise HTTPException(status_code=400, detail="invalid_esito")
    if body.esito != "preventivo":
        # solved during diagnosis / not repairable -> close now (call fee already paid)
        await db.richieste.update_one({"richiesta_id": rid},
                                      {"$set": {"esito": body.esito, "stato": "completata",
                                                "importo_totale": r.get("chiamata_fee", 0),
                                                "garanzia_fino": (now_utc() + timedelta(days=A.GARANZIA_DAYS)).isoformat() if body.esito == "risolto_diagnosi" else None,
                                                "completed_at": now_utc().isoformat(), "updated_at": now_utc().isoformat()}})
        await push_notification(r["cliente_id"], "artigiani_chiuso", "Intervento chiuso",
                                f"Esito: {next(e['it'] for e in A.ESITI if e['id']==body.esito)}", "artigiani", rid)
        return {"stato": "completata", "esito": body.esito}
    totale = round(sum(v.qta * v.prezzo_unit for v in body.voci), 2)
    scomputo = float(r.get("chiamata_fee", 0)) if body.scomputo_chiamata else 0.0
    da_pagare = round(max(0.0, totale - scomputo), 2)
    prev = {"voci": [v.dict() for v in body.voci], "descrizione_lavoro": body.descrizione_lavoro,
            "tempi": body.tempi, "totale": totale, "scomputo": scomputo, "da_pagare": da_pagare,
            "scomputo_chiamata": body.scomputo_chiamata,
            "secondo_appuntamento": body.secondo_appuntamento, "stato": "in_attesa",
            "big_job": totale >= A.BIG_JOB_THRESHOLD_EUR,
            "scade_at": (now_utc() + timedelta(days=A.PREVENTIVO_VALIDITY_DAYS)).isoformat(),
            "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"preventivo": prev, "esito": "preventivo", "stato": "preventivo",
                                            "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "artigiani_preventivo", "Preventivo pronto",
                            f"Totale €{totale:.2f} (chiamata €{scomputo:.2f} scalata → paghi €{da_pagare:.2f}). Valido 7 giorni.", "artigiani", rid)
    return prev


@router.post("/artigiani/richieste/{rid}/preventivo/accept")
async def accept_preventivo(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    prev = r.get("preventivo")
    if not prev or prev.get("stato") != "in_attesa":
        raise HTTPException(status_code=400, detail="no_pending_quote")
    if _parse(prev.get("scade_at", "")) and now_utc() > _parse(prev["scade_at"]):
        await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"preventivo.stato": "scaduto"}})
        raise HTTPException(status_code=400, detail="quote_expired")
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"preventivo.stato": "accettato", "stato": "in_corso",
                                            "pagamento.stato": "lavoro_pagato", "pagamento.lavoro": prev["da_pagare"],
                                            "updated_at": now_utc().isoformat()}})
    await push_notification(r["provider_scelto"], "artigiani_accettato", "Preventivo accettato",
                            "Il cliente ha accettato il preventivo. Puoi procedere.", "artigiani", rid)
    return {"stato": "in_corso", "pagato": prev["da_pagare"]}


@router.post("/artigiani/richieste/{rid}/preventivo/reject")
async def reject_preventivo(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if not r.get("preventivo"):
        raise HTTPException(status_code=400, detail="no_quote")
    # call stays paid, close with outcome
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"preventivo.stato": "rifiutato", "stato": "completata",
                                            "importo_totale": r.get("chiamata_fee", 0), "esito": "preventivo_rifiutato",
                                            "completed_at": now_utc().isoformat(), "updated_at": now_utc().isoformat()}})
    return {"stato": "completata", "preventivo": "rifiutato"}


# ---------------- extras in corso ----------------
class ExtraIn(BaseModel):
    descrizione: str
    importo: float


@router.post("/artigiani/richieste/{rid}/extra")
async def add_extra(rid: str, body: ExtraIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    extra = {"extra_id": new_id("ex"), "descrizione": body.descrizione, "importo": round(body.importo, 2),
             "stato": "pending", "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$push": {"extra": extra}})
    await push_notification(r["cliente_id"], "artigiani_extra", "Extra da approvare",
                            f"{body.descrizione}: €{body.importo:.2f}", "artigiani", rid)
    return extra


class ExtraApprove(BaseModel):
    extra_id: str
    approve: bool


@router.post("/artigiani/richieste/{rid}/extra/approve")
async def approve_extra(rid: str, body: ExtraApprove, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    await db.richieste.update_one({"richiesta_id": rid, "extra.extra_id": body.extra_id},
                                  {"$set": {"extra.$.stato": "approved" if body.approve else "rejected"}})
    return {"extra_id": body.extra_id, "stato": "approved" if body.approve else "rejected"}


class CloseIn(BaseModel):
    foto_dopo: List[str] = []


@router.post("/artigiani/richieste/{rid}/complete")
async def complete(rid: str, body: CloseIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    prev = r.get("preventivo") or {}
    extras = sum(e["importo"] for e in r.get("extra", []) if e.get("stato") == "approved")
    base = float(prev.get("da_pagare", 0)) + float(r.get("chiamata_fee", 0)) if r["config"]["modalita"] == "diagnosi" else float(r.get("prezzo_iniziale", 0))
    totale = round(base + extras, 2)
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"stato": "completata", "importo_totale": totale, "extra_totale": extras,
                                            "foto_dopo": body.foto_dopo, "esito": r.get("esito") or "completato",
                                            "garanzia_fino": (now_utc() + timedelta(days=A.GARANZIA_DAYS)).isoformat(),
                                            "completed_at": now_utc().isoformat(), "updated_at": now_utc().isoformat()}})
    # maintenance reminder for seasonal mestieri
    m = _mestiere(r["config"]["mestiere"])
    if m and m.get("stagionale"):
        await db.maintenance_reminders.insert_one({
            "cliente_id": r["cliente_id"], "provider_id": r["provider_scelto"], "mestiere": m["id"],
            "richiesta_id": rid, "remind_at": (now_utc() + timedelta(days=365)).isoformat(), "sent": False,
            "created_at": now_utc().isoformat()})
    await push_notification(r["cliente_id"], "artigiani_completata", "Intervento completato",
                            f"Totale €{totale:.2f}. Garanzia 30 giorni attiva. Lascia una recensione.", "artigiani", rid)
    return {"stato": "completata", "importo_totale": totale}


@router.post("/artigiani/richieste/{rid}/garanzia")
async def open_garanzia(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if not r.get("garanzia_fino") or now_utc() > _parse(r["garanzia_fino"]):
        raise HTTPException(status_code=400, detail="garanzia_expired")
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"garanzia_richiesta": True, "updated_at": now_utc().isoformat()}})
    await push_notification(r["provider_scelto"], "artigiani_garanzia", "Richiesta in garanzia",
                            "Il cliente ha aperto la garanzia: torna senza nuova chiamata.", "artigiani", rid)
    return {"garanzia_richiesta": True}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/artigiani/richieste/{rid}/review")
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
@router.get("/admin/artigiani/richieste")
async def admin_richieste(_=Depends(require_admin)):
    items = await db.richieste.find({"stato": {"$in": list(STATES_OPEN)}, **CAT}, {"_id": 0}) \
        .sort([("urgente", -1), ("created_at", -1)]).to_list(200)
    for r in items:
        cfg = r["config"]
        provs = await compatible_providers(cfg["mestiere"], r["binario"], r["lat"], r["lng"], r.get("urgente", False))
        r["compatible"] = [{
            "provider_id": pp["provider"]["user_id"], "nome": pp["provider"].get("business_name") or pp["provider"].get("name"),
            "distance": pp["distance"], "rating": pp["provider"].get("rating", 0),
            "abilitazione_ok": bool(pp["provider"].get("art_abilitazione_verified")),
            "invited": pp["provider"]["user_id"] in [i.get("provider_id") for i in r.get("provider_invitati", [])],
        } for pp in provs]
    return items


class InviteIn(BaseModel):
    provider_ids: List[str]


@router.post("/admin/artigiani/richieste/{rid}/invite")
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
        await push_notification(pid, "artigiani_invito", "Nuova richiesta artigiano",
                                "Hai ricevuto una richiesta compatibile.", "artigiani", rid)
    if new_invites:
        await db.richieste.update_one({"richiesta_id": rid},
                                      {"$push": {"provider_invitati": {"$each": new_invites}},
                                       "$set": {"stato": "in_matching", "updated_at": now_utc().isoformat()}})
    return {"invited": len(new_invites)}


class AbilitazioneDecision(BaseModel):
    verified: bool


@router.post("/admin/artigiani/{user_id}/abilitazione")
async def admin_abilitazione(user_id: str, body: AbilitazioneDecision, _=Depends(require_admin)):
    await db.users.update_one({"user_id": user_id}, {"$set": {"art_abilitazione_verified": body.verified}})
    msg = "Abilitazione verificata (badge attivo)." if body.verified else "Abilitazione non validata. Ricaricala."
    await push_notification(user_id, "artigiani_abilitazione", "Verifica abilitazione", msg, "profile", user_id)
    return {"user_id": user_id, "art_abilitazione_verified": body.verified}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/artigiani/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "artigiani_fee_pct"}, {"$set": {"value": float(body.fee_pct)}}, upsert=True)
    return {"fee_pct": body.fee_pct}
