"""Phase A: Categories commission + budgets on missions/business-requests.

Covers:
- Admin per-category commission set endpoint (200/400/404).
- Missions store optional budget (client proposal).
- End-to-end booking: jobby_fee derived from category.commission_pct.
- Business detail endpoint (price list; 404 unknown).
- Business-requests accept optional budget field.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT_TOKEN = "demo-preview-token-123"
BUSINESS_TOKEN = "biz-test-token-999"
ADMIN_TOKEN = "jobby-admin-7c2f9a"
BUSINESS_USER_ID = "user_2f996c8a010a"


def _hdr(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _admin_hdr():
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


# ---------- Admin Category Commission ----------
class TestAdminCategoryCommission:
    def test_set_commission_valid(self):
        r = requests.post(f"{API}/admin/categories/pulizie/commission",
                          headers=_admin_hdr(), json={"commission_pct": 12.5})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cat_id"] == "pulizie"
        assert data["commission_pct"] == 12.5

    def test_set_commission_invalid_high(self):
        r = requests.post(f"{API}/admin/categories/pulizie/commission",
                          headers=_admin_hdr(), json={"commission_pct": 150})
        assert r.status_code == 400
        assert "invalid_pct" in r.text

    def test_set_commission_invalid_negative(self):
        r = requests.post(f"{API}/admin/categories/pulizie/commission",
                          headers=_admin_hdr(), json={"commission_pct": -1})
        assert r.status_code == 400

    def test_set_commission_unknown_cat(self):
        r = requests.post(f"{API}/admin/categories/does_not_exist/commission",
                          headers=_admin_hdr(), json={"commission_pct": 10})
        assert r.status_code == 404

    def test_no_admin_token_forbidden(self):
        r = requests.post(f"{API}/admin/categories/pulizie/commission",
                          headers={"Content-Type": "application/json"},
                          json={"commission_pct": 10})
        assert r.status_code in (401, 403)

    def test_reset_pulizie_to_10(self):
        # IMPORTANT: reset to 10 as required by review request.
        r = requests.post(f"{API}/admin/categories/pulizie/commission",
                          headers=_admin_hdr(), json={"commission_pct": 10})
        assert r.status_code == 200
        assert r.json()["commission_pct"] == 10.0

        # Verify via /api/categories list
        r2 = requests.get(f"{API}/categories", headers=_hdr(CLIENT_TOKEN))
        assert r2.status_code == 200
        data = r2.json()
        pulizie = next((c for c in data.get("standard", []) if c["cat_id"] == "pulizie"), None)
        assert pulizie is not None, "pulizie category not found in listing"
        assert pulizie.get("commission_pct") == 10.0


# ---------- Mission budget + commission end-to-end ----------
class TestMissionBudgetAndBooking:
    mission_id = None

    def test_create_mission_with_budget(self):
        payload = {
            "category": "pulizie",
            "service_type": "service",
            "config": {"homeType": "apartment", "rooms": 3, "duration": 2},
            "address": "Via Test 1, Treviso",
            "lat": 45.6669, "lng": 12.2433,
            "date": "2026-02-01", "time": "10:00",
            "duration_hours": 2,
            "recurrence": "once",
            "budget": 80,
        }
        r = requests.post(f"{API}/missions", headers=_hdr(CLIENT_TOKEN), json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["budget"] == 80
        assert data["category"] == "pulizie"
        assert data["duration_hours"] == 2
        TestMissionBudgetAndBooking.mission_id = data["mission_id"]

    def test_mission_persisted_via_get(self):
        assert TestMissionBudgetAndBooking.mission_id, "prev test must have set mission_id"
        r = requests.get(f"{API}/missions/{TestMissionBudgetAndBooking.mission_id}",
                         headers=_hdr(CLIENT_TOKEN))
        assert r.status_code == 200
        assert r.json().get("budget") == 80

    def test_booking_commission_pct_and_fee(self):
        """Wait for a bot provider to auto-accept, then select and check booking."""
        import time
        mid = TestMissionBudgetAndBooking.mission_id
        assert mid
        accepted = []
        for _ in range(15):  # up to ~15s
            time.sleep(1)
            r = requests.get(f"{API}/missions/{mid}", headers=_hdr(CLIENT_TOKEN))
            if r.status_code != 200:
                continue
            m = r.json()
            accepted = m.get("accepted", [])
            if accepted:
                break
        if not accepted:
            pytest.skip("No bot provider auto-accepted in time; skipping booking assertion")

        provider_id = accepted[0]["provider_id"]
        labor = accepted[0]["price"]
        r = requests.post(f"{API}/missions/{mid}/select",
                          headers=_hdr(CLIENT_TOKEN), json={"provider_id": provider_id})
        assert r.status_code == 200, r.text
        booking = r.json()
        # commission was reset to 10 in the previous test class; test ordering ensures that.
        assert booking.get("commission_pct") == 10.0, f"Got {booking.get('commission_pct')}"
        assert booking.get("jobby_fee") == round(labor * 10.0 / 100.0, 2), \
            f"jobby_fee mismatch: {booking.get('jobby_fee')} vs expected {round(labor*0.1,2)}"
        assert booking.get("labor_cost") == labor
        assert booking.get("total") == round(labor + booking["jobby_fee"], 2)


# ---------- Business detail ----------
class TestBusinessDetail:
    def test_business_detail_ok(self):
        r = requests.get(f"{API}/businesses/detail/{BUSINESS_USER_ID}",
                         headers=_hdr(CLIENT_TOKEN))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user_id"] == BUSINESS_USER_ID
        assert "price_list" in data
        assert isinstance(data["price_list"], list)

    def test_business_detail_404(self):
        r = requests.get(f"{API}/businesses/detail/user_does_not_exist_xyz",
                         headers=_hdr(CLIENT_TOKEN))
        assert r.status_code == 404
        assert "business_not_found" in r.text


# ---------- Business request with budget ----------
class TestBusinessRequestBudget:
    def test_create_business_request_with_budget(self):
        # Pick a category the business actually offers (lavanderia/pulizie/tecnico per credentials).
        detail = requests.get(f"{API}/businesses/detail/{BUSINESS_USER_ID}",
                              headers=_hdr(CLIENT_TOKEN)).json()
        services = detail.get("services", []) or ["lavanderia"]
        cat = "lavanderia" if "lavanderia" in services else ("pulizie" if "pulizie" in services else services[0])
        payload = {
            "business_id": BUSINESS_USER_ID,
            "category": cat,
            "note": "TEST_ budget request",
            "address": "Via Test 1",
            "lat": 45.6, "lng": 12.2,
            "budget": 50,
        }
        r = requests.post(f"{API}/business-requests", headers=_hdr(CLIENT_TOKEN), json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["budget"] == 50
        assert data["business_id"] == BUSINESS_USER_ID
        assert data["category"] == cat

        # Verify persistence via GET.
        rid = data["request_id"]
        r2 = requests.get(f"{API}/business-requests/{rid}", headers=_hdr(CLIENT_TOKEN))
        assert r2.status_code == 200
        assert r2.json().get("budget") == 50
