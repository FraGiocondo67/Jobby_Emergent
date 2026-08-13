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
from fastapi import APIRouter, Depends

from core_pg import db
from deps_pg import get_current_user

router = APIRouter()

ACTIVE_REL_STATES = ("confermata", "in_corso", "completata", "recensita")


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
