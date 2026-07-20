"""JOBBY — Spec 6 Babysitting subsystem.

Reuses the `richieste` engine (state machine, dual-track IMPRESA-PIVA / PERSONA_LF,
payments, reviews) with the centre of gravity shifted from the price list to the
person: extended babysitter profile, child cards with two visibility levels,
meet-and-greet after paid confirmation, double start/end code with auto-confirm,
minimum guaranteed hours + overtime consuntivo, ripetizioni as an extra.
"""
import math
import random
from datetime import timedelta, datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, now_utc, new_id, haversine
from deps import get_current_user, require_admin
from routers.notifications import push_notification
import babysitting_config as B
from richieste_config import lf_round_nominale

router = APIRouter()

STATES_OPEN = ("pubblicata", "in_matching", "con_proposte")
CAT = {"categoria": "FAMIGLIA", "servizio": "BABYSITTING"}


# ---------------- settings ----------------
async def fee_pct() -> float:
    s = await db.settings.find_one({"key": "babysitting_fee_pct"})
    try:
        return float(s["value"]) if s else B.DEFAULT_FEE_PCT
    except Exception:
        return B.DEFAULT_FEE_PCT


def _parse(dt: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


def _round_quarter(hours: float) -> float:
    return round(round(hours * 60 / B.ROUNDING_MIN) * B.ROUNDING_MIN / 60.0, 2)


# ---------------- child cards (schede bambino) ----------------
class ChildIn(BaseModel):
    nome: str
    eta_mesi: int                       # age in months (>=12 to be requestable)
    sesso: str = ""                     # m | f | ""
    abitudini: str = ""
    allergie: str = ""
    note: str = ""
    consenso: bool = False


def _child_public(c: dict) -> dict:
    return {k: c.get(k) for k in ("card_id", "nome", "eta_mesi", "sesso", "abitudini",
                                  "allergie", "note", "consenso", "created_at")}


@router.get("/babysitting/children")
async def list_children(user=Depends(get_current_user)):
    cards = await db.child_cards.find({"family_id": user["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(50)
    return cards


@router.post("/babysitting/children")
async def create_child(body: ChildIn, user=Depends(get_current_user)):
    if not body.consenso:
        raise HTTPException(status_code=400, detail="consent_required")
    if not body.nome.strip():
        raise HTTPException(status_code=400, detail="name_required")
    cid = new_id("child")
    doc = {"card_id": cid, "family_id": user["user_id"], **body.dict(),
           "created_at": now_utc().isoformat()}
    await db.child_cards.insert_one(doc)
    return _child_public(doc)


@router.put("/babysitting/children/{cid}")
async def update_child(cid: str, body: ChildIn, user=Depends(get_current_user)):
    c = await db.child_cards.find_one({"card_id": cid, "family_id": user["user_id"]})
    if not c:
        raise HTTPException(status_code=404, detail="not_found")
    await db.child_cards.update_one({"card_id": cid}, {"$set": body.dict()})
    c = await db.child_cards.find_one({"card_id": cid}, {"_id": 0})
    return _child_public(c)


@router.delete("/babysitting/children/{cid}")
async def delete_child(cid: str, user=Depends(get_current_user)):
    res = await db.child_cards.delete_one({"card_id": cid, "family_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="not_found")
    return {"deleted": True}


def _age_band(eta_mesi: int) -> str:
    y = eta_mesi / 12.0
    if y < 3: return "1_3"
    if y < 6: return "3_6"
    if y < 10: return "6_10"
    if y < 14: return "10_14"
    return "over14"


def _generic_children(cards: list) -> list:
    """First visibility level — no name/photo/details, only what a provider needs to accept."""
    out = []
    for c in cards:
        band = next((b for b in B.AGE_BANDS if b["id"] == _age_band(c.get("eta_mesi", 12))), None)
        out.append({
            "eta_band": band["id"] if band else "3_6",
            "eta_band_it": band["it"] if band else "",
            "esigenza": "allergia" if (c.get("allergie") or "").strip() else "",
        })
    return out


# ---------------- babysitter extended profile (Spec 6 §3) ----------------
class BsProfileIn(BaseModel):
    esperienza_anni: int = 0
    fasce_eta: List[str] = []
    lingue: List[str] = []
    certificazioni: List[str] = []
    materie: List[str] = []
    livelli: List[str] = []
    presentazione: dict = {}            # {perche, pomeriggio, genitori}
    disponibilita: List[str] = []


@router.get("/babysitting/profile")
async def get_bs_profile(user=Depends(get_current_user)):
    p = user.get("bs_profile") or {}
    return {"bs_profile": p, "casellario": {
        "uploaded": bool(user.get("casellario_doc")),
        "verified": bool(user.get("casellario_verified")),
        "expires_at": user.get("casellario_expires"),
    }}


@router.put("/babysitting/profile")
async def set_bs_profile(body: BsProfileIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"bs_profile": body.dict()}})
    return {"bs_profile": body.dict()}


class CasellarioIn(BaseModel):
    image: str


@router.post("/babysitting/casellario")
async def upload_casellario(body: CasellarioIn, user=Depends(get_current_user)):
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="invalid_document")
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"casellario_doc": body.image, "casellario_verified": False,
                                        "casellario_uploaded_at": now_utc().isoformat()}})
    return {"uploaded": True}


