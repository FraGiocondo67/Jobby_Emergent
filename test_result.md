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
