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


@router.post("/auth/logout")
async def logout():
    """Con Supabase Auth il logout invalida la sessione lato client
    (supabase.auth.signOut()) — non esiste più un session_token custom da
    cancellare lato server. Endpoint mantenuto solo per compatibilità con
    chiamate esistenti del frontend durante la transizione; non fa nulla."""
    return {"ok": True}