# ---------------- provider listino (Spec 6 §8) ----------------
class BsListino(BaseModel):
    binario: str = "persona_lf"
    tariffa_oraria: float = 10.0
    tariffa_ripetizioni: dict = {"elementari": 12.0, "medie": 16.0, "superiori": 20.0}
    materie: List[str] = []
    maggiorazione_serale_pct: float = 0.0     # after 20:00
    maggiorazione_festiva_pct: float = 0.0
    supplemento_bambino: float = 0.0          # per additional child (optional)
    raggio_km: float = 15.0
    minimo_ore: float = 2.0


@router.get("/babysitting/listino")
async def get_listino(user=Depends(get_current_user)):
    return {"bs_binario": user.get("bs_binario", "persona_lf"), "listino": user.get("bs_listino")}


class BsListinoIn(BaseModel):
    binario: str = "persona_lf"
    listino: BsListino


@router.put("/babysitting/listino")
async def set_listino(body: BsListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    lst = body.listino.dict()
    lst["binario"] = body.binario
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"bs_binario": body.binario, "bs_listino": lst,
                                        "services": list(set((user.get("services") or []) + ["babysitting"]))}})
    return {"bs_binario": body.binario, "listino": lst}


# ---------------- price engine ----------------
class BsConfig(BaseModel):
    n_bambini: int = 1
    durata_ore: float = 3.0                    # booked hours (end - start)
    ripetizioni_attiva: bool = False
    ripetizioni_materie: List[str] = []
    ripetizioni_ore: float = 0.0
    ripetizioni_livello: str = "medie"
    serale: bool = False
    festivo: bool = False


def compute_work_total(listino: dict, config: dict) -> dict:
    ore_tot = float(config.get("durata_ore", 0) or 0)
    ore_rip = float(config.get("ripetizioni_ore", 0) or 0) if config.get("ripetizioni_attiva") else 0
    ore_rip = min(ore_rip, ore_tot)
    ore_bs = max(0.0, ore_tot - ore_rip)
    tariffa_bs = float(listino.get("tariffa_oraria", 10.0))
    livello = config.get("ripetizioni_livello", "medie")
    tariffa_rip = float((listino.get("tariffa_ripetizioni") or {}).get(livello, 15.0))
    base_bs = ore_bs * tariffa_bs
    base_rip = ore_rip * tariffa_rip
    base = base_bs + base_rip
    if config.get("serale"):
        base *= (1 + float(listino.get("maggiorazione_serale_pct", 0)) / 100.0)
    if config.get("festivo"):
        base *= (1 + float(listino.get("maggiorazione_festiva_pct", 0)) / 100.0)
    extra_children = max(0, int(config.get("n_bambini", 1)) - 1)
    supp = extra_children * float(listino.get("supplemento_bambino", 0) or 0)
    total = round(base + supp, 2)
    return {"work_total": total, "ore_babysitting": ore_bs, "ore_ripetizioni": ore_rip,
            "voce_babysitting": round(base_bs, 2), "voce_ripetizioni": round(base_rip, 2),
            "supplemento_bambini": round(supp, 2)}


