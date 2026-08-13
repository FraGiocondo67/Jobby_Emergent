"""BLOCCO 8 (pannello admin custom su Render) — nuovo router, non esisteva
prima. Copre un gap reale scoperto mentre si pianificava il pannello: nessun
blocco precedente aveva mai portato su Postgres una gestione utenti generale
(elenco di TUTTI gli utenti con filtro ruolo/stato + sospendi/riattiva) — il
vecchio pannello Mongo-based (`admin_web.py`, ritirato nel Blocco 7) la
aveva, ma non era mai stata riscritta. Gli endpoint admin già esistenti
(`provider_onboarding.py`, `disputes.py`, ecc.) coprono code specifiche
(provider in attesa, dispute, ecc.), non una vista "tutti gli utenti".

Scope di questo primo giro (MVP per sbloccare la schermata Utenti del
pannello): elenco filtrabile + sospendi/riattiva/rifiuta. **Fuori scope qui**
(rimandati a un giro successivo, non un'omissione silenziosa): reset
password (richiede l'Admin API di Supabase, `generate_link`/
`invite_user_by_email` — da verificare con cura contro la versione pinnata
del SDK prima di esporlo come azione admin) ed eliminazione utente (va
capito se soft-delete, cioè `status='deleted'` coerente con l'enum
esistente, o vera cancellazione — decisione da prendere con l'utente prima
di scrivere un'azione distruttiva).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_pg import db
from deps_pg import require_admin

router = APIRouter()

_ALLOWED_STATUS_TRANSITIONS = ("active", "suspended", "rejected")


@router.get("/admin/users")
async def admin_list_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _=Depends(require_admin),
):
    """Elenco utenti per il pannello admin. Filtro ruolo/stato fatto lato DB
    (colonne indicizzate su un enum chiuso, sicuro); la ricerca testuale `q`
    (nome/email/telefono) è fatta in Python su un batch più ampio — stesso
    pattern pragmatico già usato altrove nel progetto (es.
    provider_onboarding.admin_pending) per condizioni non facilmente
    esprimibili con i filtri di supabase-py."""
    fetch_limit = 1000 if q else max(1, min(limit, 500))
    query = (
        db.table("users")
        .select("id, email, full_name, phone, role, status, preferred_lang, is_email_verified, created_at, last_login_at")
        .order("created_at", desc=True)
        .limit(fetch_limit)
    )
    if role:
        query = query.eq("role", role)
    if status:
        query = query.eq("status", status)
    rows = query.execute().data or []

    if q:
        ql = q.strip().lower()
        rows = [
            r for r in rows
            if ql in (r.get("full_name") or "").lower()
            or ql in (r.get("email") or "").lower()
            or ql in (r.get("phone") or "").lower()
        ]
        rows = rows[offset: offset + limit]

    # BLOCCO 9: Trust score esiste già su profiles_client/profiles_provider
    # (mai esposto in nessun pannello finora, segnalato dall'utente
    # confrontando col vecchio pannello Emergent) — join Python su un batch
    # limitato, stesso pattern pragmatico già usato altrove nel progetto
    # (es. provider_onboarding.admin_pending) invece di una vera JOIN SQL.
    ids = [r["id"] for r in rows]
    if ids:
        cp = db.table("profiles_client").select("user_id, trust_score").in_("user_id", ids).execute()
        pp = db.table("profiles_provider").select("user_id, trust_score").in_("user_id", ids).execute()
        client_trust = {row["user_id"]: row.get("trust_score") for row in (cp.data or [])}
        provider_trust = {row["user_id"]: row.get("trust_score") for row in (pp.data or [])}
        for r in rows:
            r["client_trust_score"] = client_trust.get(r["id"])
            r["provider_trust_score"] = provider_trust.get(r["id"])

    total = len(rows) if q else None
    return {"users": rows, "count": total if total is not None else len(rows)}


class UserStatusIn(BaseModel):
    status: str  # active | suspended | rejected


@router.post("/admin/users/{user_id}/status")
async def admin_set_user_status(user_id: str, body: UserStatusIn, admin=Depends(require_admin)):
    if body.status not in _ALLOWED_STATUS_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"status deve essere uno tra {_ALLOWED_STATUS_TRANSITIONS}")
    res = db.table("users").select("id, status").eq("id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    db.table("users").update({"status": body.status}).eq("id", user_id).execute()
    return {"ok": True, "user_id": user_id, "status": body.status}


class UserRoleIn(BaseModel):
    role: str  # client | provider | both


@router.post("/admin/users/{user_id}/role")
async def admin_set_user_role(user_id: str, body: UserRoleIn, admin=Depends(require_admin)):
    """Cambio ruolo manuale da admin (es. correzione errore di registrazione).
    Non crea/rimuove le righe profiles_client/profiles_provider — se il
    nuovo ruolo richiede un profilo che non esiste ancora, resta da creare
    (stessa logica già vista in jobby-web upgrade-role, non duplicata qui:
    l'utente dovrà comunque completare l'onboarding del ruolo nuovo)."""
    if body.role not in ("client", "provider", "both"):
        raise HTTPException(status_code=400, detail="role deve essere client, provider o both")
    res = db.table("users").select("id").eq("id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    db.table("users").update({"role": body.role}).eq("id", user_id).execute()
    return {"ok": True, "user_id": user_id, "role": body.role}


@router.get("/admin/users/{user_id}")
async def admin_get_user(user_id: str, admin=Depends(require_admin)):
    """Dettaglio utente + profilo cliente/fornitore, per la vista dettaglio
    del pannello (stesso shape di GET /auth/me ma richiamabile dall'admin su
    un utente qualsiasi, non solo se stesso)."""
    res = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    user = {k: v for k, v in res.data[0].items() if k != "auth_id"}
    out = {"user": user}
    cp = db.table("profiles_client").select("*").eq("user_id", user_id).limit(1).execute()
    if cp.data:
        out["client_profile"] = cp.data[0]
    pp = db.table("profiles_provider").select("*").eq("user_id", user_id).limit(1).execute()
    if pp.data:
        out["provider_profile"] = pp.data[0]
    return out
