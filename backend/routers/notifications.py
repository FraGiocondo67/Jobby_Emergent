"""BLOCCO 4 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce la versione Mongo/Emergent.

Il lato INSERT era già stato risolto nel Blocco 2 (helper `notify()` in
core_pg.py, richiamato da tutti i router già migrati — vedi `_NOTIF_TYPE_MAP`
per la mappa tipo-dominio -> enum Postgres `notification_type`). Qui resta
solo il lato lettura/marcatura-come-letta, contro `public.notifications`
(già esistente, RLS `notifications_own` già attiva — vedi migrazione
storica). Stesso identico contratto REST della versione Mongo (path e forma
della risposta), tranne per gli id (uuid Postgres invece di `ntf_...`) e i
nomi dei campi booleani (`is_read`/`read_at` invece di `read`).
"""
from fastapi import APIRouter, Depends

import core as _mongo_core
from core_pg import db, now_iso
from deps_pg import get_current_user

router = APIRouter()


async def push_notification(user_id: str, ntype: str, title: str, body: str,
                           ref_type: str = "", ref_id: str = "") -> None:
    """Compat: implementazione Mongo ORIGINALE (pre-Blocco 4), invariata.
    confirm_delivery.py, routers/spec4.py e routers/provider_onboarding.py
    (non ancora migrati — Blocco 5, vedi piano) importano questa funzione a
    livello di modulo; rimuoverla romperebbe l'avvio del server. Le notifiche
    "vere" per le route già migrate passano invece da core_pg.notify() (usato
    da tutti i router Blocco 2/3/4) e finiscono su public.notifications, letto
    dagli endpoint qui sotto — le due tabelle (Mongo vs Postgres) restano
    separate finché anche quei tre router non vengono migrati."""
    if not user_id:
        return
    try:
        await _mongo_core.db.notifications.insert_one({
            "notif_id": _mongo_core.new_id("ntf"), "user_id": user_id, "type": ntype,
            "title": title, "body": body, "ref_type": ref_type, "ref_id": ref_id,
            "read": False, "created_at": _mongo_core.now_utc().isoformat(),
        })
    except Exception:
        pass


@router.get("/notifications")
async def list_notifications(user=Depends(get_current_user)):
    res = (
        db.table("notifications").select("*")
        .eq("user_id", user["id"]).order("created_at", desc=True).limit(100).execute()
    )
    unread_res = (
        db.table("notifications").select("id", count="exact")
        .eq("user_id", user["id"]).eq("is_read", False).execute()
    )
    return {"items": res.data or [], "unread": unread_res.count or 0}


@router.get("/notifications/unread-count")
async def unread_count(user=Depends(get_current_user)):
    res = (
        db.table("notifications").select("id", count="exact")
        .eq("user_id", user["id"]).eq("is_read", False).execute()
    )
    return {"unread": res.count or 0}


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user=Depends(get_current_user)):
    db.table("notifications").update({"is_read": True, "read_at": now_iso()}) \
        .eq("id", notif_id).eq("user_id", user["id"]).execute()
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    db.table("notifications").update({"is_read": True, "read_at": now_iso()}) \
        .eq("user_id", user["id"]).eq("is_read", False).execute()
    return {"ok": True}
