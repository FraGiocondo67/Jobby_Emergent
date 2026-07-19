#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## agent_communication (2026-06 fork)
-agent: "main"
-message: |
  User reports: "app is not working; activated categories in in-app Admin Panel but they don't show in user Home."
  Investigation: Backend fully working (all endpoints 200). Found 11 of 29 categories were DEACTIVATED in DB (toggled off via admin). Reactivated all 29 (active=true). Home shows 9 standard services as tiles + aggregate "Prossimità" and "Pagamenti" tiles (proximity/payment businesses appear inside those lists, not as home tiles).
  Please TEST (frontend+backend) using demo Bearer token `demo-preview-token-123` (user_id user_demopreview01, role client):
  1) Authenticated Home renders 9 standard category tiles + Prossimità + Pagamenti tiles, wallet pill shows balance.
  2) GET /api/categories returns 9 standard, 16 proximity, 4 payment (all active).
  3) Admin toggle round-trip: POST /api/admin/categories/{cat_id}/toggle with X-Admin-Token `jobby-admin-7c2f9a`, then GET /api/categories reflects change. Re-activate after.
  4) Wallet screen loads, add funds works. Request/mission creation flow works for a standard category.
  5) Chat and Richieste tabs load without crash.

## agent_communication (2026-06 fork — Real Map + radius + service_mode)
-agent: "main"
-message: |
  New features implemented:
  1) REAL interactive map (Leaflet + OpenStreetMap) via new component src/components/RealMap.tsx. Uses iframe on web (react-native-webview has no web build) and WebView on native. Used in Explore Map (app/map.tsx) and Provider Home (app/(tabs)/index.tsx). Verified rendering on web preview (Treviso streets + markers).
  2) providers/nearby now returns ONLY real registered providers (is_bot excluded) + includes role/service_mode/business_name. Confirmed real provider 'Francesco Franzin' shows; bots excluded.
  3) Service radius slider (1-50 km) in app/activities.tsx for providers & businesses -> saves radius_km.
  4) Business service_mode selector (outdoor | in_shop | both) in activities.tsx -> saves service_mode. In-shop-only businesses are NOT invited to come-to-me missions (missions.py create_mission filter). Bots still used for mission auto-accept demo.
  Please TEST both:
  Backend (Bearer demo-preview-token-123):
  - GET /api/providers/nearby?lat=45.6669&lng=12.2433 excludes bots, returns real providers with service_mode field
  - PUT /api/profile accepts {radius_km, service_mode}
  - POST /api/missions still matches (bots auto-accept) for a standard category
  Frontend (inject demo token, storage key jobby_session_token):
  - Explore Map screen shows a real map (iframe/leaflet) + provider list; empty state text if none
  - Profile -> switch to Provider -> Activities shows radius slider; switch to Business -> Activities shows service_mode selector + radius

## agent_communication (2026-06 fork — Proximity directed-request flow)
-agent: "main"
-message: |
  New proximity/business logic implemented (per user):
  - Proximity businesses now use a DIRECTED request (not broadcast): Client browses businesses in a category -> picks ONE -> sends a product/service request -> business Accepts/Declines and confirms eta + mode (pickup/delivery) + delivery_cost + price + note.
  - Providers (standard services) unchanged (broadcast -> candidacies -> select).
  - Chat is now genuinely TWO-WAY (shared thread_id) and opens automatically when a business confirms (or a provider is selected).
  New backend router routers/business.py: GET /api/businesses?category&lat&lng (real businesses only, no bots), POST /api/business-requests, GET /api/business-requests, GET /api/business-requests/incoming, POST /api/business-requests/{id}/respond. chat.py refactored for two-way threads.
  New frontend: app/businesses/[category].tsx, app/business-request/[businessId].tsx, BusinessHome in (tabs)/index.tsx with respond modal, business requests + chat button in Richieste.
  Curl-verified end-to-end (client demo + business Francesco): list->request->incoming->confirm->chat two-way all pass.
  CREDENTIALS FOR TESTING:
  - Client Bearer: demo-preview-token-123 (user_demopreview01, role client)
  - Business Bearer: biz-test-token-999 (user_2f996c8a010a 'Francesco Franzin', role business, online, offers lavanderia/pulizie/tecnico, service_mode both)

