"""
Phase B1 — Multi-method Auth + Onboarding backend tests.
Covers: register, login, demo, apple (invalid), demo read-only guard,
onboarding complete for client/business/provider, business photo/document
uploads, admin documents endpoint.
"""
import os
import uuid
import base64
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

ADMIN_TOKEN = "jobby-admin-7c2f9a"
API = f"{BASE_URL}/api"

# Tiny 1x1 base64 JPEG (dummy, not actually valid image data but backend only stores string)
TINY_IMG = "data:image/jpeg;base64," + base64.b64encode(b"jpegdata").decode()


def _rand_email(prefix="test"):
    # backend lowercases emails; keep prefix lowercase but still identifiable
    return f"test_{prefix}_{uuid.uuid4().hex[:10]}@jobby.test"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ------------------------- register -------------------------
class TestRegister:
    def test_register_success(self, s):
        email = _rand_email("reg")
        r = s.post(f"{API}/auth/register",
                   json={"email": email, "password": "secret123", "name": "Reg User"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_token" in data and data["session_token"]
        assert "user" in data
        u = data["user"]
        assert u["email"] == email
        assert u.get("onboarding_completed") is False
        assert "password_hash" not in u

    def test_register_duplicate_email(self, s):
        email = _rand_email("dup")
        s.post(f"{API}/auth/register",
               json={"email": email, "password": "secret123", "name": "A"})
        r = s.post(f"{API}/auth/register",
                   json={"email": email, "password": "secret123", "name": "B"})
        assert r.status_code == 400
        assert r.json().get("detail") == "email_exists"

    def test_register_weak_password(self, s):
        r = s.post(f"{API}/auth/register",
                   json={"email": _rand_email("weak"), "password": "12345", "name": "X"})
        assert r.status_code == 400
        assert r.json().get("detail") == "weak_password"

    def test_register_invalid_email(self, s):
        r = s.post(f"{API}/auth/register",
                   json={"email": "no-at-symbol", "password": "secret123", "name": "X"})
        assert r.status_code == 400
        assert r.json().get("detail") == "invalid_email"


# ------------------------- login -------------------------
class TestLogin:
    def test_login_existing_mario(self, s):
        # Existing seeded account
        r = s.post(f"{API}/auth/login",
                   json={"email": "mario@test.it", "password": "secret123"})
        assert r.status_code == 200, r.text
        assert "session_token" in r.json()

    def test_login_wrong_password(self, s):
        r = s.post(f"{API}/auth/login",
                   json={"email": "mario@test.it", "password": "wrongpass"})
        assert r.status_code == 401
        assert r.json().get("detail") == "invalid_credentials"

    def test_login_unknown_email(self, s):
        r = s.post(f"{API}/auth/login",
                   json={"email": _rand_email("unknown"), "password": "secret123"})
        assert r.status_code == 401


# ------------------------- demo -------------------------
class TestDemo:
    def test_demo_login(self, s):
        r = s.post(f"{API}/auth/demo")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["session_token"]
        u = data["user"]
        assert u.get("is_demo") is True
        assert u.get("onboarding_completed") is True

    def test_demo_readonly_guard(self, s):
        # Get demo token
        tok = s.post(f"{API}/auth/demo").json()["session_token"]
        H = {"Authorization": f"Bearer {tok}"}

        # GET should work
        r = s.get(f"{API}/categories", headers=H)
        assert r.status_code == 200

        # POST mission -> 403 demo_readonly
        r = s.post(f"{API}/missions", headers=H,
                   json={"category": "pulizie", "description": "x",
                         "address": "Via Roma", "lat": 45.6, "lng": 12.2})
        assert r.status_code == 403, r.text
        assert r.json().get("detail") == "demo_readonly"

        # PUT profile -> 403
        r = s.put(f"{API}/profile", headers=H, json={"bio": "hi"})
        assert r.status_code == 403
        assert r.json().get("detail") == "demo_readonly"

        # POST wallet/add -> 403
        r = s.post(f"{API}/wallet/add", headers=H, json={"amount": 10})
        assert r.status_code == 403
        assert r.json().get("detail") == "demo_readonly"

    def test_non_demo_can_post(self, s):
        # Non-demo bearer from credentials file
        H = {"Authorization": "Bearer demo-preview-token-123"}
        r = s.post(f"{API}/wallet/add", headers=H, json={"amount": 1})
        # Should NOT be 403 demo_readonly. Accept 200 or other non-403 status.
        assert r.status_code != 403 or r.json().get("detail") != "demo_readonly", r.text


# ------------------------- apple -------------------------
class TestApple:
    def test_apple_invalid_token(self, s):
        r = s.post(f"{API}/auth/apple",
                   json={"identity_token": "not.a.real.token"})
        assert r.status_code == 401
        assert r.json().get("detail") == "invalid_apple_token"


# ------------------------- onboarding -------------------------
def _fresh_account(s, prefix="onb"):
    email = _rand_email(prefix)
    r = s.post(f"{API}/auth/register",
               json={"email": email, "password": "secret123", "name": prefix})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["session_token"], d["user"]["user_id"], email


class TestOnboarding:
    def test_complete_client(self, s):
        tok, uid, _ = _fresh_account(s, "client")
        H = {"Authorization": f"Bearer {tok}"}
        r = s.post(f"{API}/onboarding/complete", headers=H,
                   json={"role": "client", "address": "Via Roma 1", "phone": "+39 000"})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["onboarding_completed"] is True
        assert u["approval_status"] == "approved"
        assert u["role"] == "client"

    def test_complete_business_pending(self, s):
        tok, uid, _ = _fresh_account(s, "biz")
        H = {"Authorization": f"Bearer {tok}"}
        r = s.post(f"{API}/onboarding/complete", headers=H,
                   json={"role": "business",
                         "business_name": "Lav TEST",
                         "vat_number": "IT99999999999",
                         "services": ["lavanderia"],
                         "address": "Via X 2"})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["onboarding_completed"] is True
        assert u["approval_status"] == "pending"
        assert u["vat_number"] == "IT99999999999"
        assert u["role"] == "business"

    def test_complete_provider_pending(self, s):
        tok, uid, _ = _fresh_account(s, "prov")
        H = {"Authorization": f"Bearer {tok}"}
        r = s.post(f"{API}/onboarding/complete", headers=H,
                   json={"role": "provider", "services": ["pulizie"], "radius_km": 15})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["approval_status"] == "pending"
        assert u["role"] == "provider"
        assert u["radius_km"] == 15


# ------------------------- uploads -------------------------
class TestBusinessUploads:
    def test_document_and_photos(self, s):
        tok, uid, _ = _fresh_account(s, "up")
        H = {"Authorization": f"Bearer {tok}"}

        # document
        r = s.post(f"{API}/onboarding/business/document", headers=H,
                   json={"image": TINY_IMG})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # 4 photos
        for i in range(4):
            r = s.post(f"{API}/onboarding/business/photo", headers=H,
                       json={"image": TINY_IMG})
            assert r.status_code == 200, r.text
            assert r.json()["count"] == i + 1

        # 5th -> 400 max_photos
        r = s.post(f"{API}/onboarding/business/photo", headers=H,
                   json={"image": TINY_IMG})
        assert r.status_code == 400
        assert r.json().get("detail") == "max_photos"

        # delete index 0 -> count 3
        r = s.delete(f"{API}/onboarding/business/photo/0", headers=H)
        assert r.status_code == 200
        assert r.json()["count"] == 3

    def test_admin_documents(self, s):
        # Set up a business user with vat + license + photos
        tok, uid, _ = _fresh_account(s, "adm")
        H = {"Authorization": f"Bearer {tok}"}
        s.post(f"{API}/onboarding/complete", headers=H,
               json={"role": "business", "business_name": "T",
                     "vat_number": "IT12312312312", "services": ["lavanderia"]})
        s.post(f"{API}/onboarding/business/document", headers=H,
               json={"image": TINY_IMG})
        s.post(f"{API}/onboarding/business/photo", headers=H,
               json={"image": TINY_IMG})

        # admin
        r = s.get(f"{API}/admin/users/{uid}/documents",
                  headers={"X-Admin-Token": ADMIN_TOKEN})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["vat_number"] == "IT12312312312"
        assert d["license_document"].startswith("data:image/jpeg")
        assert isinstance(d["business_photos"], list)
        assert len(d["business_photos"]) == 1

    def test_admin_documents_no_token(self, s):
        r = s.get(f"{API}/admin/users/anyid/documents")
        assert r.status_code == 403
