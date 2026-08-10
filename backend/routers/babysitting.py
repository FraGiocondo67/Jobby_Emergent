"""Blocco 2 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent (Spec 6 —
Babysitting: schede bambino a doppia visibilità, profilo babysitter esteso,
incontro conoscitivo, doppio codice inizio/fine con auto-conferma, ore minime
garantite + extra, doppio binario Libretto Famiglia/INPS vs P.IVA).

Stesse convenzioni già stabilite in routers/artigiani.py e routers/richieste.py
(Blocco 2 — leggere quei moduli per il contesto completo): le "richieste"
Babysitting sono righe di public.missions (category_id = service_categories
dove slug='babysitting'), stato di dettaglio del flusso in
missions.brief_answers (jsonb). Le schede bambino restano invece una tabella
Postgres dedicata (public.child_cards, con RLS "solo la propria famiglia"),
non jsonb dentro missions, perché servono due livelli di visibilità
indipendenti dal ciclo di vita della richiesta (dati generici sempre visibili
ai provider compatibili, scheda completa sbloccata solo al provider
confermato) — la stessa scelta già fatta dal sistema Mongo (collection
dedicata, non embedded).

Le costanti di dominio (school_levels, subjects, languages, certifications,
age_bands, availability_slots, ricorrenze, guided_questions, binari,
emergency_numbers) restano in babysitting_config.py: sono tassonomia/logica
di flusso a costo fisso, non un "menu" con prezzi admin-editabili come
mestieri/paniere/pulizie_extra — stessa distinzione già applicata alle altre
verticali di questo blocco.

Il profilo esteso babysitter (esperienza, lingue, certificazioni,
presentazione) e il listino prezzi vivono entrambi sotto
profiles_provider.price_list->'babysitting' (chiavi 'profile' e 'listino');
il certificato del casellario giudiziario in profiles_provider.documents
(chiavi casellario_doc/casellario_verified/casellario_uploaded_at/
casellario_expires) — stessa convenzione "documents" già usata da artigiani.py
per le abilitazioni.

BLOCCO 3 (Wallet/pagamenti/escrow) — `confirm`, `incontro/cancel-refund`,
`fine/confirm` e `review` sono ora implementati sullo stesso layer di
routers/richieste.py (Pulizie, verticale di riferimento — vedi
stripe_pg.py/lf_pg.py per il dettaglio del pattern). Nota di nomenclatura:
qui il binario "impresa" di Pulizie/Artigiani si chiama **`piva`** (stessa
semantica — vero escrow Stripe Connect), `persona_lf` è invariato (registro
Libretto Famiglia, non un vero escrow). Come in artigiani.py, i soldi possono
essere bloccati in più fasi (l'importo base al `confirm`, un eventuale
supplemento se la famiglia aggiunge un bambino durante il lavoro accettato
dalla babysitter) — vedi `_add_hold()`/`_finalize_release()`, stesso pattern
del preventivo/extra di Artigiani. **Semplificazione deliberata**: il
consuntivo ore finale (`fine/confirm`) non ricalcola un "conguaglio" in base
alle ore effettivamente lavorate rispetto a quelle preventivate — rilascia
semplicemente il totale già bloccato, stessa scelta di non toccare soldi
oltre al gap già fatta per Driver (Blocco 2, vedi sezione 0 del piano).

Il resto del flusso (schede bambino, profilo, casellario, listino,
config/estimate, creazione/lista/dettaglio richiesta, "in arrivo" lato
provider, proposte, pianificazione incontro, codici inizio/fine come
transizioni di stato, emergenza, richiesta aggiunta bambino, amministrazione)
resta invariato dal Blocco 2.
"""
import random
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import babysitting_config as B
import lf_pg as LF
import stripe_pg as SP
from richieste_config import (
    LF_COUPLE_CEILING_EUR, LF_FAMILY_ANNUAL_EUR, LF_PROVIDER_ANNUAL_EUR,
    LF_PROVIDER_HOURS, lf_round_nominale,
)
from core_pg import db, now_iso, now_utc, notify, record_trust_event, to_geography_point, parse_scheduled_at
from deps_pg import get_current_user, require_admin

router = APIRouter()

STATI_APERTI = ("pubblicata", "in_matching", "con_proposte")
_CATEGORY_SLUG = "babysitting"
_FEE_SETTING_KEY = "babysitting_fee_pct"


