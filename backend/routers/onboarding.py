"""Blocco 1 — riscritto per Postgres. Sostituisce interamente la versione
Mongo/Emergent di questo file.

Endpoint di completamento onboarding: imposta il ruolo (client|provider|both)
e crea/aggiorna il profilo Postgres corrispondente (profiles_client e/o
profiles_provider).

NOTA IMPORTANTE — semplificazione deliberata rispetto al modello Emergent:
la versione Mongo permetteva fino a 2 ruoli tra client/provider/business
(roles[] array, con vincolo "mai provider+business insieme"). Lo schema
Postgres storico invece ha un `role` enum singolo (client|provider|both|admin)
dove 'business' NON è un ruolo separato ma un flag `is_proximity_business`
dentro profiles_provider. Questo endpoint segue lo schema Postgres esistente
(già deciso da una sessione precedente, non da questa migrazione) — se serve
davvero poter combinare client + business (non solo client + provider) va
rivista la colonna `role` prima di andare oltre. Segnalato nel piano di
migrazione.

Le foto/documenti business (onboarding/business/photo, .../document) NON sono
stati portati in questo blocco: nello schema Postgres esistono già le colonne
`profiles_provider.documents` e `business_photos` (JSONB) ma l'endpoint di
upload va scritto insieme al resto del profilo provider (Blocco 2), non qui.
"""
from fastapi import APIRouter, HTTPException, Depends

from core_pg import db
from deps_pg import get_current_user
from models import OnboardingIn

router = APIRouter()

VALID_ROLES = ("client", "provider", "both")


@router.get("/onboarding/status")
async def onboarding_status(user=Depends(get_current_user)):
    has_client = bool(
        db.table("profiles_client").select("id").eq("user_id", user["id"]).limit(1).execute().data
    )
    has_provider = bool(
        db.table("profiles_provider").select("id").eq("user_id", user["id"]).limit(1).execute().data
    )
    return {
        "onboarding_completed": has_client or has_provider,
        "role": user.get("role"),
        "status": user.get("status"),
    }


@router.post("/onboarding/complete")
async def complete_onboarding(body: OnboardingIn, user=Depends(get_current_user)):
    role = body.role
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")

    user_id = user["id"]
    is_business = bool(body.business_name or body.vat_number or body.is_business)

    # BLOCCO 7c (jobby-web -> client puro, signup client-side): prima questa
    # decisione guardava `user.get("status") != "active"` per capire se era
    # la "prima volta" che l'utente diventava provider. Bug scoperto
    # implementando davvero il signup client-side per jobby-web: il trigger
    # Postgres `handle_new_user()` (Blocco 1) imposta SEMPRE status='active'
    # per qualunque nuovo signup (client o provider), quindi quel controllo
    # non distingueva più nulla — un provider al primo onboarding sarebbe
    # finito subito 'active', bypassando la coda di approvazione admin del
    # Blocco 6. Si usa invece l'esistenza di `profiles_provider`: se non
    # esiste ancora, è davvero la prima volta → va sempre in 'pending' a
    # prescindere dallo status attuale; se esiste già, questo endpoint non
    # tocca più lo status (resta competenza esclusiva di
    # provider_onboarding.py da quel momento in poi).
    existing_provider_profile = None
    if role in ("provider", "both"):
        existing_provider_profile = (
            db.table("profiles_provider").select("id, business_data").eq("user_id", user_id).limit(1).execute()
        )

    user_updates = {"role": role}
    if body.name:
        user_updates["full_name"] = body.name
    if body.phone is not None:
        user_updates["phone"] = body.phone
    if role in ("provider", "both") and not (existing_provider_profile and existing_provider_profile.data):
        user_updates["status"] = "pending"
    db.table("users").update(user_updates).eq("id", user_id).execute()

    if role in ("client", "both"):
        existing = db.table("profiles_client").select("id").eq("user_id", user_id).limit(1).execute()
        payload = {}
        if body.address is not None:
            payload["address"] = body.address
        if body.radius_km is not None:
            payload["search_radius_km"] = int(body.radius_km)
        if existing.data:
            if payload:
                db.table("profiles_client").update(payload).eq("user_id", user_id).execute()
        else:
            db.table("profiles_client").insert({"user_id": user_id, **payload}).execute()

    if role in ("provider", "both"):
        existing = existing_provider_profile
        payload = {"is_proximity_business": is_business}
        if body.radius_km is not None:
            payload["operational_radius_km"] = int(body.radius_km)
        if body.services is not None:
            payload["skills"] = body.services

        business_data = {}
        if existing.data and existing.data[0].get("business_data"):
            business_data = dict(existing.data[0]["business_data"])
        if body.business_name:
            business_data["business_name"] = body.business_name
        if body.vat_number is not None:
            business_data["vat_number"] = body.vat_number
        if body.service_mode is not None:
            business_data["service_mode"] = body.service_mode
        # `address` è condiviso col profilo cliente (sopra) ma per un business
        # di prossimità è l'indirizzo dell'attività, non un indirizzo di casa
        # — ha senso solo quando is_business è vero, altrimenti lo si ignora
        # qui (resta comunque scritto su profiles_client se role=='both').
        if is_business and body.address is not None:
            business_data["business_address"] = body.address
        if body.products is not None:
            business_data["products"] = body.products
        if business_data:
            payload["business_data"] = business_data

        # TODO (da verificare con un test reale prima del Blocco 2): `location`
        # (colonna PostGIS geography) non è impostata qui. L'insert/update di
        # una colonna geography via client REST (supabase-py) va confermato —
        # serve un formato WKT tipo 'POINT(lng lat)' o una RPC dedicata.
        # Lasciato esplicitamente TODO invece di scrivere codice non
        # verificato per un campo delicato per il matching geografico.
        if body.lat is not None and body.lng is not None:
            payload.setdefault("business_data", business_data or {})
            payload["business_data"]["last_lat"] = body.lat
            payload["business_data"]["last_lng"] = body.lng

        if existing.data:
            db.table("profiles_provider").update(payload).eq("user_id", user_id).execute()
        else:
            db.table("profiles_provider").insert({"user_id": user_id, **payload}).execute()

    refreshed = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    return {"user": refreshed.data[0] if refreshed.data else None}
