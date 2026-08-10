import random
import logging
from datetime import timedelta
from fastapi import FastAPI, APIRouter, Request
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from core import db, client, now_utc, new_id, MONGO_CONFIGURED
from catalog import seed_categories, BOT_PROVIDERS
from trust import recalc_provider_trust
from routers import auth, chat, business, onboarding, disputes, notifications, richieste, provider_onboarding, babysitting, driver, artigiani
from routers import spec4
from routers import listino
from routers import geo
from routers import stripe_connect
from routers import admin_users
import confirm_delivery

# BLOCCO 7 (migrazione Emergent -> Supabase/Render): 8 router Mongo-based mai
# migrati RITIRATI su conferma esplicita dell'utente (stesso trattamento già
# dato a missions.py/bookings.py nel Blocco 5) — wallet.py, admin_web.py,
# admin_auth.py, payments_stripe.py, payments_services.py, payments_paypal.py,
# catalog_routes.py, dashboard.py. Non più importati né esposti da questo
# file; restano nel repo con un docstring di ritiro come riferimento storico
# (vedi ciascun file). Nessun altro modulo del backend li importava (verificato
# con grep prima del ritiro), quindi nessuna altra modifica necessaria.

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="JOBBY API")

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(onboarding.router)
api.include_router(disputes.router)
api.include_router(notifications.router)
api.include_router(stripe_connect.router)
api.include_router(richieste.router)
api.include_router(babysitting.router)
api.include_router(driver.router)
api.include_router(artigiani.router)
api.include_router(spec4.router)
api.include_router(listino.router)
api.include_router(geo.router)
api.include_router(confirm_delivery.router)
api.include_router(provider_onboarding.router)
api.include_router(admin_users.router)
# missions.py/bookings.py (motore di matching generico pre-Blocco2, con
# provider "bot" simulati) RITIRATI nel Blocco 5 — decisione esplicita
# dell'utente: le 4 verticali (Pulizie/Artigiani/Babysitting/Driver, Blocco
# 2-4) coprono già gli stessi casi d'uso con flussi dedicati più ricchi e un
# vero escrow Stripe Connect; questo motore generico sarebbe rimasto
# duplicato e mai aggiornato. I file restano nel repo per riferimento
# storico ma non sono più importati né esposti — vedi il loro docstring.
api.include_router(chat.router)
api.include_router(business.router)
app.include_router(api)

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def demo_readonly_guard(request: Request, call_next):
    """Demo accounts can browse but cannot perform write actions (except auth).

    Blocco 1 (fix): se MONGO_URL non è configurato, questo controllo va
    saltato del tutto — `db.user_sessions` è un concetto del vecchio sistema
    di sessioni Mongo-based, non esiste per gli utenti Supabase Auth del
    Blocco 1, e senza Mongo raggiungibile la query qui sotto si limiterebbe
    ad appendere/fallire su ogni singola richiesta POST (inclusa
    /api/onboarding/complete, che è già Postgres e non ha nulla a che fare
    col concetto di account demo)."""
    path = request.url.path
    if MONGO_CONFIGURED and request.method not in SAFE_METHODS and path.startswith("/api/") and not path.startswith("/api/auth/"):
        authz = request.headers.get("authorization", "")
        if authz.startswith("Bearer "):
            token = authz.split(" ", 1)[1]
            session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0, "user_id": 1})
            if session:
                u = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "is_demo": 1})
                if u and u.get("is_demo"):
                    return JSONResponse(status_code=403, content={"detail": "demo_readonly"})
    return await call_next(request)


@app.on_event("startup")
async def startup():
    # Blocco 1 (fix): con MONGO_URL non configurato (scelta dell'utente: niente
    # Mongo nemmeno temporaneo, si va dritti su Supabase) saltiamo tutto
    # l'init/seed Mongo qui sotto — altrimenti il server non parte nemmeno per
    # testare le route Postgres già migrate (auth/onboarding, Blocco 1). I
    # router non ancora migrati (missions, wallet, chat, ecc.) restano quindi
    # non funzionanti finché non vengono riscritti per Postgres nei prossimi
    # blocchi — è lo stato ibrido già documentato nel piano di migrazione, non
    # una novità introdotta da questo fix.
    if not MONGO_CONFIGURED:
        logger.warning(
            "MONGO_URL non configurato: salto init/seed MongoDB all'avvio. "
            "Le route Postgres del Blocco 1 (/api/auth/*, /api/onboarding/*) "
            "funzionano; tutte le altre route (ancora Mongo-based) no."
        )
        return
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.categories.create_index("cat_id", unique=True)
    await seed_categories()
    # `admin_sessions`/`admin_auth.seed_admin()` rimossi nel Blocco 7 —
    # admin_auth.py è stato ritirato (vedi sopra), non serve più seedare
    # l'admin Mongo-based.
    # Existing users (pre-onboarding feature) should not be forced through onboarding.
    await db.users.update_many({"onboarding_completed": {"$exists": False}}, {"$set": {"onboarding_completed": True}})
    # Wallet: ensure the blocked/pending balance field exists.
    await db.users.update_many({"pending_balance": {"$exists": False}}, {"$set": {"pending_balance": 0.0}})
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
    # Seed Pulizie listini on bot cleaning providers (alternate binario for both tracks).
    idx = 0
    for p in await db.users.find({"services": "pulizie", "pulizie_listino": {"$exists": False}}, {"_id": 0, "user_id": 1, "hourly_rate": 1}).to_list(100):
        binario = "impresa" if idx % 2 == 0 else "persona_lf"
        rate = p.get("hourly_rate", 14.0)
        listino = {
            "binario": binario,
            "tariffa_ordinaria": rate, "tariffa_afondo": round(rate + 3, 2), "tariffa_posttrasloco": round(rate + 6, 2),
            "prodotti_propri": True, "supplemento_prodotti": 5.0,
            "extra": {"forno": 10.0, "frigo": 8.0, "finestre": 15.0, "balconi": 12.0},
            "stiro_ora": 12.0, "sconto_ricorrenza_pct": 10.0, "raggio_km": 20.0, "minimo_ore": 2,
        }
        await db.users.update_one({"user_id": p["user_id"]}, {"$set": {"pulizie_binario": binario, "pulizie_listino": listino}})
        idx += 1
    if idx:
        logger.info("Seeded pulizie listini on %d providers", idx)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
