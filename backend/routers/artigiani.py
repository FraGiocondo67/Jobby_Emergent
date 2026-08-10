"""Blocco 2 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent.

Modello dati: le "richieste" artigiani (che nel sistema Emergent vivevano in
una collection Mongo dedicata, db.richieste) qui NON hanno una tabella propria
— sono righe di public.missions con category_id = service_categories dove
slug='artigiani'. Tutti i campi specifici del dominio (mestiere, modalita,
parametri del brief, stato dettagliato del flusso, proposte, provider
invitati/scelto, ecc.) vivono in missions.brief_answers (jsonb), perché lo
stato Postgres `missions.status` (enum chiuso: draft/published/matched/
confirmed/in_progress/completed/reviewed/disputed/cancelled) è troppo
generico per rappresentare gli stati granulari del vecchio flusso Mongo
(pubblicata/in_matching/con_proposte/confermata/in_corso/preventivo/
completata/recensita/annullata). Convenzione adottata in questo file:
`missions.status` resta 'published' per tutti gli stati "aperti" (pubblicata,
in_matching, con_proposte — lo stato preciso è in brief_answers['stato']) e
diventa 'cancelled' solo quando la richiesta viene annullata. Gli altri stati
(confermata, in_corso, preventivo, completata, recensita) verranno mappati
quando gli endpoint corrispondenti saranno implementati (vedi sotto).

Cataloghi: mestieri/paniere non sono più costanti Python (artigiani_config.py,
ancora presente ma ridotto a sole costanti di "logica di flusso") ma tabelle
Postgres admin-editabili via Retool (public.artigiani_mestieri,
public.artigiani_paniere) — scelta esplicita dell'utente per questo blocco.
Il matching provider-richiesta usa la funzione SQL
public.artigiani_compatible_providers(...) (PostGIS ST_DWithin/ST_Distance)
al posto dell'haversine Python usato da Mongo — non ancora validata su dati
reali di produzione (nessun provider ha ancora location/price_list popolati).

BLOCCO 3 (Wallet/pagamenti/escrow) — `confirm`/`preventivo`(+accept/reject)/
`extra`(+approve)/`complete`/`garanzia`/`review` sono ora implementati, sullo
stesso layer già scritto per Pulizie (vedi routers/richieste.py, verticale di
riferimento — stripe_pg.py/lf_pg.py per il dettaglio del pattern):

- binario `impresa`: vero escrow Stripe Connect a "delayed transfer". A
  differenza di Pulizie (un solo importo), qui i soldi possono essere
  bloccati **in più fasi**: il diritto di chiamata al `confirm`, poi
  eventualmente il preventivo (accettato dal cliente) e gli extra
  (approvati durante il lavoro) — ogni fase è un hold Stripe separato
  (`_add_hold()`), accumulati in `brief['pagamento']['holds']`; il
  `complete` (o una diagnosi che si chiude subito, o un preventivo
  rifiutato) trasferisce al provider il netto TOTALE accumulato in un colpo
  solo e rilascia l'intero escrow (`release_escrow` marca `released` tutte
  le righe `payments` di tipo `escrow_hold` per la missione, non serve
  chiamarlo più volte).
- binario `persona_lf` (solo mestiere `tuttofare`, che ammette il
  Libretto Famiglia): stesso registro `lf_ledger` di Pulizie — nessun vero
  escrow. **Limite noto**: qui non esiste un concetto di "ore lavorate" nel
  modello dati (a differenza di Pulizie), quindi il tetto ore INPS
  (`LF_PROVIDER_HOURS`) non può essere fatto rispettare in questa verticale
  — solo i tetti in euro sono verificati.
- `garanzia`: NON un vero flusso di dispute/rimborso (quello è Blocco 4,
  `disputes.py` non ancora migrato) — solo un log dell'evento (riuso
  pragmatico di `admin_actions`, stesso pattern già usato in
  `babysitting.py` per l'allarme emergenza) più notifica admin, entro la
  finestra `GARANZIA_DAYS` dal completamento.

Il resto del flusso (config, ricerca/matching, creazione richiesta,
proposte, cancellazione, incoming provider, amministrazione) resta
invariato dal Blocco 2.
"""
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import artigiani_config as A
import lf_pg as LF
import stripe_pg as SP
# Costanti di massimale Libretto Famiglia (soglie legali INPS, non specifiche
# di dominio): definite una sola volta in richieste_config.py (prima
# verticale del Blocco 3 ad averne bisogno), riusate qui invece di duplicarle.
from richieste_config import (
    LF_COUPLE_CEILING_EUR, LF_FAMILY_ANNUAL_EUR, LF_PROVIDER_ANNUAL_EUR,
    LF_PROVIDER_HOURS, lf_round_nominale,
)
from core_pg import db, now_iso, now_utc, haversine, notify, TREVISO
from deps_pg import get_current_user, require_admin

router = APIRouter()

STATI_APERTI = ("pubblicata", "in_matching", "con_proposte")
_CATEGORY_SLUG = "artigiani"
_FEE_SETTING_KEY = "artigiani_fee_pct"


