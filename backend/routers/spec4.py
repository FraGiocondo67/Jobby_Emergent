"""BLOCCO 5 (migrazione Emergent -> Supabase/Render) — riscrittura mirata di
questo router. NON sostituisce 1:1 il vecchio Mongo/Emergent spec4.py: per
decisione esplicita dell'utente, qui restano SOLO le due componenti
genuinamente mancanti rispetto a quanto già implementato per-verticale nel
Blocco 2/3/4 (vedi spec4_pg.py per la spiegazione completa di ciascuna e dei
suoi limiti):

  1. Rimborso a scaglioni sulla cancellazione — endpoint cross-cutting per
     ANY missione (funziona su qualsiasi verticale, non solo Pulizie come il
     vecchio `/richieste/...` legato a `db.richieste`), più il preview
     "cancel-policy" prima di annullare.
  2. Punteggio privato cliente + affidabilità (admin).

TOLTO rispetto al vecchio spec4.py (fuori scope, decisione utente): no-show,
segnalazione ritardo, pausa/ripresa ricorrenza, tutta la Fase B recensioni
(create/delete/reply/listing — già gestita da review() nelle 4 verticali),
coda di moderazione recensioni (rimandata al Blocco 6, Retool).

IMPORTANTE — integrazione con gli endpoint di cancellazione già esistenti:
`POST /pulizie|artigiani|babysitting|driver/richieste/{rid}/cancel` (Blocco
2/3) ora chiamano `spec4_pg.apply_banded_cancellation()` al posto del
rimborso 100% incondizionato che avevano prima — piccola modifica mirata in
ciascuno dei 4 file, non un redirect a un nuovo endpoint separato: il
cliente continua a usare lo stesso pulsante "Annulla" di sempre, che ora
applica gli scaglioni. Questo file espone solo la preview (`cancel-policy`,
utile per mostrare il tier prima della conferma) più le due componenti
nuove.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import spec4_pg as S4
from core_pg import db, now_iso, record_client_trust_event
from deps_pg import get_current_user, require_admin

router = APIRouter()


def _load_mission(mission_id: str) -> dict:
    res = db.table("missions").select("*").eq("id", mission_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    return res.data[0]


def _binario(mission: dict) -> str:
    return (mission.get("brief_answers") or {}).get("binario", "impresa")


# ==================== rimborso a scaglioni ====================
@router.get("/missions/{mission_id}/cancel-policy")
async def cancel_policy(mission_id: str, user=Depends(get_current_user)):
    """Preview del tier applicabile ORA, da mostrare prima della conferma di
    cancellazione (stessa logica che verrà applicata da .../cancel)."""
    mission = _load_mission(mission_id)
    if user["id"] not in (mission["client_id"], mission.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    cfg = S4.spec4_config()
    binario = _binario(mission)
    tier, h = S4.cancel_tier(mission.get("scheduled_at"), binario, cfg)
    return {"tier": tier, "hours_until": round(h, 1) if h is not None else None,
            "binario": binario, "scheduled_at": mission.get("scheduled_at"), "config": cfg}


# ==================== punteggio privato cliente ====================
class ClientRatingIn(BaseModel):
    rating: int
    flags: List[str] = []
    note: str = ""


CLIENT_FLAGS = ["condizioni_diverse", "richieste_fuori_accordo", "comportamento_irrispettoso"]


@router.post("/missions/{mission_id}/rate-client")
async def rate_client(mission_id: str, body: ClientRatingIn, user=Depends(get_current_user)):
    """Il provider valuta privatamente il cliente a fine lavoro — mai visibile
    al cliente (vedi spec4_pg.py). Una sola valutazione per missione."""
    mission = _load_mission(mission_id)
    if mission.get("provider_id") != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = mission.get("brief_answers") or {}
    if brief.get("stato") not in ("completata", "recensita"):
        raise HTTPException(status_code=400, detail="not_completed")
    if brief.get("valutazione_cliente"):
        raise HTTPException(status_code=400, detail="already_rated")

    rating = max(1, min(5, body.rating))
    flags = [f for f in body.flags if f in CLIENT_FLAGS]
    entry = {"rating": rating, "flags": flags, "note": (body.note or "").strip()[:500], "at": now_iso()}
    brief["valutazione_cliente"] = entry
    db.table("missions").update({"brief_answers": brief}).eq("id", mission_id).execute()

    delta = round((rating - 3) * 1.5, 2)
    notes = f"Valutazione privata provider su missione {mission_id}: {rating}★"
    if flags:
        notes += f" [{', '.join(flags)}]"
    record_client_trust_event(mission["client_id"], "private_rating", delta, dimension="reliability", notes=notes)
    return {"ok": True, "flags": flags}


@router.get("/missions/{mission_id}/rate-client")
async def get_client_rating(mission_id: str, user=Depends(get_current_user)):
    mission = _load_mission(mission_id)
    if mission.get("provider_id") != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    brief = mission.get("brief_answers") or {}
    return {"valutazione_cliente": brief.get("valutazione_cliente"), "flags_available": CLIENT_FLAGS}


# ==================== admin ====================
@router.get("/admin/spec4/config")
async def admin_get_config(_=Depends(require_admin)):
    return S4.spec4_config()


@router.post("/admin/spec4/config")
async def admin_set_config(body: dict, _=Depends(require_admin)):
    return S4.set_spec4_config(body)


@router.get("/admin/spec4/reliability")
async def admin_reliability(_=Depends(require_admin)):
    """Affidabilità = profiles_client.trust_score (calcolato automaticamente
    dal trigger su client_trust_events, Blocco 4) — niente più campi ad-hoc
    come nel vecchio users.reliability_events."""
    res = (
        db.table("profiles_client").select("user_id, trust_score, users!inner(full_name)")
        .order("trust_score").limit(200).execute()
    )
    cfg = S4.spec4_config()
    out = []
    for row in (res.data or []):
        strikes_res = (
            db.table("client_trust_events").select("id", count="exact")
            .eq("client_id", row["user_id"]).eq("event_type", "cancel_late").execute()
        )
        u = row.get("users") or {}
        out.append({"user_id": row["user_id"], "name": u.get("full_name"), "trust_score": row.get("trust_score") or 0,
                    "cancel_late_events": strikes_res.count or 0,
                    "over_threshold": (strikes_res.count or 0) >= cfg["client_strike_threshold"]})
    return out
