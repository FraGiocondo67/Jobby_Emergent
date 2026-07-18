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

## Backlog
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
