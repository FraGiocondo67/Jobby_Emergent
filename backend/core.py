import os
import math
import uuid
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
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
