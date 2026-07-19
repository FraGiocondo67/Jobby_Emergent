"""Iteration 20 - Dispute flow, admin resolve, client payout endpoints, demo readonly."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
CLIENT_TOKEN = "disp-test-token-777"
DEMO_TOKEN = "demo-preview-token-123"
ADMIN_TOKEN = "jobby-admin-7c2f9a"
BOOKING_ID = "bkg_disptest01"

client_headers = {"Authorization": f"Bearer {CLIENT_TOKEN}", "Content-Type": "application/json"}
admin_headers = {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}
demo_headers = {"Authorization": f"Bearer {DEMO_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="session", autouse=True)
def reset_booking_state():
    """Reset the seeded dispute booking + delete prior disputes so create returns 201."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        from datetime import datetime, timedelta, timezone
        import asyncio, os as _os
        async def _reset():
            cli = AsyncIOMotorClient(_os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = cli["test_database"]
            exp = datetime.now(timezone.utc) + timedelta(days=30)
            await db.user_sessions.update_one({"session_token": CLIENT_TOKEN},
                                              {"$set": {"expires_at": exp}})
            await db.bookings.update_one({"booking_id": BOOKING_ID},
                                         {"$set": {"status": "completed",
                                                   "completed_at": datetime.now(timezone.utc).isoformat(),
                                                   "escrow_status": "held"}})
            await db.disputes.delete_many({"booking_id": BOOKING_ID})
            await db.wallet_holds.update_many({"booking_id": BOOKING_ID},
                                              {"$set": {"status": "pending"}})
        asyncio.get_event_loop().run_until_complete(_reset())
    except Exception as e:
        print(f"[reset_booking_state] warning: {e}")
    yield


# ---- Dispute create + get + list ----
class TestDisputeFlow:
    dispute_id = None

    def test_01_reason_codes(self):
        r = requests.get(f"{API}/disputes/reason-codes")
        assert r.status_code == 200
        codes = [x["code"] for x in r.json()]
        assert "NOT_PERFORMED" in codes

    def test_02_create_or_get_dispute(self):
        r = requests.post(f"{API}/disputes", headers=client_headers,
                          json={"booking_id": BOOKING_ID, "reason_code": "NOT_PERFORMED", "description": "TEST_iter20 - service not performed"})
        if r.status_code == 400 and r.json().get("detail") == "dispute_exists":
            # Already created in a previous run: fetch it from listing
            lst = requests.get(f"{API}/disputes", headers=client_headers).json()
            active = [d for d in lst if d["booking_id"] == BOOKING_ID and d["status"] not in ("resolved_mutual", "resolved_jobby", "rejected")]
            assert active, "dispute_exists but no active dispute in listing"
            TestDisputeFlow.dispute_id = active[0]["dispute_id"]
            assert active[0].get("ai_recommendation")
            return
        assert r.status_code in (200, 201), f"unexpected {r.status_code}: {r.text}"
        data = r.json()
        assert data["booking_id"] == BOOKING_ID
        assert data["reason_code"] == "NOT_PERFORMED"
        assert data["status"] == "open"
        # AI rec must be populated
        ai = data.get("ai_recommendation")
        assert ai is not None, "ai_recommendation missing"
        assert ai["recommendation"] in ("refund_full", "refund_partial", "reject")
        assert 0.0 <= float(ai["confidence"]) <= 1.0
        assert ai.get("rationale")
        TestDisputeFlow.dispute_id = data["dispute_id"]

    def test_03_list_disputes(self):
        r = requests.get(f"{API}/disputes", headers=client_headers)
        assert r.status_code == 200
        lst = r.json()
        assert any(d["dispute_id"] == TestDisputeFlow.dispute_id for d in lst)
        for d in lst:
            if d["dispute_id"] == TestDisputeFlow.dispute_id:
                assert d["role"] == "client"

    def test_04_get_dispute_detail(self):
        assert TestDisputeFlow.dispute_id
        r = requests.get(f"{API}/disputes/{TestDisputeFlow.dispute_id}", headers=client_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "client"
        assert d.get("ai_recommendation")
        assert d.get("messages"), "messages should include initial description"

    def test_05_add_message(self):
        assert TestDisputeFlow.dispute_id
        r = requests.post(f"{API}/disputes/{TestDisputeFlow.dispute_id}/message",
                          headers=client_headers, json={"text": "TEST_iter20 extra message"})
        assert r.status_code == 200
        assert r.json()["from"] == "client"

    def test_06_provider_respond_contract(self):
        """Provider token not available; verify endpoint contract: 401/403/404 without provider auth."""
        assert TestDisputeFlow.dispute_id
        # Call as client (wrong role) -> forbidden
        r = requests.post(f"{API}/disputes/{TestDisputeFlow.dispute_id}/respond",
                          headers=client_headers, json={"accept": True, "refund_pct": 100})
        assert r.status_code in (403, 400), f"expected 403/400 got {r.status_code}"

    def test_07_admin_list_disputes(self):
        r = requests.get(f"{API}/admin/disputes", headers=admin_headers)
        assert r.status_code == 200
        lst = r.json()
        assert any(d["dispute_id"] == TestDisputeFlow.dispute_id for d in lst)
        target = [d for d in lst if d["dispute_id"] == TestDisputeFlow.dispute_id][0]
        assert target.get("ai_recommendation")

    def test_08_admin_ui_disputes_tab(self):
        """Verify admin HTML UI includes disputes tab + loadDisputes function."""
        r = requests.get(f"{API}/admin/ui")
        assert r.status_code == 200
        html = r.text
        assert "loadDisputes" in html
        assert "Disputes" in html
        assert "resolveDispute" in html

    def test_09_admin_resolve_refund_partial(self):
        assert TestDisputeFlow.dispute_id
        r = requests.post(f"{API}/admin/disputes/{TestDisputeFlow.dispute_id}/resolve",
                          headers=admin_headers,
                          json={"decision": "refund_partial", "refund_pct": 50, "note": "TEST_iter20 partial"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "resolved_jobby"
        assert d["resolution"]["decision"] == "refund_partial"
        assert d["resolution"]["refund_pct"] == 50
        # Refund should be applied and non-zero
        assert d["resolution"].get("refund_amount", 0) > 0


# ---- Client payout endpoints ----
class TestClientPayouts:
    def test_wallet_returns_paypal_and_bank_fields(self):
        r = requests.get(f"{API}/wallet", headers=client_headers)
        assert r.status_code == 200, r.text
        w = r.json()
        # These keys must exist (may be None/empty)
        for k in ("payment_method", "bank_account", "crypto_wallets", "paypal_email"):
            assert k in w, f"missing key {k}"

    def test_set_bank_account_persists(self):
        payload = {"account_holder": "TEST Disp Client", "iban": "IT60X0542811101000000123456"}
        r = requests.put(f"{API}/wallet/bank-account", headers=client_headers, json=payload)
        assert r.status_code == 200, r.text
        # IBAN may be masked in response for privacy
        returned_iban = r.json()["bank_account"]["iban"]
        assert returned_iban.endswith("123456"), f"unexpected iban {returned_iban}"
        # GET to verify persistence
        w = requests.get(f"{API}/wallet", headers=client_headers).json()
        assert w["bank_account"]["iban"].endswith("123456")

    def test_set_paypal_email_persists(self):
        r = requests.put(f"{API}/wallet/paypal-email", headers=client_headers, json={"email": "test_iter20@paypal.com"})
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        assert r.json()["paypal_email"] == "test_iter20@paypal.com"


# ---- Demo readonly middleware ----
class TestDemoReadonly:
    def test_demo_login(self):
        r = requests.post(f"{API}/auth/demo")
        assert r.status_code == 200

    def test_demo_post_blocked(self):
        r = requests.post(f"{API}/disputes", headers=demo_headers,
                          json={"booking_id": BOOKING_ID, "reason_code": "OTHER", "description": "demo"})
        assert r.status_code == 403
        assert r.json().get("detail") == "demo_readonly"

    def test_demo_get_works(self):
        r = requests.get(f"{API}/wallet", headers=demo_headers)
        assert r.status_code == 200
