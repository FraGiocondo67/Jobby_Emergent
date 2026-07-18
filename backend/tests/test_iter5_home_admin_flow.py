"""
Iteration 5 backend regression — verifies the fix for the user complaint:
"activated categories in the Admin Panel don't show on Home".

Covers the review_request items:
  1. GET /api/categories returns 9 standard, 16 proximity, 4 payment (all active).
  2. Admin toggle round-trip (deactivate → GET reflects → reactivate → GET reflects).
  3. Wallet screen loads; /wallet/add adds funds and returns new balance.
  4. Standard-category mission creation (POST /api/missions) works & matching runs.
  5. Richieste (GET /api/requests) & Chat (GET /api/chat/conversations) load w/o crash.
  6. Auth: /auth/me works with demo Bearer, and 401 without.
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_TOKEN = "demo-preview-token-123"
ADMIN_TOKEN = "jobby-admin-7c2f9a"

AUTH_H = {"Authorization": f"Bearer {DEMO_TOKEN}", "Content-Type": "application/json"}
ADMIN_H = {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


# ---------------- Auth ----------------
class TestAuth:
    def test_auth_me_with_demo_token(self):
        r = requests.get(f"{API}/auth/me", headers=AUTH_H, timeout=15)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["user_id"] == "user_demopreview01"
        assert me["role"] == "client"
        assert "_id" not in me  # MongoDB ObjectId leak check

    def test_auth_me_without_token_401(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# ---------------- Categories (Home tiles source) ----------------
class TestCategories:
    def test_categories_shape_and_counts(self):
        r = requests.get(f"{API}/categories", headers=AUTH_H, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["standard", "proximity", "payment", "providers_online", "manifesto"]).issubset(d.keys())
        assert len(d["standard"]) == 9, [c["cat_id"] for c in d["standard"]]
        assert len(d["proximity"]) == 16, [c["cat_id"] for c in d["proximity"]]
        assert len(d["payment"]) == 4, [c["cat_id"] for c in d["payment"]]
        # Each item exposes required fields for Home tile
        for c in d["standard"] + d["proximity"] + d["payment"]:
            assert "cat_id" in c and "emoji" in c and "label" in c and "kind" in c
            assert "_id" not in c

    def test_providers_online_nonneg_and_manifesto_present(self):
        d = requests.get(f"{API}/categories", headers=AUTH_H, timeout=15).json()
        assert isinstance(d["providers_online"], int) and d["providers_online"] >= 0
        assert isinstance(d["manifesto"], list) and len(d["manifesto"]) > 0


# ---------------- Admin toggle round-trip ----------------
class TestAdminToggle:
    TARGET = "pulizie"  # a standard category

    def _get_active(self, cat_id):
        d = requests.get(f"{API}/categories", headers=AUTH_H, timeout=15).json()
        for c in d["standard"] + d["proximity"] + d["payment"]:
            if c["cat_id"] == cat_id:
                return True
        return False

    def test_admin_endpoints_require_token(self):
        r = requests.get(f"{API}/admin/categories", timeout=15)
        assert r.status_code in (401, 403), r.status_code
        r2 = requests.get(f"{API}/admin/categories", headers={"X-Admin-Token": "wrong"}, timeout=15)
        assert r2.status_code in (401, 403)

    def test_admin_list_returns_all_29(self):
        r = requests.get(f"{API}/admin/categories", headers=ADMIN_H, timeout=15)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 29
        assert all("_id" not in c for c in arr)

    def test_toggle_reflects_on_public_categories(self):
        # Pre: target is active on Home
        assert self._get_active(self.TARGET) is True, "precondition: target should be active"

        # Deactivate
        r = requests.post(f"{API}/admin/categories/{self.TARGET}/toggle", headers=ADMIN_H, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["active"] is False

        # Public GET no longer includes it
        assert self._get_active(self.TARGET) is False, "deactivated category still appears on Home"

        # Reactivate (leave DB clean)
        r2 = requests.post(f"{API}/admin/categories/{self.TARGET}/toggle", headers=ADMIN_H, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["active"] is True

        # Public GET has it back
        assert self._get_active(self.TARGET) is True

    def test_toggle_unknown_returns_404(self):
        r = requests.post(f"{API}/admin/categories/does_not_exist/toggle", headers=ADMIN_H, timeout=15)
        assert r.status_code == 404


# ---------------- Wallet ----------------
class TestWallet:
    def test_get_wallet(self):
        r = requests.get(f"{API}/wallet", headers=AUTH_H, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "balance" in d and isinstance(d["balance"], (int, float))
        assert isinstance(d["transactions"], list)
        assert d.get("mock") is True

    def test_wallet_add_returns_new_balance(self):
        before = requests.get(f"{API}/wallet", headers=AUTH_H, timeout=15).json()["balance"]
        r = requests.post(f"{API}/wallet/add", headers=AUTH_H, json={"amount": 5.0}, timeout=15)
        assert r.status_code == 200, r.text
        new_bal = r.json()["balance"]
        assert round(new_bal - before, 2) == 5.0
        # persistence
        after = requests.get(f"{API}/wallet", headers=AUTH_H, timeout=15).json()["balance"]
        assert after == new_bal

    def test_wallet_add_invalid_amount(self):
        r = requests.post(f"{API}/wallet/add", headers=AUTH_H, json={"amount": 0}, timeout=15)
        assert r.status_code == 400


# ---------------- Mission creation + matching ----------------
class TestMission:
    def test_create_mission_and_matching(self):
        payload = {
            "category": "pulizie",
            "service_type": "pulizie",
            "config": {"notes": "TEST_iter5"},
            "duration_hours": 2,
            "address": "Via Roma 1, Treviso",
            "lat": 45.6669,
            "lng": 12.2433,
            "date": "2026-02-15",
            "time": "10:00",
        }
        r = requests.post(f"{API}/missions", headers=AUTH_H, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m.get("status") in ("pending", "matched")
        mid = m["mission_id"]

        # Poll for matching (bot providers auto-accept in 2-9s)
        matched = False
        for _ in range(15):
            time.sleep(1)
            g = requests.get(f"{API}/missions/{mid}", headers=AUTH_H, timeout=15)
            assert g.status_code == 200
            gm = g.json()
            if gm.get("status") == "matched" or len(gm.get("candidates", []) or []) > 0:
                matched = True
                break
        assert matched, "no matches within 15s"


# ---------------- Richieste + Chat ----------------
class TestRequestsAndChat:
    def test_requests_endpoint_shape(self):
        r = requests.get(f"{API}/requests", headers=AUTH_H, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d, dict)
        assert "payments" in d and isinstance(d["payments"], list)
        assert "missions" in d and isinstance(d["missions"], list)

    def test_chat_conversations_load(self):
        r = requests.get(f"{API}/chat/conversations", headers=AUTH_H, timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