## agent_communication (2026-06 fork — Phase 1 Map/Discovery + Phase 2 Payments relocation)
-agent: "main"
-message: |
  PHASE 1 (Map & discovery):
  - Explore Map (app/map.tsx) now has Providers/Businesses toggle tabs, shows BOTH provider (blue) and business (purple) pins + your location (green), a legend, and two lists ('Providers online (N)', 'Nearby businesses (M)') each with Stars rating + Trust Score chip. Unapproved providers/businesses show a 'Pending approval' badge.
  - Proximity category screen (app/businesses/[category].tsx) now shows a map at top with the available businesses + trust score + pending badge in the list.
  - Backend: /providers/nearby and /businesses now include role + approval_status; new users get approval_status (client=approved; provider/business=pending on role switch unless provider_approved).
  PHASE 2 (Payments moved to Profile + crypto payout):
  - New screen app/payments-settings.tsx opened from Profile row 'Payments & Payouts' (testID profile-payments). Client: card method. Provider/Business: bank IBAN + crypto payout wallets (BTC, USDT_TRC20, USDC_ERC20, USDT_ERC20, XRP).
  - Removed card/bank setup from Wallet screen (wallet now = balance + add funds + transactions only).
  - Backend: PUT /wallet/crypto-wallet (validated tokens), GET /wallet returns crypto_wallets. Curl-verified.
  TEST both. Credentials: CLIENT demo-preview-token-123; BUSINESS biz-test-token-999 (Francesco, business, online, offers lavanderia). Storage key jobby_session_token.

## agent_communication (2026-06 fork — Phase 3: Admin mgmt + Revenue + Stripe + Web App)
-agent: "main"
-message: |
  PHASE 3 implemented:
  1) Admin user management: GET /api/admin/users (now includes approval_status, phone, address, online, business_name); POST /api/admin/users/{id}/status {status: approved|suspended|rejected} (approve sets provider_approved=true). GET /api/admin/stats now includes pending_approvals, revenue (=jobby_fees), topups_volume. Curl-verified: suspend/approve OK, invalid=400, bad user=404.
  2) REAL Stripe (emergentintegrations, test key added to backend/.env): POST /api/wallet/topup/checkout {package_id in p10/p25/p50/p100, origin_url} -> real checkout.stripe.com URL + session_id; GET /api/wallet/topup/status/{session_id} polls Stripe and idempotently credits wallet ONLY when payment_status=paid; POST /api/webhook/stripe. Curl-verified: real session URL created; invalid package=400.
  3) Wallet screen (frontend) now uses Stripe: add-funds buttons (p10/p25/p50) call topup/checkout; on web it redirects to Stripe and returns to /wallet?session_id=... then polls status; on native opens WebBrowser then polls. Removed the old instant mock add.
  4) Separate Web App at /app/admin-web (static, Netlify-ready): Dashboard (revenue + ops), Users (Approve/Suspend/Reject + filters), Categories toggle, Bookings. Connects via Backend URL + X-Admin-Token.
  TEST:
  - Backend: admin status transitions + stats fields + Stripe checkout create/status/invalid.
  - Frontend: wallet 'add-25' initiates Stripe checkout (verify a checkout.stripe.com URL/redirect is produced; DO NOT need to complete card payment). Verify status endpoint does not credit an unpaid session.
  - Admin Web App: serve /app/admin-web with a static server and Playwright-test connecting to backend https://jobby-mvp-update.preview.emergentagent.com with X-Admin-Token jobby-admin-7c2f9a; verify Users tab shows list and Approve/Suspend/Reject calls succeed (use Francesco user_2f996c8a010a; leave him 'approved' at the end).
  Credentials: CLIENT demo-preview-token-123; BUSINESS biz-test-token-999; Admin token jobby-admin-7c2f9a.