# ---------------- cataloghi (Postgres, admin-editabili) ----------------
def _category_id() -> str:
    res = db.table("service_categories").select("id").eq("slug", _CATEGORY_SLUG).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="artigiani_category_missing")
    return res.data[0]["id"]


async def fee_pct() -> float:
    res = db.table("app_settings").select("value").eq("key", _FEE_SETTING_KEY).limit(1).execute()
    if res.data:
        try:
            return float(res.data[0]["value"])
        except Exception:
            pass
    return A.DEFAULT_FEE_PCT


def _mestieri_rows() -> List[dict]:
    res = db.table("artigiani_mestieri").select("*").eq("is_active", True).order("sort_order").execute()
    return res.data or []


def _mestiere_row(slug: str) -> Optional[dict]:
    return next((m for m in _mestieri_rows() if m["slug"] == slug), None)


def _mestiere_out(m: dict) -> dict:
    """Stesso shape della vecchia costante A.MESTIERI, così il frontend non
    deve cambiare contratto anche se ora i dati vengono da Postgres."""
    return {
        "id": m["slug"], "it": m["name_it"], "en": m["name_en"], "icon": m.get("icon"),
        "abilitazione": bool(m.get("richiede_abilitazione")),
        "fgas": bool(m.get("richiede_fgas")),
        "libretto": bool(m.get("richiede_libretto_famiglia")),
        "stage2": bool(m.get("has_stage2_diagnosi")),
        "stagionale": bool(m.get("stagionale")),
    }


