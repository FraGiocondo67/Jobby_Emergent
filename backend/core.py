import os
import math
import uuid
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Blocco 1 (fix): MONGO_URL/DB_NAME letti con .get() invece che con
# indicizzazione diretta. L'utente ha deciso di NON procurarsi un Mongo
# (nemmeno temporaneo) solo per far partire il server in locale, dato che la
# direzione è comunque abbandonare Mongo per Supabase — quindi questo modulo
# (e tutti i router non ancora migrati che lo importano) deve poter essere
# IMPORTATO senza MONGO_URL configurato. `AsyncIOMotorClient` non si connette
# davvero finché non arriva la prima query (client Mongo lazy), quindi crearlo
# con un URL segnaposto non fallisce qui: fallirà solo se/quando un router
# Mongo-based riceve davvero una richiesta. MONGO_CONFIGURED lo espone a
# server.py per saltare l'init/seed Mongo nello startup (vedi lì).
MONGO_CONFIGURED = bool(os.environ.get('MONGO_URL'))
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'jobby_unconfigured')]
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'change-me')

TREVISO = {"lat": 45.6669, "lng": 12.2433}
EMERGENT_SESSION_URL = os.environ.get(
    "EMERGENT_SESSION_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)


def now_utc():
    return datetime.now(timezone.utc)


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def L(it, en):
    return {"it": it, "en": en}


def haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)
