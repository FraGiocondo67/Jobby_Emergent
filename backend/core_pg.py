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
}


async def notify(user_id: str, kind: str, title: str, body: str, ref_type: str = "", ref_id: str = "") -> None:
    """Inserisce una notifica in public.notifications. Solo insert — la lettura/
    marcatura-come-letta resta nel router notifications.py (Mongo) finché non
    viene migrato (Blocco 4); questo helper serve ai router di Blocco 2 che
    hanno bisogno di notificare senza aspettare quella migrazione."""
    if not user_id:
        return
    db.table("notifications").insert({
        "user_id": user_id,
        "type": _NOTIF_TYPE_MAP.get(kind, "system"),
        "title": title,
        "body": body,
        "data": {"kind": kind, "ref_type": ref_type, "ref_id": ref_id},
    }).execute()