def _paniere_by_mestiere() -> dict:
    res = (
        db.table("artigiani_paniere")
        .select("*, artigiani_mestieri!inner(slug)")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    out: dict = {}
    for row in (res.data or []):
        slug = (row.get("artigiani_mestieri") or {}).get("slug")
        if not slug:
            continue
        out.setdefault(slug, []).append(
            {"id": row["slug"], "it": row["name_it"], "en": row["name_en"], "prezzo": float(row["prezzo"])}
        )
    return out


def _paniere_item(mestiere_slug: str, item_slug: str) -> Optional[dict]:
    return next((x for x in _paniere_by_mestiere().get(mestiere_slug, []) if x["id"] == item_slug), None)


def _paniere_price(lst: dict, mestiere_slug: str, item_slug: str) -> Optional[float]:
    for x in (lst.get("paniere") or []):
        if x.get("id") == item_slug:
            return float(x["prezzo"])
    default = _paniere_item(mestiere_slug, item_slug)
    return float(default["prezzo"]) if default else None


# ---------------- helper di dominio (logica di flusso — restano Python) ----------------
def compute_chiamata_fee(lst: dict, distance_km: float, urgente: bool) -> float:
    """Diritto di chiamata (Ispezione): base + €/km oltre i km inclusi, +% urgenza, minimo garantito."""
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
    d = (descrizione or "").lower()
    for mid, kws in A.IMPIANTI_ROUTING.items():
        if any(k in d for k in kws):
            return mid
    return None


def _compatible_providers(mestiere: str, binario: str, lat: Optional[float], lng: Optional[float], urgente: bool) -> List[dict]:
    res = db.rpc(
        "artigiani_compatible_providers",
        {"p_mestiere": mestiere, "p_binario": binario, "p_lat": lat, "p_lng": lng, "p_urgente": urgente},
    ).execute()
    return res.data or []


def _richiesta_out(row: dict) -> dict:
    brief = row.get("brief_answers") or {}
    out = dict(brief)
    out.update({
        "richiesta_id": row["id"],
        "cliente_id": row["client_id"],
        "categoria": "ARTIGIANI",
        "servizio": "ARTIGIANI",
        "indirizzo": row.get("address"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    })
    return out


# ---------------- config / paniere / estimate ----------------
@router.get("/artigiani/config")
async def get_config(user=Depends(get_current_user)):
    return {
        "mestieri": [_mestiere_out(m) for m in _mestieri_rows()],
        "paniere": _paniere_by_mestiere(),
        "esiti": A.ESITI,
        "binari": A.BINARI,
        "parametri": A.PARAMETRI,
        "fasce_orarie": A.FASCE_ORARIE,
        "chiamata_default": A.DEFAULT_CHIAMATA,
        "fasce_urgenza": A.FASCE_URGENZA,
        "garanzia_giorni": A.GARANZIA_DAYS,
        "preventivo_giorni": A.PREVENTIVO_VALIDITY_DAYS,
        "fee_pct": await fee_pct(),
    }


class RouteCheck(BaseModel):
    descrizione: str


@router.post("/artigiani/route-check")
async def route_check(body: RouteCheck, user=Depends(get_current_user)):
    mid = route_tuttofare(body.descrizione)
    return {"suggested_mestiere": mid, "mestiere_label": _mestiere_out(_mestiere_row(mid))["it"] if mid else None}


class EstimateIn(BaseModel):
    mestiere: str
    modalita: str = "diagnosi"      # paniere | diagnosi
    intervento_id: str = ""
    binario: str = "impresa"
    urgente: bool = False
    lat: float = TREVISO["lat"]
    lng: float = TREVISO["lng"]


@router.post("/artigiani/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    if not _mestiere_row(body.mestiere):
        raise HTTPException(status_code=400, detail="invalid_mestiere")
    provs = _compatible_providers(body.mestiere, body.binario, body.lat, body.lng, body.urgente)
    prices = []
    for p in provs:
        lst = p.get("listino") or {}
        if body.modalita == "paniere":
            pr = _paniere_price(lst, body.mestiere, body.intervento_id)
            if pr is None:
                continue
            if body.urgente:
                pr = pr * (1 + float(lst.get("urgenze_pct", 0)) / 100.0)
        else:
            pr = compute_chiamata_fee(lst, p.get("distance_km") or 0, body.urgente)
        prices.append(round(pr, 2))
    return {
        "providers": len(provs), "modalita": body.modalita,
        "min": round(min(prices), 2) if prices else None,
        "max": round(max(prices), 2) if prices else None,
    }


# ---------------- provider listino (per mestiere) ----------------
class MestiereListino(BaseModel):
    binario: str = "impresa"
    chiamata_fee: float = 50.0
    chiamata_base: float = 40.0
    chiamata_per_km: float = 1.5
    chiamata_km_inclusi: float = 5.0
    chiamata_urgenza_pct: float = 20.0
    chiamata_minimo: float = 40.0
    tariffa_oraria: float = 35.0
    paniere: List[dict] = []
    urgenze: bool = False
    urgenze_pct: float = 0.0
    fasce_urgenza: List[str] = []
    raggio_km: float = 20.0
    tempi_tipici: str = ""
    abilitazione_numero: str = ""


@router.get("/artigiani/listino")
async def get_listino(user=Depends(get_current_user)):
    row = db.table("profiles_provider").select("price_list, documents").eq("user_id", user["id"]).limit(1).execute()
    price_list, documents = {}, {}
    if row.data:
        pl = row.data[0].get("price_list")
        if isinstance(pl, dict):
            price_list = pl
        documents = row.data[0].get("documents") or {}
    return {
        "art_listini": price_list.get("artigiani", {}),
        "abilitazioni": {
            "verified": bool(documents.get("art_abilitazione_verified")),
            "fgas": bool(documents.get("art_fgas_doc")),
            "uploaded": bool(documents.get("art_abilitazione_doc")),
        },
    }


class ListinoIn(BaseModel):
    mestiere: str
    listino: MestiereListino


@router.put("/artigiani/listino")
async def set_listino(body: ListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    if not _mestiere_row(body.mestiere):
        raise HTTPException(status_code=400, detail="invalid_mestiere")
    row = db.table("profiles_provider").select("price_list, skills").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    current = row.data[0].get("price_list")
    price_list = dict(current) if isinstance(current, dict) else {}
    artigiani = dict(price_list.get("artigiani", {}))
    artigiani[body.mestiere] = body.listino.dict()
    price_list["artigiani"] = artigiani
    skills = sorted(set((row.data[0].get("skills") or []) + ["artigiani"]))
    db.table("profiles_provider").update({"price_list": price_list, "skills": skills}).eq("user_id", user["id"]).execute()
    return {"mestiere": body.mestiere, "listino": body.listino.dict()}


class AbilitazioneIn(BaseModel):
    kind: str = "abilitazione"       # abilitazione | fgas
    image: str


@router.post("/artigiani/abilitazione")
async def upload_abilitazione(body: AbilitazioneIn, user=Depends(get_current_user)):
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="invalid_document")
    row = db.table("profiles_provider").select("documents").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    documents = dict(row.data[0].get("documents") or {})
    field = "art_fgas_doc" if body.kind == "fgas" else "art_abilitazione_doc"
    documents[field] = body.image
    documents["art_abilitazione_verified"] = False
    documents["art_abilitazione_uploaded_at"] = now_iso()
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user["id"]).execute()
    return {"uploaded": True}


# ---------------- richiesta CRUD ----------------
class RichiestaIn(BaseModel):
    mestiere: str
    modalita: str = "diagnosi"       # paniere | diagnosi (Ispezione)
    intervento_id: str = ""
    parametri: dict = {}
    descrizione: str = ""
    foto: List[str] = []
    binario: str = "impresa"
    urgente: bool = False
    fascia_urgenza: str = ""
    fascia_oraria: str = ""
    indirizzo: str = ""
    accesso: str = ""
    lat: float
    lng: float
    data_ora: str = ""


@router.post("/artigiani/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    m = _mestiere_row(body.mestiere)
    if not m:
        raise HTTPException(status_code=400, detail="invalid_mestiere")
    if body.binario == "persona_lf" and not m["richiede_libretto_famiglia"]:
        raise HTTPException(status_code=400, detail="binario_not_allowed")
    if body.modalita not in ("paniere", "diagnosi"):
        raise HTTPException(status_code=400, detail="invalid_modalita")

    intervento = _paniere_item(body.mestiere, body.intervento_id) if body.modalita == "paniere" else None
    provs = _compatible_providers(body.mestiere, body.binario, body.lat, body.lng, body.urgente)
    now = now_iso()
    provider_invitati = [{"provider_id": p["provider_id"], "at": now, "status": "invited", "auto": True} for p in provs]

    brief = {
        "mestiere": body.mestiere, "modalita": body.modalita, "intervento_id": body.intervento_id,
        "intervento": intervento, "parametri": body.parametri, "descrizione": body.descrizione,
        "foto": body.foto, "binario": body.binario, "urgente": body.urgente,
        "fascia_urgenza": body.fascia_urgenza, "fascia_oraria": body.fascia_oraria,
        "accesso": body.accesso,
        # NOTA: lat/lng restano qui (non in missions.location, colonna PostGIS
        # geography) — stesso TODO già documentato in routers/onboarding.py
        # (Blocco 1): la scrittura di una colonna geography via client REST
        # supabase-py non è ancora stata verificata in produzione.
        "lat": body.lat, "lng": body.lng, "data_ora": body.data_ora,
        "stato": "pubblicata", "provider_invitati": provider_invitati, "proposte": [],
        "provider_scelto": None,
        "scade_at": (now_utc() + timedelta(hours=A.PROPOSAL_WINDOW_HOURS)).isoformat(),
    }
    row = {
        "client_id": user["id"], "category_id": _category_id(),
        "title": f"Artigiani — {m['name_it']}", "description": body.descrizione,
        "status": "published", "address": body.indirizzo,
        "platform_fee_pct": await fee_pct(),
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    created = res.data[0]

    for inv in provider_invitati:
        await notify(inv["provider_id"], "nuova_richiesta", "Nuova richiesta artigiano",
                     "Hai una nuova richiesta compatibile in arrivo.", "richiesta", created["id"])
    return _richiesta_out(created)


@router.get("/artigiani/richieste")
async def my_richieste(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*")
        .eq("client_id", user["id"]).eq("category_id", _category_id())
        .order("created_at", desc=True).limit(100).execute()
    )
    return [_richiesta_out(r) for r in (res.data or [])]


@router.get("/artigiani/richieste/{rid}")
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
    if not (is_owner or is_confirmed):
        out.pop("indirizzo", None)
        out.pop("accesso", None)
    return out


@router.post("/artigiani/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") in ("completata", "recensita", "annullata"):
        raise HTTPException(status_code=400, detail="already_closed")

    binario = brief.get("binario", "impresa")
    if brief.get("stato") in ("confermata", "preventivo_inviato", "in_corso"):
        pagamento = brief.get("pagamento") or {}
        if binario == "impresa" and pagamento.get("stato") == "held" and pagamento.get("holds"):
            # Ogni fase (chiamata/preventivo/extra) è un PaymentIntent Stripe
            # separato e va rimborsata singolarmente; refund_escrow invece
            # marca in UN colpo solo tutte le righe payments di tipo
            # escrow_hold della missione come 'refunded' (stessa logica non
            # per-riga di release_escrow, vedi commento in _finalize_release)
            # — va quindi chiamata una sola volta dopo tutti i refund Stripe.
            refund_ids = [SP.refund_payment_intent(h["payment_intent_id"])["refund_id"] for h in pagamento["holds"]]
            db.rpc("refund_escrow", {
                "p_mission_id": rid, "p_reason": "cancellazione_cliente",
                "p_gateway_transaction_id": refund_ids[-1],
                "p_gateway_response": {"refund_ids": refund_ids}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["stato"] = "refunded"
            brief["pagamento"] = pagamento
        elif binario == "persona_lf" and pagamento.get("stato") == "lf_registrato" and brief.get("provider_scelto"):
            LF.record_usage(row["client_id"], brief["provider_scelto"],
                            -float(pagamento.get("totale_bloccato") or 0), 0.0)
            pagamento["stato"] = "annullato"
            brief["pagamento"] = pagamento

    brief["stato"] = "annullata"
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "annullata"}


# ---------------- provider side ----------------
@router.get("/artigiani/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        return []
    uid = user["id"]
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("created_at", desc=True).limit(200).execute()
    )
    prov_row = db.table("profiles_provider").select("price_list, business_data").eq("user_id", uid).limit(1).execute()
    pdata = prov_row.data[0] if prov_row.data else {}
    price_list = pdata.get("price_list")
    art_listini = price_list.get("artigiani", {}) if isinstance(price_list, dict) else {}
    business_data = pdata.get("business_data") or {}
    plat, plng = business_data.get("last_lat"), business_data.get("last_lng")

    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        invitati = brief.get("provider_invitati", [])
        my_invite = next((p for p in invitati if p.get("provider_id") == uid), None)
        if not my_invite or my_invite.get("status") == "declined":
            continue
        lst = art_listini.get(brief.get("mestiere"), {})
        if brief.get("modalita") == "paniere":
            pr = _paniere_price(lst, brief.get("mestiere"), brief.get("intervento_id"))
            if pr is not None and brief.get("urgente"):
                pr = round(pr * (1 + float(lst.get("urgenze_pct", 0)) / 100.0), 2)
        else:
            # Distanza approssimata via business_data.last_lat/last_lng
            # (fallback impostato in onboarding.py finché la scrittura su
            # profiles_provider.location — PostGIS — non è verificata). Se il
            # provider non ha ancora questi campi, la distanza è 0 (fee
            # migliore possibile) — stesso limite noto già documentato in
            # core_pg.haversine.
            dist = haversine(brief.get("lat", 0), brief.get("lng", 0), plat, plng) if plat is not None and plng is not None else 0.0
            pr = compute_chiamata_fee(lst, dist, brief.get("urgente", False))
        item = _richiesta_out(row)
        item["my_price"] = pr
        item["my_proposal"] = next((p for p in brief.get("proposte", []) if p.get("provider_id") == uid), None)
        item.pop("indirizzo", None)
        item.pop("accesso", None)
        out.append(item)
    return out


class ProposeIn(BaseModel):
    accept: bool
    message: str = ""


@router.post("/artigiani/richieste/{rid}/propose")
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

    prov_row = (
        db.table("profiles_provider")
        .select("price_list, business_data, avg_rating, trust_score, documents")
        .eq("user_id", uid).limit(1).execute()
    )
    pdata = prov_row.data[0] if prov_row.data else {}
    price_list = pdata.get("price_list")
    art_listini = price_list.get("artigiani", {}) if isinstance(price_list, dict) else {}
    lst = art_listini.get(brief.get("mestiere"), {})
    business_data = pdata.get("business_data") or {}
    documents = pdata.get("documents") or {}

    if brief.get("modalita") == "paniere":
        prezzo = _paniere_price(lst, brief.get("mestiere"), brief.get("intervento_id")) or 0.0
        if brief.get("urgente"):
            prezzo = round(prezzo * (1 + float(lst.get("urgenze_pct", 0)) / 100.0), 2)
    else:
        plat, plng = business_data.get("last_lat"), business_data.get("last_lng")
        dist = haversine(brief.get("lat", 0), brief.get("lng", 0), plat, plng) if plat is not None and plng is not None else 0.0
        prezzo = compute_chiamata_fee(lst, dist, brief.get("urgente", False))

    proposal = {
        "provider_id": uid, "provider_nome": business_data.get("business_name") or user.get("full_name", ""),
        "provider_rating": pdata.get("avg_rating") or 0, "provider_trust": pdata.get("trust_score") or 0,
        "abilitazione_ok": bool(documents.get("art_abilitazione_verified")),
        "tariffa_oraria": lst.get("tariffa_oraria"), "tempi_tipici": lst.get("tempi_tipici"),
        "prezzo": round(prezzo, 2), "modalita": brief.get("modalita"), "message": body.message, "at": now_iso(),
    }
    proposte = [p for p in brief.get("proposte", []) if p.get("provider_id") != uid]
    proposte.append(proposal)
    brief["proposte"] = proposte
    brief["stato"] = "con_proposte"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    label = "chiamata-diagnosi" if brief.get("modalita") == "diagnosi" else "intervento"
    await notify(row["client_id"], "artigiani_proposta", "Nuova proposta artigiano",
                f"{proposal['provider_nome']}: €{proposal['prezzo']:.2f} ({label})", "artigiani", rid)
    return proposal


# ---------------- stage 2 / conferma / soldi (Blocco 3 — vedi docstring modulo) ----------------
async def _add_hold(rid: str, brief: dict, kind: str, amount: float, client: dict, provider_id: str, extra_id: Optional[str] = None) -> dict:
    """Blocca `amount` € per questa richiesta (una delle possibili fasi:
    chiamata/preventivo/extra). Impresa: PaymentIntent Stripe reale (hold sul
    saldo JOBBY) + create_escrow_hold (RPC, registra il ledger — legge
    price_agreed/platform_fee/provider_payout da missions, quindi li
    sovrascriviamo prima con l'IMPORTO DI QUESTA FASE, poi dopo la RPC li
    riportiamo al totale CUMULATIVO per la visualizzazione/il release finale).
    Persona_lf: nessun gateway, solo il registro (vedi lf_pg.py). Ritorna il
    brief aggiornato (chiamante responsabile di salvarlo)."""
    if amount <= 0:
        return brief
    binario = brief.get("binario", "impresa")
    pagamento = brief.get("pagamento") or {"holds": [], "totale_bloccato": 0.0, "fee_totale": 0.0, "payout_totale": 0.0, "stato": "held"}

    if binario == "impresa":
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
        charge = SP.charge_hold(customer_id, pm_id, amount, {"mission_id": rid, "category": "artigiani", "kind": kind})
        db.rpc("create_escrow_hold", {
            "p_mission_id": rid, "p_gateway_transaction_id": charge["payment_intent_id"],
            "p_gateway_response": {"status": charge["status"], "kind": kind}, "p_gateway_name": "stripe",
        }).execute()

        pagamento["holds"].append({"kind": kind, "amount": amount, "payment_intent_id": charge["payment_intent_id"], "extra_id": extra_id, "at": now_iso()})
        pagamento["totale_bloccato"] = round(pagamento["totale_bloccato"] + amount, 2)
        pagamento["fee_totale"] = round(pagamento["fee_totale"] + jobby_fee, 2)
        pagamento["payout_totale"] = round(pagamento["payout_totale"] + payout, 2)
        pagamento["stato"] = "held"
        db.table("missions").update({
            "price_agreed": pagamento["totale_bloccato"], "platform_fee": pagamento["fee_totale"], "provider_payout": pagamento["payout_totale"],
        }).eq("id", rid).execute()

    elif binario == "persona_lf":
        nominale = lf_round_nominale(amount)
        LF.check_ceilings(
            family_id=client["id"], worker_id=provider_id, add_nominale=nominale, add_hours=0.0,
            couple_ceiling_eur=LF_COUPLE_CEILING_EUR, family_ceiling_eur=LF_FAMILY_ANNUAL_EUR,
            worker_ceiling_eur=LF_PROVIDER_ANNUAL_EUR, worker_ceiling_hours=LF_PROVIDER_HOURS,
        )
        LF.record_usage(client["id"], provider_id, nominale, 0.0)
        pagamento["holds"].append({"kind": kind, "nominale": nominale, "extra_id": extra_id, "at": now_iso()})
        pagamento["totale_bloccato"] = round(pagamento["totale_bloccato"] + nominale, 2)
        pagamento["stato"] = "lf_registrato"
        db.table("missions").update({"provider_id": provider_id, "price_agreed": pagamento["totale_bloccato"]}).eq("id", rid).execute()
    else:
        raise HTTPException(status_code=400, detail="invalid_binario")

    brief["pagamento"] = pagamento
    return brief


async def _finalize_release(rid: str, brief: dict, row: dict) -> dict:
    """Chiude la richiesta: trasferisce al provider il netto TOTALE
    accumulato in tutte le fasi (impresa) o non fa nulla sul gateway
    (persona_lf, l'uso è già registrato). release_escrow marca 'released'
    TUTTE le righe payments di tipo escrow_hold della missione in un colpo
    solo — va chiamata una sola volta anche se ci sono stati più hold."""
    binario = brief.get("binario", "impresa")
    pagamento = brief.get("pagamento") or {}
    provider_id = brief.get("provider_scelto")

    if binario == "impresa" and pagamento.get("stato") == "held":
        prov_row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", provider_id).limit(1).execute()
        acct_id = prov_row.data[0].get("stripe_connect_account_id") if prov_row.data else None
        if not acct_id:
            raise HTTPException(status_code=400, detail="provider_not_onboarded")
        payout = float(pagamento.get("payout_totale") or 0)
        if payout > 0:
            transfer = SP.transfer_to_provider(acct_id, payout, {"mission_id": rid, "category": "artigiani"})
            db.rpc("release_escrow", {
                "p_mission_id": rid, "p_gateway_transaction_id": transfer["transfer_id"],
                "p_gateway_response": {}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["transfer_id"] = transfer["transfer_id"]
        pagamento["stato"] = "released"
        brief["pagamento"] = pagamento
    # persona_lf: nessuna azione gateway — l'uso è già stato registrato agli hold

    brief["stato"] = "completata"
    brief["completata_at"] = now_iso()
    return brief


class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/artigiani/richieste/{rid}/confirm")
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

    amount = float(proposal.get("prezzo") or 0)
    brief["provider_scelto"] = provider_id
    brief = await _add_hold(rid, brief, "chiamata" if brief.get("modalita") == "diagnosi" else "paniere", amount, user, provider_id)
    brief["stato"] = "confermata"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(provider_id, "artigiani_confermata", "Richiesta confermata",
                "Il cliente ha confermato la tua proposta.", "artigiani", rid)
    await notify(row["client_id"], "artigiani_confermata", "Richiesta confermata",
                "Hai confermato la richiesta.", "artigiani", rid)
    return {"stato": "confermata", "pagamento": brief.get("pagamento")}


class PreventivoVoce(BaseModel):
    descrizione: str
    tipo: str = "manodopera"
    qta: float = 1
    prezzo_unit: float = 0


class PreventivoIn(BaseModel):
    esito: str
    voci: List[PreventivoVoce] = []
    descrizione_lavoro: str = ""
    tempi: str = ""
    secondo_appuntamento: str = ""
    scomputo_chiamata: bool = True


@router.post("/artigiani/richieste/{rid}/preventivo")
async def compose_preventivo(rid: str, body: PreventivoIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if brief.get("stato") != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    if body.esito not in [e["id"] for e in A.ESITI]:
        raise HTTPException(status_code=400, detail="invalid_esito")

    if body.esito != "preventivo":
        # Risolto in diagnosi / non riparabile: il diritto di chiamata già
        # bloccato al confirm è l'intero compenso, nessun ulteriore lavoro.
        brief["esito"] = body.esito
        brief = await _finalize_release(rid, brief, row)
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
        await notify(row["client_id"], "artigiani_chiuso", "Intervento chiuso",
                    "Il tecnico ha chiuso la chiamata: " + next(e["it"] for e in A.ESITI if e["id"] == body.esito), "artigiani", rid)
        return {"stato": "completata", "esito": body.esito}

    voci = [v.dict() for v in body.voci]
    lavoro_totale = round(sum(v["qta"] * v["prezzo_unit"] for v in voci), 2)
    chiamata_gia_bloccata = sum(h.get("amount", 0) for h in (brief.get("pagamento", {}).get("holds") or []) if h["kind"] == "chiamata")
    importo_da_autorizzare = lavoro_totale
    if body.scomputo_chiamata:
        importo_da_autorizzare = max(0.0, round(lavoro_totale - chiamata_gia_bloccata, 2))

    brief["preventivo"] = {
        "voci": voci, "lavoro_totale": lavoro_totale, "importo_da_autorizzare": importo_da_autorizzare,
        "descrizione_lavoro": body.descrizione_lavoro, "tempi": body.tempi,
        "secondo_appuntamento": body.secondo_appuntamento, "scomputo_chiamata": body.scomputo_chiamata,
        "stato": "in_attesa", "at": now_iso(),
    }
    brief["stato"] = "preventivo_inviato"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "artigiani_preventivo", "Preventivo ricevuto",
                f"Il tecnico ha inviato un preventivo di €{lavoro_totale:.2f}.", "artigiani", rid)
    return brief["preventivo"]


@router.post("/artigiani/richieste/{rid}/preventivo/accept")
async def accept_preventivo(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    preventivo = brief.get("preventivo") or {}
    if brief.get("stato") != "preventivo_inviato" or preventivo.get("stato") != "in_attesa":
        raise HTTPException(status_code=400, detail="no_pending_preventivo")

    importo = float(preventivo.get("importo_da_autorizzare") or 0)
    brief = await _add_hold(rid, brief, "preventivo", importo, user, brief["provider_scelto"])
    preventivo["stato"] = "accettato"
    brief["preventivo"] = preventivo
    brief["stato"] = "in_corso"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(brief["provider_scelto"], "artigiani_accettato", "Preventivo accettato",
                "Il cliente ha accettato il preventivo, puoi iniziare il lavoro.", "artigiani", rid)
    return {"stato": "in_corso", "pagamento": brief.get("pagamento")}


@router.post("/artigiani/richieste/{rid}/preventivo/reject")
async def reject_preventivo(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    preventivo = brief.get("preventivo") or {}
    if brief.get("stato") != "preventivo_inviato" or preventivo.get("stato") != "in_attesa":
        raise HTTPException(status_code=400, detail="no_pending_preventivo")

    # Il preventivo viene rifiutato: nessun lavoro extra, ma il diritto di
    # chiamata (già bloccato al confirm) resta dovuto — il servizio di
    # diagnosi è stato reso. Si chiude come un esito 'non_riparabile'.
    preventivo["stato"] = "rifiutato"
    brief["preventivo"] = preventivo
    brief["esito"] = "non_riparabile"
    brief = await _finalize_release(rid, brief, row)
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(brief["provider_scelto"], "artigiani_chiuso", "Preventivo rifiutato",
                "Il cliente ha rifiutato il preventivo. La richiesta è stata chiusa.", "artigiani", rid)
    return {"stato": "completata"}


class ExtraIn(BaseModel):
    descrizione: str
    importo: float


@router.post("/artigiani/richieste/{rid}/extra")
async def add_extra(rid: str, body: ExtraIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if brief.get("stato") != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    if body.importo <= 0:
        raise HTTPException(status_code=400, detail="invalid_importo")

    extra = {"id": uuid.uuid4().hex, "descrizione": body.descrizione, "importo": round(body.importo, 2), "stato": "in_attesa", "at": now_iso()}
    richieste_extra = brief.get("extra_richieste") or []
    richieste_extra.append(extra)
    brief["extra_richieste"] = richieste_extra
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "artigiani_extra", "Lavoro extra richiesto",
                f"Il tecnico richiede €{extra['importo']:.2f} extra: {body.descrizione}", "artigiani", rid)
    return extra


class ExtraApprove(BaseModel):
    extra_id: str
    approve: bool


@router.post("/artigiani/richieste/{rid}/extra/approve")
async def approve_extra(rid: str, body: ExtraApprove, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    richieste_extra = brief.get("extra_richieste") or []
    extra = next((e for e in richieste_extra if e["id"] == body.extra_id), None)
    if not extra or extra.get("stato") != "in_attesa":
        raise HTTPException(status_code=404, detail="extra_not_found")

    if body.approve:
        brief = await _add_hold(rid, brief, "extra", float(extra["importo"]), user, brief["provider_scelto"], extra_id=extra["id"])
        extra["stato"] = "approvato"
    else:
        extra["stato"] = "rifiutato"
    brief["extra_richieste"] = [extra if e["id"] == extra["id"] else e for e in richieste_extra]
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(brief["provider_scelto"], "artigiani_extra", "Extra " + ("approvato" if body.approve else "rifiutato"),
                f"Il cliente ha {'approvato' if body.approve else 'rifiutato'} l'extra: {extra['descrizione']}", "artigiani", rid)
    return extra


class CloseIn(BaseModel):
    foto_dopo: List[str] = []


@router.post("/artigiani/richieste/{rid}/complete")
async def complete(rid: str, body: CloseIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    if uid not in (row["client_id"], brief.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    if brief.get("stato") not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="not_in_progress")

    brief["foto_dopo"] = body.foto_dopo
    brief = await _finalize_release(rid, brief, row)
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "artigiani_completata", "Intervento completato",
                "Il lavoro è stato segnato come completato.", "artigiani", rid)
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "artigiani_completata", "Intervento completato",
                    "Hai completato il lavoro.", "artigiani", rid)
    return {"stato": "completata"}


@router.post("/artigiani/richieste/{rid}/garanzia")
async def open_garanzia(rid: str, user=Depends(get_current_user)):
    # NOTA: non è un vero flusso di dispute/rimborso (Blocco 4, disputes.py
    # non ancora migrato) — solo un log dell'evento + notifica admin, entro
    # la finestra di garanzia. Riuso pragmatico di admin_actions (admin_id è
    # in realtà il cliente che ha premuto il pulsante, stesso pattern già
    # usato in babysitting.py per l'allarme emergenza).
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") not in ("completata", "recensita"):
        raise HTTPException(status_code=400, detail="not_completed")
    completata_at = brief.get("completata_at")
    if completata_at:
        elapsed_days = (now_utc() - datetime.fromisoformat(completata_at)).days
        if elapsed_days > A.GARANZIA_DAYS:
            raise HTTPException(status_code=400, detail="garanzia_scaduta")

    brief["garanzia_richiesta"] = {"stato": "aperta", "at": now_iso()}
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    db.table("admin_actions").insert({
        "admin_id": user["id"], "action": "artigiani_garanzia", "target_type": "mission", "target_id": rid,
        "notes": "Richiesta di garanzia aperta dal cliente su un intervento Artigiani.",
    }).execute()
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "artigiani_garanzia", "Richiesta di garanzia",
                    "Il cliente ha aperto una richiesta di garanzia sul tuo intervento.", "artigiani", rid)
    return brief["garanzia_richiesta"]


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/artigiani/richieste/{rid}/review")
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
    await notify(provider_id, "artigiani_completata", "Nuova recensione",
                f"Hai ricevuto {body.rating}★ dal cliente.", "artigiani", rid)
    return brief["recensione"]


# ---------------- admin ----------------
@router.get("/admin/artigiani/richieste")
async def admin_richieste(_=Depends(require_admin)):
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("created_at", desc=True).limit(200).execute()
    )
    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        invitati = brief.get("provider_invitati", [])
        provs = _compatible_providers(
            brief.get("mestiere"), brief.get("binario", "impresa"), brief.get("lat"), brief.get("lng"), brief.get("urgente", False)
        )
        item = _richiesta_out(row)
        item["compatible"] = [{
            "provider_id": p["provider_id"], "nome": p.get("business_name") or p.get("full_name"),
            "distance": p.get("distance_km"), "rating": p.get("avg_rating") or 0,
            "abilitazione_ok": bool(p.get("abilitazione_ok")),
            "invited": p["provider_id"] in [i.get("provider_id") for i in invitati],
            "invite_status": next((i.get("status") for i in invitati if i.get("provider_id") == p["provider_id"]), None),
            "confirmed": brief.get("provider_scelto") == p["provider_id"],
        } for p in provs]
        out.append(item)
    return out


class InviteIn(BaseModel):
    provider_ids: List[str]


@router.post("/admin/artigiani/richieste/{rid}/invite")
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
                    await notify(pid, "artigiani_invito", "Nuova richiesta artigiano",
                                "Hai ricevuto di nuovo una richiesta compatibile.", "artigiani", rid)
            continue
        invitati.append({"provider_id": pid, "at": now_iso(), "status": "invited"})
        new_count += 1
        await notify(pid, "artigiani_invito", "Nuova richiesta artigiano",
                    "Hai ricevuto una richiesta compatibile.", "artigiani", rid)
    if new_count or reset_count:
        brief["provider_invitati"] = invitati
        brief["stato"] = "in_matching"
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"invited": new_count, "reactivated": reset_count}


class AbilitazioneDecision(BaseModel):
    verified: bool


@router.post("/admin/artigiani/{user_id}/abilitazione")
async def admin_abilitazione(user_id: str, body: AbilitazioneDecision, _=Depends(require_admin)):
    row = db.table("profiles_provider").select("documents").eq("user_id", user_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="not_found")
    documents = dict(row.data[0].get("documents") or {})
    documents["art_abilitazione_verified"] = body.verified
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user_id).execute()
    msg = "Abilitazione verificata (badge attivo)." if body.verified else "Abilitazione non validata. Ricaricala."
    await notify(user_id, "artigiani_abilitazione", "Verifica abilitazione", msg, "profile", user_id)
    return {"user_id": user_id, "art_abilitazione_verified": body.verified}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/artigiani/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    db.table("app_settings").upsert({"key": _FEE_SETTING_KEY, "value": float(body.fee_pct)}).execute()
    return {"fee_pct": body.fee_pct}
