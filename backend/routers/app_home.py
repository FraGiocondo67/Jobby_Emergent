"""BLOCCO 9 (fix bug mobile "app che apre ma manca tutto") - due endpoint che
la app Expo chiama da sempre (src/api.ts: api.wallet()/api.homeState(), letti
dalla home in app/(tabs)/index.tsx dentro un Promise.all) ma che non sono mai
esistiti su Postgres: esistevano solo come router Mongo-based (routers/
wallet.py, routers/dashboard.py) RITIRATI nel Blocco 7 e mai ricostruiti -
dashboard.py lo diceva esplicitamente nel proprio docstring di ritiro
("l'equivalente lato app... va ricostruito sopra le tabelle Postgres se/
quando serve, non riportato qui"). Il Promise.all falliva quindi sempre (404
su entrambi), il catch{} silenzioso della home lasciava tiles/wallet/home
vuoti - la app sembrava "senza funzioni" anche a categorie correttamente
popolate.

Scope DELIBERATO di questo fix: solo i campi davvero letti dal codice
frontend attuale (verificato via grep), non l'intera ricchezza del vecchio
wallet_dashboard Mongo-based (borsellino Libretto Famiglia, limiti di legge,
recupero fiscale...) - quella e' UI di un modello "wallet interno" che il
Blocco 3 ha esplicitamente deciso di NON riproporre (vedi stripe_pg.py:
"NESSUN fallback a wallet interno", solo Stripe Connect reale). Le schermate
che leggono ancora campi di quel vecchio modello (payments-settings.tsx,
wallet.tsx, pay/*.tsx: payment_method/bank_account/crypto_wallets/
paypal_email, e portafoglio.tsx: api.walletDashboard()) restano quindi con
placeholder onesti (null/vuoto) qui sotto - servono una decisione di prodotto
su cosa sostituisce quella UI nel nuovo modello Stripe-Connect-only, non
solo una riscrittura tecnica: NON coperte da questo fix, segnalate
all'utente a parte."""
from typing import Optional

from fastapi import APIRouter, Depends

from core_pg import db
from deps_pg import get_current_user

router = APIRouter()

ACTIVE_REL_STATES = ("confermata", "in_corso", "completata", "recensita")


@router.get("/providers/nearby")
async def providers_nearby(lat: float, lng: float, category: Optional[str] = None,
                            radius: Optional[float] = None, user=Depends(get_current_user)):
    """BLOCCO 9 (fix "cerca attorno a te... non rileva nessun provider o
    attività di prossimità"): app/map.tsx chiama questa route da sempre, ma
    esisteva solo nel motore di matching generico Mongo-based (routers/
    missions.py), RITIRATO nel Blocco 5 e mai importato da questo server —
    404 garantito, ingoiato dal catch{} della mappa, quindi "nessun
    risultato" indipendentemente da quanti provider/attività online ci
    fossero davvero nel raggio.

    Usa la funzione SQL `nearby_providers` già presente nel progetto
    Supabase (PostGIS ST_Distance/ST_DWithin su profiles_provider.location,
    filtro kyc_status='approved' incluso nella funzione stessa) invece di
    ricalcolare la distanza in Python: a differenza delle 4 verticali dedicate
    (Pulizie/Babysitting/Driver/Artigiani, che usano ancora l'haversine
    Python di core_pg.py perché operano su missions.location non sempre
    popolata), qui la posizione del provider è proprio il dato che stiamo
    cercando quindi ha senso appoggiarsi a PostGIS. Non filtra per
    availability_status nella RPC stessa (restituisce anche gli offline):
    filtrato qui perché la vecchia semantica Mongo (routers/missions.py)
    mostrava solo provider online, stessa aspettativa della UI (legenda
    mappa: "provider online")."""
    radius_km = radius if radius is not None else 10
    try:
        res = db.rpc("nearby_providers", {
            "p_lat": lat, "p_lng": lng, "p_radius_km": radius_km, "p_skill": category,
        }).execute()
    except Exception:
        return []
    rows = [r for r in (res.data or []) if r.get("availability_status") == "online"]
    if not rows:
        return []
    ids = [r["user_id"] for r in rows]
    extra = db.table("profiles_provider").select("user_id, is_proximity_business, business_data").in_("user_id", ids).execute()
    extra_map = {e["user_id"]: e for e in (extra.data or [])}
    out = []
    for r in rows:
        e = extra_map.get(r["user_id"]) or {}
        is_biz = bool(e.get("is_proximity_business"))
        biz = e.get("business_data") or {}
        out.append({
            "user_id": r["user_id"],
            "role": "business" if is_biz else "provider",
            "name": r.get("full_name") or "",
            "business_name": (biz.get("business_name") or "") if is_biz else None,
            "picture": (biz.get("photo") if is_biz else None) or r.get("avatar_url"),
            "lat": r.get("latitude"), "lng": r.get("longitude"),
            "distance_km": round(r.get("distance_km") or 0, 1),
            "services": r.get("skills") or [],
            "rating": r.get("avg_rating") or 0,
            "trust_score": r.get("trust_score") or 0,
            "hourly_rate": r.get("hourly_rate") or 0,
            # La RPC filtra già kyc_status='approved' nella WHERE — chi
            # arriva qui è per definizione approvato.
            "online": True,
            "approval_status": "approved",
        })
    return out