def price_breakdown(listino: dict, config: dict, binario: str, fee: float) -> dict:
    w = compute_work_total(listino, config)
    work = w["work_total"]
    jobby_fee = round(work * fee / 100.0, 2)
    out = {**w, "jobby_fee": jobby_fee, "fee_pct": fee, "total_client": round(work + jobby_fee, 2)}
    if binario == "persona_lf":
        nominale = lf_round_nominale(work)
        out.update({"lf_nominale": nominale, "lf_voucher": int(nominale / 10),
                    "lf_netto_lavoratrice": round(nominale * B.LF_VOUCHER_NET_RATE, 2),
                    "total_client": round(nominale + jobby_fee, 2)})
    return out


async def compatible_providers(binario: str, config: dict, lat: float, lng: float) -> list:
    q = {"role": {"$in": ["provider", "business"]}, "services": "babysitting",
         "approval_status": {"$nin": ["rejected", "suspended", "waitlist", "pending"]},
         "bs_binario": binario, "bs_listino": {"$exists": True}}
    out = []
    for p in await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(200):
        if binario == "persona_lf" and p.get("lf_inps_registered") is False:
            continue
        lst = p.get("bs_listino") or {}
        dist = haversine(lat, lng, p.get("lat", 0), p.get("lng", 0))
        if dist > float(lst.get("raggio_km", 15)):
            continue
        if float(config.get("durata_ore", 0)) < float(lst.get("minimo_ore", 0)):
            continue
        # ripetizioni subject/level filter
        if config.get("ripetizioni_attiva"):
            prof_mat = set(lst.get("materie", []))
            if not set(config.get("ripetizioni_materie", [])).issubset(prof_mat):
                continue
        out.append({"provider": p, "distance": round(dist, 1), "listino": lst})
    return out


# ---------------- config / estimate ----------------
@router.get("/babysitting/config")
async def get_config(user=Depends(get_current_user)):
    return {
        "school_levels": B.SCHOOL_LEVELS, "subjects": B.SUBJECTS, "languages": B.LANGUAGES,
        "certifications": B.CERTIFICATIONS, "age_bands": B.AGE_BANDS,
        "availability_slots": B.AVAILABILITY_SLOTS, "ricorrenze": B.RICORRENZE,
        "guided_questions": B.GUIDED_QUESTIONS, "binari": B.BINARI,
        "emergency_numbers": B.EMERGENCY_NUMBERS, "min_child_age_months": B.MIN_CHILD_AGE_MONTHS,
        "fee_pct": await fee_pct(),
    }


class EstimateIn(BaseModel):
    binario: str = "persona_lf"
    config: BsConfig
    lat: float = 45.6669
    lng: float = 12.2433


