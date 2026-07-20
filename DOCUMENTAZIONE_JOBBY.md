# 📘 JOBBY — Documentazione Architettura & Gestione

> Guida per capire com'è strutturata l'app, dove vivono i dati, come gestire il
> backend e — soprattutto — **perché a volte vedi errori e disallineamenti tra
> backend e MongoDB**.

---

## 1. Panoramica dell'architettura

JOBBY è un'app **full-stack** composta da 3 pezzi:

```
┌──────────────────────┐      HTTPS /api/*      ┌──────────────────────┐        ┌──────────────┐
│  FRONTEND (Expo/RN)  │  ───────────────────▶  │  BACKEND (FastAPI)   │  ────▶  │   MongoDB     │
│  React Native + Web  │                        │  Python · porta 8001 │        │  (database)   │
│  (app store + web)   │  ◀───────────────────  │  tutte le rotte /api │        │               │
└──────────────────────┘        JSON            └──────────────────────┘        └──────────────┘
```

- **Frontend**: Expo (React Native). Stesso codice gira su **iOS/Android** (build native) e su **web** (Metro bundler). Routing "file-based" con `expo-router`: ogni file in `/app/frontend/app/*` è una schermata.
- **Backend**: **FastAPI** (Python). Gira sempre su `0.0.0.0:8001`. **Tutte** le API iniziano con `/api`. La UI admin è servita da qui (`/api/admin/ui`).
- **Database**: **MongoDB**. Unico database dell'app. Nome database preso da variabile d'ambiente `DB_NAME`.

Il frontend NON parla mai direttamente con Mongo: passa **sempre** dal backend.

---

## 2. Struttura delle cartelle

```
/app
├── backend/                      # FastAPI (Python)
│   ├── server.py                 # entrypoint: registra tutti i "router"
│   ├── core.py                   # connessione MongoDB + utility (db, now_utc…)
│   ├── catalog.py                # SEED delle categorie/servizi (fonte di verità!)
│   ├── escrow.py, dispute_ai.py  # logica pagamenti in garanzia + AI dispute
│   ├── *_config.py               # configuratori (pulizie, babysitting, driver, artigiani)
│   ├── .env                      # MONGO_URL, DB_NAME, chiavi (NON modificare a mano)
│   └── routers/                  # un file per area funzionale
│       ├── auth.py               # registrazione/login (email + Google)
│       ├── admin_web.py          # UI + API pannello admin
│       ├── richieste.py          # Pulizie
│       ├── babysitting.py, driver.py, artigiani.py
│       ├── payments_split.py     # pagamenti reali split (Stripe/PayPal)
│       ├── payments_connect/stripe/paypal.py
│       ├── wallet.py, dashboard.py, spec4.py, chat.py …
│
├── frontend/                     # Expo (React Native)
│   ├── app/                      # SCHERMATE (routing per file)
│   │   ├── (tabs)/               # Home, Attività, Portafoglio, Profilo
│   │   ├── pulizie/ babysitting/ driver/ artigiani/   # flussi per categoria
│   │   ├── onboarding.tsx, activities.tsx, payments-settings.tsx …
│   ├── src/                      # codice NON-schermata
│   │   ├── api.ts                # tutte le chiamate al backend
│   │   ├── i18n.ts               # testi IT/EN
│   │   ├── context/              # AuthContext, LanguageContext
│   │   └── components/           # componenti riusabili (PaymentSection…)
│   └── .env                      # EXPO_PUBLIC_BACKEND_URL (NON modificare)
│
└── memory/                       # PRD.md, credenziali di test
```

---

## 3. Dove sono i dati (collezioni MongoDB)

Tutti i dati stanno in **una** base dati Mongo. Collezioni principali:

