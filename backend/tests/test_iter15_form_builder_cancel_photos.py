"""Iteration 15 backend tests.

Covers:
- Admin form-builder: PUT /admin/categories/{cat_id}/questions + GET /categories reflection + 404
- Mission cancel lifecycle (client cancel, forbidden other user, cannot_cancel again)
- Business-request cancel lifecycle
- Business photos on detail + list endpoints
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
ADMIN_TOKEN = "jobby-admin-7c2f9a"
CLIENT_TOKEN = "demo-preview-token-123"
OTHER_TOKEN = "biz-test-token-999"
BUSINESS_ID = "user_2f996c8a010a"


def client_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def admin_headers() -> dict:
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


# ----- Form builder -----

class TestFormBuilder:
    """Admin form builder for category questions."""

    def test_put_questions_driver_ok_and_get_reflects(self):
        payload = {"questions": [{
            "id": "note",
            "label": {"it": "Nota", "en": "Note"},
            "type": "text",
            "placeholder": {"it": "x", "en": "x"},
        }]}
        r = requests.put(f"{BASE_URL}/api/admin/categories/driver/questions",
                         headers=admin_headers(), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cat_id"] == "driver"
        assert isinstance(body["questions"], list)
        assert body["questions"][0]["id"] == "note"

        # GET /api/categories reflects the update
        g = requests.get(f"{BASE_URL}/api/categories", headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert g.status_code == 200, g.text
        cats = g.json()
        # /api/categories returns a dict grouped by kind (standard/proximity/payment)
        all_cats = []
        if isinstance(cats, dict):
            for v in cats.values():
                if isinstance(v, list):
                    all_cats.extend(v)
        elif isinstance(cats, list):
            all_cats = cats
        driver = next((c for c in all_cats if c.get("cat_id") == "driver"), None)
        assert driver is not None, "driver category missing"
        qs = driver.get("questions") or []
        assert any(q.get("id") == "note" for q in qs), f"note field not reflected: {qs}"

    def test_put_questions_unknown_cat_returns_404(self):
        r = requests.put(f"{BASE_URL}/api/admin/categories/__doesnotexist__/questions",
                         headers=admin_headers(), json={"questions": []}, timeout=15)
        assert r.status_code == 404, r.text


# ----- Mission cancel -----

class TestMissionCancel:
    """Client mission cancel lifecycle."""

    def _create_mission(self) -> str:
        body = {
            "category": "driver",
            "service_type": "one_off",
            "config": {},
            "address": "Via Test 1, Treviso",
            "lat": 45.6669,
            "lng": 12.2433,
            "date": "2026-02-01",
            "time": "10:00",
            "duration_hours": 2,
        }
        r = requests.post(f"{BASE_URL}/api/missions", headers=client_headers(CLIENT_TOKEN), json=body, timeout=20)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] in ("pending", "matched")
        return m["mission_id"]

    def test_cancel_success_then_cannot_cancel(self):
        mid = self._create_mission()
        r1 = requests.post(f"{BASE_URL}/api/missions/{mid}/cancel",
                           headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("status") == "cancelled"

        # Verify persistence via GET
        g = requests.get(f"{BASE_URL}/api/missions/{mid}", headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert g.status_code == 200
        assert g.json().get("status") == "cancelled"

        # Cancel again -> 400 cannot_cancel
        r2 = requests.post(f"{BASE_URL}/api/missions/{mid}/cancel",
                           headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert r2.status_code == 400, r2.text
        assert "cannot_cancel" in r2.text

    def test_cancel_by_other_user_forbidden(self):
        mid = self._create_mission()
        r = requests.post(f"{BASE_URL}/api/missions/{mid}/cancel",
                          headers=client_headers(OTHER_TOKEN), timeout=15)
        assert r.status_code == 403, r.text
        assert "forbidden" in r.text

        # Cleanup: cancel with real owner so mission list stays tidy
        requests.post(f"{BASE_URL}/api/missions/{mid}/cancel",
                      headers=client_headers(CLIENT_TOKEN), timeout=15)


# ----- Business-request cancel -----

class TestBusinessRequestCancel:
    """Client business-request cancel lifecycle."""

    def _create(self) -> str:
        body = {
            "business_id": BUSINESS_ID,
            "category": "lavanderia",
            "note": "TEST_iter15",
            "address": "x",
            "lat": 45.6,
            "lng": 12.2,
        }
        r = requests.post(f"{BASE_URL}/api/business-requests",
                          headers=client_headers(CLIENT_TOKEN), json=body, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        return d["request_id"]

    def test_cancel_success_then_cannot_cancel(self):
        rid = self._create()
        r1 = requests.post(f"{BASE_URL}/api/business-requests/{rid}/cancel",
                           headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("status") == "cancelled"

        # GET verifies persistence
        g = requests.get(f"{BASE_URL}/api/business-requests/{rid}",
                         headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert g.status_code == 200
        assert g.json().get("status") == "cancelled"

        r2 = requests.post(f"{BASE_URL}/api/business-requests/{rid}/cancel",
                           headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert r2.status_code == 400
        assert "cannot_cancel" in r2.text


# ----- Business photos on detail + list -----

class TestBusinessPhotos:
    """business_photos + price_list keys should be present."""

    def test_business_detail_has_photos_and_price_list(self):
        r = requests.get(f"{BASE_URL}/api/businesses/detail/{BUSINESS_ID}",
                         headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "business_photos" in d, f"missing business_photos: {list(d.keys())}"
        assert isinstance(d["business_photos"], list)
        assert "price_list" in d
        assert isinstance(d["price_list"], list)

    def test_businesses_list_includes_photos(self):
        r = requests.get(f"{BASE_URL}/api/businesses",
                         params={"category": "lavanderia", "lat": 45.6, "lng": 12.2},
                         headers=client_headers(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list) and len(items) > 0
        for it in items:
            assert "business_photos" in it, f"item missing business_photos: {list(it.keys())}"
