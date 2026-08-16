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

from core_pg import db, to_geography_point
from deps_pg import get_current_user
from models import PriceItem

router = APIRouter()


class ProfilePatchIn(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    preferred_lang: Optional[str] = None
    # profiles_client (address vale anche per provider puro, vedi sotto:
    # non esisteva una colonna dedicata per un provider non-business, va in
    # business_data.address)
    address: Optional[str] = None
    search_radius_km: Optional[float] = None
    preferred_categories: Optional[List[str]] = None
    # BLOCCO 9 (fix "l'indirizzo non ha la funzione di localizzazione da
    # mappa" in Profilo/Dettagli personali): app/profile-details.tsx non
    # aveva alcun modo di salvare lat/lng (a differenza di
    # provider-onboarding.tsx, che li scrive già su profiles_provider.
    # location tramite POST /onboarding/provider/profile) — aggiunta qui la
    # stessa possibilità, riusando /geocode e /reverse-geocode già esistenti
    # (routers/geo.py) lato frontend.
    lat: Optional[float] = None
    lng: Optional[float] = None
    # BLOCCO 9 (fix "Dettagli personali... ogni modifica non viene
    # memorizzata"): app/profile-details.tsx ha da sempre un campo
    # "Preferenze" (TextInput libero) che non è mai stato incluso nel
    # payload inviato né supportato qui — le modifiche a quel campo
    # venivano scartate in silenzio (nessuna colonna, nessun errore).
    # Colonna nuova su public.users (vale per client e provider, il campo
    # non è vincolato al ruolo). NB: il campo "Email" della stessa
    # schermata resta volutamente non collegato — cambiarlo scriverebbe
    # solo su public.users.email senza toccare l'email vera di Supabase
    # Auth, disallineando login e profilo; serve il flusso dedicato di
    # cambio email di Supabase Auth, non una PATCH generica come questa.
    preferences: Optional[str] = None
    # profiles_provider
    bio: Optional[str] = None
    hourly_rate: Optional[float] = None
    skills: Optional[List[str]] = None
    operational_radius_km: Optional[float] = None
    # BLOCCO 9 (fix "l'attività scelta dal provider non si salva mai"):
    # app/activities.tsx chiama api.updateProfile({services, radius_km,
    # service_mode}) — nomi che qui non sono mai esistiti (le colonne vere
    # sono skills/operational_radius_km, stesso alias già esposto in lettura
    # da routers/auth.py flat["services"]/flat["radius_km"]). Pydantic
    # ignorava questi campi sconosciuti: il PUT tornava 200 ma non scriveva
    # mai le attività scelte. Accettati qui come alias comodi (stesso
    # pattern di `online` sopra) — usati solo se il campo "vero" non è
    # anch'esso presente nella stessa richiesta.
    services: Optional[List[str]] = None
    radius_km: Optional[float] = None
    # service_mode (outdoor/in_shop/both, solo attività di prossimità) non ha
    # una colonna dedicata — va dentro business_data (jsonb), con merge non
    # overwrite, vedi sotto.
    service_mode: Optional[str] = None
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
    if body.preferences is not None:
        user_updates["preferences"] = body.preferences
    if user_updates:
        db.table("users").update(user_updates).eq("id", user_id).execute()

    if role in ("client", "both"):
        cp_updates: Dict[str, Any] = {}
        if body.address is not None:
            cp_updates["address"] = body.address
        if body.search_radius_km is not None:
            # BLOCCO 9 (fix "attività non salvate", 500 su PUT /profile —
            # visto live nei log Render: postgrest.exceptions.APIError
            # 'invalid input syntax for type integer: "10.0"'):
            # search_radius_km/operational_radius_km sono colonne
            # `integer` in Postgres, ma qui sopra sono dichiarate
            # `Optional[float]` (per accettare anche un eventuale valore
            # decimale dal client) — pydantic quindi le passa a supabase-py
            # come float Python (es. 10.0), che PostgREST prova a castare
            # con un bind testuale ('10.0'::integer), NON ammesso da
            # Postgres (serve un numero intero letterale, non una stringa
            # con virgola). Ogni salvataggio del raggio falliva quindi con
            # un 500 — activities.tsx interrompeva save() prima di
            # refresh()/router.back(), quindi SEMBRAVA che "nessuna
            # modifica" venisse salvata anche per gli altri campi nello
            # stesso payload (services). round()+int() qui risolve alla
            # radice, senza dover toccare il tipo dichiarato sopra.
            cp_updates["search_radius_km"] = int(round(body.search_radius_km))
        if body.preferred_categories is not None:
            cp_updates["preferred_categories"] = body.preferred_categories
        if body.lat is not None and body.lng is not None:
            cp_updates["location"] = to_geography_point(body.lat, body.lng)
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
        elif body.services is not None:
            pp_updates["skills"] = body.services
        # BLOCCO 9: stesso bug di search_radius_km sopra —
        # operational_radius_km è anch'essa `integer` su Postgres.
        if body.operational_radius_km is not None:
            pp_updates["operational_radius_km"] = int(round(body.operational_radius_km))
        elif body.radius_km is not None:
            pp_updates["operational_radius_km"] = int(round(body.radius_km))
        if body.availability_status is not None:
            if body.availability_status not in ("online", "offline", "busy"):
                raise HTTPException(status_code=400, detail="invalid_availability_status")
            pp_updates["availability_status"] = body.availability_status
        elif body.online is not None:
            pp_updates["availability_status"] = "online" if body.online else "offline"
        if body.payout_details is not None:
            pp_updates["payout_details"] = body.payout_details
        if body.business_data is not None or body.service_mode is not None or body.address is not None:
            # BLOCCO 9: prima era un overwrite secco di tutta business_data —
            # avrebbe cancellato business_name/vat_number/photo/indirizzo già
            # salvati in onboarding non appena qualcuno avesse chiamato
            # updateProfile con un business_data parziale (es. solo
            # service_mode, come farebbe activities.tsx). Ora fa merge.
            # address qui dentro (non su una colonna dedicata) perché un
            # provider puro non-business non ha profiles_client: prima
            # l'indirizzo digitato in Profilo/Dettagli personali veniva
            # sempre scartato per questi utenti (role="provider").
            current = db.table("profiles_provider").select("business_data").eq("user_id", user_id).limit(1).execute()
            merged: Dict[str, Any] = dict((current.data[0].get("business_data") or {}) if current.data else {})
            if body.business_data is not None:
                merged.update(body.business_data)
            if body.service_mode is not None:
                merged["service_mode"] = body.service_mode
            if body.address is not None:
                merged["address"] = body.address
            pp_updates["business_data"] = merged
        if body.lat is not None and body.lng is not None:
            pp_updates["location"] = to_geography_point(body.lat, body.lng)
        if body.price_list is not None:
            pp_updates["price_list"] = [p.dict() for p in body.price_list]
        if pp_updates:
            db.table("profiles_provider").update(pp_updates).eq("user_id", user_id).execute()

    return {"message": "Profilo aggiornato con successo"}