## agent_communication (2026-06 fork — Fix: backend console findability)
-agent: "main"
-message: |
  User reported "can't find admin-web folder". The folder exists & is git-tracked at /app/admin-web (index.html, netlify.toml, README.md) but the platform surfaces frontend/backend, so it's easy to miss. FIX: upgraded the backend-served admin console at GET /api/admin/ui to the FULL console (previously it lacked user-management + revenue). Now it has: Dashboard with 'Revenue monitoring' cards + Operations; Users tab with Approve/Suspend/Reject buttons + filters (All/Pending/Providers/Business/Clients); Categories toggle; Bookings. Accessible in any browser at {backend}/api/admin/ui with admin token jobby-admin-7c2f9a (no folder needed). Standalone Netlify app remains at /app/admin-web.
  TEST (frontend/web page only, no Expo needed): Open https://jobby-mvp-update.preview.emergentagent.com/api/admin/ui, enter admin token jobby-admin-7c2f9a, Connect. Verify: Dashboard shows Revenue monitoring cards; Users tab lists users with Approve/Suspend/Reject; click Suspend then Approve on Francesco (user_2f996c8a010a) and confirm status flips (LEAVE approved at end); Categories tab toggles; Bookings tab lists.

## agent_communication (2026-06 fork — Real Stripe for BOOKING payments)
-agent: "main"
-message: |
  Extended real Stripe to BOOKING payments (not just wallet top-up):
  - Bookings now have payment_status (default 'unpaid'; set at creation in missions.py select).
  - POST /api/bookings/{booking_id}/pay {origin_url} -> real checkout.stripe.com session, amount = booking.total from DB (server-side, never client). Returns url+session_id, or {already_paid:true}. 404 unknown booking, 403 non-owner.
  - GET /api/payments/status/{session_id} -> generic settle; idempotent: on paid, booking_payment sets booking.payment_status=paid + client transaction (negative amount); wallet_topup still credits wallet. Curl-verified: real session created, 404 for unknown booking.
  - Frontend booking/[id].tsx (CLIENT): shows 'Pay now · €total' button when unpaid; on web redirects to Stripe then returns to /booking/{id}?session_id=... and polls status; on native opens WebBrowser then polls. When paid shows Paid banner and only THEN the Complete button. Provider side unchanged (Start service).
  TEST both:
  - Backend: /bookings/{id}/pay creates session; /payments/status doesn't mark paid for unpaid session; 404/403 guards.
  - Frontend (CLIENT demo-preview-token-123): open a confirmed unpaid booking -> 'Pay now' button visible, Complete hidden until paid; tapping pay initiates Stripe checkout (verify checkout.stripe.com session/redirect; DO NOT complete card).
  Credentials: CLIENT demo-preview-token-123. A booking exists: bkg_7c6591810676 (may already be used). Provider biz-test-token-999.

