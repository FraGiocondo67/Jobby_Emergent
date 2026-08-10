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
    result = {"user": _serialize_user(user)}

    client_profile = db.table("profiles_client").select("*").eq("user_id", user["id"]).limit(1).execute()
    if client_profile.data:
        result["client_profile"] = client_profile.data[0]

    provider_profile = db.table("profiles_provider").select("*").eq("user_id", user["id"]).limit(1).execute()
    if provider_profile.data:
        result["provider_profile"] = provider_profile.data[0]

    return result


@router.post("/auth/logout")
async def logout():
    """Con Supabase Auth il logout invalida la sessione lato client
    (supabase.auth.signOut()) — non esiste più un session_token custom da
    cancellare lato server. Endpoint mantenuto solo per compatibilità con
    chiamate esistenti del frontend durante la transizione; non fa nulla."""
    return {"ok": True}