@router.get("/providers/{provider_id}/public")
async def provider_public(provider_id: str, user=Depends(get_current_user)):
    """BLOCCO 9 (fix "seleziono un provider da 'cerca intorno a te' -> pagina
    bianca con 'Errore'"): app/provider/[id].tsx chiama api.providerPublic()
    da sempre (src/api.ts: GET /providers/{id}/public), ma la route esisteva
    SOLO nel motore Mongo-based di routers/missions.py — stesso file RITIRATO
    nel Blocco 5 di /providers/nearby (vedi sopra) e mai importato da questo
    server: 404 garantito, ingoiato dal catch{} dello useEffect, p resta
    null -> `if (!p) return ... {t("error")}` -> esattamente lo schermo
    bianco con "Errore" segnalato. Bug presente per QUALSIASI provider
    selezionato dalla mappa (non solo per "pulizie"), perché la route
    mancava a monte per tutti.

    Ricostruita sullo schema Postgres corrente: profiles_provider ha già
    tutti i campi che la card provider legge (bio/skills/hourly_rate/
    avg_rating/kyc_status/is_proximity_business/business_data); le
    recensioni vengono dalla tabella `reviews` (scritta da review() nelle 4
    verticali Pulizie/Babysitting/Driver/Artigiani, vedi routers/
    richieste.py) filtrate per reviewee_id, stesso pattern già in uso per
    l'admin (routers/spec4.py, admin_reviews_pending). `categoria` per
    singola recensione (presente nella vecchia risposta Mongo) omesso: non
    esiste un join diretto recensione->categoria nello schema Postgres
    attuale (reviews non ha una colonna categoria, solo mission_id) e la UI
    (app/provider/[id].tsx) già gestisce la sua assenza (mostra la stella
    senza il tag categoria)."""
    urow = db.table("users").select("id, full_name, avatar_url, role").eq("id", provider_id).limit(1).execute()
    if not urow.data:
        raise HTTPException(status_code=404, detail="provider_not_found")
    u = urow.data[0]

    pp_row = db.table("profiles_provider").select(
        "bio, skills, hourly_rate, availability_status, avg_rating, trust_score, "
        "kyc_status, is_proximity_business, business_data"
    ).eq("user_id", provider_id).limit(1).execute()
    if not pp_row.data:
        raise HTTPException(status_code=404, detail="provider_not_found")
    pp = pp_row.data[0]

    is_biz = bool(pp.get("is_proximity_business"))
    biz = pp.get("business_data") or {}

    reviews_res = (
        db.table("reviews")
        .select("rating, comment, reply, created_at")
        .eq("reviewee_id", provider_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    reviews = [
        {"rating": r.get("rating"), "comment": r.get("comment"), "reply": r.get("reply"), "at": r.get("created_at")}
        for r in (reviews_res.data or [])
        if r.get("rating")
    ]

    return {
        "user_id": provider_id,
        "name": u.get("full_name") or "",
        "business_name": (biz.get("business_name") or "") if is_biz else "",
        "picture": (biz.get("photo") if is_biz else None) or u.get("avatar_url") or "",
        "role": "business" if is_biz else "provider",
        "bio": pp.get("bio") or "",
        "address": biz.get("address") or "",
        "services": pp.get("skills") or [],
        "rating": pp.get("avg_rating") or 0,
        "reviews_count": len(reviews),
        "reviews": reviews,
        "trust_score": pp.get("trust_score") or 0,
        "hourly_rate": pp.get("hourly_rate") or 0,
        "online": pp.get("availability_status") == "online",
        "verified": pp.get("kyc_status") == "approved",
        "approval_status": pp.get("kyc_status") or "approved",
        "business_photos": biz.get("photos") or [],
    }


@router.get("/trust")
async def trust_score(user=Depends(get_current_user)):
    """BLOCCO 9 (fix card "Affidabilità" sempre vuota in Profilo): stessa
    causa dei fix sopra — GET /trust esisteva solo in routers/bookings.py,
    RITIRATO nel Blocco 5 insieme a missions.py, mai importato da questo
    server (404 sempre, osservato live nei log Render). I punteggi reali
    esistono già come colonne su profiles_client/profiles_provider (scritte
    da trust.py legacy Mongo mai riportato qui, o dai default della riga) —
    questo endpoint si limita a esporle in lettura nella forma che
    app/(tabs)/profile.tsx si aspetta ({provider_score,provider_subscores,
    client_score,client_subscores}), non le ricalcola."""
    cp = db.table("profiles_client").select(
        "trust_score, trust_score_identity, trust_score_education, "
        "trust_score_brief_accuracy, trust_score_payment_punctuality, "
        "trust_score_cancellation, trust_score_tips, trust_score_reviews"
    ).eq("user_id", user["id"]).limit(1).execute()
    pp = db.table("profiles_provider").select(
        "trust_score, trust_score_kyc, trust_score_punctuality, "
        "trust_score_quality, trust_score_communication, trust_score_cancellation"
    ).eq("user_id", user["id"]).limit(1).execute()
    c = cp.data[0] if cp.data else {}
    p = pp.data[0] if pp.data else {}
    return {
        "client_score": c.get("trust_score") or 0,
        "client_subscores": {k: v for k, v in c.items() if k != "trust_score" and v is not None},
        "provider_score": p.get("trust_score") or 0,
        "provider_subscores": {k: v for k, v in p.items() if k != "trust_score" and v is not None},
    }


@router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    """Placeholder honesto: nel modello Stripe-Connect-only (Blocco 3) non
    esiste un saldo wallet interno per il cliente - paga ad ogni richiesta
    con la carta salvata (SetupIntent, vedi /pay/setup-card). balance=0 e'
    quindi lo stato corretto, non un dato mancante. payment_method rispecchia
    la carta salvata se presente; gli altri campi (bank_account/
    crypto_wallets/paypal_email) sono residui del vecchio modello Mongo e non
    hanno equivalente Postgres - vedi docstring del modulo."""
    row = db.table("users").select("default_payment_method_id").eq("id", user["id"]).limit(1).execute()
    has_card = bool(row.data and row.data[0].get("default_payment_method_id"))
    return {
        "balance": 0.0,
        "pending": 0.0,
        "payment_method": "card" if has_card else None,
        "bank_account": None,
        "crypto_wallets": [],
        "paypal_email": "",
    }


@router.get("/home/state")
async def home_state(user=Depends(get_current_user)):
    """Versione Postgres minimale del vecchio /home/state Mongo (routers/
    dashboard.py, ritirato Blocco 7): stesso contratto {state, relationships}
    - state="recurring" se il cliente ha almeno una richiesta gia' completata
    in una delle 4 verticali (Pulizie/Babysitting/Driver/Artigiani, tutte
    righe di public.missions con lo stato nel jsonb brief_answers.stato, vedi
    routers/richieste.py). relationships lasciato vuoto: verificato via grep
    che nessuna schermata della app lo legge oggi (la card "prossimo
    provider" del vecchio dashboard.py non e' mai stata portata sul nuovo
    frontend Expo) - solo home.state e' davvero consumato (app/(tabs)/
    index.tsx, per nascondere/mostrare la card fiducia e il tile Pulizie
    ripetuto)."""
    res = (
        db.table("missions")
        .select("brief_answers")
        .eq("client_id", user["id"])
        .execute()
    )
    has_completed = any(
        (m.get("brief_answers") or {}).get("stato") in ("completata", "recensita")
        for m in (res.data or [])
    )
    return {"state": "recurring" if has_completed else "new", "relationships": []}
