"""
Batch D (iter44) - Admin wallet + user detail refinements
- multiple bonus grants with descriptions
- /admin/users returns 'roles' array
- /admin/users/{id}/detail full structure
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
ADMIN_TOKEN = "jobby-admin-7c2f9a"
TEST_USER = "user_disptest01"


@pytest.fixture
def admin_headers():
    return {"Content-Type": "application/json", "X-Admin-Token": ADMIN_TOKEN}


# ---------- Multiple bonus grants ----------
class TestMultipleBonusGrants:
    def test_grant_bonus_first_time(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/bonus",
            headers=admin_headers,
            json={"amount": 5.0, "description": "TEST_iter44 first"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user_id"] == TEST_USER
        assert d["granted"] is True
        assert d["description"] == "TEST_iter44 first"
        assert d["bonus_credit"] >= 5.0
        pytest.first_bonus_total = d["bonus_credit"]

    def test_grant_bonus_second_time_cumulative(self, admin_headers):
        # This is the critical assertion for #3: no 'bonus_already_granted' 400
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/bonus",
            headers=admin_headers,
            json={"amount": 3.0, "description": "TEST_iter44 second"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["granted"] is True
        assert d["description"] == "TEST_iter44 second"
        # Cumulative should be > first
        assert d["bonus_credit"] >= getattr(pytest, "first_bonus_total", 0) + 2.9

    def test_bonus_grants_recorded_in_detail(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/detail",
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        grants = d.get("bonus_grants", [])
        descriptions = [g.get("description", "") for g in grants]
        assert any("TEST_iter44 first" in x for x in descriptions), f"first bonus not recorded: {descriptions}"
        assert any("TEST_iter44 second" in x for x in descriptions), f"second bonus not recorded: {descriptions}"

    def test_bonus_transaction_created_with_spendable_only(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/detail",
            headers=admin_headers,
        )
        assert r.status_code == 200
        tx = r.json().get("transactions", [])
        bonus_tx = [t for t in tx if t.get("type") == "bonus"]
        assert len(bonus_tx) >= 2, f"expected >=2 bonus transactions, got {len(bonus_tx)}"
        # Every bonus tx should have spendable_only=True
        for t in bonus_tx:
            assert t.get("spendable_only") is True, f"tx not spendable_only: {t}"

    def test_invalid_bonus_amount(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/bonus",
            headers=admin_headers,
            json={"amount": 0, "description": "bad"},
        )
        assert r.status_code == 400


# ---------- Roles in list ----------
class TestAdminUsersRolesArray:
    def test_admin_users_returns_roles_array(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) > 0
        for u in users[:20]:
            assert "role" in u
            assert "roles" in u, f"roles missing on {u.get('user_id')}"
            assert isinstance(u["roles"], list)


# ---------- User detail endpoint ----------
class TestAdminUserDetail:
    def test_detail_structure_for_known_user(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/detail",
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # Required top-level keys
        for k in [
            "user_id", "name", "email", "roles", "role", "services",
            "wallet_balance", "pending_balance", "bonus_credit",
            "flows", "transactions", "as_client", "as_provider", "bonus_grants",
        ]:
            assert k in d, f"missing key '{k}' in detail response"
        # Types
        assert isinstance(d["roles"], list)
        assert isinstance(d["services"], list)
        assert isinstance(d["transactions"], list)
        assert isinstance(d["as_client"], list)
        assert isinstance(d["as_provider"], list)
        assert isinstance(d["bonus_grants"], list)
        # Flows structure
        for k in ("topups", "bonus", "spent"):
            assert k in d["flows"], f"flows missing '{k}'"

    def test_detail_as_client_nonempty_for_disptest(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users/{TEST_USER}/detail",
            headers=admin_headers,
        )
        assert r.status_code == 200
        d = r.json()
        # per prompt: as_client is expected non-empty for user_disptest01
        assert len(d["as_client"]) > 0, "as_client should be non-empty for user_disptest01"
        # slim shape
        row = d["as_client"][0]
        for k in ("richiesta_id", "cat", "stato", "data"):
            assert k in row, f"slim row missing '{k}'"

    def test_detail_404_for_unknown_user(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users/user_does_not_exist_zzz/detail",
            headers=admin_headers,
        )
        assert r.status_code == 404

    def test_detail_requires_admin_token(self):
        r = requests.get(f"{BASE_URL}/api/admin/users/{TEST_USER}/detail")
        assert r.status_code in (401, 403)
