"""Blocco 1 (migrazione Emergent -> Supabase/Render) — riscritto per Supabase
Auth + Postgres. Sostituisce interamente la versione Mongo/Emergent di questo
file.

Con Supabase Auth, signup/login/OAuth Google/Sign in with Apple avvengono lato
client (SDK @supabase/supabase-js sull'app Expo e su jobby-web), NON più
tramite endpoint custom del backend. Per questo /auth/register, /auth/login,
/auth/apple, /auth/session (scambio col server Emergent) e /auth/demo — tutti
presenti nella versione Emergent/Mongo — sono stati RIMOSSI: non servono più.
Il backend si limita a verificare il token che il client ha già ottenuto da
Supabase Auth (vedi deps_pg.get_current_user) e a esporre i dati applicativi
collegati. La riga public.users viene creata automaticamente al signup dal
trigger Postgres `on_auth_user_created` (migrazione
auto_provision_public_users_on_signup), non da un endpoint /auth/register.

Cosa NON è stato portato in questo blocco (deliberatamente, da riprendere):
- /profile (PUT), /profile/qr-confirm, /verification/* — dipendevano da campi
  Mongo (qr_confirm_enabled, verification_status mock) senza un equivalente
  ancora deciso nello schema Postgres. Vanno ripresi nel Blocco 2/4 insieme al
  resto del profilo provider (KYC reale via Sumsub, non più mock).
- L'arricchimento di /auth/me con `provider_state` (da
  routers/provider_onboarding.py, non ancora migrato: è Mongo-based e usa una
  forma dati — user_id/roles[] — incompatibile con lo schema Postgres
  client/provider/both). Da ricollegare quando quel modulo verrà riscritto.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core_pg import db
from deps_pg import get_current_user

router = APIRouter()


def _serialize_user(user: dict) -> dict:
    """Nasconde eventuali campi interni prima di restituire l'utente al client."""
    return {k: v for k, v in user.items() if k != "auth_id"}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    base = _serialize_user(user)

    client_profile = db.table("profiles_client").select("*").eq("user_id", user["id"]).limit(1).execute()
    cp = client_profile.data[0] if client_profile.data else None

    provider_profile = db.table("profiles_provider").select("*").eq("user_id", user["id"]).limit(1).execute()
    pp = provider_profile.data[0] if provider_profile.data else None

    # BLOCCO 9 (fix bug "mancano parecchie funzioni" nella app mobile):
    # questa route restituiva SOLO {user, client_profile, provider_profile}
    # annidati (riscrittura Blocco 7b per jobby-web, vedi
    # jobby-web/app/api/auth/me/route.ts che infatti legge data.user/
    # data.client_profile/data.provider_profile). La app Expo pero' fa
    # `setUser(await api.me())` e poi legge decine di campi PIATTI su `user`
    # (user?.role, user?.name, user?.online, user?.hourly_rate,
    # user?.services, user?.rating, ... — stesso modello a singolo documento
    # della vecchia utenza Mongo, mai aggiornato quando lo schema e' stato
    # separato in users/profiles_client/profiles_provider). Risultato: OGNI
    # campo su `user` era undefined lato mobile, compreso `role` — quindi
    # HomeTab() apriva SEMPRE CustomerHome di default, mai ProviderHome/
    # BusinessHome, indipendentemente dal ruolo reale. Probabilmente la causa
    # singola piu' grave dei "funzioni mancanti" segnalati, piu' ancora delle
    # categorie (vedi routers/categories.py) — le due cose si sommavano: pure
    # trovando le categorie, un provider vedeva comunque la home cliente.
    #
    # Fix additivo, NON distruttivo: si aggiungono alias piatti alla radice
    # della risposta mantenendo INVARIATI i campi user/client_profile/
    # provider_profile annidati da cui dipende jobby-web.
    flat = dict(base)
    flat["name"] = base.get("full_name")
    flat["picture"] = base.get("avatar_url")
    flat["wallet_balance"] = 0.0  # nessun wallet interno (Blocco 3), vedi routers/app_home.py
    # BLOCCO 9 (fix bug "ad ogni login la app rifà l'onboarding"): public.users
    # non ha mai avuto una colonna onboarding_completed nello schema Postgres
    # (era un campo diretto nel documento Mongo — vedi il vecchio
    # server.py/seed di allora) — app/index.tsx pero' controlla ancora
    # `user.onboarding_completed` per decidere se aprire "/onboarding-flow" o
    # la app vera: sempre undefined -> sempre falsy -> onboarding ripetuto ad
    # ogni login, qualunque cosa l'utente avesse gia' scelto. Stesso segnale
    # gia' calcolato correttamente da GET /onboarding/status (routers/
    # onboarding.py): "ha gia' un profilo client o provider" = onboarding
    # fatto. Replicato qui cosi' non serve chiamare due endpoint.
    flat["onboarding_completed"] = bool(cp or pp)
    if cp:
        flat["address"] = cp.get("address")
        flat["radius_km"] = cp.get("search_radius_km")
    if pp:
        business_data = pp.get("business_data") or {}
        # Lo schema Postgres non ha un valore di ruolo "business" a se'
        # stante (users.role e' client/provider/both/admin): le attivita' di
        # prossimita' sono provider con is_proximity_business=true. La app
        # mobile invece smista la home su 3 rami (`user?.role ===
        # "provider"/"business"`, vedi app/(tabs)/index.tsx HomeTab) — senza
        # questo alias un'attivita' di prossimita' finiva sempre nella home
        # provider "missioni", mai nella sua home dedicata.
        if pp.get("is_proximity_business") and flat.get("role") in ("provider", "both"):
            flat["role"] = "business"
        flat["business_name"] = business_data.get("business_name", "")
        # BLOCCO 9: un provider puro (role="provider", niente
        # profiles_client) non aveva alcun modo di rivedersi l'indirizzo
        # salvato da app/profile-details.tsx — flat["address"] veniva
        # popolato SOLO da cp sopra. Ora business_data.address (scritto da
        # routers/profile.py update_profile(), stessa chiave) fa da
        # fallback quando manca un profilo cliente.
        flat["address"] = flat.get("address") or business_data.get("address")
        # BLOCCO 9: app/activities.tsx legge user?.service_mode per
        # precompilare la modalità (outdoor/in_shop/both) di un'attività di
        # prossimità — mai stato esposto qui (vive in business_data.
        # service_mode, scritto da routers/profile.py update_profile()).
        flat["service_mode"] = business_data.get("service_mode")
        flat["picture"] = flat.get("picture") or business_data.get("photo")
        flat["hourly_rate"] = pp.get("hourly_rate")
        flat["services"] = pp.get("skills") or []
        flat["radius_km"] = pp.get("operational_radius_km") or flat.get("radius_km")
        flat["online"] = pp.get("availability_status") == "online"
        flat["availability"] = pp.get("availability_status")
        flat["rating"] = pp.get("avg_rating")
        flat["reviews_count"] = pp.get("completed_missions")
        flat["verification_status"] = pp.get("kyc_status")
        flat["price_list"] = pp.get("price_list")
        # lat/lng: profiles_*.location e' un tipo geography PostGIS, non
        # estraibile qui senza una RPC/vista dedicata (fuori scope di questo
        # fix) — lasciato assente piuttosto che sbagliato; RealMap() sulla
        # app ha gia' un fallback a coordinate di default quando mancano.

    return {**flat, "user": base, "client_profile": cp, "provider_profile": pp}


