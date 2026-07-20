"""JOBBY — Spec 2: provider onboarding (registration, phone OTP, 3 tracks,
Libretto Famiglia guided flow, availability, fee, 5-state machine, admin approval)."""
import os
import random
from datetime import datetime, date, timedelta

import requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from core import db, now_utc
from deps import get_current_user, require_admin
from routers.notifications import push_notification

router = APIRouter()

# --- Resend (Email OTP verification) ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "JOBBY <verifica@yobbyfree.it>")
RESEND_BASE = "https://api.resend.com/emails"
OTP_TTL_MIN = 10

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


def _send_email(to: str, subject: str, html: str):
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="email_not_configured")
    try:
        r = requests.post(
            RESEND_BASE,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": RESEND_FROM, "to": [to], "subject": subject, "html": html},
            timeout=15,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"resend_unreachable: {e}")
    if r.status_code not in (200, 201, 202):
        detail = "resend_error"
        try:
            detail = r.json().get("message") or detail
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"resend_error: {detail}")


def _otp_email_html(code: str) -> str:
    return (
        f"<div style='font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px'>"
        f"<h2 style='color:#1a1a1a'>JOBBY — Verifica email</h2>"
        f"<p style='font-size:15px;color:#444'>Il tuo codice di verifica è:</p>"
        f"<div style='font-size:34px;font-weight:bold;letter-spacing:8px;color:#2563eb;"
        f"background:#eff4ff;border-radius:12px;padding:18px;text-align:center;margin:16px 0'>{code}</div>"
        f"<p style='font-size:13px;color:#888'>Il codice scade tra {OTP_TTL_MIN} minuti. "
        f"Se non hai richiesto questa verifica, ignora questa email.</p></div>"
    )


def provider_state(u: dict) -> str:
    """5 human states derived from the user doc."""
    if not u.get("role") in ("provider", "business"):
        return "client"
    appr = u.get("approval_status", "pending")
    if appr == "suspended":
        return "sospeso"
    if appr == "rejected":
        return "rifiutato"
    if appr == "waitlist":
        return "waitlist"
    if appr == "approved":
        if u.get("provider_profile_type") == "persona_lf" and u.get("lf_inps_registered") is not True:
            return "attivo_inps_pending"
        return "attivo"
    # pending
    return "in_verifica" if u.get("onboarding_completed") else "incompleto"


# ---------------- email OTP (Resend) ----------------
class EmailIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    email: EmailStr
    code: str


@router.post("/email/send-otp")
async def send_otp(body: EmailIn, user=Depends(get_current_user)):
    # #3 — verifica email DISATTIVATA per ora: l'email si considera verificata
    # subito, senza invio codice (integrazione reale in un momento successivo).
    email = body.email.strip().lower()
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"email": email, "email_verified": True}})
    return {"status": "verified", "auto_verified": True}


@router.post("/email/verify-otp")
async def verify_otp(body: VerifyIn, user=Depends(get_current_user)):
    email = body.email.strip().lower()
    rec = await db.otp_requests.find_one({"user_id": user["user_id"], "email": email})
    if not rec or not rec.get("code"):
        raise HTTPException(status_code=400, detail="no_pending_verification")
    try:
        expired = now_utc() > datetime.fromisoformat(rec["expires_at"])
    except Exception:
        expired = False
    if expired:
        await db.otp_requests.delete_one({"_id": rec["_id"]})
        raise HTTPException(status_code=400, detail="code_expired")
    if body.code.strip() != rec["code"]:
        raise HTTPException(status_code=400, detail="invalid_code")
    await db.otp_requests.delete_one({"_id": rec["_id"]})
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"contact_email": email, "email_verified": True}})
    return {"verified": True}


# ---------------- provider profile / tracks ----------------
def _is_adult(dob_str: str) -> bool:
    try:
        d = datetime.fromisoformat(dob_str).date()
    except Exception:
        return False
    today = date.today()
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return age >= 18


class ProfileIn(BaseModel):
    profile_type: str            # impresa | piva | persona_lf
    dob: str                     # YYYY-MM-DD
    name: Optional[str] = None
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
    role = "business" if body.profile_type == "impresa" else "provider"
    # #8 — vincolo multi-ruolo: max 2 profili e mai provider+business insieme.
    owned = set(user.get("roles") or [user.get("role") or "client"])
    if role not in owned:
        if len(owned) >= 2:
            raise HTTPException(status_code=400, detail="max_two_roles")
        if (role == "provider" and "business" in owned) or (role == "business" and "provider" in owned):
            raise HTTPException(status_code=400, detail="role_conflict")
    upd = {"role": role, "provider_profile_type": body.profile_type, "dob": body.dob}
    for k in ("name", "business_name", "vat_number", "codice_fiscale", "address", "iban", "bio", "condizione_soggettiva"):
        v = getattr(body, k)
        if v is not None:
            upd[k] = v
    if body.lat is not None:
        upd["lat"] = body.lat
    if body.lng is not None:
        upd["lng"] = body.lng
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd, "$addToSet": {"roles": role}})
    return {"ok": True, "role": role}