## agent_communication (2026-06 fork — Phase A: Categories & Requests)
-agent: "main"
-message: |
  PHASE A implemented (Categories & Requests enhancements):
  1) Category commission (default 10%) REPLACES the old fixed 15% jobby_fee. Each category has commission_pct (migration set 10.0 on all standard/proximity cats). Admin: POST /api/admin/categories/{cat_id}/commission {commission_pct 0-100}. missions.py select_provider now computes jobby_fee = labor * commission_pct/100 and stores commission_pct on the booking. Admin UI (/api/admin/ui Categories tab) has an editable commission % input per service/proximity category.
  2) Budget proposal field for clients: MissionIn.budget + BusinessRequestIn.budget (optional). Shown on request/[id].tsx (service) and business-request/[businessId].tsx. Provider sees "💰 Budget: €X" on incoming missions (index.tsx ProviderHome) and business sees it on incoming requests (BusinessHome). Also shown in richieste.tsx cards.
  3) Backend-configured dynamic forms: already driven by category.questions via request/[id].tsx (unchanged, confirmed working).
  4) Editable pricing for proximity businesses: business edits price_list in profile-details.tsx (existing). NEW GET /api/businesses/detail/{business_id} returns price_list; business-request screen now displays the business price list to the client. list_businesses also returns price_list.
  5) Client requests filtering + date sorting: richieste.tsx CustomerRequests now merges missions+bizReqs+bookings+payments into one list with filter chips (All/Active/Completed, testID filter-all/active/completed) and a sort toggle (testID sort-toggle, Newest/Oldest by created_at).
  Curl-verified: commission migration (all cats=10), set commission (12.5 ok, 150=400 invalid), mission budget stored (80.0), business detail price_list (2 items).
  TEST both:
  - Backend: POST /api/admin/categories/{id}/commission (valid+invalid+404); create mission with budget; business detail endpoint (404 unknown); confirm booking uses category commission_pct (create mission -> provider accept -> client select -> booking.jobby_fee == labor*pct/100 and booking.commission_pct present).
  - Frontend (CLIENT demo-preview-token-123): richieste filter chips + sort toggle work; request/[id] shows budget field; business-request shows price list + budget. (BUSINESS biz-test-token-999).
  Credentials: CLIENT demo-preview-token-123; BUSINESS biz-test-token-999; Admin token jobby-admin-7c2f9a. Storage key jobby_session_token.

