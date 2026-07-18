"""Phase 3 tests: admin user status/stats/users, Stripe topup checkout & status."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
ADMIN_TOKEN = "jobby-admin-7c2f9a"
CLIENT_BEARER = "demo-preview-token-123"
BIZ_USER_ID = "user_2f996c8a010a"


@pytest.fixture(scope="module")
def admin_headers():
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def client_headers():
    return {"Authorization": f"Bearer {CLIENT_BEARER}", "Content-Type": "application/json"}


# ---------------- Admin stats ----------------
class TestAdminStats:
    def test_stats_contains_phase3_fields(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("pending_approvals", "revenue", "topups_volume", "gmv", "jobby_fees"):
            assert key in data, f"missing key {key}"
        assert isinstance(data["revenue"], (int, float))
        assert isinstance(data["topups_volume"], (int, float))
        assert isinstance(data["gmv"], (int, float))
        assert isinstance(data["jobby_fees"], (int, float))
        assert isinstance(data["pending_approvals"], int)


# ---------------- Admin users ----------------
class TestAdminUsers:
    def test_users_list_contains_required_fields(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) > 0
        u = users[0]
        for key in ("user_id", "approval_status", "phone", "business_name", "online", "role"):
            assert key in u, f"missing key {key}"

    def test_users_includes_francesco(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert any(u["user_id"] == BIZ_USER_ID for u in r.json())


# ---------------- Admin set user status ----------------
class TestAdminSetStatus:
    def test_invalid_status_returns_400(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{BIZ_USER_ID}/status",
            headers=admin_headers,
            json={"status": "bogus"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_unknown_user_returns_404(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/user_does_not_exist_xyz/status",
            headers=admin_headers,
            json={"status": "approved"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_suspend_then_approve_francesco(self, admin_headers):
        # Suspend
        r1 = requests.post(
            f"{BASE_URL}/api/admin/users/{BIZ_USER_ID}/status",
            headers=admin_headers, json={"status": "suspended"}, timeout=15,
        )
        assert r1.status_code == 200
        assert r1.json()["approval_status"] == "suspended"

        users = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, timeout=15).json()
        f = next(u for u in users if u["user_id"] == BIZ_USER_ID)
        assert f["approval_status"] == "suspended"

        # Approve (leaves Francesco approved at the end per instructions)
        r2 = requests.post(
            f"{BASE_URL}/api/admin/users/{BIZ_USER_ID}/status",
            headers=admin_headers, json={"status": "approved"}, timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json()["approval_status"] == "approved"

        users = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, timeout=15).json()
        f = next(u for u in users if u["user_id"] == BIZ_USER_ID)
        assert f["approval_status"] == "approved"

    def test_missing_admin_token_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/admin/stats", timeout=15)
        assert r.status_code in (401, 403)


# ---------------- Stripe topup ----------------
class TestStripeTopup:
    session_id = None

    def test_invalid_package_returns_400(self, client_headers):
        r = requests.post(
            f"{BASE_URL}/api/wallet/topup/checkout",
            headers=client_headers,
            json={"package_id": "invalid_pkg", "origin_url": BASE_URL},
            timeout=20,
        )
        assert r.status_code == 400

    def test_create_checkout_p25(self, client_headers):
        r = requests.post(
            f"{BASE_URL}/api/wallet/topup/checkout",
            headers=client_headers,
            json={"package_id": "p25", "origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "url" in data and "session_id" in data
        assert "checkout.stripe.com" in data["url"], f"unexpected url: {data['url']}"
        TestStripeTopup.session_id = data["session_id"]

    def test_status_unpaid_does_not_credit(self, client_headers):
        assert TestStripeTopup.session_id, "no session_id"
        # capture wallet balance
        w0 = requests.get(f"{BASE_URL}/api/wallet", headers=client_headers, timeout=15)
        assert w0.status_code == 200
        bal_before = w0.json()["balance"]

        r = requests.get(
            f"{BASE_URL}/api/wallet/topup/status/{TestStripeTopup.session_id}",
            headers=client_headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["payment_status"] != "paid", f"unexpectedly paid: {data}"
        assert data.get("credited") is False

        w1 = requests.get(f"{BASE_URL}/api/wallet", headers=client_headers, timeout=15)
        bal_after = w1.json()["balance"]
        assert abs(bal_after - bal_before) < 0.001, f"balance changed: {bal_before} -> {bal_after}"
