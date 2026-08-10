"""Blocco 1 (migrazione Emergent -> Supabase/Render) — layer Postgres/Supabase
per i router già migrati (auth, onboarding).

I router non ancora migrati continuano a usare core.py (Mongo) finché la
riscrittura non è completa nei blocchi successivi del piano di migrazione
(vedi JOBBY_piano_migrazione_emergent_claude.md, sezione 4.5 — approccio
ibrido: le funzioni Postgres già esistenti nello schema storico (escrow,
payout, pricing, trust score) restano lì; il backend le richiama via RPC
invece di reimplementarle in Python).

ATTENZIONE: questo file NON sostituisce core.py — i due coesistono finché
tutti i router non sono stati migrati. Il deploy su Render, finché la
migrazione non è completa, richiede quindi sia MONGO_URL (per i router non
ancora migrati) sia SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY (per quelli già
migrati).
"""
import os
import math
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# Client "service role": bypassa la RLS. È sicuro usarlo qui perché ogni
# endpoint autorizza esplicitamente la richiesta a monte via
# deps_pg.get_current_user()/require_admin() prima di leggere o scrivere —
# stesso pattern già usato per DODO Service.
db: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

TREVISO = {"lat": 45.6669, "lng": 12.2433}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def haversine(lat1, lng1, lat2, lng2) -> float:
    """Distanza in km tra due punti — stessa formula di core.py (Mongo), copiata
    qui (non importata da core.py) perché questo modulo non deve dipendere da
    Mongo. Usata per il matching provider finché le scritture su
    profiles_provider.location (PostGIS) non sono verificate in produzione —
    vedi TODO in routers/onboarding.py (Blocco 1). Una volta che i provider
    hanno davvero una `location` valorizzata, i router di Blocco 2 dovrebbero
    passare a query PostGIS (ST_DWithin/ST_Distance, vedi la funzione SQL
    find_providers_nearby già esistente) invece di calcolare la distanza in
    Python su lat/lng letti a parte."""
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return float("inf")
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# Mappa tipo-notifica specifico di dominio (Mongo) -> valore più vicino
# nell'enum Postgres `notification_type`, che è chiuso e più generico
# (system, mission_request, mission_confirmed, mission_completed,
# mission_cancelled, payment_received, review_received, new_message,
# dispute_opened, dispute_resolved, kyc_update, trust_score_updated). Il
# messaggio vero e proprio resta in chiaro in title/body; `data` porta il
# tipo Mongo originale così il frontend può comunque distinguere i casi.
_NOTIF_TYPE_MAP = {
    "nuova_richiesta": "mission_request",
    "artigiani_invito": "mission_request",
    "artigiani_proposta": "mission_request",
    "artigiani_confermata": "mission_confirmed",
    "artigiani_accettato": "mission_confirmed",
    "artigiani_preventivo": "mission_request",
    "artigiani_extra": "mission_request",
    "artigiani_chiuso": "mission_completed",
    "artigiani_completata": "mission_completed",
    "artigiani_garanzia": "system",
    "artigiani_abilitazione": "kyc_update",
    "richiesta_invito": "mission_request",
    "richiesta_proposta": "mission_request",
    "richiesta_confermata": "mission_confirmed",
    "richiesta_completata": "mission_completed",
    "babysitting_proposta": "mission_request",
    "babysitting_invito": "mission_request",
    "babysitting_confermata": "mission_confirmed",
    "babysitting_incontro": "mission_request",
    "babysitting_annullata": "mission_cancelled",
    "babysitting_inizio": "mission_confirmed",
    "babysitting_fine": "mission_request",
    "babysitting_completata": "mission_completed",
    "babysitting_add_child": "mission_request",
    "babysitting_casellario": "kyc_update",
    "driver_invito": "mission_request",
    "driver_proposta": "mission_request",
    "driver_confermata": "mission_confirmed",
    "driver_annullata": "mission_cancelled",
    "driver_in_arrivo": "mission_confirmed",
    "driver_passeggero": "mission_request",
    "driver_extra": "mission_request",
    "driver_noshow": "system",
    "driver_completata": "mission_completed",
    "driver_auth": "kyc_update",
    # Blocco 4 (dispute/claims/chat)
    "claim_opened": "dispute_opened",
    "claim_escalated": "dispute_opened",
    "claim_dismissed": "dispute_resolved",
    "claim_resolved": "dispute_resolved",
    "dispute_resolved": "dispute_resolved",
    "chat_message": "new_message",
}


