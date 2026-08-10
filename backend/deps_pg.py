"""Blocco 1 — dipendenza di autenticazione per i router già migrati a
Postgres/Supabase Auth. Sostituisce deps.py (Mongo, session_token custom) solo
per i router che importano esplicitamente da qui (auth.py, onboarding.py) —
i router non ancora migrati continuano a usare deps.py.
"""
from typing import Optional

from fastapi import Header, HTTPException, Depends

from core_pg import db


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Verifica il JWT emesso da Supabase Auth (ottenuto lato client con
    supabase.auth.signInWithPassword / signInWithOAuth / signInWithIdToken) e
    restituisce la riga public.users collegata — creata automaticamente al
    signup dal trigger on_auth_user_created (vedi migrazione
    auto_provision_public_users_on_signup)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]

    try:
        auth_resp = db.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    auth_user = getattr(auth_resp, "user", None)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    result = db.table("users").select("*").eq("auth_id", auth_user.id).limit(1).execute()
    rows = result.data or []
    if not rows:
        # Non dovrebbe succedere (il trigger crea la riga al signup) — rete di
        # sicurezza nel caso il trigger non sia (ancora) applicato sul progetto
        # Supabase in uso, o sia fallito per qualche motivo.
        raise HTTPException(status_code=404, detail="Profilo utente non trovato — trigger di signup mancante?")

    user = rows[0]
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account sospeso")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accesso admin richiesto")
    return user