@router.post("/babysitting/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    cfg = body.config.dict()
    fee = await fee_pct()
    result = {}
    for binario in ("persona_lf", "piva"):
        provs = await compatible_providers(binario, cfg, body.lat, body.lng)
        prices = [price_breakdown(pp["listino"], cfg, binario, fee)["total_client"] for pp in provs]
        result[binario] = {"providers": len(provs),
                           "min": round(min(prices), 2) if prices else None,
                           "max": round(max(prices), 2) if prices else None}
    return {"fee_pct": fee, "ranges": result}


# ---------------- richiesta CRUD ----------------
class RichiestaIn(BaseModel):
    binario: str = "persona_lf"
    bambini: List[str] = []                    # child card ids
    config: BsConfig
    indirizzo: str = ""
    lat: float
    lng: float
    data_ora: str = ""                          # start ISO
    ora_fine: str = ""                          # end ISO
    urgente: bool = False
    ricorrenza: str = "una_tantum"
    giorni_preferiti: List[str] = []
    note: str = ""
    accesso: str = ""
    publish: bool = True


@router.post("/babysitting/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    if body.binario not in ("persona_lf", "piva"):
        raise HTTPException(status_code=400, detail="invalid_binario")
    # validate children exist + age gate (>=12 months)
    cards = await db.child_cards.find({"card_id": {"$in": body.bambini}, "family_id": user["user_id"]},
                                      {"_id": 0}).to_list(20)
    if not cards:
        raise HTTPException(status_code=400, detail="no_children_selected")
    for c in cards:
        if int(c.get("eta_mesi", 0)) < B.MIN_CHILD_AGE_MONTHS:
            raise HTTPException(status_code=400, detail="child_too_young")
    cfg = body.config.dict()
    cfg["n_bambini"] = len(cards)
    # derive booked hours from start/end when both present
    st, en = _parse(body.data_ora), _parse(body.ora_fine)
    if st and en and en > st:
        cfg["durata_ore"] = _round_quarter((en - st).total_seconds() / 3600.0)
    rid = new_id("bsr")
    doc = {
        "richiesta_id": rid, "cliente_id": user["user_id"], "cliente_nome": user.get("name", ""),
        **CAT, "binario": body.binario, "config": cfg, "bambini": body.bambini,
        "bambini_generic": _generic_children(cards),
        "indirizzo": body.indirizzo, "accesso": body.accesso, "lat": body.lat, "lng": body.lng,
        "data_ora": body.data_ora, "ora_fine": body.ora_fine, "urgente": body.urgente,
        "ricorrenza": body.ricorrenza, "giorni_preferiti": body.giorni_preferiti,
        "durata_ore": cfg.get("durata_ore"), "note": body.note,
        "stato": "pubblicata" if body.publish else "bozza",
        "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "incontro": None, "inizio": None, "fine": None, "consuntivo": None,
        "pagamento_fee": {"stato": "authorized" if body.publish else "none"},
        "pagamento_lavoro": {"stato": "none"},
        "recensione": None, "created_at": now_utc().isoformat(), "updated_at": now_utc().isoformat(),
    }
    if body.publish:
        doc["scade_at"] = (now_utc() + timedelta(hours=B.PROPOSAL_WINDOW_HOURS)).isoformat()
    await db.richieste.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def _maybe_autoconfirm(r: dict) -> dict:
    """Lazy auto-confirm: if provider ended and parent didn't confirm within 15 min."""
    fine = r.get("fine")
    if r["stato"] == "in_corso" and fine and fine.get("provider_at") and not fine.get("confirmed_at"):
        deadline = _parse(fine.get("deadline", ""))
        if deadline and now_utc() > deadline:
            r = await _finalize_fine(r, auto=True)
    return r


@router.get("/babysitting/richieste")
async def my_richieste(user=Depends(get_current_user)):
    items = await db.richieste.find({"cliente_id": user["user_id"], **CAT}, {"_id": 0}).sort("created_at", -1).to_list(100)
    out = []
    for r in items:
        r = await _maybe_autoconfirm(r)
        out.append(r)
    return out


@router.get("/babysitting/richieste/{rid}")
async def get_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    is_owner = r["cliente_id"] == user["user_id"]
    is_confirmed = r.get("provider_scelto") == user["user_id"]
    is_invited = user["user_id"] in [p.get("provider_id") for p in r.get("provider_invitati", [])]
    if not (is_owner or is_invited or is_confirmed):
        raise HTTPException(status_code=403, detail="forbidden")
    r = await _maybe_autoconfirm(r)
    r["role"] = "client" if is_owner else "provider"
    if is_owner:
        # full child cards for the family
        r["bambini_full"] = await db.child_cards.find({"card_id": {"$in": r.get("bambini", [])}}, {"_id": 0}).to_list(20)
    elif is_confirmed:
        # second visibility level unlocked to the confirmed babysitter
        r["bambini_full"] = await db.child_cards.find({"card_id": {"$in": r.get("bambini", [])}}, {"_id": 0}).to_list(20)
    else:
        r.pop("indirizzo", None)      # exact address hidden until confirmed
        r.pop("accesso", None)
        r.pop("bambini", None)
    return r


@router.post("/babysitting/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] in ("completata", "recensita"):
        raise HTTPException(status_code=400, detail="already_done")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"stato": "annullata", "updated_at": now_utc().isoformat()}})
    return {"stato": "annullata"}


