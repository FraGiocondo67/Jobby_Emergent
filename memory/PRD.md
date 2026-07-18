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

## Next Tasks
- Add authorization checks + provider profile detail screen.
- Consider Stripe/YOB Pay for the JOBBY service fee.
