"""BLOCCO 7b (jobby-web -> client puro) - nuovo endpoint di editing libero del
profilo utente. Prima non esisteva una route generica per aggiornare i campi
base (nome/telefono/lingua) o i campi profilo cliente/fornitore fuori dal
flusso KYC di provider_onboarding.py - jobby-web scriveva questi campi
direttamente su Supabase (app/api/profile/route.ts, PATCH). Stessi campi
esatti gia gestiti li, per non perdere comportamento nella conversione a
proxy.

Nota: qui NON si puo cambiare `role` (resta di competenza di
POST /onboarding/complete, che gestisce anche la creazione dei profili
client/provider mancanti) ne lo status/KYC (provider_onboarding.py) - un
utente non puo promuoversi da solo cambiando questi campi."""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_pg import db
from deps_pg import get_current_user
from models import PriceItem

router = APIRouter()


class ProfilePatchIn(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    preferred_lang: Optional[str] = None
    # profiles_client
    address: Optional[str] = None
    search_radius_km: Optional[float] = None
    preferred_categories: Optional[List[str]] = None
    # profiles_provider
    bio: Optional[str] = None
    hourly_rate: Optional[float] = None
    skills: Optional[List[str]] = None
    operational_radius_km: Optional[float] = None
    availability_status: Optional[str] = None
    # BLOCCO 9: la app Expo (ProviderHome.toggleOnline, app/(tabs)/index.tsx)
    # chiama api.updateProfile({online: bool}) - un campo che qui non e' mai
    # esistito (solo availability_status: "online"/"offline"/"busy"). Il
    # PATCH veniva quindi accettato (pydantic ignora i campi sconosciuti) ma
    # non aggiornava nulla: i provider non potevano davvero mettersi online.
    # Accettato qui come alias comodo, tradotto sotto in availability_status.
    online: Optional[bool] = None
    payout_details: Optional[Dict[str, Any]] = None
    business_data: Optional[Dict[str, Any]] = None
    # BLOCCO 9 (fix "il listino prezzi salvato da app/profile-details.tsx non
    # si vede più da nessuna parte"): profiles_provider.price_list esiste da
    # sempre in lettura (routers/auth.py, flat["price_list"]) ma questo
    # modello non aveva mai avuto un campo per scriverlo — pydantic ignora i
    # campi sconosciuti, quindi il PUT veniva accettato (200) ma non
    # scriveva nulla. Stesso bug del campo `online` sopra.
    price_list: Optional[List[PriceItem]] = None


# BLOCCO 9: la app Expo chiama questa route con PUT (src/api.ts:
# updateProfile -> request("/profile", {method:"PUT"})), non PATCH - FastAPI
# le tratta come route distinte, quindi ogni PUT falliva con 405 Method Not
# Allowed (mai stato notato perche' il chiamante lo ingoia in try/catch).
# Stessa funzione esposta su entrambi i verbi, nessun'altra modifica di
# comportamento per chi gia' chiama PATCH (jobby-web).
@router.put("/profile")
@router.patch("/profile")
async def update_profile(body: ProfilePatchIn, user=Depends(get_current_user)):
    user_id = user["id"]
    role = user.get("role")

    user_updates: Dict[str, Any] = {}
    if body.full_name is not None:
        user_updates["full_name"] = body.full_name.strip()
    if body.phone is not None:
        user_updates["phone"] = body.phone or None
    if body.preferred_lang is not None:
        user_updates["preferred_lang"] = body.preferred_lang
    if user_updates:
        db.table("users").update(user_updates).eq("id", user_id).execute()

    if role in ("client", "both"):
        cp_updates: Dict[str, Any] = {}
        if body.address is not None:
            cp_updates["address"] = body.address
        if body.search_radius_km is not None:
            cp_updates["search_radius_km"] = body.search_radius_km
        if body.preferred_categories is not None:
            cp_updates["preferred_categories"] = body.preferred_categories
        if cp_updates:
            db.table("profiles_client").update(cp_updates).eq("user_id", user_id).execute()

    if role in ("provider", "both"):
        pp_updates: Dict[str, Any] = {}
        if body.bio is not None:
            pp_updates["bio"] = body.bio
        if body.hourly_rate is not None:
            pp_updates["hourly_rate"] = body.hourly_rate
        if body.skills is not None:
            pp_updates["skills"] = body.skills
        if body.operational_radius_km is not None:
            pp_updates["operational_radius_km"] = body.operational_radius_km
        if body.availability_status is not None:
            if body.availability_status not in ("online", "offline", "busy"):
                raise HTTPException(status_code=400, detail="invalid_availability_status")
            pp_updates["availability_status"] = body.availability_status
        elif body.online is not None:
            pp_updates["availability_status"] = "online" if body.online else "offline"
        if body.payout_details is not None:
            pp_updates["payout_details"] = body.payout_details
        if body.business_data is not None:
            pp_updates["business_data"] = body.business_data
        if body.price_list is not None:
            pp_updates["price_list"] = [p.dict() for p in body.price_list]
        if pp_updates:
            db.table("profiles_provider").update(pp_updates).eq("user_id", user_id).execute()

    return {"message": "Profilo aggiornato con successo"}
