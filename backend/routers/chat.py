"""BLOCCO 4 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent.

Cambio di modello dati (non un semplice re-platforming): il vecchio sistema
teneva `conversations` (una riga per-viewer, con `thread_id` condiviso) più
`messages` legate a un `thread_id` cross-categoria, alimentate da
`bookings`/`business_requests` (quest'ultima tabella è dominio del Blocco 5,
non ancora migrato). Lo schema Postgres storico ha invece già una tabella
`public.messages` molto più semplice, legata direttamente a `mission_id`
(non a un thread cross-missione) — vedi piano di migrazione, sezione 4.6,
riga `conversations`/`messages`: "Da confermare se il modello per-missione è
sufficiente". Decisione presa in questo blocco: sì, per ora — la chat è
sempre nel contesto di una missione (le 4 verticali già migrate: Pulizie,
Artigiani, Babysitting, Driver). Non esiste ancora una nozione di chat
"libera" prima che una missione esista, né di thread cross-missione — se
servirà in futuro (es. business/Blocco 5) andrà riconsiderato.

Ne consegue un contratto REST diverso da quello Mongo (niente più
`conversation_id`): le rotte sono ora chiavate su `mission_id`. Il frontend
Expo (`api.ts` e la schermata chat) va aggiornato di conseguenza — stesso
gap già segnalato per Blocco 3 (non incluso in questo blocco, che resta
backend-only).

RLS già presente e corretta su `public.messages` (`users_can_read_own_messages`,
`users_can_send_messages`, `users_can_mark_read`) — il backend usa comunque la
service role key (vedi core_pg.py) quindi l'autorizzazione reale è applicata
qui sotto negli endpoint.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core_pg import db, now_iso, notify
from deps_pg import get_current_user

router = APIRouter()


class MessageIn(BaseModel):
    content: str


def _load_mission(mission_id: str, uid: str) -> dict:
    res = db.table("missions").select("*").eq("id", mission_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    if uid not in (row["client_id"], row.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    return row


@router.get("/chat/missions")
async def list_chat_missions(user=Depends(get_current_user)):
    """Elenco missioni con una conversazione attiva/potenziale per l'utente
    (client o provider), con anteprima ultimo messaggio e conteggio non letti.
    Solo missioni con un provider già assegnato (senza provider_id non c'è un
    secondo interlocutore con cui chattare)."""
    uid = user["id"]
    res = (
        db.table("missions").select("id, client_id, provider_id, title, status, updated_at")
        .or_(f"client_id.eq.{uid},provider_id.eq.{uid}")
        .not_.is_("provider_id", "null")
        .order("updated_at", desc=True).limit(100).execute()
    )
    missions = res.data or []
    if not missions:
        return []
    mission_ids = [m["id"] for m in missions]

    msgs_res = (
        db.table("messages").select("mission_id, sender_id, receiver_id, content, read_at, created_at")
        .in_("mission_id", mission_ids).order("created_at", desc=True).execute()
    )
    last_by_mission = {}
    unread_by_mission = {}
    for m in (msgs_res.data or []):
        mid = m["mission_id"]
        if mid not in last_by_mission:
            last_by_mission[mid] = m
        if m["receiver_id"] == uid and not m["read_at"]:
            unread_by_mission[mid] = unread_by_mission.get(mid, 0) + 1

    out = []
    for m in missions:
        other_id = m["provider_id"] if m["client_id"] == uid else m["client_id"]
        last = last_by_mission.get(m["id"])
        out.append({
            "mission_id": m["id"], "mission_title": m.get("title"), "mission_status": m.get("status"),
            "other_id": other_id,
            "last_message": last.get("content") if last else None,
            "last_message_at": last.get("created_at") if last else None,
            "unread": unread_by_mission.get(m["id"], 0),
        })
    out.sort(key=lambda c: c["last_message_at"] or "", reverse=True)
    return out


@router.get("/chat/{mission_id}")
async def get_messages(mission_id: str, user=Depends(get_current_user)):
    uid = user["id"]
    _load_mission(mission_id, uid)
    res = (
        db.table("messages").select("*").eq("mission_id", mission_id)
        .order("created_at", desc=False).limit(500).execute()
    )
    msgs = res.data or []
    unread_ids = [m["id"] for m in msgs if m["receiver_id"] == uid and not m["read_at"]]
    if unread_ids:
        db.table("messages").update({"read_at": now_iso()}).in_("id", unread_ids).execute()
        for m in msgs:
            if m["id"] in unread_ids:
                m["read_at"] = now_iso()
    return msgs


@router.post("/chat/{mission_id}")
async def send_message(mission_id: str, body: MessageIn, user=Depends(get_current_user)):
    uid = user["id"]
    mission = _load_mission(mission_id, uid)
    if not (body.content or "").strip():
        raise HTTPException(status_code=400, detail="empty_message")
    receiver_id = mission["provider_id"] if mission["client_id"] == uid else mission["client_id"]

    ins = db.table("messages").insert({
        "mission_id": mission_id, "sender_id": uid, "receiver_id": receiver_id,
        "content": body.content.strip(),
    }).execute()
    msg = ins.data[0] if ins.data else None

    await notify(receiver_id, "chat_message", f"💬 {user.get('full_name', 'Nuovo messaggio')}",
                body.content.strip()[:120], "mission", mission_id)
    return msg