## agent_communication (2026-06 fork — Phase B1: Auth methods + Onboarding + Demo)
-agent: "main"
-message: |
  Implemented multi-method auth + onboarding + read-only demo:
  1) NEW auth endpoints (coexist with existing Emergent Google + session_token model): POST /api/auth/register {email,password,name}, POST /api/auth/login {email,password} (bcrypt), POST /api/auth/apple {identity_token,name?,email?} (verifies vs Apple JWKS RS256, aud=APPLE_AUDIENCES; iOS build only), POST /api/auth/demo (read-only user). All return {user, session_token}; password_hash never returned.
  2) Demo read-only: server.py middleware blocks POST/PUT/DELETE/PATCH on /api/* (except /api/auth/*) for is_demo users -> 403 {"detail":"demo_readonly"}. Frontend api.ts surfaces an Alert on demo_readonly. Demo banner shown on client Home (testID demo-banner).
  3) Onboarding: new users get onboarding_completed=false. app/index.tsx gate routes user->/onboarding-flow when not completed, else /(tabs). app/onboarding-flow.tsx: step0 role (testID role-client/provider/business, role-next), step1 details. Client: name+phone+address. Provider: activities chips + radius slider + phone. Business: business name + Partita IVA (onb-vat) + license upload (onb-license, POST /api/onboarding/business/document) + up to 4 photos (onb-add-photo/onb-photo-del-i, POST/DELETE /api/onboarding/business/photo) + stays approval_status=pending. Submit -> POST /api/onboarding/complete (onb-submit).
  4) Login screen app/onboarding.tsx rebuilt: segmented Accedi/Registrati (seg-signin/seg-signup) with auth-email/auth-password/auth-name + auth-submit; Google (google-login-button); Apple button (iOS only); demo (demo-button).
  5) Admin (/api/admin/ui): Users tab now has a 'Docs' button for business users -> modal showing VAT + license image + business photos (GET /api/admin/users/{id}/documents). admin_users returns vat_number.
  6) Existing users migrated onboarding_completed=true (startup) so they aren't disrupted.
  Curl-verified: register/login (dup=400 email_exists, wrong pw=401), demo read-only guard (GET 200, POST/PUT/DELETE 403), onboarding/complete (business->pending, vat stored), apple invalid token=401, admin docs endpoint.
  TEST both (focus on NEW auth + onboarding + demo; do NOT re-test Phase A which passed iteration 13):
  - Backend: register/login/demo endpoints + validation; demo write guard on a few endpoints; onboarding/complete for each role; onboarding photo add/delete + document set (use a fresh registered account, NOT demo); admin documents endpoint.
  - Frontend (web): login screen shows Accedi/Registrati/Google/Prova la demo (Apple hidden on web = correct). Register a new email -> lands on /onboarding-flow role step. Pick 'client', fill address, finish -> lands on tabs. Demo button -> tabs with demo-banner; attempting a write (e.g., add funds / create request) shows the demo Alert and is blocked.
  Credentials: existing mario@test.it/secret123 (business, pending). Register fresh emails for onboarding tests. Admin token jobby-admin-7c2f9a. Storage key jobby_session_token (JSON.stringify the value on web).

## agent_communication (2026-06 fork — Phase B2: photos + form-builder + cancel/lifecycle + GPS)
-agent: "main"
-message: |
  Implemented (PayPal + payment-services deferred to next delivery, awaiting PayPal keys):
  1) Business photos to clients: GET /api/businesses/detail/{id} and /api/businesses now return business_photos. business-request/[businessId].tsx shows a horizontal photo gallery (testID biz-photo-0..) + existing price list.
  2) Admin form-builder: PUT /api/admin/categories/{cat_id}/questions {questions:[...]} (require_admin) replaces a category's request-form fields. Admin UI (/api/admin/ui Categories tab) has a 'Fields' button per category opening a visual editor (add/remove fields; id, type text|number|select, IT/EN labels, placeholder for text, min/max/default for number, options list for select) -> Save calls the PUT. Frontend request/[id].tsx already renders these dynamically.
  3) Request cancellation + lifecycle: POST /api/missions/{id}/cancel (client only, before booked -> status cancelled; already-booked/cancelled -> 400) and POST /api/business-requests/{id}/cancel (client only, only while pending -> cancelled; else 400). Frontend richieste.tsx shows a 'Annulla richiesta' button (testID cancel-mission-{id} for pending/matched missions, cancel-biz-{id} for pending biz requests) with Alert confirm; 'cancelled' status pill added. Lifecycle unchanged: mission = request -> provider proposal(accept) -> client approval(select->booking); biz = request -> shop approval.
  4) GPS real: new hook src/hooks/use-device-location.ts (real GPS via expo-location, fallback Treviso). Wired into map.tsx and businesses/[category].tsx (map center + nearby query use device GPS). Request forms keep existing 'Use my location' button.
  Curl-verified: PUT questions (driver, 200), mission cancel (200 then 400), biz cancel (200), business detail returns business_photos.
  TEST both (do NOT re-test Phase A/B1):
  - Backend: PUT /api/admin/categories/{id}/questions (valid + 404 unknown cat); mission cancel (client demo-preview-token-123: create+cancel ok, re-cancel 400, cancel someone else's -> 403); business-request cancel (pending ok, non-pending 400); businesses/detail returns business_photos & price_list.
  - Frontend (web, client demo-preview-token-123): Richieste tab -> a pending mission/biz request shows 'Annulla richiesta' button; tapping it and confirming removes/marks cancelled. Proximity flow -> a business with photos shows the photo gallery (biz-photo-0) on the business-request screen.
  - Admin UI: /api/admin/ui (token jobby-admin-7c2f9a) -> Categories -> 'Fields' on a category opens editor; add a field, Save; reopening shows it persisted.
  Credentials: client demo-preview-token-123; business user_2f996c8a010a; admin token jobby-admin-7c2f9a.

## agent_communication (2026-06 fork — Phase C: Payment services structure + transaction history)
-agent: "main"
-message: |
  Implemented payment SERVICES structure (simulated charge; real Aimon/OpenAPI/YOB PAY + PayPal wired later once user gives PayPal keys):
  Backend (routers/payments_services.py, mounted):
  - GET /api/payments/options?country=IT -> {operators:[10 IT mobile ops], billers:[14 IT utility providers]}.
  - Beneficiaries: GET /api/beneficiaries[?type=abroad|local], POST /api/beneficiaries {name,type,iban,swift,bank_name,country} (400 invalid_type/name_required/iban_required), DELETE /api/beneficiaries/{id}.
  - POST /api/payments/service {kind:topup|bill|abroad|local, amount, source:wallet|card, operator_id/phone_number | biller_id/bill_ref | beneficiary_id}. Validations: invalid_kind/amount/source, operator_required, phone_required, biller_required, beneficiary_required. Charge: source=wallet blocks with 400 insufficient_funds if amount>balance and deducts; source=card requires user.payment_method else 400 no_card (simulated, no real charge). Records a transaction {type:service, kind, label, amount:-x, source, jobby_benefit, meta}.
  - GET /api/payments/history?kind=all|topup|bill|abroad|local -> filterable list from transactions (type=service).
  Frontend (new app/pay/*):
  - /pay hub (testID pay-topup/pay-bill/pay-abroad/pay-local, pay-history, pay-beneficiaries) shows wallet balance + 4 service tiles.
  - /pay/[kind] dynamic screen: topup(svc-operator dropdown+svc-phone), bill(svc-biller dropdown+svc-billref), abroad/local(svc-beneficiary dropdown + svc-add-ben link). svc-amount, source toggle (svc-src-wallet/svc-src-card), svc-pay. Handles insufficient/no_card with alerts.
  - /pay/beneficiaries: list + add form (ben-type-abroad/local, ben-name, ben-iban, ben-swift, ben-bank, ben-country, ben-save; ben-del-{id}).
  - /pay/history: filter chips (hist-filter-all/topup/bill/abroad/local) + list.
  - Home 'Pagamenti' tile now routes to /pay.
  Curl-verified: options (10 ops/14 billers), create beneficiary, topup wallet (benefit 0.4), abroad wallet (benefit 2.5), insufficient_funds 400, history all=2 topup=1.
  TEST both (do NOT retest Phase A/B1/B2). Client demo-preview-token-123 (client), storage key jobby_session_token JSON.stringify. NOTE: demo user demo@jobby.app is read-only (blocked) — use demo-preview-token-123 which is a normal client. Admin token jobby-admin-7c2f9a.
  Frontend flows: /pay hub -> topup: pick operator + phone + amount + wallet -> Pay -> success -> lands on history; bill similarly; abroad: add a beneficiary via svc-add-ben then select + amount + pay; history filter chips filter list. PayPal NOT built yet (awaiting keys) — do not test PayPal.

## agent_communication (2026-06 fork — PayPal real integration, SANDBOX)
-agent: "main"
-message: |
  PayPal integrated (SANDBOX — keys provided authenticate only against api-m.sandbox.paypal.com; live keys pending). routers/payments_paypal.py:
  - PUT /api/wallet/paypal-email {email} -> stores provider payout email (400 invalid_email).
  - POST /api/bookings/{id}/paypal/create {origin_url} -> creates PayPal v2 order for booking.total (EUR), returns {order_id, url(approval)}; 404 booking_not_found, 403 forbidden (non-owner), already_paid short-circuit.
  - POST /api/paypal/capture/{order_id} -> captures order, marks booking paid (idempotent via credited flag), records transaction.
  - POST /api/bookings/{id}/payout -> provider withdraws labor_cost to their paypal_email via PayPal Payouts; 400 not_paid / already_paid_out / no_paypal_email, 403 non-provider.
  Frontend: booking/[id].tsx has 'Paga con PayPal' (paypal-button) beside Stripe, handles web return via ?token=<order_id> -> capture, and provider 'Ritira su PayPal' (payout-button) when booking paid+completed + payout-banner when done. payments-settings.tsx has PayPal email field (paypal-row/paypal-email/save-paypal). wallet GET returns paypal_email.
  Curl-verified: OAuth token OK (sandbox), set paypal-email OK, order create returns real sandbox approval URL + order_id (booking bkg_77489dbd2535). Capture & payout require a PayPal sandbox BUYER login -> cannot be automated in preview.
  TEST backend only (do NOT retest other phases): validate error/permission paths WITHOUT completing a real PayPal approval:
  - PUT /api/wallet/paypal-email valid + invalid_email (Bearer demo-preview-token-123).
  - POST /api/bookings/{id}/paypal/create: 404 for unknown booking; 403 when a different user (biz-test-token-999) tries to pay a booking owned by demo-preview-token-123; success returns order_id+url for an unpaid booking owned by the client.
  - POST /api/bookings/{id}/payout: 400 not_paid for an unpaid booking (provider bearer); 403 when a non-provider calls it. (Do NOT expect a real payout to succeed.)
  Credentials: client demo-preview-token-123; other user biz-test-token-999; admin jobby-admin-7c2f9a.

## agent_communication (2026-06 fork — Escrow + Wallet 3-balance + Withdraw)
-agent: "main"
-message: |
  Implemented escrow-based booking payments + 3-balance wallet + withdrawals:
  WALLET: wallet_balance = AVAILABLE, pending_balance = BLOCKED. GET /api/wallet returns available_balance, pending_balance, total_balance, holds[], transactions, bank/crypto/paypal. Lazy maturation: matured wallet_holds (release_at<=now) auto-move from pending->available on wallet read.
  ESCROW (escrow.py): booking has escrow_status none|held|released|refunded + escrow_amount.
  - POST /api/bookings/{id}/pay-escrow (client): blocks booking.total from AVAILABLE wallet (400 insufficient_funds if not enough; 403 non-owner). Sets escrow_status=held, payment_status=paid, deducts client available.
  - POST /api/bookings/{id}/complete: on client/member confirmation, releases held escrow -> provider gets labor_cost; if provider.role==business -> credited to AVAILABLE immediately; else (generic provider) -> credited to PENDING + a wallet_hold with release_at=now+hold_days (default 2, admin-configurable). Platform keeps jobby_fee.
  - POST /api/bookings/{id}/cancel (client, before completion) -> refunds held escrow to client available, status cancelled.
  - Dispute against provider on held escrow -> refunds client.
  WITHDRAW: POST /api/wallet/withdraw {method:bank|crypto|yobpay, amount, target_id?} deducts AVAILABLE (400 insufficient_available / no_bank_account / no_crypto_wallet / invalid_method), records payout (yobpay=processing structure-only, bank/crypto=sent simulated) + transaction. GET /api/wallet/payouts lists them.
  ADMIN: GET/POST /api/admin/settings/hold-days {days} (0..30).
  Frontend: wallet.tsx shows Totale/Disponibile/Bloccato + pending holds (release date) + withdraw section (wm-bank/wm-crypto/wm-yobpay, withdraw-amount, withdraw-btn). booking/[id].tsx client 'Blocca in garanzia' (escrow-button) -> pay-escrow; insufficient -> alert offering Deposit->/wallet; escrow held shows paid-banner; client cancel-booking-button refunds; provider sees earning-banner (funds -> wallet). payments-settings.tsx has PayPal email field.
  Curl-verified end-to-end: insufficient(400)->add funds->pay-escrow held (client avail down)->complete->provider PENDING 25 + hold release_at +2d; forced-mature moved pending->available; admin hold-days set/get; withdraw yobpay ok + insufficient 400 + no_bank_account.
  TEST both (do NOT retest earlier phases). Client demo-preview-token-123 (client), storage key jobby_session_token JSON.stringify. Admin token jobby-admin-7c2f9a. To test a fresh escrow cycle, find an UNPAID booking owned by the client (GET /api/bookings) with escrow_status none/absent; ensure client has enough available (POST /api/wallet/add) then pay-escrow -> complete -> verify provider pending/available and client transactions. Also test wallet withdraw (yobpay works without bank) and the wallet screen 3 balances render + withdraw flow on web.