| Collezione | Cosa contiene |
|---|---|
| `users` | Utenti (client, provider, business): ruolo, stato approvazione, wallet, KYC |
| `user_sessions` | Token di sessione (login attivi) |
| `categories` | Categorie servizi (Pulizie, Babysitting, Driver, Artigiani…) + `active` |
| `richieste` | **Tabella centrale** di tutte le richieste servizio (tutte le categorie) |
| `bookings` | Prenotazioni legacy / escrow |
| `payment_transactions` | Pagamenti (Stripe/PayPal/simulati) e split |
| `transactions` | Movimenti wallet (ricariche, compensi, rimborsi) |
| `wallet_holds`, `payouts` | Fondi in garanzia e pagamenti ai provider |
| `disputes` | Contestazioni + raccomandazione AI |
| `reviews`, `trust_events`, `client_trust_events` | Recensioni e Trust Score |
| `child_cards` | Schede bambini (babysitting) — es. campo `eta_mesi`, `family_id` |
| `conversations`, `messages` | Chat |
| `notifications` | Notifiche in-app |
| `settings` | Regole/soglie (fee, strike, cooldown) |

> La categoria è **attiva** se `active: true`. La lista canonica delle categorie
> è definita in `backend/catalog.py` (funzione `seed_categories`).

---

## 4. ⚠️ I DUE AMBIENTI: Preview vs Produzione (Deployed)

**Questa è la causa numero 1 dei disallineamenti che hai notato.**

Esistono **due installazioni separate** dell'app, ognuna con **il suo database Mongo**:

| | PREVIEW (sviluppo) | PRODUZIONE (Deployed / Apple / TestFlight) |
|---|---|---|
| Chi la usa | Io (agente) mentre sviluppo; tu dal browser di anteprima | I tuoi utenti reali dall'app pubblicata / TestFlight |
| URL backend | `…preview.emergentagent.com` | URL del deploy pubblicato |
| **Database Mongo** | **DB di preview** (`test_database`) | **DB di produzione (separato!)** |
| Aggiornato quando | Sempre all'ultima versione del codice | Solo quando fai **Publish/Deploy** |

### Perché "gli ultimi utenti registrati non appaiono nel backend"
- Gli utenti **Overland doo / IT FIRE / Antonio Briguglio** si sono registrati **dall'app Apple** → sono finiti nel **DB di PRODUZIONE**.
- Il pannello admin che stavi guardando è quello di **PREVIEW** → legge il **DB di PREVIEW**, dove quei 3 utenti **non esistono**.
- Ho verificato: nel DB di preview ci sono **36 utenti**, e quei 3 email **non sono presenti**. Quindi non è un bug del codice: stai guardando **due database diversi**.

### Cosa fare
- Per vedere gli utenti **reali/produzione** → usa il pannello admin **dell'URL di produzione** (`https://<url-deploy>/api/admin/ui`), oppure collega il tuo visualizzatore Mongo al **DB di produzione**.
- Per vedere i dati di **preview** → pannello admin dell'URL di **preview**.
- **Non mischiare** i due: sono ambienti indipendenti, come "brutta copia" e "bella copia".

> Analogamente, categorie attivate/disattivate o prenotazioni "demo" fatte in
> preview **NON** si trasferiscono in produzione: la produzione parte dal **seed**
> (`catalog.py`) + dai dati reali dei tuoi utenti.

---

## 5. Perché "il backend va in errore" (404 / 502)

Le cause tipiche, in ordine di frequenza:

