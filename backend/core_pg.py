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