async def notify(user_id: str, kind: str, title: str, body: str, ref_type: str = "", ref_id: str = "") -> None:
    """Inserisce una notifica in public.notifications. Scritto nel Blocco 2
    per i router già migrati; il lato lettura/marcatura-come-letta è stato
    migrato a sua volta nel Blocco 4 (routers/notifications.py)."""
    if not user_id:
        return
    db.table("notifications").insert({
        "user_id": user_id,
        "type": _NOTIF_TYPE_MAP.get(kind, "system"),
        "title": title,
        "body": body,
        "data": {"kind": kind, "ref_type": ref_type, "ref_id": ref_id},
    }).execute()


# ---------------- trust score (Blocco 4) ----------------
# Il motore di calcolo (recalculate_trust_score / recalculate_client_trust_score)
# esisteva già nello schema Postgres storico (vedi piano di migrazione, sezione
# 4.5), con un trigger AFTER INSERT su trust_events/client_trust_events che lo
# richiama automaticamente — ma prima del Blocco 4 NESSUN router inseriva mai
# righe in quelle due tabelle, quindi il trigger non scattava mai e il
# punteggio restava sempre a 0 per chiunque, anche con recensioni/missioni
# reali. Questi due helper chiudono il cerchio: vanno richiamati nei punti del
# dominio dove succede qualcosa che deve incidere sul trust score (per ora:
# review() nelle 4 verticali, risoluzione dispute in routers/disputes.py).
#
# `delta`/`score_after` qui sono solo annotazioni per l'audit trail in
# trust_events/client_trust_events (colonne NOT NULL) — valori di primo
# calibraggio, non derivati dal modello Emergent originale (che usava un
# motore Python separato, non questo schema, e non è più disponibile per
# confronto). Il punteggio vero (profiles_provider.trust_score /
# profiles_client.trust_score) viene ricalcolato da zero dalla funzione SQL a
# partire dai dati reali (recensioni, dispute, kyc, ecc.), non da questi due
# campi: se le costanti sotto si rivelano scalate male, si possono correggere
# senza alcun impatto sui punteggi già calcolati.
def record_trust_event(provider_id: str, event_type: str, delta: float, dimension: str = "", notes: str = "") -> None:
    if not provider_id:
        return
    prov = db.table("profiles_provider").select("trust_score").eq("user_id", provider_id).limit(1).execute()
    before = float(prov.data[0]["trust_score"]) if prov.data and prov.data[0].get("trust_score") is not None else 0.0
    after = max(0.0, min(100.0, before + delta))
    db.table("trust_events").insert({
        "provider_id": provider_id, "event_type": event_type, "delta": delta,
        "score_before": before, "score_after": after, "dimension": dimension, "notes": notes,
    }).execute()


def record_client_trust_event(client_id: str, event_type: str, delta: float, dimension: str = "", notes: str = "") -> None:
    if not client_id:
        return
    cli = db.table("profiles_client").select("trust_score").eq("user_id", client_id).limit(1).execute()
    before = float(cli.data[0]["trust_score"]) if cli.data and cli.data[0].get("trust_score") is not None else 0.0
    after = max(0.0, min(100.0, before + delta))
    db.table("client_trust_events").insert({
        "client_id": client_id, "event_type": event_type, "delta": delta,
        "score_before": before, "score_after": after, "dimension": dimension, "notes": notes,
    }).execute()