1. **Backend in riavvio durante lo sviluppo.** Ogni volta che modifico il codice riavvio il backend (`supervisorctl restart backend`). Per ~2–5 secondi le richieste possono rispondere **404/502**. Riprovando dopo qualche secondo funziona. La 404 su `/api/admin/ui` che hai visto rientra quasi sicuramente qui: **ora quella pagina risponde 200** (verificato).
2. **URL sbagliato o ambiente sbagliato.** `/api/admin/ui` esiste solo sul backend; se lo apri sull'URL di produzione ma il deploy è vecchio, può dare 404. Verifica sempre di essere sull'URL giusto (preview vs produzione).
3. **Sessione scaduta (401).** Se il token di login è scaduto, le API rispondono 401. (Abbiamo appena aggiunto la gestione: l'app ti riporta al login invece di andare in crash.)
4. **Deploy con versione vecchia.** Se il Publish pubblica uno snapshot vecchio, il backend di produzione gira codice datato → comportamenti diversi dal preview.

### Come diagnosticare velocemente
- Stato servizi: `sudo supervisorctl status`
- Log backend: `/var/log/supervisor/backend.err.log` e `backend.out.log`
- Test rapido "è vivo?": aprire `…/api/admin/ui` → deve dare la pagina admin.

---

## 6. Come gestire il backend

| Azione | Comando |
|---|---|
| Riavviare il backend | `sudo supervisorctl restart backend` |
| Riavviare il frontend (Expo) | `sudo supervisorctl restart expo` |
| Stato di tutti i servizi | `sudo supervisorctl status` |
| Log backend (errori) | `tail -f /var/log/supervisor/backend.err.log` |
| Pannello Admin (web) | apri `https://<url>/api/admin/ui` e incolla l'**Admin Token** |

- **Admin Token**: si trova in `backend/.env` (variabile `ADMIN_TOKEN`). Serve per
  entrare nel pannello admin e per le API admin (header `X-Admin-Token`).
- **Non** modificare a mano `MONGO_URL`, `DB_NAME`, `EXPO_PUBLIC_BACKEND_URL`,
  `EXPO_PACKAGER_*`: sono gestite dalla piattaforma e romperebbero l'ambiente.
- **Categorie**: per attivare/disattivare in modo **permanente** (che sopravvive
  ai deploy) si modifica il **seed** in `catalog.py`, non solo il DB.

---

## 7. Il Backoffice WEB (Admin) — con login sicuro

Il backoffice è un **sito web separato**, servito dal backend, **NON più dentro l'app mobile**.

### 🔑 Accesso
- **URL (Preview)**: `https://jobby-mvp-update.preview.emergentagent.com/api/admin/login`
- **URL (Produzione)**: `https://<url-deploy>/api/admin/login` (dopo il deploy; se il browser non lo raggiunge, vedi nota ambienti + supporto)
- **Login**: email + **password** + **2FA (Google Authenticator)**
  - Email: `hello@jobbyfree.it`
  - Password iniziale: comunicata a parte (da cambiare al primo accesso)
  - Al **primo accesso** compare un **QR code**: inquadralo con Google Authenticator/Authy, poi inserisci il codice a 6 cifre. Dai login successivi servirà sempre il codice 2FA.
- **Logout**: link in alto a destra nel pannello.

### Sezioni disponibili
**Dashboard, Categories, Users** (All / Pending / Providers / Business / Clients con **Approva/Rifiuta**), **Bookings, Disputes, Pulizie, Babysitting, Driver, Artigiani, Regole, Verifiche, Onboarding**.

> ⚠️ Il vecchio "Pannello Admin" dentro l'app mobile è stato **rimosso**: nessun utente finale vede più sezioni admin.
> La sicurezza (password + 2FA) vale sia in Preview che in Produzione perché è lo stesso codice.

---

## 8. Integrazioni esterne

| Servizio | Uso | Chiave |
|---|---|---|
| **Stripe** (Checkout + Connect) | Pagamenti e split marketplace | chiavi in `backend/.env` |
| **PayPal** (Sandbox) | Pagamenti/split | in `.env` |
| **Claude Sonnet 4.6** | Raccomandazioni sulle dispute | Emergent LLM Key |
| **Resend** | Email verifica provider | in `.env` (attende verifica DNS dominio) |

---

## 9. Checklist quando "qualcosa non torna"

1. **Preview o Produzione?** Controlla l'URL. Utenti/dati reali stanno in produzione.
2. **Backend vivo?** `…/api/admin/ui` deve rispondere. Se 404/502 → attendi 5s (riavvio) o `supervisorctl restart backend`.
3. **Sessione valida?** Se molte API danno 401 → rifai login.
4. **Deploy aggiornato?** Se produzione ≠ preview → rifai **Publish** e **rigenera la build** (le build Apple NON si aggiornano da sole).
5. **Categoria mancante dopo deploy?** Verifica che sia nel **seed** `catalog.py` (non solo nel DB di preview).

---

_Ultimo aggiornamento: giugno 2026. Mantieni questo file allineato quando cambia l'architettura._
