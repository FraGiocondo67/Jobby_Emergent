"""JOBBY backend — Iteration 2 tests for NEW endpoints:
categories, wallet, payments, service requests, chat, and Modello D on ANY category.
Auth = Emergent Google OAuth. We seed a user + user_sessions doc directly in MongoDB
to obtain a Bearer token.
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path("/app/backend/.env"))
load_dotenv(Path("/app/frontend/.env"))

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
TREVISO = {"lat": 45.6669, "lng": 12.2433}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def _mk_user(mongo, role="customer", wallet_balance=92.29, services=None):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    token = f"tok_{uuid.uuid4().hex}"
    email = f"TEST_{uid}@jobby.test"
    mongo.users.insert_one({
        "user_id": uid, "email": email, "name": f"TEST {role}",
        "picture": "", "role": role, "language": "it", "bio": "",
        "hourly_rate": 13.0, "radius_km": 15.0,
        "services": services or ["cleaning", "ironing"],
        "online": role == "provider", "rating": 0.0, "reviews_count": 0,
        "verified": role == "provider",
        "wallet_balance": wallet_balance,
        "lat": TREVISO["lat"], "lng": TREVISO["lng"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "session_token": token, "user_id": uid,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    })
    return uid, token, email


def _cleanup_user(mongo, uid):
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})
    mongo.transactions.delete_many({"user_id": uid})
    mongo.service_requests.delete_many({"user_id": uid})
    mongo.missions.delete_many({"customer_id": uid})
    mongo.bookings.delete_many({"customer_id": uid})
    mongo.conversations.delete_many({"user_id": uid})


@pytest.fixture(scope="session")
def customer(mongo):
    uid, token, email = _mk_user(mongo, role="customer", wallet_balance=100.0)
    yield {"user_id": uid, "token": token, "email": email}
    _cleanup_user(mongo, uid)


def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Categories ----------------
class TestCategories:
    def test_list_categories_shape(self):
        r = requests.get(f"{API}/categories")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "categories" in body and "providers_online" in body and "manifesto" in body
        cats = body["categories"]
        assert len(cats) == 9, f"expected 9 categories, got {len(cats)}"

        ids = [c["id"] for c in cats]
        for expected in ("pulizie", "babysitting", "petsitting", "tuttofare",
                         "hospitality", "assistenza", "tecnico",
                         "prossimita", "pagamenti"):
            assert expected in ids, f"missing category {expected}"

        # 7 service-type categories
        service_cats = [c for c in cats if c["type"] == "service"]
        assert len(service_cats) == 7, f"expected 7 service categories, got {len(service_cats)}"

        # Prossimità badge/subcategories=7
        prox = next(c for c in cats if c["id"] == "prossimita")
        assert prox["type"] == "proximity"
        assert prox["badge"] == 7
        assert len(prox["subcategories"]) == 7

        # Pagamenti badge/subcategories=4
        pay = next(c for c in cats if c["id"] == "pagamenti")
        assert pay["type"] == "payment"
        assert pay["badge"] == 4
        assert len(pay["subcategories"]) == 4

        # providers_online should be >= seeded bots (8)
        assert body["providers_online"] >= 1

        # manifesto is array of {it,en}
        assert isinstance(body["manifesto"], list) and len(body["manifesto"]) >= 1
        for m in body["manifesto"]:
            assert "it" in m and "en" in m

    def test_get_category_with_questions(self):
        r = requests.get(f"{API}/categories/pulizie")
        assert r.status_code == 200
        c = r.json()
        assert c["id"] == "pulizie"
        assert "questions" in c and len(c["questions"]) >= 1

    def test_get_subcategory_ricarica(self):
        r = requests.get(f"{API}/categories/ricarica")
        assert r.status_code == 200
        c = r.json()
        assert c["id"] == "ricarica"
        assert c["parent"] == "pagamenti"
        assert c["parent_type"] == "payment"
        assert "questions" in c and any(q["id"] == "amount" for q in c["questions"])

    def test_get_subcategory_lavanderia(self):
        r = requests.get(f"{API}/categories/lavanderia")
        assert r.status_code == 200
        c = r.json()
        assert c["id"] == "lavanderia"
        assert c["parent"] == "prossimita"
        assert c["parent_type"] == "proximity"

    def test_get_category_not_found(self):
        r = requests.get(f"{API}/categories/does-not-exist")
        assert r.status_code == 404


# ---------------- Wallet ----------------
class TestWallet:
    def test_wallet_default_balance(self, mongo):
        # New user should default to 92.29
        uid, token, _ = _mk_user(mongo, role="customer", wallet_balance=92.29)
        try:
            r = requests.get(f"{API}/wallet", headers=hdr(token))
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["balance"] == 92.29
            assert isinstance(data["transactions"], list)
        finally:
            _cleanup_user(mongo, uid)

    def test_wallet_topup_creates_transaction(self, customer, mongo):
        # get starting balance
        r0 = requests.get(f"{API}/wallet", headers=hdr(customer["token"]))
        assert r0.status_code == 200
        start = r0.json()["balance"]

        r = requests.post(f"{API}/wallet/add", json={"amount": 25.5}, headers=hdr(customer["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["balance"] == round(start + 25.5, 2)

        # verify GET reflects
        r2 = requests.get(f"{API}/wallet", headers=hdr(customer["token"]))
        assert r2.status_code == 200
        data = r2.json()
        assert data["balance"] == round(start + 25.5, 2)
        topups = [t for t in data["transactions"] if t.get("type") == "topup"]
        assert len(topups) >= 1
        assert topups[0]["amount"] == 25.5
        assert topups[0]["label"] == "Wallet top-up"


# ---------------- Payments ----------------
class TestPayments:
    def test_payment_deducts_balance_and_creates_request(self, mongo):
        uid, token, _ = _mk_user(mongo, role="customer", wallet_balance=100.0)
        try:
            payload = {"service_id": "ricarica", "label": "Mobile top-up",
                       "amount": 10.0, "answers": {"phone": "+39 333 1234567", "amount": 10}}
            r = requests.post(f"{API}/payments", json=payload, headers=hdr(token))
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["balance"] == 90.0
            assert data["tx"]["type"] == "payment"
            assert data["tx"]["amount"] == -10.0
            assert data["tx"]["service_id"] == "ricarica"

            # verify wallet balance persisted
            w = requests.get(f"{API}/wallet", headers=hdr(token)).json()
            assert w["balance"] == 90.0
            neg = [t for t in w["transactions"] if t.get("type") == "payment"]
            assert len(neg) == 1 and neg[0]["amount"] == -10.0

            # verify service request created
            reqs = requests.get(f"{API}/requests", headers=hdr(token)).json()
            assert "payments" in reqs and "missions" in reqs
            pay_reqs = reqs["payments"]
            assert len(pay_reqs) == 1
            assert pay_reqs[0]["kind"] == "payment"
            assert pay_reqs[0]["category_id"] == "ricarica"
            assert pay_reqs[0]["amount"] == 10.0
            assert pay_reqs[0]["status"] == "completed"
        finally:
            _cleanup_user(mongo, uid)

    def test_payment_insufficient_funds_400(self, mongo):
        uid, token, _ = _mk_user(mongo, role="customer", wallet_balance=5.0)
        try:
            r = requests.post(f"{API}/payments",
                              json={"service_id": "estero", "label": "Send abroad",
                                    "amount": 200.0, "answers": {}},
                              headers=hdr(token))
            assert r.status_code == 400
            assert r.json().get("detail") == "insufficient_funds"

            # balance unchanged
            w = requests.get(f"{API}/wallet", headers=hdr(token)).json()
            assert w["balance"] == 5.0
        finally:
            _cleanup_user(mongo, uid)


# ---------------- Requests (Richieste) ----------------
class TestRequests:
    def test_requests_returns_payments_and_missions(self, mongo):
        uid, token, _ = _mk_user(mongo, role="customer", wallet_balance=100.0)
        try:
            # make a payment
            requests.post(f"{API}/payments",
                          json={"service_id": "bollette", "label": "Pay bills",
                                "amount": 30.0, "answers": {"biller": "Enel"}},
                          headers=hdr(token))
            # create a mission
            m = requests.post(f"{API}/missions", json={
                "category": "cleaning", "service_type": "home", "config": {},
                "address": "Via Test", "lat": TREVISO["lat"], "lng": TREVISO["lng"],
                "date": "2026-03-01", "time": "10:00", "duration_hours": 2.0,
                "recurrence": "once",
            }, headers=hdr(token))
            assert m.status_code == 200

            r = requests.get(f"{API}/requests", headers=hdr(token))
            assert r.status_code == 200
            data = r.json()
            assert len(data["payments"]) == 1
            assert data["payments"][0]["category_id"] == "bollette"
            assert len(data["missions"]) >= 1
            assert data["missions"][0]["customer_id"] == uid
        finally:
            _cleanup_user(mongo, uid)


# ---------------- Chat ----------------
class TestChat:
    def test_conversations_auto_created_from_booking(self, mongo):
        uid, token, _ = _mk_user(mongo, role="customer", wallet_balance=100.0)
        try:
            # Create mission + wait for bot accept + select -> booking
            m = requests.post(f"{API}/missions", json={
                "category": "cleaning", "service_type": "home", "config": {},
                "address": "Via Chat", "lat": TREVISO["lat"], "lng": TREVISO["lng"],
                "date": "2026-03-02", "time": "10:00", "duration_hours": 2.0,
                "recurrence": "once",
            }, headers=hdr(token))
            assert m.status_code == 200
            mission_id = m.json()["mission_id"]
            accepted = []
            for _ in range(15):
                time.sleep(1)
                g = requests.get(f"{API}/missions/{mission_id}", headers=hdr(token)).json()
                accepted = g.get("accepted", [])
                if accepted:
                    break
            assert accepted, "no bot accepted"
            sel = requests.post(f"{API}/missions/{mission_id}/select",
                                json={"provider_id": accepted[0]["provider_id"]},
                                headers=hdr(token))
            assert sel.status_code == 200

            # GET conversations should auto-create one per partner
            r = requests.get(f"{API}/chat/conversations", headers=hdr(token))
            assert r.status_code == 200, r.text
            convos = r.json()
            assert len(convos) >= 1
            convo = next(c for c in convos if c["other_id"] == accepted[0]["provider_id"])
            cid = convo["conversation_id"]

            # Send a message
            s = requests.post(f"{API}/chat/{cid}",
                              json={"text": "TEST hello provider"},
                              headers=hdr(token))
            assert s.status_code == 200
            msg = s.json()
            assert msg["text"] == "TEST hello provider"
            assert msg["sender_id"] == uid

            # Get conversation + messages
            g = requests.get(f"{API}/chat/{cid}", headers=hdr(token))
            assert g.status_code == 200
            data = g.json()
            assert data["conversation"]["conversation_id"] == cid
            assert data["conversation"]["last_message"] == "TEST hello provider"
            assert len(data["messages"]) >= 1
            assert data["messages"][-1]["text"] == "TEST hello provider"

            # cleanup
            mongo.messages.delete_many({"conversation_id": cid})
            mongo.conversations.delete_many({"conversation_id": cid})
            mongo.bookings.delete_many({"customer_id": uid})
            mongo.missions.delete_many({"mission_id": mission_id})
        finally:
            _cleanup_user(mongo, uid)

    def test_chat_unknown_conversation_404(self, customer):
        r = requests.get(f"{API}/chat/conv_doesnotexist", headers=hdr(customer["token"]))
        assert r.status_code == 404
        r2 = requests.post(f"{API}/chat/conv_doesnotexist",
                           json={"text": "hi"}, headers=hdr(customer["token"]))
        assert r2.status_code == 404


# ---------------- Modello D on ANY category ----------------
class TestModelloDAnyCategory:
    @pytest.mark.parametrize("category", ["babysitting", "tecnico"])
    def test_bots_accept_any_category(self, mongo, category):
        uid, token, _ = _mk_user(mongo, role="customer")
        try:
            r = requests.post(f"{API}/missions", json={
                "category": category, "service_type": "generic",
                "config": {}, "address": "Via Any 1",
                "lat": TREVISO["lat"], "lng": TREVISO["lng"],
                "date": "2026-04-01", "time": "09:00",
                "duration_hours": 2.0, "recurrence": "once",
            }, headers=hdr(token))
            assert r.status_code == 200, r.text
            mission = r.json()
            mission_id = mission["mission_id"]
            assert mission["category"] == category
            # Bots must be invited regardless of category
            assert len(mission["invited_provider_ids"]) >= 1, \
                f"expected bots to be invited for category={category}"

            # Wait for at least one bot to accept
            accepted = []
            for _ in range(15):
                time.sleep(1)
                g = requests.get(f"{API}/missions/{mission_id}", headers=hdr(token)).json()
                accepted = g.get("accepted", [])
                if accepted:
                    break
            assert accepted, f"no bot accepted for category={category} within 15s"

            # Select and confirm booking
            sel = requests.post(f"{API}/missions/{mission_id}/select",
                                json={"provider_id": accepted[0]["provider_id"]},
                                headers=hdr(token))
            assert sel.status_code == 200
            b = sel.json()
            assert b["category"] == category
            assert b["status"] == "confirmed"

            mongo.missions.delete_one({"mission_id": mission_id})
            mongo.bookings.delete_one({"booking_id": b["booking_id"]})
        finally:
            _cleanup_user(mongo, uid)


# ---------------- Auth guards on NEW endpoints ----------------
class TestAuthGuardsNewEndpoints:
    @pytest.mark.parametrize("method,path,body", [
        ("GET", "/wallet", None),
        ("POST", "/wallet/add", {"amount": 10}),
        ("POST", "/payments", {"service_id": "ricarica", "label": "x", "amount": 5, "answers": {}}),
        ("GET", "/requests", None),
        ("GET", "/chat/conversations", None),
        ("GET", "/chat/conv_x", None),
        ("POST", "/chat/conv_x", {"text": "hi"}),
    ])
    def test_endpoint_requires_bearer(self, method, path, body):
        url = f"{API}{path}"
        if method == "GET":
            r = requests.get(url)
        else:
            r = requests.post(url, json=body)
        assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"
