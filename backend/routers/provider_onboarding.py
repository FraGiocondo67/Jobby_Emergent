"""BLOCCO 6 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent. Era rimasto
indietro dal Blocco 1 (segnalato più volte nel piano) — fino a questo blocco
non esisteva alcun modo, né da app né da admin, di completare/approvare
davvero un profilo provider su Postgres.

Rapporto con `routers/onboarding.py` (Blocco 1): quel router gestisce la
scelta iniziale del ruolo (`client`/`provider`/`both`) e crea la riga
`profiles_provider` con `is_proximity_business`/`skills`/`business_data`
essenziali — questo router **completa** quel profilo con i dati KYC/fiscali
(documenti, IBAN, tipo profilo fiscale, disponibilità) e gestisce
l'approvazione admin. Non duplica la logica ruolo/business: si aspetta che
`profiles_provider` esista già (creata da `/onboarding/complete`).

Semplificazione strutturale rispetto al vecchio Mongo: il vecchio modello
aveva `roles[]` con vincolo "max 2, mai provider+business insieme" perché
"business" era un ruolo a sé. Nello schema Postgres (già deciso prima di
questa migrazione, poi confermato nel Blocco 5) `role` è un enum chiuso
(client/provider/both/admin) e "business" è ortogonale — un flag
`is_proximity_business` su `profiles_provider`, non un ruolo. Questo router
quindi non ha più bisogno di alcuna logica di conflitto ruoli: si limita ad
arricchire il profilo provider che esiste già.

Dove vivono i dati (niente tabelle nuove, solo colonne già esistenti nello
schema storico ma mai scritte da nessun router fino ad ora):
- `profiles_provider.fiscal_data` (jsonb, NUOVO USO): profile_type
  (impresa/piva/persona_lf — categoria fiscale, INDIPENDENTE dal binario che
  ogni verticale usa per il matching, vedi sotto), dob, codice_fiscale, iban,
  condizione_soggettiva.
- `profiles_provider.documents` (jsonb): stessa convenzione già usata da
  artigiani.py/babysitting.py/driver.py (chiavi prefissate, verified
  booleani) — qui id_document_front/id_document_back/selfie_document/
  presentation_photo, più lf_delega_signed/lf_delega_name/lf_delega_at/
  lf_inps_registered, submitted_at, onboarding_waitlisted.
- `profiles_provider.business_data` (jsonb, Blocco 1/5): vat_number/
  business_name/last_lat/last_lng — riusa esattamente le chiavi già scritte
  da onboarding.py, non introduce un secondo posto per lo stesso dato.
- `profiles_provider.bio`/`time_slots`/`kyc_status`/`kyc_verified_at`:
  colonne dedicate già esistenti, mai scritte finora.
- `profiles_provider.location` (PostGIS): scritta qui con
  `core_pg.to_geography_point()` (stesso helper verificato nel Blocco 5 per
  `missions.location`) — chiude il TODO lasciato esplicitamente aperto in
  `onboarding.py` dal Blocco 1 ("da verificare... lasciato TODO invece di
  scrivere codice non verificato").

NOTA — `profile_type` (impresa/piva/persona_lf, categoria fiscale KYC) è
DIVERSO dal `binario` che client/provider scelgono per-verticale in
richieste.py/artigiani.py/babysitting.py/driver.py (letto da
`p_binario` nelle RPC `*_compatible_providers`, mai da questo file) — il
vecchio Mongo derivava il ruolo "business" da profile_type=='impresa', qui
NON più: sono due concetti ortogonali, coerente con la nota sopra.

MIGLIORAMENTO deliberato rispetto al vecchio comportamento: la
"sospensione volontaria" del provider (pausa temporanea, non un
provvedimento admin) NON tocca più `users.status` (che blocca l'intero
accesso via `deps_pg.get_current_user` — un self-suspend avrebbe reso
impossibile anche il self-resume, dato che l'utente sospeso riceve 403 dal
gate di autenticazione prima ancora di raggiungere l'endpoint: bug latente
mai emerso nel vecchio Mongo perché mai testato end-to-end). Usa invece
`profiles_provider.availability_status` (online/offline/busy, colonna
dedicata già esistente) — più corretto semanticamente e non rischia di
autobloccare l'utente.

FUORI SCOPE (non riportato, nessun consumer noto): verifica email via OTP
reale (Resend) — già disattivata "per ora" nel vecchio sistema (auto-verify
senza invio codice), stesso comportamento mantenuto qui. Se serve attivarla
davvero è lavoro nuovo, non porting.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core_pg import db, now_iso, notify, to_geography_point
from deps_pg import get_current_user, require_admin

router = APIRouter()

DEFAULT_FEE = {"visit_fixed_total": 8.0, "provider_share": 4.0, "client_share": 4.0,
               "recurring_total": 6.0, "recurring_after_month": 1}
DEFAULT_PRICE_RANGES = {
    "ordinaria": {"min": 14, "max": 18}, "afondo": {"min": 18, "max": 24},
    "posttrasloco": {"min": 22, "max": 30}, "stiro": {"min": 10, "max": 14},
}
CONDIZIONI = [
    {"id": "nessuna", "it": "Nessuna", "en": "None"},
    {"id": "studente", "it": "Studente/ssa (fino a 25 anni)", "en": "Student (under 25)"},
    {"id": "pensionato", "it": "Pensionato/a", "en": "Retired"},
    {"id": "disoccupato", "it": "Disoccupato/a", "en": "Unemployed"},
]


def _provider_row(user_id: str) -> dict:
    res = db.table("profiles_provider").select("*").eq("user_id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="complete_onboarding_first")
    return res.data[0]


def _save_documents(user_id: str, documents: dict) -> None:
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user_id).execute()


def provider_state(user: dict, provider: Optional[dict]) -> str:
    """7 stati derivati, stessa semantica del vecchio Mongo — vedi docstring
    modulo per dove vive ciascun campo nel nuovo schema."""
    if user.get("role") not in ("provider", "both"):
        return "client"
    if not provider:
        return "incompleto"
    documents = provider.get("documents") or {}
    fiscal = provider.get("fiscal_data") or {}
    status = user.get("status", "pending")
    if status == "suspended":
        return "sospeso"
    if status == "rejected":
        return "rifiutato"
    if documents.get("onboarding_waitlisted"):
        return "waitlist"
    if status == "active":
        if fiscal.get("profile_type") == "persona_lf" and not documents.get("lf_inps_registered"):
            return "attivo_inps_pending"
        return "attivo"
    return "in_verifica" if documents.get("submitted_at") else "incompleto"


# ---------------- email verification (disattivata "per ora", vedi docstring) ----------------
class EmailIn(BaseModel):
    email: str


@router.post("/email/send-otp")
async def send_otp(body: EmailIn, user=Depends(get_current_user)):
    email = body.email.strip().lower()
    db.table("users").update({"email": email, "is_email_verified": True}).eq("id", user["id"]).execute()
    return {"status": "verified", "auto_verified": True}


@router.post("/email/verify-otp")
async def verify_otp(user=Depends(get_current_user)):
    # Nessun OTP reale da verificare (vedi send_otp) — endpoint tenuto per
    # compatibilità con eventuali chiamate residue lato app.
    return {"verified": bool(user.get("is_email_verified"))}


# ---------------- provider profile ----------------
def _is_adult(dob_str: str) -> bool:
    try:
        d = datetime.fromisoformat(dob_str).date()
    except Exception:
        return False
    today = datetime.now().date()
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return age >= 18


class ProfileIn(BaseModel):
    profile_type: str            # impresa | piva | persona_lf (categoria fiscale, vedi docstring)
    dob: str                     # YYYY-MM-DD
    business_name: Optional[str] = None
    vat_number: Optional[str] = None
    codice_fiscale: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    iban: Optional[str] = None
    bio: Optional[str] = None
    condizione_soggettiva: Optional[str] = None


@router.post("/onboarding/provider/profile")
async def set_profile(body: ProfileIn, user=Depends(get_current_user)):
    if body.profile_type not in ("impresa", "piva", "persona_lf"):
        raise HTTPException(status_code=400, detail="invalid_profile_type")
    if not _is_adult(body.dob):
        raise HTTPException(status_code=400, detail="minor_not_allowed")
    provider = _provider_row(user["id"])

    fiscal = dict(provider.get("fiscal_data") or {})
    fiscal.update({"profile_type": body.profile_type, "dob": body.dob, "codice_fiscale": body.codice_fiscale,
                   "iban": body.iban, "condizione_soggettiva": body.condizione_soggettiva})
    business_data = dict(provider.get("business_data") or {})
    if body.business_name:
        business_data["business_name"] = body.business_name
    if body.vat_number is not None:
        business_data["vat_number"] = body.vat_number
    if body.address is not None:
        business_data["address"] = body.address
    if body.lat is not None:
        business_data["last_lat"] = body.lat
    if body.lng is not None:
        business_data["last_lng"] = body.lng

    upd = {"fiscal_data": fiscal, "business_data": business_data}
    if body.bio is not None:
        upd["bio"] = body.bio
    if body.lat is not None and body.lng is not None:
        upd["location"] = to_geography_point(body.lat, body.lng)
    db.table("profiles_provider").update(upd).eq("user_id", user["id"]).execute()
    return {"ok": True, "profile_type": body.profile_type}


class DocIn(BaseModel):
    kind: str   # id_front | id_back | selfie | presentation
    image: str


@router.post("/onboarding/provider/document")
async def upload_doc(body: DocIn, user=Depends(get_current_user)):
    field = {"id_front": "id_document_front", "id_back": "id_document_back",
             "selfie": "selfie_document", "presentation": "presentation_photo"}.get(body.kind)
    if not field or not body.image.strip():
        raise HTTPException(status_code=400, detail="invalid_document")
    provider = _provider_row(user["id"])
    documents = dict(provider.get("documents") or {})
    documents[field] = body.image
    _save_documents(user["id"], documents)
    return {"ok": True}


# ---------------- Libretto Famiglia guided steps ----------------
class DelegaIn(BaseModel):
    signature_name: str


@router.post("/onboarding/lf/delega")
async def sign_delega(body: DelegaIn, user=Depends(get_current_user)):
    if not body.signature_name.strip():
        raise HTTPException(status_code=400, detail="empty_signature")
    provider = _provider_row(user["id"])
    documents = dict(provider.get("documents") or {})
    documents.update({"lf_delega_signed": True, "lf_delega_name": body.signature_name.strip(), "lf_delega_at": now_iso()})
    _save_documents(user["id"], documents)
    return {"lf_delega_signed": True}


class InpsIn(BaseModel):
    registered: bool


@router.post("/onboarding/lf/inps")
async def set_inps(body: InpsIn, user=Depends(get_current_user)):
    provider = _provider_row(user["id"])
    documents = dict(provider.get("documents") or {})
    documents["lf_inps_registered"] = body.registered
    _save_documents(user["id"], documents)
    return {"lf_inps_registered": body.registered}


# ---------------- availability ----------------
class AvailabilityIn(BaseModel):
    availability: dict   # {mon: {morning, afternoon, evening}, ...}


@router.put("/onboarding/availability")
async def set_availability(body: AvailabilityIn, user=Depends(get_current_user)):
    _provider_row(user["id"])
    db.table("profiles_provider").update({"time_slots": body.availability}).eq("user_id", user["id"]).execute()
    return {"availability": body.availability}


# ---------------- config (fee + price ranges) ----------------
def _setting(key: str, default: dict) -> dict:
    res = db.table("app_settings").select("value").eq("key", key).limit(1).execute()
    if res.data and isinstance(res.data[0].get("value"), dict):
        return {**default, **res.data[0]["value"]}
    return dict(default)


@router.get("/onboarding/config")
async def onboarding_config(user=Depends(get_current_user)):
    return {"fee": _setting("onboarding_fee", DEFAULT_FEE), "price_ranges": _setting("price_ranges", DEFAULT_PRICE_RANGES),
            "condizioni": CONDIZIONI}


# ---------------- finalize + status ----------------
@router.post("/onboarding/provider/submit")
async def submit_provider(user=Depends(get_current_user)):
    provider = _provider_row(user["id"])
    if not user.get("is_email_verified"):
        raise HTTPException(status_code=400, detail="email_not_verified")
    fiscal = provider.get("fiscal_data") or {}
    if not fiscal.get("profile_type"):
        raise HTTPException(status_code=400, detail="profile_incomplete")
    documents = dict(provider.get("documents") or {})
    documents["submitted_at"] = now_iso()
    upd = {"documents": documents}
    if provider.get("kyc_status") in (None, "not_started"):
        upd["kyc_status"] = "pending"
    db.table("profiles_provider").update(upd).eq("user_id", user["id"]).execute()
    provider["documents"] = documents
    return {"ok": True, "provider_state": provider_state(user, provider)}


@router.get("/onboarding/provider/status")
async def provider_status(user=Depends(get_current_user)):
    res = db.table("profiles_provider").select("*").eq("user_id", user["id"]).limit(1).execute()
    provider = res.data[0] if res.data else None
    documents = (provider or {}).get("documents") or {}
    fiscal = (provider or {}).get("fiscal_data") or {}
    return {
        "provider_state": provider_state(user, provider),
        "profile_type": fiscal.get("profile_type"),
        "email_verified": bool(user.get("is_email_verified")),
        "onboarding_completed": bool(documents.get("submitted_at")),
        "lf_delega_signed": bool(documents.get("lf_delega_signed")),
        "lf_inps_registered": bool(documents.get("lf_inps_registered")),
        "has_id": bool(documents.get("id_document_front")),
        "has_selfie": bool(documents.get("selfie_document")),
        "iban": fiscal.get("iban", ""),
    }


# ---------------- voluntary pause (vedi MIGLIORAMENTO nel docstring modulo) ----------------
class SuspendIn(BaseModel):
    suspend: bool


@router.post("/provider/suspend")
async def self_suspend(body: SuspendIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    _provider_row(user["id"])
    status = "offline" if body.suspend else "online"
    db.table("profiles_provider").update({"availability_status": status}).eq("user_id", user["id"]).execute()
    return {"availability_status": status}


# ---------------- admin: approval + fee config ----------------
@router.get("/admin/onboarding/pending")
async def admin_pending(_=Depends(require_admin)):
    # Filtro su users.status fatto in Python, non con .eq()/.in_() su una
    # colonna della relazione embedded — pattern non usato altrove in questo
    # progetto con supabase-py, meglio non introdurlo qui non verificato
    # (stesso approccio pragmatico già usato in admin_reviews_pending/
    # admin_renewals per condizioni su dati annidati).
    res = (
        db.table("profiles_provider").select("*, users!inner(id, full_name, email, role, status, is_email_verified)")
        .order("created_at", desc=True).limit(1000).execute()
    )
    out = []
    for p in (res.data or []):
        u = p.pop("users", None) or {}
        if u.get("status") != "pending":
            continue
        documents = p.get("documents") or {}
        # Solo chi ha davvero completato il submit (submitted_at) o è in
        # lista d'attesa è "in coda" — gli altri sono ancora "incompleto" e
        # non serve mostrarli in questa lista.
        if not (documents.get("submitted_at") or documents.get("onboarding_waitlisted")):
            continue
        out.append({**u, "provider_state": provider_state(u, p), "business_name": (p.get("business_data") or {}).get("business_name"),
                    "vat_number": (p.get("business_data") or {}).get("vat_number"), "codice_fiscale": (p.get("fiscal_data") or {}).get("codice_fiscale"),
                    "iban": (p.get("fiscal_data") or {}).get("iban"), "provider_profile_type": (p.get("fiscal_data") or {}).get("profile_type"),
                    "address": (p.get("business_data") or {}).get("address"), "id_document_front": documents.get("id_document_front"),
                    "id_document_back": documents.get("id_document_back"), "selfie_document": documents.get("selfie_document"),
                    "presentation_photo": documents.get("presentation_photo"), "casellario_doc": documents.get("casellario_doc"),
                    "casellario_verified": documents.get("casellario_verified"), "contact_email": u.get("email"),
                    "email_verified": u.get("is_email_verified"), "lf_delega_signed": documents.get("lf_delega_signed"),
                    "lf_inps_registered": documents.get("lf_inps_registered"), "user_id": u.get("id")})
    return out


class AdminDecisionIn(BaseModel):
    action: str   # approve | suspend | reject | waitlist | convert_lf


@router.post("/admin/onboarding/{user_id}/decision")
async def admin_decision(user_id: str, body: AdminDecisionIn, _=Depends(require_admin)):
    ures = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    if not ures.data:
        raise HTTPException(status_code=404, detail="not_found")
    provider = _provider_row(user_id)
    documents = dict(provider.get("documents") or {})
    user_upd, provider_upd, msg = {}, {}, ""

    if body.action == "approve":
        user_upd = {"status": "active"}
        provider_upd = {"kyc_status": "approved", "kyc_verified_at": now_iso()}
        documents["onboarding_waitlisted"] = False
        msg = "Il tuo profilo è stato approvato: ora puoi ricevere richieste!"
    elif body.action == "suspend":
        user_upd = {"status": "suspended"}
        msg = "Il tuo profilo è stato sospeso. Ti contatteremo."
    elif body.action == "reject":
        user_upd = {"status": "rejected"}
        provider_upd = {"kyc_status": "rejected"}
        msg = "La tua registrazione non è stata approvata."
    elif body.action == "waitlist":
        documents["onboarding_waitlisted"] = True
        msg = "Sei in lista d'attesa: ti avvisiamo appena apriamo nella tua zona."
    elif body.action == "convert_lf":
        fiscal = dict(provider.get("fiscal_data") or {})
        fiscal["profile_type"] = "persona_lf"
        provider_upd = {"fiscal_data": fiscal, "kyc_status": "pending"}
        user_upd = {"status": "pending"}
        msg = "Ti abbiamo proposto il percorso Libretto Famiglia."
    else:
        raise HTTPException(status_code=400, detail="invalid_action")

    if user_upd:
        db.table("users").update(user_upd).eq("id", user_id).execute()
    provider_upd["documents"] = documents
    db.table("profiles_provider").update(provider_upd).eq("user_id", user_id).execute()
    await notify(user_id, "kyc_update", "Aggiornamento profilo", msg, "profile", user_id)

    ures2 = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    pres2 = db.table("profiles_provider").select("*").eq("user_id", user_id).limit(1).execute()
    return {"user_id": user_id, "provider_state": provider_state(ures2.data[0], pres2.data[0] if pres2.data else None)}


class FeeConfigIn(BaseModel):
    visit_fixed_total: float
    provider_share: float
    client_share: float
    recurring_total: float


@router.post("/admin/onboarding/fee")
async def admin_set_fee(body: FeeConfigIn, _=Depends(require_admin)):
    db.table("app_settings").upsert({"key": "onboarding_fee", "value": body.dict()}).execute()
    return _setting("onboarding_fee", DEFAULT_FEE)


# ==================== trigger IDV scritto + promemoria rinnovi ====================
def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


@router.get("/admin/idv-trigger")
async def admin_idv_trigger(_=Depends(require_admin)):
    """Monitora il volume settimanale di registrazioni persone fisiche
    (provider senza business_name in business_data) vs soglia scritta."""
    cfg = _setting("idv_config", {"weekly_threshold": 15, "consecutive_weeks": 3, "multi_area": False, "provider": "manual"})
    res = (
        db.table("profiles_provider").select("created_at, business_data, users!inner(role)")
        .eq("users.role", "provider").limit(5000).execute()
    )
    counts: dict = {}
    for p in (res.data or []):
        bd = p.get("business_data") or {}
        if bd.get("business_name"):
            continue
        ca = p.get("created_at")
        if not ca:
            continue
        try:
            dt = datetime.fromisoformat(str(ca).replace("Z", ""))
            key = _iso_week_key(dt)
            counts[key] = counts.get(key, 0) + 1
        except Exception:
            pass
    now = datetime.now()
    weeks = []
    for i in range(cfg["consecutive_weeks"]):
        wk = _iso_week_key(now - timedelta(weeks=i))
        weeks.append({"week": wk, "count": counts.get(wk, 0)})
    over = all(w["count"] >= cfg["weekly_threshold"] for w in weeks) and len(weeks) == cfg["consecutive_weeks"]
    triggered = over or bool(cfg["multi_area"])
    return {"config": cfg, "weeks": weeks, "over_volume": over, "multi_area": cfg["multi_area"],
            "triggered": triggered, "current_idv_provider": cfg["provider"],
            "recommendation": ("Adotta un fornitore IDV automatico: sostituisce SOLO il controllo visivo del documento." if triggered
                               else "Verifica manuale sufficiente: volume sotto soglia.")}


@router.post("/admin/idv-config")
async def admin_idv_config(body: dict, _=Depends(require_admin)):
    cur = _setting("idv_config", {"weekly_threshold": 15, "consecutive_weeks": 3, "multi_area": False, "provider": "manual"})
    for k in ("weekly_threshold", "consecutive_weeks", "multi_area", "provider"):
        if k in body:
            cur[k] = body[k]
    db.table("app_settings").upsert({"key": "idv_config", "value": cur}).execute()
    return cur


@router.get("/admin/renewals")
async def admin_renewals(_=Depends(require_admin)):
    """Casellari in scadenza (o scaduti) entro N giorni — filtrato in Python
    sullo stesso jsonb documents letto per la verifica (stesso limite già
    accettato altrove nel progetto: niente query indicizzata su una chiave
    jsonb per un volume che oggi non lo giustifica)."""
    horizon_days = 60
    now = datetime.now()
    res = (
        db.table("profiles_provider").select("user_id, documents, business_data, users!inner(full_name)")
        .limit(2000).execute()
    )
    out = []
    for p in (res.data or []):
        documents = p.get("documents") or {}
        exp = documents.get("casellario_expires")
        if not exp:
            continue
        try:
            dt = datetime.fromisoformat(str(exp).replace("Z", ""))
            days = (dt.replace(tzinfo=None) - now).days
        except Exception:
            continue
        if days <= horizon_days:
            u = p.get("users") or {}
            out.append({"user_id": p["user_id"], "name": (p.get("business_data") or {}).get("business_name") or u.get("full_name"),
                        "type": "casellario", "expires_at": exp, "days_left": days,
                        "expired": days < 0, "verified": bool(documents.get("casellario_verified"))})
    out.sort(key=lambda x: x["days_left"])
    return {"horizon_days": horizon_days, "items": out}