def _parse(dt: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


def _round_quarter(hours: float) -> float:
    return round(round(hours * 60 / B.ROUNDING_MIN) * B.ROUNDING_MIN / 60.0, 2)


# ---------------- schede bambino ----------------
class ChildIn(BaseModel):
    nome: str
    eta_mesi: int
    sesso: str = ""
    abitudini: str = ""
    allergie: str = ""
    note: str = ""
    consenso: bool = False


def _child_public(c: dict) -> dict:
    return {
        "card_id": c["id"], "nome": c.get("nome"), "eta_mesi": c.get("eta_mesi"), "sesso": c.get("sesso"),
        "abitudini": c.get("abitudini"), "allergie": c.get("allergie"), "note": c.get("note"),
        "consenso": c.get("consenso"), "created_at": c.get("created_at"),
    }


@router.get("/babysitting/children")
async def list_children(user=Depends(get_current_user)):
    res = db.table("child_cards").select("*").eq("family_id", user["id"]).order("created_at").limit(50).execute()
    return [_child_public(c) for c in (res.data or [])]


@router.post("/babysitting/children")
async def create_child(body: ChildIn, user=Depends(get_current_user)):
    if not body.consenso:
        raise HTTPException(status_code=400, detail="consent_required")
    if not body.nome.strip():
        raise HTTPException(status_code=400, detail="name_required")
    res = db.table("child_cards").insert({**body.dict(), "family_id": user["id"]}).execute()
    return _child_public(res.data[0])


@router.put("/babysitting/children/{cid}")
async def update_child(cid: str, body: ChildIn, user=Depends(get_current_user)):
    existing = db.table("child_cards").select("id").eq("id", cid).eq("family_id", user["id"]).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="not_found")
    res = db.table("child_cards").update(body.dict()).eq("id", cid).execute()
    return _child_public(res.data[0])


@router.delete("/babysitting/children/{cid}")
async def delete_child(cid: str, user=Depends(get_current_user)):
    res = db.table("child_cards").delete().eq("id", cid).eq("family_id", user["id"]).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    return {"deleted": True}


def _age_band(eta_mesi: int) -> str:
    y = eta_mesi / 12.0
    if y < 3: return "1_3"
    if y < 6: return "3_6"
    if y < 10: return "6_10"
    if y < 14: return "10_14"
    return "over14"


def _generic_children(cards: List[dict]) -> List[dict]:
    out = []
    for c in cards:
        band = next((b for b in B.AGE_BANDS if b["id"] == _age_band(c.get("eta_mesi", 12))), None)
        out.append({
            "eta_band": band["id"] if band else "3_6",
            "eta_band_it": band["it"] if band else "",
            "esigenza": "allergia" if (c.get("allergie") or "").strip() else "",
        })
    return out


# ---------------- profilo babysitter esteso ----------------
class BsProfileIn(BaseModel):
    esperienza_anni: int = 0
    fasce_eta: List[str] = []
    lingue: List[str] = []
    certificazioni: List[str] = []
    materie: List[str] = []
    livelli: List[str] = []
    presentazione: dict = {}
    disponibilita: List[str] = []


def _price_list(user_id: str) -> tuple:
    """Ritorna (price_list_dict, provider_row) per user_id, o ({}, None) se il
    profilo provider non esiste ancora."""
    row = db.table("profiles_provider").select("*").eq("user_id", user_id).limit(1).execute()
    if not row.data:
        return {}, None
    pl = row.data[0].get("price_list")
    return (pl if isinstance(pl, dict) else {}), row.data[0]


@router.get("/babysitting/profile")
async def get_bs_profile(user=Depends(get_current_user)):
    pl, prow = _price_list(user["id"])
    bs = pl.get("babysitting", {})
    documents = (prow or {}).get("documents") or {}
    return {"bs_profile": bs.get("profile") or {}, "casellario": {
        "uploaded": bool(documents.get("casellario_doc")),
        "verified": bool(documents.get("casellario_verified")),
        "expires_at": documents.get("casellario_expires"),
    }}


@router.put("/babysitting/profile")
async def set_bs_profile(body: BsProfileIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    pl, prow = _price_list(user["id"])
    if prow is None:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    bs = dict(pl.get("babysitting", {}))
    bs["profile"] = body.dict()
    pl["babysitting"] = bs
    db.table("profiles_provider").update({"price_list": pl}).eq("user_id", user["id"]).execute()
    return {"bs_profile": body.dict()}


class CasellarioIn(BaseModel):
    image: str


@router.post("/babysitting/casellario")
async def upload_casellario(body: CasellarioIn, user=Depends(get_current_user)):
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="invalid_document")
    row = db.table("profiles_provider").select("documents").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    documents = dict(row.data[0].get("documents") or {})
    documents["casellario_doc"] = body.image
    documents["casellario_verified"] = False
    documents["casellario_uploaded_at"] = now_iso()
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user["id"]).execute()
    return {"uploaded": True}


# ---------------- listino provider ----------------
class BsListino(BaseModel):
    binario: str = "persona_lf"
    tariffa_oraria: float = 10.0
    tariffa_ripetizioni: dict = {"elementari": 12.0, "medie": 16.0, "superiori": 20.0}
    materie: List[str] = []
    maggiorazione_serale_pct: float = 0.0
    maggiorazione_festiva_pct: float = 0.0
    supplemento_bambino: float = 0.0
    raggio_km: float = 15.0
    minimo_ore: float = 2.0


@router.get("/babysitting/listino")
async def get_listino(user=Depends(get_current_user)):
    pl, _ = _price_list(user["id"])
    bs = pl.get("babysitting", {})
    lst = bs.get("listino")
    return {"bs_binario": (lst or {}).get("binario", "persona_lf"), "listino": lst}