# ---------------- provider side ----------------
@router.get("/babysitting/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        return []
    uid = user["user_id"]
    items = await db.richieste.find(
        {**CAT, "$or": [
            {"provider_invitati": {"$elemMatch": {"provider_id": uid, "status": {"$ne": "declined"}}}, "stato": {"$in": list(STATES_OPEN)}},
            {"provider_scelto": uid, "stato": {"$in": ["confermata", "in_corso"]}},
        ]},
        {"_id": 0}).sort([("urgente", -1), ("created_at", -1)]).to_list(100)
    fee = await fee_pct()
    out = []
    for r in items:
        r.pop("indirizzo", None); r.pop("accesso", None); r.pop("bambini", None)
        lst = user.get("bs_listino") or {}
        r["price"] = price_breakdown(lst, r["config"], r["binario"], fee)
        r["my_proposal"] = next((p for p in r.get("proposte", []) if p.get("provider_id") == user["user_id"]), None)
        out.append(r)
    return out


class ProposeIn(BaseModel):
    accept: bool
    message: str = ""


@router.post("/babysitting/richieste/{rid}/propose")
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
    lst = user.get("bs_listino") or {}
    fee = await fee_pct()
    pb = price_breakdown(lst, r["config"], r["binario"], fee)
    bsp = user.get("bs_profile") or {}
    proposal = {
        "provider_id": user["user_id"], "provider_nome": user.get("business_name") or user.get("name", ""),
        "provider_rating": user.get("rating", 0), "provider_trust": user.get("trust_score", 0),
        "provider_foto": user.get("presentation_photo") or user.get("selfie_document"),
        "esperienza_anni": bsp.get("esperienza_anni", 0), "lingue": bsp.get("lingue", []),
        "certificazioni": bsp.get("certificazioni", []), "presentazione": bsp.get("presentazione", {}),
        "casellario_ok": bool(user.get("casellario_verified")),
        "price": pb["total_client"], "breakdown": pb, "message": body.message, "at": now_utc().isoformat(),
    }
    await db.richieste.update_one({"richiesta_id": rid}, {"$pull": {"proposte": {"provider_id": user["user_id"]}}})
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$push": {"proposte": proposal},
                                   "$set": {"stato": "con_proposte", "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "babysitting_proposta", "Nuova babysitter disponibile",
                            f"{proposal['provider_nome']} è disponibile (€{pb['total_client']:.2f}).", "babysitting", rid)
    return proposal


# ---------------- client confirm + meet-and-greet ----------------
class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/babysitting/richieste/{rid}/confirm")
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
        # engage booked hours + 1h prudential margin (1h of work at the same avg rate)
        nominale = prop["breakdown"].get("lf_nominale", prop["price"])
        work = float(prop["breakdown"].get("work_total", 0))
        booked = max(1.0, float(r["config"].get("durata_ore", 1)))
        margin_nom = lf_round_nominale(work / booked * B.VOUCHER_MARGIN_HOURS)
        impegno = nominale + margin_nom
        bors = round(user.get("lf_borsellino", 0), 2)
        if bors < impegno:
            raise HTTPException(status_code=400, detail="lf_insufficient_borsellino")
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$inc": {"lf_borsellino": -impegno, "lf_year_total": nominale,
                                            "lf_year_hours": float(r["config"].get("durata_ore", 0))}})
        lf = {"nominale": nominale, "impegnato": impegno, "margine": margin_nom,
              "voucher": prop["breakdown"].get("lf_voucher"),
              "netto_lavoratrice": prop["breakdown"].get("lf_netto_lavoratrice"), "stato": "impegnato"}
    upd = {
        "stato": "confermata", "provider_scelto": body.provider_id,
        "pagamento_fee": {"stato": "charged", "importo": prop["breakdown"]["jobby_fee"], "at": now_utc().isoformat()},
        "pagamento_lavoro": ({"stato": "psp_pending", "importo": prop["price"]} if r["binario"] != "persona_lf"
                             else {**lf, "stato": "lf"}),
        "prezzo_finale": prop["price"], "updated_at": now_utc().isoformat(),
    }
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": upd})
    await push_notification(body.provider_id, "babysitting_confermata", "Sei stata scelta!",
                            "Una famiglia ti ha scelto. Organizza l'incontro conoscitivo.", "babysitting", rid)
    return {**r, **upd}


class IncontroIn(BaseModel):
    mode: str                      # video | persona
    slot: str = ""                 # ISO datetime for the planned event


@router.post("/babysitting/richieste/{rid}/incontro")
async def set_incontro(rid: str, body: IncontroIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    if body.mode not in ("video", "persona"):
        raise HTTPException(status_code=400, detail="invalid_mode")
    incontro = {"mode": body.mode, "slot": body.slot, "created_at": now_utc().isoformat(), "stato": "pianificato"}
    if body.mode == "video":
        incontro["link"] = f"https://meet.jit.si/JOBBY-{rid}-{new_id('m')[-6:]}"
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"incontro": incontro, "updated_at": now_utc().isoformat()}})
    await push_notification(r["provider_scelto"], "babysitting_incontro", "Incontro conoscitivo",
                            "La famiglia ha proposto un incontro conoscitivo." + (" Videochiamata." if body.mode == "video" else ""),
                            "babysitting", rid)
    return incontro


