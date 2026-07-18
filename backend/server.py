import random
import logging
from datetime import timedelta
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core import db, client, now_utc, new_id
from catalog import seed_categories, BOT_PROVIDERS
from trust import recalc_provider_trust
from routers import auth, catalog_routes, missions, bookings, wallet, chat, admin_web, business

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="JOBBY API")

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(catalog_routes.router)
api.include_router(missions.router)
api.include_router(bookings.router)
api.include_router(wallet.router)
api.include_router(chat.router)
api.include_router(business.router)
api.include_router(admin_web.router)
app.include_router(api)

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.categories.create_index("cat_id", unique=True)
    await seed_categories()
    if await db.users.count_documents({"is_bot": True}) == 0:
        for i, (name, services, rate, rating, reviews, lat, lng) in enumerate(BOT_PROVIDERS):
            await db.users.insert_one({
                "user_id": new_id("prov"), "email": f"provider{i}@jobby.demo", "name": name,
                "picture": f"https://i.pravatar.cc/200?u=jobby{i}", "role": "provider", "language": "it",
                "bio": "Professionista verificato, con esperienza e assicurazione inclusa.", "business_name": "",
                "hourly_rate": rate, "radius_km": 15.0, "services": services, "online": True, "rating": rating,
                "reviews_count": reviews, "verified": True, "verification_status": "verified", "wallet_balance": 0.0,
                "payment_method": None, "bank_account": None, "trust_score": 0.0, "trust_subscores": {},
                "client_trust_score": 0.0, "client_trust_subscores": {}, "is_admin": False, "is_bot": True,
                "lat": lat, "lng": lng, "created_at": (now_utc() - timedelta(days=random.randint(60, 400))).isoformat()})
        logger.info("Seeded bot providers")
    for p in await db.users.find({"is_bot": True}, {"_id": 0, "user_id": 1}).to_list(100):
        await recalc_provider_trust(p["user_id"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
