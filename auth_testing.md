# JOBBY Auth Testing (Phase B1 — Auth methods + Onboarding + Demo)

## Methods
- Email/Password (works everywhere incl. web preview)
- Google (Emergent-managed, existing)
- Apple Sign In (iOS native build ONLY — not testable in Expo Go/web)
- Demo mode (read-only account)

## Endpoints
- POST /api/auth/register {email, password, name} -> {user, session_token}
- POST /api/auth/login {email, password} -> {user, session_token}
- POST /api/auth/apple {identity_token, name?, email?} -> {user, session_token}
- POST /api/auth/demo -> {user, session_token} (read-only demo user)
- GET  /api/auth/me (Bearer)
- Onboarding: POST /api/onboarding/complete, POST /api/onboarding/business/photo, DELETE /api/onboarding/business/photo/{i}, POST /api/onboarding/business/document

## Demo read-only
Backend middleware blocks POST/PUT/DELETE/PATCH for is_demo users on any /api path except /api/auth/*. Returns 403 {"detail":"demo_readonly"}.

## Apple
APPLE_AUDIENCES in backend/.env = "com.frafra1067.jobbyclean,host.exp.Exponent". Verified vs Apple JWKS (RS256), issuer https://appleid.apple.com. User keyed by apple_sub. Name/email only on first sign-in.

## Test creds
- CLIENT: demo-preview-token-123
- BUSINESS: biz-test-token-999
- Admin token: jobby-admin-7c2f9a