@router.post("/babysitting/richieste/{rid}/incontro/cancel-refund")
async def cancel_after_incontro(rid: str, user=Depends(get_current_user)):
    """Garanzia primo incontro — full refund even under 48h if the meet didn't convince."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "confermata" or not r.get("incontro"):
        raise HTTPException(status_code=400, detail="no_incontro")
    refund = {}
    if r["binario"] == "persona_lf":
        impegno = float((r.get("pagamento_lavoro") or {}).get("impegnato", 0))
        nominale = float((r.get("pagamento_lavoro") or {}).get("nominale", 0))
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$inc": {"lf_borsellino": impegno, "lf_year_total": -nominale,
                                            "lf_year_hours": -float(r["config"].get("durata_ore", 0))}})
        refund = {"lf_restituito": impegno}
    fee = float((r.get("pagamento_fee") or {}).get("importo", 0))
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"stato": "annullata", "garanzia_incontro": True,
                                            "pagamento_fee": {"stato": "refunded", "importo": fee},
                                            "updated_at": now_utc().isoformat()}})
    await push_notification(r["provider_scelto"], "babysitting_annullata", "Incontro non confermato",
                            "La famiglia ha usato la garanzia primo incontro.", "babysitting", rid)
    return {"stato": "annullata", "refunded_fee": fee, **refund}


# ---------------- double start/end code + consuntivo ----------------
@router.post("/babysitting/richieste/{rid}/inizio")
async def inizio_start(rid: str, user=Depends(get_current_user)):
    """Babysitter taps 'Inizio attività' → generates code for the parent to confirm."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    code = f"{random.randint(0, 9999):04d}"
    inizio = {"provider_at": now_utc().isoformat(), "code": code, "confirmed_at": None}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"inizio": inizio, "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "babysitting_inizio", "Conferma inizio attività",
                            f"La babysitter è arrivata. Codice inizio: {code}", "babysitting", rid)
    return {"code": code}


class CodeIn(BaseModel):
    code: str = ""


@router.post("/babysitting/richieste/{rid}/inizio/confirm")
async def inizio_confirm(rid: str, body: CodeIn, user=Depends(get_current_user)):
    """Parent confirms start (code optional — tapping the notification is enough)."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if not r.get("inizio") or not r["inizio"].get("provider_at"):
        raise HTTPException(status_code=400, detail="no_start")
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"inizio.confirmed_at": now_utc().isoformat(),
                                            "stato": "in_corso", "updated_at": now_utc().isoformat()}})
    return {"stato": "in_corso"}


async def _finalize_fine(r: dict, auto: bool) -> dict:
    """Compute billable hours from start→end confirmations, minimum guaranteed + overtime."""
    rid = r["richiesta_id"]
    st = _parse((r.get("inizio") or {}).get("confirmed_at") or (r.get("inizio") or {}).get("provider_at") or "")
    en = _parse((r.get("fine") or {}).get("provider_at") or "")
    booked = float(r["config"].get("durata_ore", 0) or 0)
    worked = _round_quarter((en - st).total_seconds() / 3600.0) if (st and en and en > st) else booked
    billable = max(booked, worked)                       # minimum guaranteed
    extra_hours = round(max(0.0, billable - booked), 2)
    # overtime consuntivo at the same babysitting rate
    prop = next((p for p in r.get("proposte", []) if p.get("provider_id") == r.get("provider_scelto")), {})
    lst_rate = float((prop.get("breakdown") or {}).get("voce_babysitting", 0))
    per_hour = round(lst_rate / booked, 2) if booked else 0
    extra_amount = round(extra_hours * per_hour, 2)
    consuntivo = {"booked_ore": booked, "worked_ore": worked, "billable_ore": billable,
                  "extra_ore": extra_hours, "extra_importo": extra_amount, "auto": auto}
    upd = {"fine.confirmed_at": now_utc().isoformat(), "fine.auto": auto, "consuntivo": consuntivo,
           "stato": "completata", "completed_at": now_utc().isoformat(),
           "contestabile_fino": (now_utc().replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
           "updated_at": now_utc().isoformat()}
    if r["binario"] == "persona_lf":
        upd["lf_comunicazione"] = {"prestatrice_id": r.get("provider_scelto"), "committente_id": r["cliente_id"],
                                   "ore": billable, "generata_at": now_utc().isoformat(), "stato": "da_trasmettere"}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": upd})
    await push_notification(r["cliente_id"], "babysitting_completata", "Servizio completato",
                            f"Ore certificate: {billable}h. Puoi lasciare una recensione.", "babysitting", rid)
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    return r


@router.post("/babysitting/richieste/{rid}/fine")
async def fine_start(rid: str, user=Depends(get_current_user)):
    """Babysitter taps 'Fine attività' → parent has 15 min to confirm, else auto-confirm."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    code = f"{random.randint(0, 9999):04d}"
    fine = {"provider_at": now_utc().isoformat(), "code": code, "confirmed_at": None,
            "deadline": (now_utc() + timedelta(minutes=B.AUTO_CONFIRM_MIN)).isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"fine": fine, "updated_at": now_utc().isoformat()}})
    await push_notification(r["cliente_id"], "babysitting_fine", "Conferma fine attività",
                            f"Inserisci il codice fine: {code}", "babysitting", rid)
    return {"code": code}