class QrConfirmIn(BaseModel):
    enabled: bool


@router.post("/profile/qr-confirm")
async def set_qr_confirm(body: QrConfirmIn, user=Depends(get_current_user)):
    """BLOCCO 10 (fix "attivo QR Code nel Profilo -> errore"): mai migrato da
    Mongo a Postgres (vedi nota nel docstring di modulo) — public.users non
    aveva la colonna qr_confirm_enabled che app/(tabs)/profile.tsx si
    aspettava, quindi POST /profile/qr-confirm 404ava sempre. Aggiunta la
    colonna (migrazione add_qr_confirm_enabled_to_users) ed esposto qui
    l'endpoint mancante — stessa preferenza cliente che verrà letta dal
    flusso di conferma QR a fine servizio (Blocco 10, in corso)."""
    db.table("users").update({"qr_confirm_enabled": body.enabled}).eq("id", user["id"]).execute()
    return {"qr_confirm_enabled": body.enabled}


@router.post("/auth/logout")
async def logout():
    """Con Supabase Auth il logout invalida la sessione lato client
    (supabase.auth.signOut()) — non esiste più un session_token custom da
    cancellare lato server. Endpoint mantenuto solo per compatibilità con
    chiamate esistenti del frontend durante la transizione; non fa nulla."""
    return {"ok": True}