class DocIn(BaseModel):
    kind: str   # id_front | id_back | selfie | presentation
    image: str


@router.post("/onboarding/provider/document")
async def upload_doc(body: DocIn, user=Depends(get_current_user)):
    field = {"id_front": "id_document_front", "id_back": "id_document_back",
             "selfie": "selfie_document", "presentation": "presentation_photo"}.get(body.kind)
    if not field or not body.image.strip():
        raise HTTPException(status_code=400, detail="invalid_document")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {field: body.image}})
    return {"ok": True}


# ---------------- Libretto Famiglia guided steps ----------------
class DelegaIn(BaseModel):
    signature_name: str


@router.post("/onboarding/lf/delega")
async def sign_delega(body: DelegaIn, user=Depends(get_current_user)):
    if not body.signature_name.strip():
        raise HTTPException(status_code=400, detail="empty_signature")
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"lf_delega_signed": True, "lf_delega_name": body.signature_name.strip(),
                                        "lf_delega_at": now_utc().isoformat()}})
    return {"lf_delega_signed": True}


class InpsIn(BaseModel):
    registered: bool


@router.post("/onboarding/lf/inps")
async def set_inps(body: InpsIn, user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"lf_inps_registered": body.registered}})
    return {"lf_inps_registered": body.registered}


# ---------------- availability ----------------
class AvailabilityIn(BaseModel):
    availability: dict   # {mon: {morning, afternoon, evening}, ...}


@router.put("/onboarding/availability")
async def set_availability(body: AvailabilityIn, user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"availability": body.availability}})
    return {"availability": body.availability}


# ---------------- config (fee + price ranges) ----------------
async def get_fee_config() -> dict:
    s = await db.settings.find_one({"key": "onboarding_fee"})
    return {**DEFAULT_FEE, **(s.get("value") if s else {})}


async def get_price_ranges() -> dict:
    s = await db.settings.find_one({"key": "price_ranges"})
    return {**DEFAULT_PRICE_RANGES, **(s.get("value") if s else {})}


@router.get("/onboarding/config")
async def onboarding_config(user=Depends(get_current_user)):
    return {"fee": await get_fee_config(), "price_ranges": await get_price_ranges(), "condizioni": CONDIZIONI}


# ---------------- finalize + status ----------------
@router.post("/onboarding/provider/submit")
async def submit_provider(user=Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not u.get("email_verified"):
        raise HTTPException(status_code=400, detail="email_not_verified")
    if not u.get("provider_profile_type"):
        raise HTTPException(status_code=400, detail="profile_incomplete")
    appr = "approved" if u.get("provider_approved") else "pending"
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"onboarding_completed": True, "approval_status": appr,
                                        "submitted_at": now_utc().isoformat()}})
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    u["provider_state"] = provider_state(u)
    return u


@router.get("/onboarding/provider/status")
async def provider_status(user=Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {
        "provider_state": provider_state(u),
        "profile_type": u.get("provider_profile_type"),
        "email_verified": u.get("email_verified", False),
        "onboarding_completed": u.get("onboarding_completed", False),
        "lf_delega_signed": u.get("lf_delega_signed", False),
        "lf_inps_registered": u.get("lf_inps_registered", False),
        "has_id": bool(u.get("id_document_front")),
        "has_selfie": bool(u.get("selfie_document")),
        "iban": u.get("iban", ""),
    }


# ---------------- voluntary suspend ----------------
class SuspendIn(BaseModel):
    suspend: bool


@router.post("/provider/suspend")
async def self_suspend(body: SuspendIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "business"):
        raise HTTPException(status_code=403, detail="providers_only")
    if body.suspend:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"approval_status": "suspended", "self_suspended": True}})
    else:
        # resume only if it was a voluntary suspension
        if user.get("self_suspended"):
            await db.users.update_one({"user_id": user["user_id"]},
                                      {"$set": {"approval_status": "approved", "self_suspended": False}})
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"provider_state": provider_state(u)}


# ---------------- admin: approval + fee config ----------------
@router.get("/admin/onboarding/pending")
async def admin_pending(_=Depends(require_admin)):
    users = await db.users.find(
        {"role": {"$in": ["provider", "business"]}, "approval_status": {"$in": ["pending", "waitlist"]}},
        {"_id": 0, "password_hash": 0}).sort("submitted_at", -1).to_list(200)
    for u in users:
        u["provider_state"] = provider_state(u)
    return users


