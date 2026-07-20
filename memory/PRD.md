# JOBBY — Product Requirements Document

## Original Problem Statement
Build the JOBBY mobile MVP: an on-demand local services marketplace for the "Economy of Time", connecting customers who need trusted home services with verified providers. Maximise UI and features, make the MVP performant. Source docs: JOBBY Vision Manifesto, Foundations, Strategic Document.

## Vision
"Work should adapt to life, not life to work." A geolocated, reputation-based, payment-enabled platform where trust is the product.

## Architecture
- **Frontend**: Expo Router (React Native, SDK 54), file-based routing, Plus Jakarta Sans, Sage Green (#4A7B59) / Terracotta palette.
- **Backend**: FastAPI + MongoDB (motor). All routes under `/api`.
- **Auth**: Emergent-managed Google OAuth (session tokens, 7-day expiry, stored via storage util).
- **i18n**: Italian + English toggle (context-based).

## User Personas
1. **Customer** — a family/household in Treviso needing trusted, legal home help (cleaning/ironing).
2. **Provider** — an individual with time/skills wanting flexible, tracked income.

## Core Requirements (static)
- Both roles in one app with a role switch.
- "Modello D" matching: request → invite nearby providers → providers accept → customer chooses.
- Real device geolocation + stylized map of nearby providers.
- Payment breakdown: labor (INPS Libretto voucher) + separate 15% JOBBY service fee.
- Trust layer: verified badges, insurance, ratings & reviews.

## Implemented (2026-06-18 — MVP v1)
- Google OAuth login + onboarding (bilingual, trust background).
- Role switch (customer ⇄ provider) from Profile.
- Customer: Home dashboard, category cards (cleaning/ironing), multi-step Mission Creation Wizard (config → location → date/time, real geolocation), Matching Radar (real-time polling, seeded bots auto-accept 2-9s), Provider Selection with price breakdown, Booking confirmation, complete + review flow.
- Provider: online/offline toggle, incoming missions map + list, accept/decline, Earnings dashboard.
- Bookings list (customer) / jobs list (provider) with status pills.
- Backend: 8 seeded verified provider bots around Treviso, reviews recompute provider rating, earnings aggregation, duplicate-review guard.
- Verified via testing agent: 10/10 backend flows passing.

## Implemented (2026-07-18 — Redesign v2, matching provided screenshots + logo)
- **UI redesign** to match screenshots: warm off-white theme, orange primary / green (payments) / purple (proximity) accents, emoji category icons, official JOBBY logo on onboarding (navy) + home header.
- **Home**: greeting, wallet balance pill, search, "Explore the map" card, 3-col category grid (Pulizie, Babysitting, Pet Sitting, Tuttofare, Hospitality, Assistenza, Tecnico, Prossimità[badge 7], Pagamenti[badge 4]), floating "+ Request service".
- **Server-managed categories**: GET /api/categories tree (7 services + Prossimità businesses + Pagamenti services), each with localized labels (IT/EN) + quick-questions.
- **Dynamic request flow** (/request/[id]): renders quick-questions (select/number/text) → services/proximity broadcast a mission; payments deduct wallet.
- **Wallet**: balance, add funds, transactions (GET/POST /api/wallet). **Payments**: /api/payments with insufficient-funds + amount>0 guards.
- **Richieste** tab (missions + bookings + payments), **Chat** tab (conversations + threads, ownership-checked), **Map** explore screen, **Wallet** screen.
- Tabs: Home · Richieste · Chat · Profile.
- Verified via testing agent: 21/21 new backend flows passing; Home & Pagamenti screens visually confirmed.

## Implemented (2026-07-18 — Sprint 3, per "Jobby new.docx")
- **Server-managed catalog in DB**: 9 standard services + 16 proximity businesses + 4 payment services; **admin can activate/deactivate** (X-Admin-Token gated) + admin trust recalc.
- **3 roles on one account** (client · provider · business), switchable in Profile; providers/business pick candidate activities (/activities).
- **Simulated KYC verification** (Sumsub-ready mock): /verification screen (document + selfie → verified), feeds Trust KYC subscore. MOCKED.
- **Request statuses**: pending → matched → confirmed → in_progress → completed (+ disputed), colored pills; provider "Start service" transition.
- **Wallet**: balance, top-up, **payment method (card)** + **bank account (IBAN)** setup — all SIMULATED.
- **Trust Score engine**: weighted provider (8 factors) + client (7 factors) scores in Python/Mongo, trust_events + client_trust_events logs, auto-recalc on review / rate-client / dispute; shown in Profile.
- Ownership guards added on booking/mission lifecycle endpoints.
- Verified via testing agent: 25/25 Sprint-3 backend flows passing. Profile screen visually confirmed.

## Implemented (2026-07-18 — Sprint 3.1: refactor + Admin UI)
- **Backend split into routers/modules**: `core.py` (db/helpers), `models.py`, `deps.py` (auth/admin deps), `trust.py` (score engine), `catalog.py` (catalog + seed), and `routers/` (auth, catalog_routes, missions, bookings, wallet, chat). `server.py` now only wires routers + startup. All prior endpoints preserved (verified end-to-end).
- **In-app Admin screen** (`/admin`): token-gated (X-Admin-Token), lists all categories grouped by kind with activate/deactivate switches + "Recalculate Trust Scores". Linked from Profile.
- Regression verified via curl: mission pending→matched→confirmed→in_progress→completed→review→trust; admin toggle round-trip; payment guard.

## Backlog
- **Real interactive map** (Leaflet + OpenStreetMap, no API key) via `src/components/RealMap.tsx` — iframe on web, `react-native-webview` on native. Used in Explore Map (`app/map.tsx`) and Provider Home. Shows the user + real provider pins with a coverage circle.
- **Map shows only REAL registered providers** (demo bots excluded from `GET /api/providers/nearby`); friendly empty state when none online. Bots retained ONLY for mission auto-accept demo.
- **Service radius slider (1–50 km)** in `app/activities.tsx` for Providers & Businesses → persists `radius_km` (used in matching + map filtering).
- **Business service mode** selector (`outdoor` / `in_shop` / `both`, default `both`) → persists `service_mode`. In-shop-only providers/businesses are excluded from come-to-me mission invites.
- **Proximity = directed request** (iteration 7): Client browses real businesses in a category → picks one → sends product/service request → business Accepts/Declines and confirms eta + mode (pickup/delivery) + delivery cost + price/note. New `routers/business.py` + `/businesses`, `/business-requests*` endpoints; screens `businesses/[category].tsx`, `business-request/[businessId].tsx`, `BusinessHome`.
- **Two-way chat** (shared `thread_id`) opens automatically on business confirm / provider selection.
- Verified via testing agent (iter 6 & 7): all backend + frontend flows pass.

## Backlog (open)
- **Phase 3 — DONE:** Admin user management (Approve/Suspend/Reject; clients auto-approved, providers/business need approval) + revenue monitoring; **real Stripe** wallet top-up (test key in backend/.env; live key to be swapped at the end); **separate Netlify web app** at `/app/admin-web` (Dashboard/Users/Categories/Bookings) — verified iter 10.
- **Real Stripe booking payments (DONE, iter 12):** bookings have `payment_status`; client pays `booking.total` via real Stripe Checkout (`POST /api/bookings/{id}/pay`, `GET /api/payments/status/{id}` — idempotent, server-side amounts). Complete action gated behind payment.
- **Remaining:** swap in user's LIVE Stripe key; real Sumsub KYC (mocked); crypto settlement (addresses stored only); provider payout of collected booking funds (earnings tracked, no real transfer yet).
- **Phase 3 (next):** (a) Backend admin APIs — user management list + Approve/Suspend/Reject (clients auto-approved; providers/business need approval), and revenue monitoring; (b) **separate Web App project** for backend management (deployable to Netlify, connects to backend APIs with admin token); (c) **real Stripe** payments (test key `STRIPE_API_KEY` present; user's live key at the end).
- Crypto payout currently stores wallet addresses (BTC, USDT_TRC20, USDC_ERC20, USDT_ERC20, XRP); actual crypto settlement not wired.
### P1
- Provider ownership/authorization checks on mission/booking mutation endpoints.
- Provider profile detail screen with full review list.
- Recurring booking scheduling & "Zero Pensieri" subscription.
- Real map (react-native-maps) on native builds.
### P2
- Decreasing commission on recurrence (anti-disintermediation lever).
- Libretto Famiglia guided flow + intermediary integration.
- Push notifications for new missions/acceptances (on user request; needs build).
- Expand categories: babysitting, dogsitting, tutoring.

## Implemented (2026-06 — Spec 3 Pagamenti, avvio)
- **Fix bug**: la HOME "+ Richiedi servizio" → `/list/all` ora instrada Babysitting/Driver/Artigiani ai NUOVI configuratori (prima cadevano nel vecchio `/request/<cat>`).
- **Regola fee 50/50 (Impresa)**: `price_breakdown` corretto — cliente paga lavoro + metà fee; provider netto = lavoro − metà fee; JOBBY tiene la fee intera. `confirm()` registra `pagamento_fee.importo=fee_client` (+`jobby_fee_total`) e `pagamento_lavoro.importo=provider_net` (+`fee_provider`).
- **Libretto**: fee 100% a carico del cliente (`total_client=lf_nominale+jobby_fee`), invariato. Testato 20/20 (iter28).
- Chiavi Stripe (STRIPE_API_KEY, STRIPE_CONNECT_SECRET_KEY) e PayPal (PAYPAL_CLIENT_ID/SECRET/BASE) già presenti in `backend/.env`.

## Spec 3 — Backlog pagamenti (da fare, in ordine deciso dall'utente)
1. Addebito REALE alla conferma: Stripe Connect destination charge (application_fee = fee intera, transfer_data.amount = provider_net) + PayPal Orders v2 con platform_fees. SetupIntent off_session per ricorrenti. [tutte le categorie]
2. Rimborsi automatici: cancellazione cliente ≥48h → rimborso integrale; cancellazione provider → rimborso + risostituzione + evento su profilo (reverse_transfer + refund_application_fee).
3. Garanzia primo servizio (nuovo cliente, segnalazione ≤48h, gestione admin, rimborso min. fee).
4. Contestazione ≤48h: Impresa congelamento pre-trasferimento; Libretto sospensione comunicazione INPS.
5. Motore ricorrenti: 1ª visita alla conferma, successive addebito 48h prima + notifica + gestione fallimenti (sospensione a 24h).
6. Rifiniture Libretto: importo mancante + ricarica "un mese", avviso tempi F24, suggerimento Impresa per prenotazioni ravvicinate.
7. Estendere tutte le regole ad Artigiani/Babysitting/Driver.

## Implemented (2026-06 — Spec 5 Navigazione/Home/Dashboard)
- **Tab bar 4 voci**: Home · Attività · Portafoglio · Profilo (tab Chat nascosta con href:null, rotta /chat ancora raggiungibile).
- **Home due stati** (`/api/home/state`): nuovo=pagina conversione (promessa + entry "Pulizie e stiro" + segnali fiducia + griglia categorie); ricorrente=card della relazione (nome collaboratrice, prossima visita, 3 azioni riprenota/sposta/scrivi, flag problema) + "Altri servizi". Altre categorie sempre accessibili sotto.
- **Portafoglio cliente 4 blocchi** (`/api/wallet/dashboard`): borsellino (caricato/impegnato/spendibile + ricariche in transito), limiti di legge (barra annua 10.000€, per-collaboratrice 2.500€ con peso 75% agevolate, utilizzi esterni via `/api/wallet/external-usage`, upsell all'80%), attività+documenti, recupero fiscale (stima deducibile). Impresa-only → metodo pagamento + ricevute.
- **Dashboard provider 3 blocchi** (`/api/provider/dashboard`): guadagni con date accredito (INPS il 15 del mese dopo / trasferimento impresa), limiti personali (5.000€/2.500€/280h), storico+recensioni+affidabilità + toggle "Non disturbarmi" (`/api/provider/dnd`).
- **Pulsante WhatsApp globale** ("Serve una mano?") su tutte le tab; numero configurabile da backend (`db.settings` key `support_whatsapp`, default +393481136876) via `GET /api/settings/support` + `POST /api/admin/settings/support`.
- **Fix bug**: `/list/all` (+Richiedi servizio) ora instrada Babysitting/Driver/Artigiani ai nuovi configuratori.
- Costanti limiti in `richieste_config.py`: LF_FAMILY_ANNUAL_EUR=10000, LF_COUPLE_CEILING_EUR=2500, LF_PROVIDER_ANNUAL_EUR=5000, LF_PROVIDER_HOURS=280, LF_AGEVOLATE_WEIGHT=0.75, LF_WARN_THRESHOLD=0.8.
- Testato 9/9 backend + frontend (iter Spec 5). Seed demo: `bstest@jobby.app` ora ha 1 richiesta completata + 1 futura → Home ricorrente con card Giulia.

## Implemented (2026-06 — Spec 4 Cancellazioni/No-show/Recensioni)
- **Motore generico** `routers/spec4.py` sul collection condiviso `db.richieste` (endpoint `/api/richieste/{rid}/...`), valido per tutte le categorie; importi su **ledger simulato** (wallet_balance / lf_borsellino liberato).
- **Cancellazioni a scaglioni** (Impresa): ≥48h rimborso pieno · 24–48h solo fee trattenuta · <24h fee + **50%** lavoro come indennizzo al provider + strike. **Libretto**: tardiva = perde fee + strike + priorità rimatching + voucher liberati.
- **Provider-cancel** (rimborso pieno + stato→in_matching + risostituzione + alert admin), **no-show** (grazia 15 min + alert, verifica admin), **report-delay**, **pausa/riprendi ricorrenza**.
- **Recensioni**: finestra 14gg, moderazione admin (pubblica solo `moderato:true`), 1 replica provider, cliente elimina la propria entro 14gg, badge **"Nuovo su JOBBY"** < 3 recensioni (media nascosta finché nuovo).
- **Punteggio privato cliente** (provider valuta 1–5 + flag + nota, mai pubblico) + **contatori affidabilità** (strike cancel<24h/no-show, soglia 3/180gg → alert admin).
- Soglie **tutte configurabili** (`db.settings` key `spec4_config`) via admin tab **"Regole"** (soglie + coda moderazione + affidabilità).
- Frontend Pulizie `[id].tsx` cablato (cancel tier-aware, no-show, provider-cancel, valuta cliente, replica recensione). `cancelRichiesta`/`reviewRichiesta` ripuntati al motore generico.
- Testato 17/17 backend + frontend (iter30). Fix bug JSX orfano post-test.
- Costanti default in `richieste_config.py` (`SPEC4_DEFAULTS`).

## Next Tasks
- Add authorization checks + provider profile detail screen.
- Consider Stripe/YOB Pay for the JOBBY service fee.

## Implemented (2026-06 — Spec 3.1 Pagamenti REALI split marketplace)
- **Modulo generico** `routers/payments_split.py` sul collection condiviso `db.richieste` (endpoint `/api/pay/*`), valido per TUTTE le categorie sul binario `impresa`/`piva` (il `persona_lf` resta su voucher INPS/borsellino, NON PSP).
- **Stripe Connect destination charge** (Checkout hosted, raw `STRIPE_CONNECT_SECRET_KEY`): il cliente paga l'intero importo, `application_fee_amount` = fee JOBBY intera, `transfer_data.destination` = connected account del provider → il provider riceve il netto. Richiede provider onboardato (else 400 `provider_not_onboarded_stripe`).
- **PayPal Orders v2 multiparty**: `payee` + `payment_instruction.platform_fees` = fee JOBBY (else 400 `provider_not_onboarded_paypal`).
- **Fallback wallet SIMULATO** (escrow) per demo testabili: addebito wallet cliente → `held` → `/release` accredita il netto al provider (JOBBY trattiene la fee intera). Verificato: cliente −41.92, provider +36.07, JOBBY +5.85.
- **Rimborsi** `/api/pay/richiesta/{rid}/refund` (admin): Stripe `reverse_transfer`+`refund_application_fee` / PayPal `platform_fees` / simulato riaccredito cliente.
- **Ricorrenti**: `SetupIntent off_session` via Checkout `mode=setup` (`/api/pay/setup-card`) + addebito automatico destination-charge su carta salvata (`/api/pay/richiesta/{rid}/charge-recurring`).
- **Frontend**: componente riusabile `src/components/PaymentSection.tsx` (3 pulsanti Carta/PayPal/Portafoglio, redirect web + WebBrowser nativo + polling) cablato in pulizie/babysitting/driver/artigiani `[id].tsx`. i18n `pay*` (IT/EN).
- Testato 6/6 backend (iter31) + UI E2E (held→release). NOTE: lo split reale Stripe/PayPal completa E2E solo con Connect abilitato sul platform account + provider onboardato (azione utente); ora è testabile E2E solo il percorso wallet(simulato).

## Implemented (2026-07-19 — Spec 7 ARTIGIANI, replaces Tuttofare)
- **Artigiani category** fully wired & E2E-tested (25/25 backend green): two-stage flow — Stage 1 "paniere" (fixed-price interventions) and Stage 2 "chiamata-diagnosi" (paid diagnosis → in-app quote valid 7d, call-fee scomputo, extras approval, mandatory close with outcome, 30-day guarantee). 6 mestieri (idraulico/elettricista/caldaista/climatizzazione/giardiniere/tuttofare-su-Libretto), abilitazione DM 37/2008 + F-Gas verify.
- Backend: `routers/artigiani.py`, `artigiani_config.py` (endpoints `/api/artigiani/*`, `/api/admin/artigiani/*`).
- Frontend wired: Home tile → `/artigiani/configura`; Richieste tab client cards + provider incoming section; Profile provider "Listino artigiano" link; screens `app/artigiani/{configura,[id],listino}.tsx`.
- Admin web (`admin_web.py`): new "Artigiani" tab (manual matching/invite) + abilitazione verify button in Onboarding.
- Legacy `tuttofare` category set `active:false`; `artigiani` active.

## Implemented (2026-06 — Fase 3: Listini prodotti per attività di PROSSIMITÀ)
- **Backend** `routers/listino.py` (registrato in server.py). Prodotto: `item_id · category · descrizione · unita(pz|nr|hr|kg|bulk) · prezzo · foto(base64 opz)`. Il Business gestisce il listino SOLO per le categorie in `services`.
  - CRUD business: `GET /api/listino/mine[?category]`, `POST /api/listino`, `PUT/DELETE /api/listino/{item_id}`.
  - Cliente: `GET /api/listino/business/{business_id}[?category]`; `POST /api/listino/order {business_id,category,items[{item_id,qty}],address,lat,lng,note}` → totale calcolato lato server, importo BLOCCATO nel wallet (prima `bonus_credit`, poi `wallet_balance`), crea doc `business_requests {order:true, items[], total, held, held_from_bonus/wallet, payment_status:held}` + transazione `held`.
  - Ciclo di vita: `POST /api/listino/order/{rid}/respond {accept,eta,mode,note}` (business; rifiuto → rimborso; conferma → apre chat), `POST .../complete` (business → sblocca held verso wallet business), `POST .../cancel` (cliente pending → rimborso).
- **Frontend**: Business gestisce catalogo in `/listino` (Profilo → "Il mio listino"; add/edit/delete con foto da fotocamera o galleria, selettore unità, prezzo). Cliente ordina in `/business-request/[businessId]` (stepper quantità + carrello + totale + blocco wallet; fallback a nota libera se il business non ha listino per quella categoria). BusinessHome mostra ordini in arrivo con articoli + "Segna consegnato". Tab Richieste mostra card ordine con importo in garanzia + annulla.
- Verificato: backend via curl (CRUD, split bonus+wallet, accept→complete, decline/cancel→refund, insufficient_wallet guard); frontend via testing agent iter35 (ADD/EDIT/DELETE, ordine happy path, i18n IT, nessun crash).
- **NOTA regressione risolta**: durante l'aggiunta stringhe i18n era stato rimosso per errore il boundary it/en in `src/i18n.ts` (tutto finito in `it:`, `en` undefined → UI in inglese). Ripristinati i blocchi `it:{}`/`en:{}` e reso `t()` null-safe in LanguageContext.

## Implemented (2026-06 — Fix onboarding attività + filtro listini per ruolo/attività)
- **Modello ruoli confermato dall'utente**: il ruolo (Professionista=provider vs Attività di prossimità=business) è deciso dalla SCELTA INIZIALE, non più dal tipo profilo legale. `set_profile` accetta `role` opzionale (provider|business) che ha priorità su Impresa/P.IVA/Libretto. Professionista → solo categorie standard; Attività → prossimità + standard.
- **Nuovo step onboarding "Quale attività offri?"** in `provider-onboarding.tsx` (dopo "data"): mostra le categorie giuste in base al ruolo (business=prossimità+standard, provider=standard), multiselezione, salva via `PUT /profile {services}`. `onboarding-flow` e `profile` passano `?role=` al provider-onboarding.
- **activities.tsx**: le Attività ora vedono prossimità + standard (prima solo prossimità).
- **profile.tsx**: i listini specializzati (pulizie/driver/artigiani/babysitting) appaiono SOLO per provider e SOLO se la categoria è tra i `services` selezionati; "Il mio listino" (prodotti prossimità) appare per role=business.
- Verificato: backend curl (role override, services proximity+standard); frontend testing agent iter36 (filtro listini provider/business, activities business, step attività via code-inspection perché OTP Resend blocca il walkthrough completo — ma send-otp auto-verifica e il FE gestisce auto_verified, quindi l'onboarding è completabile con un click su "Invia codice").

## Implemented (2026-06 — Geolocalizzazione, Esplora Mappa, Rating/Stato, Admin date, Lingua dispositivo)
- **Geocoding reale** (OpenStreetMap Nominatim, no key): nuovo `routers/geo.py` → `POST /api/geocode {query}` (indirizzo→lat/lng+label) e `POST /api/reverse-geocode {lat,lng}` (→label). `api.geocode`/`api.reverseGeocode`. Cablato in `business-request` (indirizzo digitato geocodificato all'invio; "usa posizione" reverse-geocode in indirizzo leggibile).
- **Esplora MAPPA** (Home card `explore-map` → `/map`): mappa reale con cerchio di copertura, selettore raggio (chip 2/5/10/20/50 km), filtro categoria (standard+prossimità). `GET /providers/nearby` ora accetta `radius` opzionale (filtra per distanza dal centro) e ritorna `online`. Mostra SOLO attivi/online (scelta utente).
- **Rating + stato**: ogni card provider/attività mostra Stars, Trust chip e badge Attivo/Non attivo (ActivePill).
- **Admin USERS backend** (`admin_web.py`): sotto ogni utente mostra attività selezionate + "📅 Attivo dal" (created_at) e "🕑 Ultimo login" (last_login). `last_login` salvato in `issue_session` e nel login OAuth.
- **Lingua dispositivo** (`expo-localization`): `LanguageContext` default = locale dispositivo (it→Italiano, altrimenti Inglese); override manuale IT/EN persistito in `jobby_lang`.
- Verificato: backend curl (geocode/reverse, radius filter, last_login); frontend testing agent iter37 (lingua device, esplora mappa raggio+categoria+stato, geocoding ordine, regressione Fase 3) — tutti PASS.
- Nota: bstest@jobby.app e provtest@jobby.app sono entrambi role=provider (test_credentials aggiornato).

## Implemented (2026-06 — Geocoding esteso a tutti i configuratori + onboarding)
- Pattern geocoding (reverseGeocode su "usa posizione" → indirizzo leggibile; geocode dell'indirizzo digitato via resolveCoords() prima del submit) esteso a: `pulizie/configura`, `babysitting/configura`, `artigiani/configura`, `onboarding-flow` (cliente), `provider-onboarding` (professionista/attività). Driver aveva già geocoding waypoint.
- Verificato via testing agent iter38: pubblicazione richieste Pulizie/Babysitting/Artigiani OK (POST /api/geocode 200, naviga al dettaglio), onboarding submit chiama resolveCoords prima di completeOnboarding. Nessuna regressione.
- Nota minore pre-esistente: badge stato "In pubblicazione" hardcoded IT su babysitting/[id] e artigiani/[id] (non legato a questo task).

## Implemented (2026-06 — Profilo pubblico provider/attività da mappa "Cerca attorno a te")
- Backend `GET /api/providers/{id}/public`: profilo pubblico (nome, foto, servizi, rating medio, trust, online, bio, indirizzo, business_photos) + lista recensioni (da richieste.recensione + legacy db.reviews). `api.providerPublic`.
- Nuova schermata `app/provider/[id].tsx`: profilo + stato Attivo/Non attivo + trust + recensioni + (per attività) anteprima prodotti listino + CTA. CTA business = "Vedi prodotti e ordina" → `/business-request/[id]` (categoria del primo prodotto disponibile); CTA provider = "Richiedi un servizio" → configuratore della categoria principale.
- Le card provider/attività sulla mappa (`/map`) ora sono toccabili → `/provider/[id]`.
- Verificato testing agent iter39: tap business→profilo (6 recensioni, 4 prodotti, CTA ordine), tap provider→profilo senza prodotti + CTA richiesta; filtri raggio/categoria mappa OK.

## Implemented (2026-06 — BATCH A bug critici dai test utente)
- #1 Indirizzo driver: `PlaceInput` era un componente definito dentro il render → ricreato ad ogni tasto e perdita focus. Convertito in `renderPlace()` inline in `driver/configura.tsx`. Aggiunto hint "Tocca 🔍 per cercare".
- #12 Tariffe driver con virgola: `driver/listino.tsx` ora memorizza il valore grezzo mentre si digita e converte virgola→punto con `num()` al salvataggio (niente più NaN). Accetta sia 2,5 che 2.5.
- #6 Richieste generiche non arrivavano al provider: `ProviderHome` (index.tsx) ora aggrega `pulizieIncoming/bsIncoming/drvIncoming/artIncoming` in base a `user.services` in una sezione "🔔 Nuove opportunità" che apre il dettaglio della richiesta. Prima leggeva solo `incomingMissions` (vecchio sistema).
- #8 Rifiuto non aggiornava la vista: gli endpoint `/driver|pulizie|babysitting|artigiani/incoming` ora escludono gli inviti con status "declined" (`$elemMatch`).
- #9 Riassegnazione dopo rifiuto: gli endpoint admin invite (pulizie + driver) riattivano gli inviti precedentemente "declined" (reset a "invited" + notifica).
- Verificato testing agent iter41: #1 focus 0 perdite, #12 salva 2,5→2.5, #6 opportunità appare dopo invito e apre dettaglio. TODO batch successivi: #5 dettaglio richiesta+chat+accettazione driver/contro-prezzo pendente, #13 mappa→form guidato, #7 notifiche in-app (+push su richiesta), #2/#4/#10/#11 backend/ruoli/bonus, #3 bonus multiplo+nota.

## Fix #8/#9 backend+admin (rifiuto & riassegnazione) — tutte le categorie
- Causa #8 "nuove richieste non appaiono nel backend": l'endpoint admin driver richieste andava in 500 se `compatible_drivers`/`ncc_price` falliva su una richiesta → ora avvolto in try/except (una richiesta problematica non blocca la lista).
- Causa #8 "rifiuto non aggiorna": l'admin mostrava i provider invitati come "checked disabled" senza distinguere il rifiuto. Ora ogni provider compatibile ha `invite_status` (invited/declined) + `confirmed`; l'admin mostra badge "✗ rifiutato · riassegnabile" / "invited" / "confermato".
- Fix #9 riassegnazione: le checkbox dei provider "declined" NON sono più disabilitate → l'admin può riselezionarli; l'endpoint invite riattiva gli inviti declined (status→invited, stato→in_matching, notifica). Applicato a driver + pulizie + babysitting + artigiani.
- `/*/incoming` escludono gli inviti "declined" (via $elemMatch) → dopo il rifiuto la richiesta sparisce dalla Home del provider; dopo la riassegnazione riappare.
- Verificato con test DB integrato: admin vede nuova richiesta ✓, incoming prima del rifiuto ✓, escluso dopo rifiuto ✓, invite_status=declined ✓, riappare dopo riassegnazione ✓.
- NOTA client "rifiutata": nessun endpoint imposta mai `stato` richiesta a "declined"; con la riassegnazione ora `stato`=in_matching. Non riproducibile lato codice — chiedere repro all'utente se persiste.

## Implemented (2026-06 — Fix isolamento categorie + timeline ciclo di vita + geocode/mappa + Batch C notifiche)
- **BUG duplicato richieste (root cause)**: `/api/pulizie/richieste` e `/pulizie/incoming` NON filtravano per categoria → restituivano anche driver/babysitting/artigiani dello stesso cliente (stesso documento mostrato due volte; annullando driver spariva "pulizia"). Aggiunto filtro `categoria=CASA, servizio=PULIZIA`. Verificato: 79→47 doc.
- **Incoming provider** (tutte le categorie): la query ora include anche i lavori confermati/in_corso del provider scelto (`$or` provider_scelto) → la Home mostra opportunità + lavori attivi.
- **Tab Attività provider ricostruita**: nuovo endpoint `GET /api/provider/jobs` (tutte le categorie, attivi+completati) → card cliccabili verso il dettaglio (dove risiedono pagamento e recensione), filtri Attivi/Completati (testid job-*, jobfilter-*).
- **StatusTimeline** (`src/components/StatusTimeline.tsx`) su tutti e 4 i dettagli: Confermata → In esecuzione → Completata → Pagata → Recensita, con avviso "in attesa di conferma". Risolve la confusione confermata≠eseguita.
- **Geocode multi-risultato**: `POST /api/geocode/search` → fino a 5 risultati con etichette pulite ("Via Roma, Pigra (Como)"); lista selezionabile in `driver/configura` (drv-*-res-*). Risolve "una via = 5 città".
- **Ping su mappa**: nuovo `src/components/MapPicker.tsx` (Leaflet WebView/iframe, tap per posizionare pin) + reverse-geocode → indirizzo. Pulsante "Segna sulla mappa" in driver/configura.
- **i18n driver detail**: aggiunte chiavi mancanti (drvConfirmTrip, drvModifyPrice, clientLabel, ecc.) IT/EN.
- **Fix**: `_parse()` in driver.py ora tz-aware (cancel driver crashava con 500).
- **Batch C — Notifiche in-app**: chat message ora genera notifica al destinatario (ref_type=chat, ref_id = conversazione del destinatario). Campanella con badge unread (`NotifBell`) in tutte e 3 le Home; schermata `/notifications` con routing per tipo (richiesta→pulizie, driver, babysitting, artigiani, chat, dispute, booking). Notifiche per user_id → persistono al cambio profilo. Push rimandate (richiede google-services.json + build).
- Verificato: testing agent iter42 (backend 14/14 + frontend) e iter43 (notifiche backend 8/8 + frontend). Nessuna regressione; recensioni/dispute/pagamenti intatti.

## Fix driver + reset DB (2026-06)
- **Auto-matching su pubblicazione**: `create_richiesta` driver ora invita i driver compatibili nel raggio (`compatible_drivers`) + notifica. Prima `provider_invitati=[]` → nessun driver riceveva la richiesta.
- **Richiesta diretta**: `RichiestaIn.target_provider_id`; profilo provider passa `?provider=<id>` al configuratore. Il driver target è pre-invitato con `direct:true`. **Auto-conferma**: se il driver target accetta al prezzo di listino (senza contro-prezzo) → stato passa direttamente a `confermata` (il cliente ha già scelto). Con contro-prezzo resta `con_proposte` per conferma cliente.
- **Wallet/guadagni driver**: nuovo `_credit_provider()` accredita il netto (post-fee) sul `wallet_balance` al saldo corsa (NCC su complete, taxi su pay). `/earnings` (bookings.py) riscritto per includere le `richieste` di tutte le categorie (prima solo `bookings` → total_earned restava 0).
- **Filtri anti-confusione**: Home mostra solo opportunità recenti/attive (max 6) + link "Vedi tutte in Attività"; tab Attività cliente default su "Attive" (filtri all/active/completed scrollabili).
- **Reset DB test**: cancellate tutte le collezioni attività/transazioni/chat/notifiche/dispute; mantenuti users, sessioni, settings, categorie, listino_prodotti, child_cards; saldi wallet/bonus azzerati.
- DA DECIDERE con utente: verifica saldo prima della prenotazione (opzioni a: solo avviso / b: blocco wallet / c: prepagato obbligatorio alla conferma).
