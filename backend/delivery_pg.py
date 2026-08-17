"""BLOCCO 10 — porting Postgres del layer di conferma "QR / codice a 6
cifre" per la liberazione del pagamento a fine servizio.

Il vecchio confirm_delivery.py (root del backend, ancora montato su
server.py) implementa esattamente questa funzione ma su Mongo (`from core
import db`, MONGO_URL non configurato su questo deploy — vedi core.py) e
contro le collezioni pre-migrazione `richieste`/`business_requests`: ogni
sua query si blocca/fallisce nel deploy attuale. Il frontend però è GIA'
interamente pronto e collegato (src/components/DeliveryConfirm.tsx —
ClientDeliveryQR + EarnerConfirm, usati da pulizie/babysitting/driver/
artigiani/[id].tsx, (tabs)/richieste.tsx, (tabs)/index.tsx — tutti leggono
già `r.conferma_pending` e chiamano già /delivery/ref, /delivery/status,
/delivery/confirm, /delivery/confirm-code) — stesso pattern ricorrente di
questa migrazione: frontend pronto, backend mai portato.

Design invariato dal vecchio modulo, solo il layer dati è Postgres e la
liberazione del pagamento non è più un generico wallet_escrow.py (Mongo)
ma la funzione di rilascio GIA' esistente e testata di ciascuna verticale
(Stripe transfer_to_provider per binario impresa, nessuna azione gateway
per persona_lf — vedi routers/richieste.py, babysitting.py, driver.py,
artigiani.py) — questo modulo fa solo da gate PRIMA di eseguirla, non la
duplica. Ogni router registra la propria funzione di rilascio con
register_releaser(kind, fn) al momento dell'import (fn: async def(ref_id)
-> None, deve fare TUTTO quello che serve: rilascio soldi + stato +
notifiche — arm_or_release() non tocca nient'altro).

Due modalità:
- mandatory=True (le verticali con pagamento reale in piattaforma —
  Pulizie, Babysitting, Driver, Artigiani della casa, come da decisione
  esplicita dell'utente): arma SEMPRE, ignora la preferenza del cliente.
- mandatory=False (attività di prossimità/ordini da listino, come da
  decisione esplicita dell'utente): guarda users.qr_confirm_enabled del
  cliente — se spento, rilascia subito come oggi.

Auto-release dopo 24h se il provider non scansiona mai (stessa policy del
vecchio modulo Mongo) — applicato lazy da /delivery/status e /delivery/mine
in routers/delivery.py, non serve un cron dedicato.
"""
import random
import secrets
from datetime import timedelta
from typing import Awaitable, Callable, Optional

from core_pg import db, now_iso, now_utc, notify

CONFIRM_TTL_HOURS = 24

_RELEASERS: dict[str, Callable[[str], Awaitable[None]]] = {}


def register_releaser(kind: str, fn: Callable[[str], Awaitable[None]]) -> None:
    _RELEASERS[kind] = fn


def _qr_enabled(client_id: str) -> bool:
    row = db.table("users").select("qr_confirm_enabled").eq("id", client_id).limit(1).execute()
    return bool(row.data and row.data[0].get("qr_confirm_enabled"))


def get_active_confirmation(ref_id: str) -> Optional[dict]:
    row = (
        db.table("delivery_confirmations").select("*")
        .eq("ref_id", ref_id).eq("released", False).limit(1).execute()
    )
    return row.data[0] if row.data else None


async def arm_or_release(kind: str, ref_id: str, client_id: str, earner_id: str,
                          label: str, mandatory: bool) -> dict:
    """Chiamata dal complete()/finalize di ciascuna verticale al posto del
    rilascio diretto. Se non deve armare, esegue subito il releaser
    registrato per `kind` e ritorna {"armed": False}. Altrimenti crea (o
    riusa, se già presente) la conferma pendente e ritorna {"armed": True}."""
    if not mandatory and not _qr_enabled(client_id):
        releaser = _RELEASERS.get(kind)
        if releaser:
            await releaser(ref_id)
        return {"armed": False}

    existing = get_active_confirmation(ref_id)
    if existing:
        return {"armed": True, "deadline": existing["deadline"]}

    token = secrets.token_urlsafe(18)
    code = f"{random.randint(0, 999999):06d}"
    deadline = (now_utc() + timedelta(hours=CONFIRM_TTL_HOURS)).isoformat()
    db.table("delivery_confirmations").insert({
        "token": token, "code": code, "kind": kind, "ref_id": ref_id,
        "client_id": client_id, "earner_id": earner_id, "label": label,
        "deadline": deadline,
    }).execute()
    await notify(client_id, "consegna_conferma", "Conferma consegna",
                "Mostra il tuo QR (o il codice) al professionista per liberare il pagamento.",
                kind, ref_id)
    return {"armed": True, "deadline": deadline}


async def _do_release(conf: dict) -> None:
    if conf.get("released"):
        return
    releaser = _RELEASERS.get(conf["kind"])
    if releaser:
        await releaser(conf["ref_id"])
    db.table("delivery_confirmations").update({
        "released": True, "released_at": now_iso(),
    }).eq("id", conf["id"]).execute()


async def confirm_by_token(token: str, earner_id: str) -> dict:
    row = db.table("delivery_confirmations").select("*").eq("token", token).eq("released", False).limit(1).execute()
    if not row.data:
        raise ValueError("not_found")
    conf = row.data[0]
    if conf["earner_id"] != earner_id:
        raise PermissionError("not_your_delivery")
    db.table("delivery_confirmations").update({"verified": True, "verified_at": now_iso()}).eq("id", conf["id"]).execute()
    await _do_release(conf)
    await notify(conf["client_id"], "consegna_confermata", "Consegna confermata",
                "Il pagamento è stato liberato. Grazie!", conf["kind"], conf["ref_id"])
    return {"confirmed": True}


async def confirm_by_code(ref_id: str, code: str, earner_id: str) -> dict:
    row = db.table("delivery_confirmations").select("*").eq("ref_id", ref_id).eq("released", False).limit(1).execute()
    if not row.data:
        raise ValueError("not_found")
    conf = row.data[0]
    if conf["earner_id"] != earner_id:
        raise PermissionError("not_your_delivery")
    if (code or "").strip() != conf["code"]:
        raise ValueError("invalid_code")
    db.table("delivery_confirmations").update({"verified": True, "verified_at": now_iso()}).eq("id", conf["id"]).execute()
    await _do_release(conf)
    await notify(conf["client_id"], "consegna_confermata", "Consegna confermata",
                "Il pagamento è stato liberato. Grazie!", conf["kind"], conf["ref_id"])
    return {"confirmed": True}


async def auto_release_expired(ref_id: str) -> None:
    """Rilascia una conferma scaduta (24h) senza scansione — chiamata lazy
    da GET /delivery/status e /delivery/mine, nessun cron dedicato."""
    conf = get_active_confirmation(ref_id)
    if conf and conf["deadline"] <= now_iso():
        await _do_release(conf)
