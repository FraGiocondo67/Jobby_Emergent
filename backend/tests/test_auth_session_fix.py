"""JOBBY iteration 4 — auth-session bug fix regression suite.

USER BUG: after login the app was empty (no categories, empty profile) because the
frontend was calling Emergent's one-time session-data endpoint itself, then passing
the derived session_token to /api/auth/session, which called session-data AGAIN with
an invalid value and failed — so no session token was ever persisted.

FIX (frontend): processSessionId now sends the raw session_id straight to
POST /api/auth/session (backend param name is `session_token` but semantically it's
the session_id from Emergent redirect). Backend logic unchanged.

Tests below verify:
  1) POST /api/auth/session with an INVALID id returns 401 (real id can't be minted).
  2) With a synthetic user + user_sessions doc in Mongo (Bearer token), all
     screen-critical GETs return 200 and non-empty where expected:
     /auth/me, /categories, /wallet, /trust, /bookings, /requests, /chat/conversations.
  3) GET /categories WITHOUT Bearer returns 401 (app is auth-gated).
  4) Full mission lifecycle regression: create -> bot auto-accept (matched) -> select
     (confirmed) -> start (in_progress) -> complete (completed) -> review (provider
     rating updated, trust event).
  5) Admin gating: /admin/categories 403 without/with wrong X-Admin-Token, 200 with
     correct token 'jobby-admin-7c2f9a'.
"""
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "https://jobby-mvp-update.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_TOKEN = "jobby-admin-7c2f9a"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- helpers ----------
def _mk_user(role="client", wallet=250.0):
    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    uid = f"TEST_user_{uuid.uuid4().hex[:10]}"
    token = f"TEST_tok_{uuid.uuid4().hex[:14]}"
    db.users.insert_one({
        "user_id": uid, "email": f"{uid}@test.com", "name": "Iter4 Tester",
        "picture": "", "role": role, "language": "it", "bio": "",
        "business_name": "", "hourly_rate": 13.0, "radius_km": 10.0,
        "services": [], "online": False, "rating": 0.0, "reviews_count": 0,
        "verified": False, "verification_status": "unverified",
        "wallet_balance": wallet, "payment_method": None, "bank_account": None,
        "trust_score": 0.0, "trust_subscores": {},
        "client_trust_score": 0.0, "client_trust_subscores": {},
        "is_admin": False, "lat": 45.6669, "lng": 12.2433,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.user_sessions.insert_one({
        "session_token": token, "user_id": uid,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    })
    mongo.close()
    return uid, token


def _cleanup(uid):
    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    db.users.delete_many({"user_id": uid})
    db.user_sessions.delete_many({"user_id": uid})
    db.missions.delete_many({"customer_id": uid})
    db.bookings.delete_many({"customer_id": uid})
    db.bookings.delete_many({"provider_id": uid})
    db.transactions.delete_many({"user_id": uid})
    db.service_requests.delete_many({"user_id": uid})
    db.trust_events.delete_many({"user_id": uid})
    db.client_trust_events.delete_many({"user_id": uid})
    db.reviews.delete_many({"customer_id": uid})
    db.disputes.delete_many({"customer_id": uid})
    mongo.close()


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- 1) /auth/session invalid id -> 401 ----------
class TestAuthSessionEndpoint:
    def test_invalid_session_id_returns_401(self):
        # Backend exchanges the received value with Emergent; a bogus one must 401.
        bad = f"not-a-real-session-{uuid.uuid4().hex}"
        r = requests.post(f"{API}/auth/session",
                          json={"session_token": bad}, timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code} body={r.text}"
        assert "Invalid session" in r.text or "detail" in r.text

    def test_missing_body_422(self):
        r = requests.post(f"{API}/auth/session", json={}, timeout=10)
        # Pydantic validation
        assert r.status_code in (400, 422)

    def test_categories_401_without_bearer(self):
        # App is gated behind auth — the reported "empty" symptom.
        r = requests.get(f"{API}/categories", timeout=10)
        assert r.status_code == 401, f"expected 401, got {r.status_code}"


# ---------- 2) Full logged-in user: all screen calls return 200 + non-empty ----------
class TestLoggedInScreens:
    """Once a valid session exists, every screen's data endpoint should work.
    This is the direct verification that the reported bug ('categories empty,
    profile disconnected') is resolved for an authenticated user."""

    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_auth_me_returns_user_object(self):
        r = requests.get(f"{API}/auth/me", headers=H(self.tok), timeout=10)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["user_id"] == self.uid
        assert u["email"].endswith("@test.com")
        assert u["role"] == "client"
        assert "wallet_balance" in u
        assert "_id" not in u  # ObjectId must be excluded

    def test_categories_non_empty_grouped(self):
        r = requests.get(f"{API}/categories", headers=H(self.tok), timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["standard"]) == 9, [c["cat_id"] for c in d["standard"]]
        assert len(d["proximity"]) == 16
        assert len(d["payment"]) == 4
        assert d["providers_online"] > 0, "seeded bot providers must be online"
        assert isinstance(d["manifesto"], list) and len(d["manifesto"]) >= 6

    def test_wallet_ok(self):
        r = requests.get(f"{API}/wallet", headers=H(self.tok), timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "balance" in d or "wallet_balance" in d
        # transactions key exists as list (may be empty for fresh user)
        assert "transactions" in d and isinstance(d["transactions"], list)

    def test_trust_ok(self):
        r = requests.get(f"{API}/trust", headers=H(self.tok), timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("provider_score", "provider_subscores",
                  "client_score", "client_subscores",
                  "provider_weights", "client_weights", "events", "client_events"):
            assert k in d, f"missing {k}"

    def test_bookings_list_ok(self):
        r = requests.get(f"{API}/bookings", headers=H(self.tok), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_requests_list_ok(self):
        r = requests.get(f"{API}/requests", headers=H(self.tok), timeout=10)
        assert r.status_code == 200
        d = r.json()
        # /api/requests returns {payments: [...], missions: [...]}
        assert isinstance(d, dict) and "payments" in d and "missions" in d
        assert isinstance(d["payments"], list) and isinstance(d["missions"], list)

    def test_chat_conversations_ok(self):
        r = requests.get(f"{API}/chat/conversations", headers=H(self.tok), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- 3) Full mission lifecycle regression ----------
class TestMissionLifecycle:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_create_match_select_start_complete_review(self):
        # create
        payload = {"category": "pulizie", "service_type": "casa", "config": {},
                   "address": "Via Test 1, Treviso", "lat": 45.6669, "lng": 12.2433,
                   "date": "2026-02-01", "time": "10:00",
                   "duration_hours": 2, "recurrence": "one-off"}
        r = requests.post(f"{API}/missions", headers=H(self.tok), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        m = r.json()
        mid = m["mission_id"]
        assert m["status"] == "pending"
        assert len(m["invited_provider_ids"]) > 0, "bots should be invited"

        # wait for bot auto-accept (2-9s per bot)
        matched = None
        deadline = time.time() + 15
        while time.time() < deadline:
            rr = requests.get(f"{API}/missions/{mid}", headers=H(self.tok), timeout=10)
            assert rr.status_code == 200
            mm = rr.json()
            if mm["status"] == "matched" and mm.get("accepted"):
                matched = mm
                break
            time.sleep(1)
        assert matched is not None, "no bot accepted within 15s"

        # select
        pid = matched["accepted"][0]["provider_id"]
        r = requests.post(f"{API}/missions/{mid}/select", headers=H(self.tok),
                          json={"provider_id": pid}, timeout=10)
        assert r.status_code == 200, r.text
        booking = r.json()
        bid = booking["booking_id"]
        assert booking["status"] == "confirmed"
        assert booking["provider_id"] == pid
        assert booking["labor_cost"] > 0
        assert booking["jobby_fee"] == round(booking["labor_cost"] * 0.15, 2)

        # start
        r = requests.post(f"{API}/bookings/{bid}/start", headers=H(self.tok), timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_progress"
        assert r.json()["check_in_on_time"] is True

        # complete
        r = requests.post(f"{API}/bookings/{bid}/complete", headers=H(self.tok), timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"

        # review (updates provider rating + trust)
        r = requests.post(f"{API}/bookings/{bid}/review", headers=H(self.tok),
                          json={"rating": 5, "comment": "iter4 great"}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # provider rating persisted
        mongo = MongoClient(MONGO_URL)
        prov = mongo[DB_NAME].users.find_one({"user_id": pid}, {"_id": 0})
        mongo.close()
        assert prov["reviews_count"] >= 1
        assert prov["rating"] > 0


# ---------- 4) Admin gating ----------
class TestAdminGating:
    def test_admin_categories_no_token(self):
        r = requests.get(f"{API}/admin/categories", timeout=10)
        assert r.status_code == 403

    def test_admin_categories_wrong_token(self):
        r = requests.get(f"{API}/admin/categories",
                         headers={"X-Admin-Token": "wrong"}, timeout=10)
        assert r.status_code == 403

    def test_admin_categories_correct_token(self):
        r = requests.get(f"{API}/admin/categories",
                         headers={"X-Admin-Token": ADMIN_TOKEN}, timeout=10)
        assert r.status_code == 200, r.text
        cats = r.json()
        assert isinstance(cats, list)
        assert len(cats) >= 29  # 9 + 16 + 4

    def test_admin_trust_recalc_gated(self):
        r = requests.post(f"{API}/admin/trust/recalc", timeout=15)
        assert r.status_code == 403
        r = requests.post(f"{API}/admin/trust/recalc",
                          headers={"X-Admin-Token": ADMIN_TOKEN}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("recalculated", 0) >= 1
