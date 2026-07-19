"""JOBBY — Spec 2: provider onboarding (registration, phone OTP, 3 tracks,
Libretto Famiglia guided flow, availability, fee, 5-state machine, admin approval)."""
import os
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from core import db, now_utc
from deps import get_current_user, require_admin
from routers.notifications import push_notification

router = APIRouter()

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_VERIFY = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")

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


def _twilio_client():
    from twilio.rest import Client
    return Client(TWILIO_SID, TWILIO_TOKEN)


def provider_state(u: dict) -> str:
    """5 human states derived from the user doc."""
    if not u.get("role") in ("provider", "business"):
        return "client"
    appr = u.get("approval_status", "pending")
    if appr == "suspended":
        return "sospeso"
    if appr == "waitlist":
        return "waitlist"
    if appr == "approved":
        if u.get("provider_profile_type") == "persona_lf" and u.get("lf_inps_registered") is not True:
            return "attivo_inps_pending"
        return "attivo"
    # pending
    return "in_verifica" if u.get("onboarding_completed") else "incompleto"


# ---------------- phone OTP (Twilio Verify) ----------------
class PhoneIn(BaseModel):
    phone: str


class VerifyIn(BaseModel):
    phone: str
    code: str


@router.post("/phone/send-otp")
async def send_otp(body: PhoneIn, user=Depends(get_current_user)):
    if not TWILIO_VERIFY:
        raise HTTPException(status_code=503, detail="sms_not_configured")
    phone = body.phone.strip().replace(" ", "")
    try:
        c = _twilio_client()
        v = c.verify.v2.services(TWILIO_VERIFY).verifications.create(to=phone, channel="sms")
        return {"status": v.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"twilio_error: {e}")


@router.post("/phone/verify-otp")
async def verify_otp(body: VerifyIn, user=Depends(get_current_user)):
    if not TWILIO_VERIFY:
        raise HTTPException(status_code=503, detail="sms_not_configured")
    phone = body.phone.strip().replace(" ", "")
    try:
        c = _twilio_client()
        check = c.verify.v2.services(TWILIO_VERIFY).verification_checks.create(to=phone, code=body.code.strip())
        ok = check.status == "approved"
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"twilio_error: {e}")
    if not ok:
        raise HTTPException(status_code=400, detail="invalid_code")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"phone": phone, "phone_verified": True}})
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
    upd = {"role": role, "provider_profile_type": body.profile_type, "dob": body.dob}
    for k in ("name", "business_name", "vat_number", "codice_fiscale", "address", "iban", "bio", "condizione_soggettiva"):
        v = getattr(body, k)
        if v is not None:
            upd[k] = v
    if body.lat is not None:
        upd["lat"] = body.lat
    if body.lng is not None:
        upd["lng"] = body.lng
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
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
    if not u.get("phone_verified"):
        raise HTTPException(status_code=400, detail="phone_not_verified")
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
        "phone_verified": u.get("phone_verified", False),
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