@router.post("/babysitting/richieste/{rid}/fine/confirm")
async def fine_confirm(rid: str, body: CodeIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if not r.get("fine") or not r["fine"].get("provider_at"):
        raise HTTPException(status_code=400, detail="no_end")
    if body.code.strip() and body.code.strip() != r["fine"].get("code"):
        raise HTTPException(status_code=400, detail="invalid_code")
    r = await _finalize_fine(r, auto=False)
    return {"stato": "completata", "consuntivo": r.get("consuntivo")}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/babysitting/richieste/{rid}/review")
async def review(rid: str, body: ReviewIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] != "completata":
        raise HTTPException(status_code=400, detail="not_completed")
    rev = {"rating": max(1, min(5, body.rating)), "comment": body.comment, "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"recensione": rev, "stato": "recensita", "updated_at": now_utc().isoformat()}})
    return rev


# ---------------- emergency + add-child ----------------
@router.post("/babysitting/richieste/{rid}/emergency")
async def emergency(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or user["user_id"] not in (r["cliente_id"], r.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    fam = await db.users.find_one({"user_id": r["cliente_id"]}, {"_id": 0})
    await db.admin_alerts.insert_one({"type": "babysitting_emergency", "richiesta_id": rid,
                                      "by": user["user_id"], "at": now_utc().isoformat()})
    return {"emergency_numbers": B.EMERGENCY_NUMBERS,
            "parent_contact": {"nome": fam.get("name"), "phone": fam.get("phone", "")}}


class AddChildIn(BaseModel):
    card_id: str


@router.post("/babysitting/richieste/{rid}/add-child")
async def add_child(rid: str, body: AddChildIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    if r["stato"] not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="not_active")
    c = await db.child_cards.find_one({"card_id": body.card_id, "family_id": user["user_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="child_not_found")
    req = {"card_id": body.card_id, "at": now_utc().isoformat(), "stato": "richiesto"}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"add_child_request": req, "updated_at": now_utc().isoformat()}})
    await push_notification(r["provider_scelto"], "babysitting_add_child", "Aggiunta bambino",
                            "La famiglia chiede di aggiungere un bambino. Accetti?", "babysitting", rid)
    return req


class AddChildDecisionIn(BaseModel):
    accept: bool


@router.post("/babysitting/richieste/{rid}/add-child/decision")
async def add_child_decision(rid: str, body: AddChildDecisionIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(status_code=404, detail="not_found")
    reqc = r.get("add_child_request")
    if not reqc or reqc.get("stato") != "richiesto":
        raise HTTPException(status_code=400, detail="no_request")
    if not body.accept:
        await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"add_child_request.stato": "rifiutato"}})
        await push_notification(r["cliente_id"], "babysitting_add_child", "Aggiunta bambino rifiutata",
                                "La babysitter non può accogliere il bambino aggiuntivo.", "babysitting", rid)
        return {"accepted": False}
    supp = float((r.get("bs_listino_cache") or {}).get("supplemento_bambino", 0))
    if not supp:
        prov = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
        supp = float((prov.get("bs_listino") or {}).get("supplemento_bambino", 0))
    new_cfg = {**r["config"], "n_bambini": int(r["config"].get("n_bambini", 1)) + 1}
    await db.richieste.update_one({"richiesta_id": rid},
                                  {"$set": {"add_child_request.stato": "accettato", "config": new_cfg,
                                            "supplemento_applicato": supp, "updated_at": now_utc().isoformat()},
                                   "$push": {"bambini": reqc["card_id"]}})
    await push_notification(r["cliente_id"], "babysitting_add_child", "Bambino aggiunto",
                            f"La babysitter ha accettato (+€{supp:.2f}).", "babysitting", rid)
    return {"accepted": True, "supplemento": supp}


# ---------------- admin manual matching + casellario ----------------
@router.get("/admin/babysitting/richieste")
async def admin_richieste(_=Depends(require_admin)):
    items = await db.richieste.find({"stato": {"$in": list(STATES_OPEN)}, **CAT}, {"_id": 0}) \
        .sort([("urgente", -1), ("created_at", -1)]).to_list(200)
    fee = await fee_pct()
    for r in items:
        provs = await compatible_providers(r["binario"], r["config"], r["lat"], r["lng"])
        bs_of = {}
        r["compatible"] = []
        for pp in provs:
            p = pp["provider"]; bsp = p.get("bs_profile") or {}
            r["compatible"].append({
                "provider_id": p["user_id"], "nome": p.get("business_name") or p.get("name"),
                "distance": pp["distance"], "rating": p.get("rating", 0), "trust": p.get("trust_score", 0),
                "esperienza_anni": bsp.get("esperienza_anni", 0),
                "certificazioni": bsp.get("certificazioni", []), "casellario_ok": bool(p.get("casellario_verified")),
                "price": price_breakdown(pp["listino"], r["config"], r["binario"], fee)["total_client"],
                "invited": p["user_id"] in [i.get("provider_id") for i in r.get("provider_invitati", [])],
                "invite_status": next((i.get("status") for i in r.get("provider_invitati", []) if i.get("provider_id") == p["user_id"]), None),
                "confirmed": r.get("provider_scelto") == p["user_id"],
            })
    return items


class InviteIn(BaseModel):
    provider_ids: List[str]


@router.post("/admin/babysitting/richieste/{rid}/invite")
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
                await push_notification(pid, "babysitting_invito", "Nuova richiesta babysitting",
                                        "Hai ricevuto di nuovo una richiesta compatibile.", "babysitting", rid)
            continue
        new_invites.append({"provider_id": pid, "at": now_utc().isoformat(), "status": "invited"})
        await push_notification(pid, "babysitting_invito", "Nuova richiesta babysitting",
                                "Hai ricevuto una richiesta compatibile. Rispondi entro 24h.", "babysitting", rid)
    if new_invites or reset:
        upd = {"$set": {"stato": "in_matching", "updated_at": now_utc().isoformat()}}
        if new_invites:
            upd["$push"] = {"provider_invitati": {"$each": new_invites}}
        await db.richieste.update_one({"richiesta_id": rid}, upd)
    return {"invited": len(new_invites), "reactivated": reset}


class CasellarioDecisionIn(BaseModel):
    verified: bool


@router.post("/admin/babysitting/{user_id}/casellario")
async def admin_casellario(user_id: str, body: CasellarioDecisionIn, _=Depends(require_admin)):
    upd = {"casellario_verified": body.verified}
    if body.verified:
        upd["casellario_expires"] = (now_utc() + timedelta(days=365)).isoformat()
    await db.users.update_one({"user_id": user_id}, {"$set": upd})
    msg = "I tuoi controlli sono stati verificati (badge 'controlli superati')." if body.verified \
        else "Il certificato del casellario non è stato validato. Ricaricalo."
    await push_notification(user_id, "babysitting_casellario", "Verifica casellario", msg, "profile", user_id)
    return {"user_id": user_id, "casellario_verified": body.verified, "expires_at": upd.get("casellario_expires")}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/babysitting/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "babysitting_fee_pct"}, {"$set": {"value": float(body.fee_pct)}}, upsert=True)
    return {"fee_pct": body.fee_pct}