class AdminDecisionIn(BaseModel):
    action: str   # approve | suspend | reject | waitlist | convert_lf


@router.post("/admin/onboarding/{user_id}/decision")
async def admin_decision(user_id: str, body: AdminDecisionIn, _=Depends(require_admin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="not_found")
    upd = {}
    msg = ""
    if body.action == "approve":
        upd = {"approval_status": "approved", "provider_approved": True}
        msg = "Il tuo profilo è stato approvato: ora puoi ricevere richieste!"
    elif body.action == "suspend":
        upd = {"approval_status": "suspended"}; msg = "Il tuo profilo è stato sospeso. Ti contatteremo."
    elif body.action == "reject":
        upd = {"approval_status": "rejected"}; msg = "La tua registrazione non è stata approvata."
    elif body.action == "waitlist":
        upd = {"approval_status": "waitlist"}; msg = "Sei in lista d'attesa: ti avvisiamo appena apriamo nella tua zona."
    elif body.action == "convert_lf":
        upd = {"provider_profile_type": "persona_lf", "role": "provider", "approval_status": "pending"}
        msg = "Ti abbiamo proposto il percorso Libretto Famiglia."
    else:
        raise HTTPException(status_code=400, detail="invalid_action")
    await db.users.update_one({"user_id": user_id}, {"$set": upd})
    await push_notification(user_id, "onboarding", "Aggiornamento profilo", msg, "profile", user_id)
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user_id": user_id, "provider_state": provider_state(u)}


class FeeConfigIn(BaseModel):
    visit_fixed_total: float
    provider_share: float
    client_share: float
    recurring_total: float


@router.post("/admin/onboarding/fee")
async def admin_set_fee(body: FeeConfigIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "onboarding_fee"}, {"$set": {"value": body.dict()}}, upsert=True)
    return await get_fee_config()


# ==================== Spec 9 — trigger IDV scritto + promemoria rinnovi ====================
def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


@router.get("/admin/idv-trigger")
async def admin_idv_trigger(_=Depends(require_admin)):
    """Monitora il volume settimanale di registrazioni persone fisiche vs soglia scritta."""
    s = await db.settings.find_one({"key": "idv_config"})
    cfg = {"weekly_threshold": 15, "consecutive_weeks": 3, "multi_area": False, "provider": "manual"}
    if s and isinstance(s.get("value"), dict):
        cfg.update(s["value"])
    # persone fisiche = provider senza business_name
    users = await db.users.find({"role": "provider", "$or": [{"business_name": {"$in": [None, ""]}}, {"business_name": {"$exists": False}}]},
                                {"_id": 0, "created_at": 1}).to_list(5000)
    counts: dict = {}
    for u in users:
        ca = u.get("created_at")
        if not ca:
            continue
        try:
            dt = datetime.fromisoformat(str(ca).replace("Z", ""))
            counts[_iso_week_key(dt)] = counts.get(_iso_week_key(dt), 0) + 1
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
    s = await db.settings.find_one({"key": "idv_config"})
    cur = {"weekly_threshold": 15, "consecutive_weeks": 3, "multi_area": False, "provider": "manual"}
    if s and isinstance(s.get("value"), dict):
        cur.update(s["value"])
    for k in ("weekly_threshold", "consecutive_weeks", "multi_area", "provider"):
        if k in body:
            cur[k] = body[k]
    await db.settings.update_one({"key": "idv_config"}, {"$set": {"value": cur}}, upsert=True)
    return cur


@router.get("/admin/renewals")
async def admin_renewals(_=Depends(require_admin)):
    """Casellari e documenti in scadenza (o scaduti) entro N giorni."""
    horizon_days = 60
    now = datetime.now()
    out = []
    cur = db.users.find({"casellario_expires": {"$exists": True, "$ne": None}},
                        {"_id": 0, "user_id": 1, "name": 1, "business_name": 1, "casellario_expires": 1, "casellario_verified": 1})
    for u in await cur.to_list(2000):
        exp = u.get("casellario_expires")
        try:
            dt = datetime.fromisoformat(str(exp).replace("Z", ""))
            days = (dt.replace(tzinfo=None) - now).days
        except Exception:
            continue
        if days <= horizon_days:
            out.append({"user_id": u["user_id"], "name": u.get("business_name") or u.get("name"),
                        "type": "casellario", "expires_at": exp, "days_left": days,
                        "expired": days < 0, "verified": bool(u.get("casellario_verified"))})
    out.sort(key=lambda x: x["days_left"])
    return {"horizon_days": horizon_days, "items": out}
