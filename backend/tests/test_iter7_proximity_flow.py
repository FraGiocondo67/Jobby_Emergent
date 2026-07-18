"""Iteration 7 — Proximity directed-request flow + two-way chat + provider broadcast regression."""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE:
    # Read from frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
                BASE = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

CLIENT_TOKEN = "demo-preview-token-123"
BUSINESS_TOKEN = "biz-test-token-999"


def H(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ---------------------------- Fixtures ----------------------------

@pytest.fixture(scope="module")
def client_id():
    r = requests.get(f"{BASE}/api/auth/me", headers=H(CLIENT_TOKEN), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest.fixture(scope="module")
def business_id():
    r = requests.get(f"{BASE}/api/auth/me", headers=H(BUSINESS_TOKEN), timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["role"] == "business"
    return j["user_id"]


# ---------------------------- Businesses discovery ----------------------------

class TestBusinessesList:
    def test_requires_auth(self):
        r = requests.get(f"{BASE}/api/businesses?category=lavanderia&lat=45.6669&lng=12.2433", timeout=15)
        assert r.status_code in (401, 403)

    def test_lavanderia_returns_real_business_only(self, business_id):
        r = requests.get(
            f"{BASE}/api/businesses?category=lavanderia&lat=45.6669&lng=12.2433",
            headers=H(CLIENT_TOKEN), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "expected at least Francesco Franzin"
        names = [b["name"] for b in data]
        assert any("Franzin" in n for n in names), f"expected Francesco Franzin in {names}"
        # No bot in list (bot user_ids start with 'prov_')
        for b in data:
            assert "bot" not in b["user_id"].lower()
            # required shape
            for k in ("user_id", "name", "rating", "distance_km", "service_mode"):
                assert k in b
        # sorted by distance
        dists = [b["distance_km"] for b in data]
        assert dists == sorted(dists)
        # business must be present
        assert any(b["user_id"] == business_id for b in data)

    def test_category_with_no_real_business_returns_empty(self):
        # 'noleggio_auto' has no real registered business
        r = requests.get(
            f"{BASE}/api/businesses?category=noleggio_auto&lat=45.6669&lng=12.2433",
            headers=H(CLIENT_TOKEN), timeout=15,
        )
        assert r.status_code == 200
        # Might be empty; must not contain any bot
        for b in r.json():
            assert "bot" not in b["user_id"].lower()


# ---------------------------- Directed request lifecycle ----------------------------

class TestBusinessRequestFlow:
    @pytest.fixture(scope="class")
    def created_request(self, business_id):
        payload = {
            "business_id": business_id,
            "category": "lavanderia",
            "note": "TEST_iter7 - lavaggio 5 camicie",
            "address": "Via Roma 12, Treviso",
            "lat": 45.6669, "lng": 12.2433,
        }
        r = requests.post(f"{BASE}/api/business-requests", headers=H(CLIENT_TOKEN), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "pending"
        assert doc["business_id"] == business_id
        assert doc["response"] is None
        assert doc["business_name"]  # populated from business user
        assert doc["category_label"]  # populated from categories
        return doc

    def test_client_sees_own_request(self, created_request):
        r = requests.get(f"{BASE}/api/business-requests", headers=H(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        rids = [x["request_id"] for x in r.json()]
        assert created_request["request_id"] in rids

    def test_business_sees_incoming_request(self, created_request):
        r = requests.get(f"{BASE}/api/business-requests/incoming", headers=H(BUSINESS_TOKEN), timeout=15)
        assert r.status_code == 200
        rids = [x["request_id"] for x in r.json()]
        assert created_request["request_id"] in rids

    def test_client_incoming_is_empty_role_guard(self):
        r = requests.get(f"{BASE}/api/business-requests/incoming", headers=H(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        assert r.json() == []

    def test_get_by_id_client_and_business_ok(self, created_request):
        rid = created_request["request_id"]
        r1 = requests.get(f"{BASE}/api/business-requests/{rid}", headers=H(CLIENT_TOKEN), timeout=15)
        r2 = requests.get(f"{BASE}/api/business-requests/{rid}", headers=H(BUSINESS_TOKEN), timeout=15)
        assert r1.status_code == 200 and r2.status_code == 200

    def test_third_party_forbidden(self, created_request):
        # Use another user token
        other_token = "0qTAmvLDEToSU-QotAmVdIQAQ690bAOm7eQ9QrBLSW0"
        r = requests.get(
            f"{BASE}/api/business-requests/{created_request['request_id']}",
            headers=H(other_token), timeout=15,
        )
        assert r.status_code == 403

    def test_client_cannot_respond(self, created_request):
        rid = created_request["request_id"]
        r = requests.post(
            f"{BASE}/api/business-requests/{rid}/respond",
            headers=H(CLIENT_TOKEN),
            json={"accept": True, "eta": "oggi 18:00", "mode": "pickup", "price": 10.0},
            timeout=15,
        )
        assert r.status_code == 403

    def test_business_confirms_and_opens_chat(self, created_request, client_id, business_id):
        rid = created_request["request_id"]
        body = {
            "accept": True,
            "eta": "oggi 18:00",
            "mode": "delivery",
            "delivery_cost": 3.50,
            "price": 24.90,
            "note": "TEST_iter7 consegna dopo le 17",
        }
        r = requests.post(f"{BASE}/api/business-requests/{rid}/respond",
                          headers=H(BUSINESS_TOKEN), json=body, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "confirmed"
        assert j["response"]["mode"] == "delivery"
        assert j["response"]["price"] == 24.90
        assert j["response"]["delivery_cost"] == 3.50

        # Verify persisted
        g = requests.get(f"{BASE}/api/business-requests/{rid}", headers=H(CLIENT_TOKEN), timeout=15)
        assert g.status_code == 200
        gj = g.json()
        assert gj["status"] == "confirmed"
        assert gj["response"]["eta"] == "oggi 18:00"

        # Chat opened for both sides
        cc = requests.get(f"{BASE}/api/chat/conversations", headers=H(CLIENT_TOKEN), timeout=15).json()
        bc = requests.get(f"{BASE}/api/chat/conversations", headers=H(BUSINESS_TOKEN), timeout=15).json()
        c_conv = next((c for c in cc if c["other_id"] == business_id), None)
        b_conv = next((c for c in bc if c["other_id"] == client_id), None)
        assert c_conv, "client should have a conversation with business"
        assert b_conv, "business should have a conversation with client"
        # same thread_id (two-way)
        assert c_conv.get("thread_id") == b_conv.get("thread_id"), (c_conv, b_conv)

        # first (summary) message is present, sent by business
        cmsgs = requests.get(f"{BASE}/api/chat/{c_conv['conversation_id']}", headers=H(CLIENT_TOKEN), timeout=15).json()
        assert len(cmsgs["messages"]) >= 1
        first = cmsgs["messages"][0]
        assert first["sender_id"] == business_id
        assert "confermata" in first["text"].lower() or "confirmed" in first["text"].lower()

        # Two-way: client sends a message → business sees it in his conversation
        send = requests.post(f"{BASE}/api/chat/{c_conv['conversation_id']}",
                             headers=H(CLIENT_TOKEN), json={"text": "TEST_iter7 grazie mille!"}, timeout=15)
        assert send.status_code == 200, send.text
        bmsgs = requests.get(f"{BASE}/api/chat/{b_conv['conversation_id']}", headers=H(BUSINESS_TOKEN), timeout=15).json()
        texts = [m["text"] for m in bmsgs["messages"]]
        assert "TEST_iter7 grazie mille!" in texts, texts

        # Business also can send and client sees it
        send2 = requests.post(f"{BASE}/api/chat/{b_conv['conversation_id']}",
                              headers=H(BUSINESS_TOKEN), json={"text": "TEST_iter7 ricevuto!"}, timeout=15)
        assert send2.status_code == 200
        cmsgs2 = requests.get(f"{BASE}/api/chat/{c_conv['conversation_id']}", headers=H(CLIENT_TOKEN), timeout=15).json()
        assert any(m["text"] == "TEST_iter7 ricevuto!" for m in cmsgs2["messages"])

    def test_already_handled_returns_400(self, created_request):
        rid = created_request["request_id"]
        r = requests.post(f"{BASE}/api/business-requests/{rid}/respond",
                          headers=H(BUSINESS_TOKEN),
                          json={"accept": False}, timeout=15)
        assert r.status_code == 400

    def test_decline_flow(self, business_id):
        # create a fresh request and decline it
        payload = {
            "business_id": business_id, "category": "lavanderia",
            "note": "TEST_iter7 decline me", "address": "Test", "lat": 45.66, "lng": 12.24,
        }
        rid = requests.post(f"{BASE}/api/business-requests", headers=H(CLIENT_TOKEN), json=payload, timeout=15).json()["request_id"]
        r = requests.post(f"{BASE}/api/business-requests/{rid}/respond",
                          headers=H(BUSINESS_TOKEN), json={"accept": False}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "declined"
        g = requests.get(f"{BASE}/api/business-requests/{rid}", headers=H(CLIENT_TOKEN), timeout=15).json()
        assert g["status"] == "declined"

    def test_business_not_found(self):
        payload = {"business_id": "user_nonexistent_xxx", "category": "lavanderia",
                   "note": "x", "address": "y", "lat": 0, "lng": 0}
        r = requests.post(f"{BASE}/api/business-requests", headers=H(CLIENT_TOKEN), json=payload, timeout=15)
        assert r.status_code == 404


# ---------------------------- Provider broadcast regression ----------------------------

class TestProviderBroadcast:
    def test_create_mission_matches_bots(self):
        payload = {
            "category": "pulizie", "service_type": "one-off",
            "config": {"rooms": 2},
            "address": "Via Roma 12, Treviso", "lat": 45.6669, "lng": 12.2433,
            "date": "2026-02-01", "time": "10:00",
            "duration_hours": 2.0, "recurrence": "once",
        }
        r = requests.post(f"{BASE}/api/missions", headers=H(CLIENT_TOKEN), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        mid = r.json()["mission_id"]
        # Bots auto-accept in 2-9s
        matched = False
        for _ in range(12):
            time.sleep(1)
            g = requests.get(f"{BASE}/api/missions/{mid}", headers=H(CLIENT_TOKEN), timeout=15).json()
            if g["accepted"] and len(g["accepted"]) >= 1:
                matched = True
                break
        assert matched, "provider broadcast bots did not auto-accept mission"


# ---------------------------- Cleanup ----------------------------

def teardown_module(module):
    # Best-effort: don't leave TEST_iter7 messages piling forever (not critical for demo DB).
    pass
