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
async def list_notifications(limit: int = 100, unread: bool = False, user=Depends(get_current_user)):
    # limit/unread: BLOCCO 7b (jobby-web -> client puro), aggiunti per parità
    # con app/api/notifications/route.ts (GET ?limit=&unread=true) — prima
    # questo endpoint aveva solo il comportamento di default (ultime 100,
    # nessun filtro), che resta invariato per chi non passa i parametri.
    limit = max(1, min(limit, 200))
    query = db.table("notifications").select("*").eq("user_id", user["id"])
    if unread:
        query = query.eq("is_read", False)
    res = query.order("created_at", desc=True).limit(limit).execute()
    unread_res = (
        db.table("notifications").select("id", count="exact")
        .eq("user_id", user["id"]).eq("is_read", False).execute()
    )
    # BLOCCO 10 (segnalato dall'utente: "le notifiche sono visibili ma non
    # sono selezionabili e non è possibile segnarle come lette"): il
    # docstring del modulo AMMETTEVA la differenza di nomi campo (id/is_read
    # Postgres vs notif_id/read Mongo) ma non la riconciliava mai — le righe
    # venivano restituite grezze. app/notifications.tsx legge n.notif_id
    # (sempre undefined -> key React undefined, PATCH /notifications/
    # undefined/read che non trova mai nulla) e n.read (sempre undefined ->
    # ogni notifica appariva sempre "non letta", pallino rosso incluso, anche
    # dopo "segna tutte come lette" perché il campo letto dal frontend non
    # cambiava mai). Normalizzato qui allo shape atteso dal frontend.
    items = [{**n, "notif_id": n.get("id"), "read": bool(n.get("is_read"))} for n in (res.data or [])]
    return {"items": items, "unread": unread_res.count or 0}


@router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, user=Depends(get_current_user)):
    """BLOCCO 7b: prima non esisteva alcun modo di eliminare una notifica dal
    backend — jobby-web lo faceva scrivendo direttamente su Supabase
    (app/api/notifications/route.ts, DELETE)."""
    db.table("notifications").delete().eq("id", notif_id).eq("user_id", user["id"]).execute()
    return {"ok": True}


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
