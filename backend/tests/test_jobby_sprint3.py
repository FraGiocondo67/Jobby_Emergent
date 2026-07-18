"""JOBBY Sprint 3 backend tests — categories DB, roles, verification, wallet,
request status flow, trust score, admin gating."""
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    # frontend/.env value (public preview)
    BASE_URL = "https://jobby-mvp-update.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_TOKEN = "jobby-admin-7c2f9a"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _mk_user(role="client"):
    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    uid = f"TEST_user_{uuid.uuid4().hex[:8]}"
    token = f"TEST_tok_{uuid.uuid4().hex[:12]}"
    db.users.insert_one({
        "user_id": uid, "email": f"{uid}@test.com", "name": "Tester", "picture": "",
        "role": role, "language": "it", "bio": "", "business_name": "",
        "hourly_rate": 13.0, "radius_km": 10.0, "services": [], "online": False,
        "rating": 0.0, "reviews_count": 0, "verified": False,
        "verification_status": "unverified", "wallet_balance": 500.0,
        "payment_method": None, "bank_account": None,
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
    db.transactions.delete_many({"user_id": uid})
    db.service_requests.delete_many({"user_id": uid})
    db.trust_events.delete_many({"user_id": uid})
    db.client_trust_events.delete_many({"user_id": uid})
    db.reviews.delete_many({"customer_id": uid})
    db.disputes.delete_many({"customer_id": uid})
    mongo.close()


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- Categories ----------------
class TestCategories:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_grouped_9_16_4(self):
        r = requests.get(f"{API}/categories", headers=H(self.tok))
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["standard"]) == 9, [c["cat_id"] for c in data["standard"]]
        assert len(data["proximity"]) == 16
        assert len(data["payment"]) == 4
        assert "providers_online" in data
        assert isinstance(data["manifesto"], list) and len(data["manifesto"]) >= 6

    def test_get_single_category_with_questions(self):
        for cid in ("pulizie", "lavanderia", "ricarica"):
            r = requests.get(f"{API}/categories/{cid}", headers=H(self.tok))
            assert r.status_code == 200, f"{cid} -> {r.status_code}"
            body = r.json()
            assert body["cat_id"] == cid
            assert "questions" in body and isinstance(body["questions"], list) and body["questions"]

    def test_unknown_category_404(self):
        r = requests.get(f"{API}/categories/does_not_exist", headers=H(self.tok))
        assert r.status_code == 404

    def test_401_without_auth(self):
        r = requests.get(f"{API}/categories")
        assert r.status_code == 401


# ---------------- Admin ----------------
class TestAdminCategories:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_admin_requires_token(self):
        assert requests.get(f"{API}/admin/categories").status_code == 403
        assert requests.get(f"{API}/admin/categories", headers={"X-Admin-Token": "wrong"}).status_code == 403
        r = requests.get(f"{API}/admin/categories", headers={"X-Admin-Token": ADMIN_TOKEN})
        assert r.status_code == 200
        assert len(r.json()) >= 29

    def test_toggle_deactivates_and_reactivates(self):
        cat_id = "sarta"
        # off
        r = requests.post(f"{API}/admin/categories/{cat_id}/toggle",
                          headers={"X-Admin-Token": ADMIN_TOKEN})
        assert r.status_code == 200 and r.json()["active"] is False
        # gone from public listing
        listing = requests.get(f"{API}/categories", headers=H(self.tok)).json()
        ids = [c["cat_id"] for c in listing["standard"]]
        assert cat_id not in ids
        # on again
        r = requests.post(f"{API}/admin/categories/{cat_id}/toggle",
                          headers={"X-Admin-Token": ADMIN_TOKEN})
        assert r.status_code == 200 and r.json()["active"] is True
        listing = requests.get(f"{API}/categories", headers=H(self.tok)).json()
        assert cat_id in [c["cat_id"] for c in listing["standard"]]

    def test_admin_recalc(self):
        r = requests.post(f"{API}/admin/trust/recalc",
                          headers={"X-Admin-Token": ADMIN_TOKEN})
        assert r.status_code == 200
        assert r.json()["recalculated"] >= 1
        # non-admin blocked
        assert requests.post(f"{API}/admin/trust/recalc").status_code == 403


# ---------------- Profile / Roles ----------------
class TestRoles:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_switch_roles(self):
        for role in ("provider", "business", "client"):
            r = requests.put(f"{API}/profile", headers=H(self.tok),
                             json={"role": role, "services": ["pulizie"]})
            assert r.status_code == 200
            assert r.json()["role"] == role
            assert r.json()["services"] == ["pulizie"]


# ---------------- Verification ----------------
class TestVerification:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_start_then_complete(self):
        r = requests.post(f"{API}/verification/start", headers=H(self.tok))
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

        me = requests.get(f"{API}/auth/me", headers=H(self.tok)).json()
        assert me["verification_status"] == "pending"

        r = requests.post(f"{API}/verification/complete", headers=H(self.tok))
        assert r.status_code == 200
        assert r.json()["status"] == "verified"

        me = requests.get(f"{API}/auth/me", headers=H(self.tok)).json()
        assert me["verification_status"] == "verified"
        assert me["verified"] is True

        trust = requests.get(f"{API}/trust", headers=H(self.tok)).json()
        assert trust["provider_subscores"]["kyc"] == 100


# ---------------- Wallet ----------------
class TestWallet:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_wallet_shape(self):
        r = requests.get(f"{API}/wallet", headers=H(self.tok))
        assert r.status_code == 200
        d = r.json()
        assert "balance" in d and "payment_method" in d and "bank_account" in d

    def test_set_payment_method(self):
        r = requests.put(f"{API}/wallet/payment-method", headers=H(self.tok),
                         json={"card_holder": "Tester T", "card_last4": "4242",
                               "card_brand": "visa", "expiry": "12/28"})
        assert r.status_code == 200
        pm = r.json()["payment_method"]
        assert pm["card_last4"] == "4242"
        w = requests.get(f"{API}/wallet", headers=H(self.tok)).json()
        assert w["payment_method"]["card_last4"] == "4242"

    def test_set_bank_account_iban_masked(self):
        iban = "IT60X0542811101000000123456"
        r = requests.put(f"{API}/wallet/bank-account", headers=H(self.tok),
                         json={"account_holder": "Tester T", "iban": iban})
        assert r.status_code == 200
        ba = r.json()["bank_account"]
        assert ba["iban"].endswith(iban[-6:])
        assert ba["iban"].startswith("*")

    def test_add_reject_zero_and_negative(self):
        assert requests.post(f"{API}/wallet/add", headers=H(self.tok), json={"amount": 0}).status_code == 400
        assert requests.post(f"{API}/wallet/add", headers=H(self.tok), json={"amount": -10}).status_code == 400

    def test_payments_reject_zero(self):
        r = requests.post(f"{API}/payments", headers=H(self.tok),
                          json={"service_id": "ricarica", "label": "top-up", "amount": 0, "answers": {}})
        assert r.status_code == 400


# ---------------- Request status flow ----------------
class TestRequestFlow:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def test_full_status_flow(self):
        # create
        r = requests.post(f"{API}/missions", headers=H(self.tok), json={
            "category": "pulizie", "service_type": "pulizie", "config": {},
            "address": "Treviso", "lat": 45.6669, "lng": 12.2433,
            "date": "2025-12-01", "time": "10:00", "duration_hours": 2,
            "recurrence": "once",
        })
        assert r.status_code == 200, r.text
        mission = r.json()
        mid = mission["mission_id"]
        assert mission["status"] == "pending"

        # bots auto-accept -> matched within ~10s
        accepted = None
        for _ in range(20):
            m = requests.get(f"{API}/missions/{mid}", headers=H(self.tok)).json()
            if m.get("accepted"):
                accepted = m
                break
            time.sleep(0.7)
        assert accepted, "no bot accepted within timeout"
        assert accepted["status"] == "matched"

        # select
        provider_id = accepted["accepted"][0]["provider_id"]
        r = requests.post(f"{API}/missions/{mid}/select",
                          headers=H(self.tok), json={"provider_id": provider_id})
        assert r.status_code == 200
        booking = r.json()
        assert booking["status"] == "confirmed"
        bid = booking["booking_id"]

        # start
        r = requests.post(f"{API}/bookings/{bid}/start", headers=H(self.tok))
        assert r.status_code == 200
        b = r.json()
        assert b["status"] == "in_progress"
        assert b["check_in_on_time"] is True

        # complete
        r = requests.post(f"{API}/bookings/{bid}/complete", headers=H(self.tok))
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

        # save for downstream trust test
        self.__class__.bid = bid
        self.__class__.provider_id = provider_id


# ---------------- Trust ----------------
class TestTrust:
    def setup_method(self):
        self.uid, self.tok = _mk_user()

    def teardown_method(self):
        _cleanup(self.uid)

    def _create_completed_booking(self):
        r = requests.post(f"{API}/missions", headers=H(self.tok), json={
            "category": "pulizie", "service_type": "pulizie", "config": {},
            "address": "Treviso", "lat": 45.6669, "lng": 12.2433,
            "date": "2025-12-01", "time": "10:00", "duration_hours": 2,
            "recurrence": "once",
        })
        mid = r.json()["mission_id"]
        for _ in range(20):
            m = requests.get(f"{API}/missions/{mid}", headers=H(self.tok)).json()
            if m.get("accepted"):
                break
            time.sleep(0.7)
        pid = m["accepted"][0]["provider_id"]
        booking = requests.post(f"{API}/missions/{mid}/select",
                                headers=H(self.tok),
                                json={"provider_id": pid}).json()
        bid = booking["booking_id"]
        requests.post(f"{API}/bookings/{bid}/start", headers=H(self.tok))
        requests.post(f"{API}/bookings/{bid}/complete", headers=H(self.tok))
        return bid, pid

    def test_review_updates_provider_trust(self):
        bid, pid = self._create_completed_booking()
        r = requests.post(f"{API}/bookings/{bid}/review", headers=H(self.tok),
                          json={"rating": 5, "comment": "great"})
        assert r.status_code == 200

        # login as the bot provider by inserting a session for it
        mongo = MongoClient(MONGO_URL)
        db = mongo[DB_NAME]
        tok = f"TEST_tok_{uuid.uuid4().hex[:12]}"
        db.user_sessions.insert_one({
            "session_token": tok, "user_id": pid,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        })
        mongo.close()

        try:
            t = requests.get(f"{API}/trust", headers=H(tok)).json()
            assert t["provider_score"] > 0
            subs = t["provider_subscores"]
            for k in ("kyc", "punctuality", "quality", "communication",
                      "cancellation", "completed", "dispute", "tenure"):
                assert k in subs, f"missing subscore {k}"
            assert any(e.get("type") == "review" for e in t["events"])
        finally:
            mongo = MongoClient(MONGO_URL)
            mongo[DB_NAME].user_sessions.delete_one({"session_token": tok})
            mongo.close()

    def test_rate_client_logs_event_and_score(self):
        bid, pid = self._create_completed_booking()
        # provider rates client — call as bot provider by inserting a session
        mongo = MongoClient(MONGO_URL)
        db = mongo[DB_NAME]
        ptok = f"TEST_tok_{uuid.uuid4().hex[:12]}"
        db.user_sessions.insert_one({
            "session_token": ptok, "user_id": pid,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        })
        mongo.close()
        try:
            r = requests.post(f"{API}/bookings/{bid}/rate-client",
                              headers=H(ptok),
                              json={"rating": 5, "brief_accuracy": 5, "tip": 2.0})
            assert r.status_code == 200
        finally:
            mongo = MongoClient(MONGO_URL)
            mongo[DB_NAME].user_sessions.delete_one({"session_token": ptok})
            mongo.close()

        t = requests.get(f"{API}/trust", headers=H(self.tok)).json()
        assert t["client_score"] > 0
        assert any(e.get("type") == "client_rated" for e in t["client_events"])

    def test_dispute_recomputes_both(self):
        bid, pid = self._create_completed_booking()
        r = requests.post(f"{API}/bookings/{bid}/dispute", headers=H(self.tok),
                          json={"reason": "not done"})
        assert r.status_code == 200
        b = requests.get(f"{API}/bookings/{bid}", headers=H(self.tok)).json()
        assert b["status"] == "disputed"
        t = requests.get(f"{API}/trust", headers=H(self.tok)).json()
        assert any(e.get("type") == "dispute" for e in t["client_events"])


# ---------------- Auth guards ----------------
class TestAuthGuards:
    @pytest.mark.parametrize("path,method", [
        ("/categories", "GET"),
        ("/categories/pulizie", "GET"),
        ("/wallet", "GET"),
        ("/trust", "GET"),
        ("/missions", "GET"),
        ("/verification/start", "POST"),
        ("/verification/complete", "POST"),
    ])
    def test_401_without_bearer(self, path, method):
        r = requests.request(method, f"{API}{path}")
        assert r.status_code == 401, f"{path} -> {r.status_code}"
