"""
PayPal SANDBOX integration tests for JOBBY.

Scope (per review_request):
- PUT /api/wallet/paypal-email (set + validation)
- POST /api/bookings/{id}/paypal/create (200 + order/url, 403 forbidden, 404 not found)
- POST /api/bookings/{id}/payout (400 not_paid on unpaid booking, 403 non-provider)
- Sanity: /api/categories and /api/bookings still return 200

NOTE: We do NOT complete PayPal buyer approval / capture (no sandbox buyer available).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")

CLIENT_TOKEN = "demo-preview-token-123"          # user_demopreview01 (client)
OTHER_TOKEN = "biz-test-token-999"               # user_2f996c8a010a (business)
ORIGIN = "https://jobby-mvp-update.preview.emergentagent.com"


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def unpaid_booking_id() -> str:
    """Find an unpaid booking owned by user_demopreview01."""
    r = requests.get(f"{BASE_URL}/api/bookings", headers=_h(CLIENT_TOKEN), timeout=30)
    assert r.status_code == 200, r.text
    unpaid = [b for b in r.json() if b.get("payment_status") == "unpaid"]
    assert unpaid, "no unpaid booking found for demo-preview account"
    return unpaid[0]["booking_id"]


# ---------- Sanity ----------
class TestSanity:
    def test_categories_still_200(self):
        r = requests.get(f"{BASE_URL}/api/categories", headers=_h(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        # server returns a dict grouping standard/proximity/payment or a list
        data = r.json()
        assert isinstance(data, (list, dict))
        if isinstance(data, dict):
            assert any(k in data for k in ("standard", "proximity", "payment"))

    def test_bookings_still_200(self):
        r = requests.get(f"{BASE_URL}/api/bookings", headers=_h(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- PUT /api/wallet/paypal-email ----------
class TestPaypalEmail:
    def test_set_valid_paypal_email(self):
        payload = {"email": "x@paypal.com"}
        r = requests.put(f"{BASE_URL}/api/wallet/paypal-email", headers=_h(CLIENT_TOKEN), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("paypal_email") == "x@paypal.com"

        # verify persistence via GET /api/wallet
        r2 = requests.get(f"{BASE_URL}/api/wallet", headers=_h(CLIENT_TOKEN), timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("paypal_email") == "x@paypal.com"

    def test_invalid_paypal_email_returns_400(self):
        r = requests.put(f"{BASE_URL}/api/wallet/paypal-email", headers=_h(CLIENT_TOKEN),
                         json={"email": "notanemail"}, timeout=15)
        assert r.status_code == 400, r.text
        assert r.json().get("detail") == "invalid_email"

    def test_unauth_returns_401(self):
        r = requests.put(f"{BASE_URL}/api/wallet/paypal-email", json={"email": "a@b.com"}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- POST /api/bookings/{id}/paypal/create ----------
class TestPaypalCreateOrder:
    def test_unknown_booking_404(self):
        r = requests.post(f"{BASE_URL}/api/bookings/does_not_exist/paypal/create",
                          headers=_h(CLIENT_TOKEN), json={"origin_url": ORIGIN}, timeout=30)
        assert r.status_code == 404, r.text
        assert r.json().get("detail") == "booking_not_found"

    def test_forbidden_when_not_customer(self, unpaid_booking_id):
        r = requests.post(f"{BASE_URL}/api/bookings/{unpaid_booking_id}/paypal/create",
                          headers=_h(OTHER_TOKEN), json={"origin_url": ORIGIN}, timeout=30)
        assert r.status_code == 403, r.text
        assert r.json().get("detail") == "forbidden"

    def test_create_order_success(self, unpaid_booking_id):
        r = requests.post(f"{BASE_URL}/api/bookings/{unpaid_booking_id}/paypal/create",
                          headers=_h(CLIENT_TOKEN), json={"origin_url": ORIGIN}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # if it happened to be already paid we would get {"already_paid": True}; we picked unpaid
        assert "order_id" in data, data
        assert "url" in data, data
        assert data["url"], "approve url should not be empty"
        assert "sandbox.paypal.com" in data["url"], f"expected sandbox approval url, got {data['url']}"
        # order_id has PayPal shape (uppercase alnum, typically 17 chars)
        assert isinstance(data["order_id"], str) and len(data["order_id"]) >= 10


# ---------- POST /api/bookings/{id}/payout ----------
class TestPaypalPayout:
    def test_payout_forbidden_for_non_provider(self, unpaid_booking_id):
        # client (customer, not provider) calling payout
        r = requests.post(f"{BASE_URL}/api/bookings/{unpaid_booking_id}/payout",
                          headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 403, r.text
        assert r.json().get("detail") == "forbidden"

    def test_payout_forbidden_for_unrelated_user(self, unpaid_booking_id):
        # other business user, not provider on this booking
        r = requests.post(f"{BASE_URL}/api/bookings/{unpaid_booking_id}/payout",
                          headers=_h(OTHER_TOKEN), timeout=30)
        assert r.status_code == 403, r.text
        assert r.json().get("detail") == "forbidden"

    def test_payout_unknown_booking_404(self):
        r = requests.post(f"{BASE_URL}/api/bookings/nonexistent/payout",
                          headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 404
        assert r.json().get("detail") == "booking_not_found"

    def test_payout_not_paid_when_called_by_actual_provider(self, unpaid_booking_id):
        """
        Need to call payout as the actual provider for the picked unpaid booking to hit 400 not_paid.
        We fetch booking to get provider_id, then create a session token for that provider directly in Mongo.
        If we can't mint a token, we skip.
        """
        # Fetch booking details
        r = requests.get(f"{BASE_URL}/api/bookings", headers=_h(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        booking = next((b for b in r.json() if b["booking_id"] == unpaid_booking_id), None)
        assert booking is not None
        provider_id = booking["provider_id"]

        # Try creating a session token for the provider via Mongo (localhost)
        try:
            from pymongo import MongoClient
        except Exception:
            pytest.skip("pymongo not available to seed provider session token")

        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
        db = client[db_name]

        # provider should exist in users collection (JOBBY stores providers as users w/ role=provider)
        user_doc = db.users.find_one({"user_id": provider_id})
        if not user_doc:
            pytest.skip(f"provider user {provider_id} not found in users collection")

        # ensure paypal_email set so we don't hit no_paypal_email branch first
        db.users.update_one({"user_id": provider_id},
                            {"$set": {"paypal_email": user_doc.get("paypal_email") or "provider@paypal.com"}})

        token = f"TEST_prov_token_{provider_id[-8:]}"
        from datetime import datetime, timedelta, timezone
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        db.user_sessions.update_one(
            {"session_token": token},
            {"$set": {"session_token": token, "user_id": provider_id, "expires_at": expires_at}},
            upsert=True,
        )

        try:
            rr = requests.post(f"{BASE_URL}/api/bookings/{unpaid_booking_id}/payout",
                               headers=_h(token), timeout=30)
            assert rr.status_code == 400, rr.text
            assert rr.json().get("detail") == "not_paid"
        finally:
            db.user_sessions.delete_one({"session_token": token})