class BsListinoIn(BaseModel):
    binario: str = "persona_lf"
    listino: BsListino


@router.put("/babysitting/listino")
async def set_listino(body: BsListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    row = db.table("profiles_provider").select("price_list, skills").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    current = row.data[0].get("price_list")
    pl = dict(current) if isinstance(current, dict) else {}
    bs = dict(pl.get("babysitting", {}))
    lst = body.listino.dict()
    lst["binario"] = body.binario
    bs["listino"] = lst
    pl["babysitting"] = bs
    skills = sorted(set((row.data[0].get("skills") or []) + ["babysitting"]))
    db.table("profiles_provider").update({"price_list": pl, "skills": skills}).eq("user_id", user["id"]).execute()
    return {"bs_binario": body.binario, "listino": lst}


# ---------------- price engine (logica pura — resta Python) ----------------
class BsConfig(BaseModel):
    n_bambini: int = 1
    durata_ore: float = 3.0
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


def _compatible_providers(binario: str, config: dict, lat: Optional[float], lng: Optional[float]) -> List[dict]:
    materie = config.get("ripetizioni_materie") or [] if config.get("ripetizioni_attiva") else []
    res = db.rpc(
        "babysitting_compatible_providers",
        {
            "p_binario": binario, "p_lat": lat, "p_lng": lng,
            "p_durata_ore": float(config.get("durata_ore", 0) or 0),
            "p_materie": materie or None,
        },
    ).execute()
    return res.data or []


def _richiesta_out(row: dict) -> dict:
    brief = row.get("brief_answers") or {}
    out = dict(brief)
    out.update({
        "richiesta_id": row["id"],
        "cliente_id": row["client_id"],
        "categoria": "FAMIGLIA",
        "servizio": "BABYSITTING",
        "indirizzo": row.get("address"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    })
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


async def fee_pct() -> float:
    res = db.table("app_settings").select("value").eq("key", _FEE_SETTING_KEY).limit(1).execute()
    if res.data:
        try:
            return float(res.data[0]["value"])
        except Exception:
            pass
    return B.DEFAULT_FEE_PCT


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
        provs = _compatible_providers(binario, cfg, body.lat, body.lng)
        prices = [price_breakdown(pp.get("listino") or {}, cfg, binario, fee)["total_client"] for pp in provs]
        result[binario] = {"providers": len(provs),
                           "min": round(min(prices), 2) if prices else None,
                           "max": round(max(prices), 2) if prices else None}
    return {"fee_pct": fee, "ranges": result}


def _category_id() -> str:
    res = db.table("service_categories").select("id").eq("slug", _CATEGORY_SLUG).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="babysitting_category_missing")
    return res.data[0]["id"]


# ---------------- richiesta CRUD ----------------
class RichiestaIn(BaseModel):
    binario: str = "persona_lf"
    bambini: List[str] = []
    config: BsConfig
    indirizzo: str = ""
    lat: float
    lng: float
    data_ora: str = ""
    ora_fine: str = ""
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
    cards_res = db.table("child_cards").select("*").in_("id", body.bambini).eq("family_id", user["id"]).execute()
    cards = cards_res.data or []
    if not cards:
        raise HTTPException(status_code=400, detail="no_children_selected")
    for c in cards:
        if int(c.get("eta_mesi", 0)) < B.MIN_CHILD_AGE_MONTHS:
            raise HTTPException(status_code=400, detail="child_too_young")
    cfg = body.config.dict()
    cfg["n_bambini"] = len(cards)
    st, en = _parse(body.data_ora), _parse(body.ora_fine)
    if st and en and en > st:
        cfg["durata_ore"] = _round_quarter((en - st).total_seconds() / 3600.0)

    brief = {
        "binario": body.binario, "config": cfg, "bambini": [c["id"] for c in cards],
        "bambini_generic": _generic_children(cards),
        "accesso": body.accesso, "data_ora": body.data_ora, "ora_fine": body.ora_fine, "urgente": body.urgente,
        "ricorrenza": body.ricorrenza, "giorni_preferiti": body.giorni_preferiti,
        "durata_ore": cfg.get("durata_ore"), "note": body.note,
        "stato": "pubblicata" if body.publish else "bozza",
        "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "incontro": None, "inizio": None, "fine": None, "consuntivo": None,
        "pagamento_fee": {"stato": "authorized" if body.publish else "none"},
        "pagamento_lavoro": {"stato": "none"}, "recensione": None,
    }
    if body.publish:
        brief["scade_at"] = (now_utc() + timedelta(hours=B.PROPOSAL_WINDOW_HOURS)).isoformat()
        provs = _compatible_providers(body.binario, cfg, body.lat, body.lng)
        brief["provider_invitati"] = [{"provider_id": pp["provider_id"], "at": now_iso(), "status": "invited", "auto": True} for pp in provs]

    row = {
        "client_id": user["id"], "category_id": _category_id(),
        "title": "Babysitting", "description": body.note,
        "status": "published" if body.publish else "draft", "address": body.indirizzo,
        "location": to_geography_point(body.lat, body.lng),
        "scheduled_at": parse_scheduled_at(body.data_ora),
        "platform_fee_pct": await fee_pct(),
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    created = res.data[0]
    if body.publish:
        for inv in brief["provider_invitati"]:
            await notify(inv["provider_id"], "nuova_richiesta", "Nuova richiesta babysitting",
                        "Hai una nuova richiesta compatibile in arrivo.", "richiesta", created["id"])
    return _richiesta_out(created)


@router.get("/babysitting/richieste")
async def my_richieste(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*")
        .eq("client_id", user["id"]).eq("category_id", _category_id())
        .order("created_at", desc=True).limit(100).execute()
    )
    return [_richiesta_out(r) for r in (res.data or [])]


@router.get("/babysitting/richieste/{rid}")
async def get_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    is_owner = row["client_id"] == uid
    is_confirmed = brief.get("provider_scelto") == uid
    is_invited = uid in [p.get("provider_id") for p in brief.get("provider_invitati", [])]
    if not (is_owner or is_invited or is_confirmed):
        raise HTTPException(status_code=403, detail="forbidden")
    out = _richiesta_out(row)
    out["role"] = "client" if is_owner else "provider"
    bambini_ids = brief.get("bambini", [])
    if is_owner or is_confirmed:
        cards_res = db.table("child_cards").select("*").in_("id", bambini_ids).execute() if bambini_ids else None
        out["bambini_full"] = [_child_public(c) for c in (cards_res.data or [])] if cards_res else []
    else:
        out.pop("indirizzo", None)
        out.pop("accesso", None)
        out.pop("bambini", None)
    return out


async def _cancel_with_refund(rid: str, row: dict, brief: dict) -> dict:
    """Annulla la richiesta, rimborsando/stornando quanto già bloccato (se
    la richiesta era già stata confermata). Condivisa tra il /cancel
    generico e /incontro/cancel-refund (stessa operazione, due punti diversi
    del flusso in cui la famiglia può volerla invocare)."""
    binario = brief.get("binario", "piva")
    if brief.get("stato") in ("confermata", "in_corso"):
        pagamento = brief.get("pagamento_lavoro") or {}
        if binario == "piva" and pagamento.get("stato") == "held" and pagamento.get("holds"):
            refund_ids = [SP.refund_payment_intent(h["payment_intent_id"])["refund_id"] for h in pagamento["holds"]]
            db.rpc("refund_escrow", {
                "p_mission_id": rid, "p_reason": "cancellazione_famiglia",
                "p_gateway_transaction_id": refund_ids[-1],
                "p_gateway_response": {"refund_ids": refund_ids}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["stato"] = "refunded"
            brief["pagamento_lavoro"] = pagamento
        elif binario == "persona_lf" and pagamento.get("stato") == "lf_registrato" and brief.get("provider_scelto"):
            LF.record_usage(row["client_id"], brief["provider_scelto"],
                            -float(pagamento.get("totale_bloccato") or 0), 0.0)
            pagamento["stato"] = "annullato"
            brief["pagamento_lavoro"] = pagamento

    brief["stato"] = "annullata"
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "annullata"}


@router.post("/babysitting/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") in ("completata", "recensita"):
        raise HTTPException(status_code=400, detail="already_done")
    return await _cancel_with_refund(rid, row, brief)


# ---------------- provider side ----------------
@router.get("/babysitting/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        return []
    uid = user["id"]
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("urgente", desc=True).order("created_at", desc=True).limit(200).execute()
    )
    pl, _ = _price_list(uid)
    lst = (pl.get("babysitting", {}) or {}).get("listino") or {}
    fee = await fee_pct()

    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        invitati = brief.get("provider_invitati", [])
        my_invite = next((p for p in invitati if p.get("provider_id") == uid), None)
        is_chosen = brief.get("provider_scelto") == uid
        if not my_invite and not is_chosen:
            continue
        if my_invite and my_invite.get("status") == "declined" and not is_chosen:
            continue
        item = _richiesta_out(row)
        item.pop("indirizzo", None)
        item.pop("accesso", None)
        item.pop("bambini", None)
        item["price"] = price_breakdown(lst, brief.get("config", {}), brief.get("binario", "persona_lf"), fee)
        item["my_proposal"] = next((p for p in brief.get("proposte", []) if p.get("provider_id") == uid), None)
        out.append(item)
    return out


class ProposeIn(BaseModel):
    accept: bool
    message: str = ""


@router.post("/babysitting/richieste/{rid}/propose")
async def propose(rid: str, body: ProposeIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    invitati = brief.get("provider_invitati", [])
    uid = user["id"]
    if uid not in [p.get("provider_id") for p in invitati]:
        raise HTTPException(status_code=403, detail="not_invited")
    if brief.get("stato") not in STATI_APERTI:
        raise HTTPException(status_code=400, detail="not_open")

    if not body.accept:
        for p in invitati:
            if p.get("provider_id") == uid:
                p["status"] = "declined"
        brief["provider_invitati"] = invitati
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
        return {"declined": True}

    pl, prow = _price_list(uid)
    bs = pl.get("babysitting", {})
    lst = bs.get("listino") or {}
    bsp = bs.get("profile") or {}
    documents = (prow or {}).get("documents") or {}
    business_data = (prow or {}).get("business_data") or {}
    fee = await fee_pct()
    pb = price_breakdown(lst, brief.get("config", {}), brief.get("binario", "persona_lf"), fee)
    proposal = {
        "provider_id": uid, "provider_nome": business_data.get("business_name") or user.get("full_name", ""),
        "provider_rating": (prow or {}).get("avg_rating") or 0, "provider_trust": (prow or {}).get("trust_score") or 0,
        "esperienza_anni": bsp.get("esperienza_anni", 0), "lingue": bsp.get("lingue", []),
        "certificazioni": bsp.get("certificazioni", []), "presentazione": bsp.get("presentazione", {}),
        "casellario_ok": bool(documents.get("casellario_verified")),
        "price": pb["total_client"], "breakdown": pb, "message": body.message, "at": now_iso(),
    }
    proposte = [p for p in brief.get("proposte", []) if p.get("provider_id") != uid]
    proposte.append(proposal)
    brief["proposte"] = proposte
    brief["stato"] = "con_proposte"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(row["client_id"], "babysitting_proposta", "Nuova babysitter disponibile",
                f"{proposal['provider_nome']} è disponibile (€{pb['total_client']:.2f}).", "babysitting", rid)
    return proposal


# ---------------- confirm + incontro (Blocco 3 — vedi docstring modulo) ----------------
async def _add_hold(rid: str, brief: dict, kind: str, amount: float, client: dict, provider_id: str) -> dict:
    """Stesso pattern di artigiani.py's _add_hold — vedi quel modulo per il
    dettaglio commentato. Qui il binario Stripe si chiama `piva`."""
    if amount <= 0:
        return brief
    binario = brief.get("binario", "piva")
    pagamento = brief.get("pagamento_lavoro") or {}
    if pagamento.get("stato") not in ("held", "lf_registrato"):
        pagamento = {"holds": [], "totale_bloccato": 0.0, "fee_totale": 0.0, "payout_totale": 0.0, "stato": "held"}

    if binario == "piva":
        prov_row = db.table("profiles_provider").select("stripe_payouts_enabled").eq("user_id", provider_id).limit(1).execute()
        if not prov_row.data or not prov_row.data[0].get("stripe_payouts_enabled"):
            raise HTTPException(status_code=400, detail="provider_not_onboarded")
        customer_id = client.get("stripe_customer_id")
        pm_id = client.get("default_payment_method_id")
        if not customer_id or not pm_id:
            raise HTTPException(status_code=400, detail="client_payment_method_missing")

        pct = await fee_pct()
        jobby_fee = round(amount * pct / 100.0, 2)
        payout = round(amount - jobby_fee, 2)

        db.table("missions").update({"provider_id": provider_id, "price_agreed": amount}).eq("id", rid).execute()
        charge = SP.charge_hold(customer_id, pm_id, amount, {"mission_id": rid, "category": "babysitting", "kind": kind})
        db.rpc("create_escrow_hold", {
            "p_mission_id": rid, "p_gateway_transaction_id": charge["payment_intent_id"],
            "p_gateway_response": {"status": charge["status"], "kind": kind}, "p_gateway_name": "stripe",
        }).execute()

        pagamento["holds"].append({"kind": kind, "amount": amount, "payment_intent_id": charge["payment_intent_id"], "at": now_iso()})
        pagamento["totale_bloccato"] = round(pagamento["totale_bloccato"] + amount, 2)
        pagamento["fee_totale"] = round(pagamento["fee_totale"] + jobby_fee, 2)
        pagamento["payout_totale"] = round(pagamento["payout_totale"] + payout, 2)
        pagamento["stato"] = "held"
        db.table("missions").update({
            "price_agreed": pagamento["totale_bloccato"], "platform_fee": pagamento["fee_totale"], "provider_payout": pagamento["payout_totale"],
        }).eq("id", rid).execute()

    elif binario == "persona_lf":
        durata_ore = float((brief.get("config") or {}).get("durata_ore") or 0) if kind == "base" else 0.0
        nominale = lf_round_nominale(amount)
        LF.check_ceilings(
            family_id=client["id"], worker_id=provider_id, add_nominale=nominale, add_hours=durata_ore,
            couple_ceiling_eur=LF_COUPLE_CEILING_EUR, family_ceiling_eur=LF_FAMILY_ANNUAL_EUR,
            worker_ceiling_eur=LF_PROVIDER_ANNUAL_EUR, worker_ceiling_hours=LF_PROVIDER_HOURS,
        )
        LF.record_usage(client["id"], provider_id, nominale, durata_ore)
        pagamento["holds"].append({"kind": kind, "nominale": nominale, "at": now_iso()})
        pagamento["totale_bloccato"] = round(pagamento["totale_bloccato"] + nominale, 2)
        pagamento["stato"] = "lf_registrato"
        db.table("missions").update({"provider_id": provider_id, "price_agreed": pagamento["totale_bloccato"]}).eq("id", rid).execute()
    else:
        raise HTTPException(status_code=400, detail="invalid_binario")

    brief["pagamento_lavoro"] = pagamento
    return brief


async def _finalize_release(rid: str, brief: dict) -> dict:
    """Rilascia il totale bloccato in tutte le fasi al provider (piva) o non
    fa nulla sul gateway (persona_lf, l'uso è già registrato)."""
    binario = brief.get("binario", "piva")
    pagamento = brief.get("pagamento_lavoro") or {}
    provider_id = brief.get("provider_scelto")

    if binario == "piva" and pagamento.get("stato") == "held":
        prov_row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", provider_id).limit(1).execute()
        acct_id = prov_row.data[0].get("stripe_connect_account_id") if prov_row.data else None
        if not acct_id:
            raise HTTPException(status_code=400, detail="provider_not_onboarded")
        payout = float(pagamento.get("payout_totale") or 0)
        if payout > 0:
            transfer = SP.transfer_to_provider(acct_id, payout, {"mission_id": rid, "category": "babysitting"})
            db.rpc("release_escrow", {
                "p_mission_id": rid, "p_gateway_transaction_id": transfer["transfer_id"],
                "p_gateway_response": {}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["transfer_id"] = transfer["transfer_id"]
        pagamento["stato"] = "released"
        brief["pagamento_lavoro"] = pagamento

    brief["stato"] = "completata"
    return brief


class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/babysitting/richieste/{rid}/confirm")
async def confirm(rid: str, body: ConfirmIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") not in STATI_APERTI:
        raise HTTPException(status_code=400, detail="not_open")
    provider_id = body.provider_id
    proposal = next((p for p in brief.get("proposte", []) if p.get("provider_id") == provider_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")

    amount = float(proposal.get("price") or (proposal.get("breakdown") or {}).get("total_client") or 0)
    brief["provider_scelto"] = provider_id
    brief = await _add_hold(rid, brief, "base", amount, user, provider_id)
    brief["stato"] = "confermata"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(provider_id, "babysitting_confermata", "Richiesta confermata",
                "La famiglia ha confermato la tua disponibilità.", "babysitting", rid)
    await notify(row["client_id"], "babysitting_confermata", "Richiesta confermata",
                "Hai confermato la babysitter.", "babysitting", rid)
    return {"stato": "confermata", "pagamento_lavoro": brief.get("pagamento_lavoro")}


class IncontroIn(BaseModel):
    mode: str
    slot: str = ""


@router.post("/babysitting/richieste/{rid}/incontro")
async def set_incontro(rid: str, body: IncontroIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    if body.mode not in ("video", "persona"):
        raise HTTPException(status_code=400, detail="invalid_mode")
    incontro = {"mode": body.mode, "slot": body.slot, "created_at": now_iso(), "stato": "pianificato"}
    if body.mode == "video":
        incontro["link"] = f"https://meet.jit.si/JOBBY-{rid[-8:]}"
    brief["incontro"] = incontro
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(brief.get("provider_scelto"), "babysitting_incontro", "Incontro conoscitivo",
                "La famiglia ha proposto un incontro conoscitivo." + (" Videochiamata." if body.mode == "video" else ""),
                "babysitting", rid)
    return incontro


@router.post("/babysitting/richieste/{rid}/incontro/cancel-refund")
async def cancel_after_incontro(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") in ("completata", "recensita", "annullata"):
        raise HTTPException(status_code=400, detail="already_done")
    result = await _cancel_with_refund(rid, row, brief)
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "babysitting_annullata", "Richiesta annullata",
                    "La famiglia ha annullato dopo l'incontro conoscitivo.", "babysitting", rid)
    return result


# ---------------- doppio codice inizio/fine + consuntivo ----------------
@router.post("/babysitting/richieste/{rid}/inizio")
async def inizio_start(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    code = f"{random.randint(0, 9999):04d}"
    brief["inizio"] = {"provider_at": now_iso(), "code": code, "confirmed_at": None}
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "babysitting_inizio", "Conferma inizio attività",
                f"La babysitter è arrivata. Codice inizio: {code}", "babysitting", rid)
    return {"code": code}


class CodeIn(BaseModel):
    code: str = ""


@router.post("/babysitting/richieste/{rid}/inizio/confirm")
async def inizio_confirm(rid: str, body: CodeIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if not brief.get("inizio") or not brief["inizio"].get("provider_at"):
        raise HTTPException(status_code=400, detail="no_start")
    brief["inizio"]["confirmed_at"] = now_iso()
    brief["stato"] = "in_corso"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "in_corso"}


@router.post("/babysitting/richieste/{rid}/fine")
async def fine_start(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    code = f"{random.randint(0, 9999):04d}"
    brief["fine"] = {"provider_at": now_iso(), "code": code, "confirmed_at": None,
                     "deadline": (now_utc() + timedelta(minutes=B.AUTO_CONFIRM_MIN)).isoformat()}
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "babysitting_fine", "Conferma fine attività",
                f"Inserisci il codice fine: {code}", "babysitting", rid)
    return {"code": code}


@router.post("/babysitting/richieste/{rid}/fine/confirm")
async def fine_confirm(rid: str, body: CodeIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if not brief.get("fine") or not brief["fine"].get("provider_at"):
        raise HTTPException(status_code=400, detail="no_end")
    if brief.get("stato") != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")

    brief["fine"]["confirmed_at"] = now_iso()
    brief["consuntivo"] = {"confermato_at": now_iso()}
    brief = await _finalize_release(rid, brief)
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "babysitting_completata", "Attività completata",
                    "La famiglia ha confermato la fine dell'attività.", "babysitting", rid)
    return {"stato": "completata"}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/babysitting/richieste/{rid}/review")
async def review(rid: str, body: ReviewIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "completata":
        raise HTTPException(status_code=400, detail="not_completed")
    if not (1 <= body.rating <= 5):
        raise HTTPException(status_code=400, detail="invalid_rating")
    provider_id = brief.get("provider_scelto")
    if not provider_id:
        raise HTTPException(status_code=400, detail="no_provider")

    db.table("reviews").insert({
        "mission_id": rid, "reviewer_id": user["id"], "reviewee_id": provider_id,
        "rating": body.rating, "comment": body.comment,
    }).execute()
    agg = db.table("reviews").select("rating").eq("reviewee_id", provider_id).execute()
    ratings = [r["rating"] for r in (agg.data or [])]
    if ratings:
        new_avg = round(sum(ratings) / len(ratings), 2)
        db.table("profiles_provider").update({"avg_rating": new_avg}).eq("user_id", provider_id).execute()

    brief["recensione"] = {"rating": body.rating, "comment": body.comment, "at": now_iso()}
    brief["stato"] = "recensita"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    # Blocco 4: fa scattare recalculate_trust_score (vedi core_pg.record_trust_event).
    record_trust_event(provider_id, "review_received", round((body.rating - 3) * 2, 2),
                       dimension="quality", notes=f"Recensione {body.rating}★ su richiesta babysitting {rid}")

    await notify(provider_id, "babysitting_completata", "Nuova recensione",
                f"Hai ricevuto {body.rating}★ dalla famiglia.", "babysitting", rid)
    return brief["recensione"]


# ---------------- emergenza + aggiunta bambino ----------------
@router.post("/babysitting/richieste/{rid}/emergency")
async def emergency(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    if uid not in (row["client_id"], brief.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    fam_res = db.table("users").select("full_name, phone").eq("id", row["client_id"]).limit(1).execute()
    fam = fam_res.data[0] if fam_res.data else {}
    # NOTA: riuso pragmatico di admin_actions come log dell'evento — Postgres
    # non ha ancora un equivalente della collection Mongo db.admin_alerts
    # (alert da rivedere, distinta dall'audit log "azioni compiute da un
    # admin" a cui admin_actions è realmente pensata: qui `admin_id` è
    # in realtà l'utente — cliente o babysitter — che ha premuto il
    # pulsante, non un admin). Sufficiente per non perdere l'evento adesso;
    # se il volume/uso di questi alert cresce vale la pena creare una tabella
    # dedicata (stesso gap che si ripresenterà per la moderazione di
    # spec4.py, non ancora migrato in questo blocco).
    db.table("admin_actions").insert({
        "admin_id": uid, "action": "babysitting_emergency", "target_type": "mission", "target_id": rid,
        "notes": "Pulsante di emergenza attivato durante una richiesta Babysitting.",
    }).execute()
    return {"emergency_numbers": B.EMERGENCY_NUMBERS,
            "parent_contact": {"nome": fam.get("full_name"), "phone": fam.get("phone", "")}}


class AddChildIn(BaseModel):
    card_id: str


@router.post("/babysitting/richieste/{rid}/add-child")
async def add_child(rid: str, body: AddChildIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="not_active")
    card = db.table("child_cards").select("id").eq("id", body.card_id).eq("family_id", user["id"]).limit(1).execute()
    if not card.data:
        raise HTTPException(status_code=404, detail="child_not_found")
    req = {"card_id": body.card_id, "at": now_iso(), "stato": "richiesto"}
    brief["add_child_request"] = req
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(brief.get("provider_scelto"), "babysitting_add_child", "Aggiunta bambino",
                "La famiglia chiede di aggiungere un bambino. Accetti?", "babysitting", rid)
    return req


class AddChildDecisionIn(BaseModel):
    accept: bool


@router.post("/babysitting/richieste/{rid}/add-child/decision")
async def add_child_decision(rid: str, body: AddChildDecisionIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    reqc = brief.get("add_child_request")
    if not reqc or reqc.get("stato") != "richiesto":
        raise HTTPException(status_code=400, detail="no_request")
    if not body.accept:
        reqc["stato"] = "rifiutato"
        brief["add_child_request"] = reqc
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
        await notify(row["client_id"], "babysitting_add_child", "Aggiunta bambino rifiutata",
                    "La babysitter non può accogliere il bambino aggiuntivo.", "babysitting", rid)
        return {"accepted": False}
    pl, _ = _price_list(user["id"])
    supp = float(((pl.get("babysitting", {}) or {}).get("listino") or {}).get("supplemento_bambino", 0))
    cfg = dict(brief.get("config", {}))
    cfg["n_bambini"] = int(cfg.get("n_bambini", 1)) + 1
    reqc["stato"] = "accettato"
    brief["add_child_request"] = reqc
    brief["config"] = cfg
    brief["supplemento_applicato"] = supp
    brief["bambini"] = list(brief.get("bambini", [])) + [reqc["card_id"]]
    # Il bambino aggiuntivo comporta un supplemento reale sul compenso: si
    # blocca subito (stessa logica dell'extra approvato di artigiani.py), non
    # si aspetta fine/confirm — coerente col fatto che qui l'accettazione è
    # già una decisione vincolante della babysitter.
    client_res = db.table("users").select("*").eq("id", row["client_id"]).limit(1).execute()
    client = client_res.data[0] if client_res.data else {"id": row["client_id"]}
    brief = await _add_hold(rid, brief, "supplemento", supp, client, user["id"])
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "babysitting_add_child", "Bambino aggiunto",
                f"La babysitter ha accettato (+€{supp:.2f}).", "babysitting", rid)
    return {"accepted": True, "supplemento": supp}


# ---------------- amministrazione ----------------
@router.get("/admin/babysitting/richieste")
async def admin_richieste(_=Depends(require_admin)):
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("created_at", desc=True).limit(200).execute()
    )
    fee = await fee_pct()
    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        if brief.get("stato") not in STATI_APERTI:
            continue
        invitati = brief.get("provider_invitati", [])
        provs = _compatible_providers(brief.get("binario", "persona_lf"), brief.get("config", {}), row.get("lat"), row.get("lng"))
        item = _richiesta_out(row)
        item["compatible"] = [{
            "provider_id": p["provider_id"], "nome": p.get("business_name") or p.get("full_name"),
            "distance": p.get("distance_km"), "rating": p.get("avg_rating") or 0, "trust": p.get("trust_score") or 0,
            "esperienza_anni": (p.get("profile") or {}).get("esperienza_anni", 0),
            "certificazioni": (p.get("profile") or {}).get("certificazioni", []), "casellario_ok": bool(p.get("casellario_ok")),
            "price": price_breakdown(p.get("listino") or {}, brief.get("config", {}), brief.get("binario", "persona_lf"), fee)["total_client"],
            "invited": p["provider_id"] in [i.get("provider_id") for i in invitati],
            "invite_status": next((i.get("status") for i in invitati if i.get("provider_id") == p["provider_id"]), None),
            "confirmed": brief.get("provider_scelto") == p["provider_id"],
        } for p in provs]
        out.append(item)
    return out


class InviteIn(BaseModel):
    provider_ids: List[str]


@router.post("/admin/babysitting/richieste/{rid}/invite")
async def admin_invite(rid: str, body: InviteIn, _=Depends(require_admin)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    invitati = brief.get("provider_invitati", [])
    already = [i.get("provider_id") for i in invitati]
    new_count, reset_count = 0, 0
    for pid in body.provider_ids:
        if pid in already:
            for i in invitati:
                if i.get("provider_id") == pid and i.get("status") == "declined":
                    i["status"] = "invited"
                    i["reinvited_at"] = now_iso()
                    reset_count += 1
                    await notify(pid, "babysitting_invito", "Nuova richiesta babysitting",
                                "Hai ricevuto di nuovo una richiesta compatibile.", "babysitting", rid)
            continue
        invitati.append({"provider_id": pid, "at": now_iso(), "status": "invited"})
        new_count += 1
        await notify(pid, "babysitting_invito", "Nuova richiesta babysitting",
                    "Hai ricevuto una richiesta compatibile. Rispondi entro 24h.", "babysitting", rid)
    if new_count or reset_count:
        brief["provider_invitati"] = invitati
        brief["stato"] = "in_matching"
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"invited": new_count, "reactivated": reset_count}


class CasellarioDecisionIn(BaseModel):
    verified: bool


@router.post("/admin/babysitting/{user_id}/casellario")
async def admin_casellario(user_id: str, body: CasellarioDecisionIn, _=Depends(require_admin)):
    row = db.table("profiles_provider").select("documents").eq("user_id", user_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="not_found")
    documents = dict(row.data[0].get("documents") or {})
    documents["casellario_verified"] = body.verified
    if body.verified:
        documents["casellario_expires"] = (now_utc() + timedelta(days=365)).isoformat()
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user_id).execute()
    msg = "I tuoi controlli sono stati verificati (badge 'controlli superati')." if body.verified \
        else "Il certificato del casellario non è stato validato. Ricaricalo."
    await notify(user_id, "babysitting_casellario", "Verifica casellario", msg, "profile", user_id)
    return {"user_id": user_id, "casellario_verified": body.verified, "expires_at": documents.get("casellario_expires")}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/babysitting/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    db.table("app_settings").upsert({"key": _FEE_SETTING_KEY, "value": float(body.fee_pct)}).execute()
    return {"fee_pct": body.fee_pct}
