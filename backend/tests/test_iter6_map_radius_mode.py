"""
Iteration 6 backend tests — Map (real providers only), Radius, Service-mode.

Covers review_request items:
  1. GET /api/providers/nearby → only real registered providers (no is_bot). Each item exposes role, service_mode, business_name.
  2. PUT /api/profile persists {radius_km, service_mode: 'outdoor'|'in_shop'|'both'}.
  3. POST /api/missions creates + matches for a standard category (bots auto-accept).
  4. Matching in create_mission excludes businesses with service_mode == 'in_shop' from invites.
"""

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_TOKEN = "demo-preview-token-123"
ADMIN_TOKEN = "jobby-admin-7c2f9a"

AUTH_H = {"Authorization": f"Bearer {DEMO_TOKEN}", "Content-Type": "application/json"}
ADMIN_H = {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


# ---------------- Providers Nearby (map source) ----------------
class TestProvidersNearby:
    def test_nearby_excludes_bots_and_has_new_fields(self):
        r = requests.get(f"{API}/providers/nearby", params={"lat": 45.6669, "lng": 12.2433}, headers=AUTH_H, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # No _id leak
        for p in data:
            assert "_id" not in p
            # New fields required for map display + radius/mode features
            assert "role" in p, f"missing role: {p}"
            assert p["role"] in ("provider", "business"), f"unexpected role: {p['role']}"
            assert "service_mode" in p, f"missing service_mode: {p}"
            assert p["service_mode"] in ("outdoor", "in_shop", "both"), f"bad mode: {p['service_mode']}"
            assert "business_name" in p, f"missing business_name key: {p}"
            # lat/lng must be non-null for map pins
            assert p.get("lat") is not None and p.get("lng") is not None

    def test_nearby_bots_absent(self):
        # We can inspect via ADMIN endpoints? Not available directly, but we can
        # cross-check that no returned user_id is one of the seeded bot ids (they typically start with 'user_bot').
        r = requests.get(f"{API}/providers/nearby", params={"lat": 45.6669, "lng": 12.2433}, headers=AUTH_H, timeout=20)
        assert r.status_code == 200
        for p in r.json():
            uid = p.get("user_id", "")
            assert "bot" not in uid.lower(), f"bot returned in nearby: {uid}"

    def test_nearby_sorted_by_distance(self):
        r = requests.get(f"{API}/providers/nearby", params={"lat": 45.6669, "lng": 12.2433}, headers=AUTH_H, timeout=20)
        assert r.status_code == 200
        dists = [p["distance_km"] for p in r.json()]
        assert dists == sorted(dists), "results not sorted by distance"

    def test_nearby_requires_auth(self):
        r = requests.get(f"{API}/providers/nearby", params={"lat": 45.6669, "lng": 12.2433}, timeout=15)
        assert r.status_code == 401


# ---------------- Profile update (radius / service_mode) ----------------
class TestProfileRadiusMode:
    def _get_me(self):
        return requests.get(f"{API}/auth/me", headers=AUTH_H, timeout=15).json()

    def test_persist_radius_km(self):
        # set to 25, verify GET, then restore original
        me0 = self._get_me()
        original_radius = me0.get("radius_km", 10)
        r = requests.put(f"{API}/profile", headers=AUTH_H, json={"radius_km": 25}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["radius_km"] == 25
        me1 = self._get_me()
        assert me1["radius_km"] == 25
        # restore
        requests.put(f"{API}/profile", headers=AUTH_H, json={"radius_km": original_radius}, timeout=15)

    @pytest.mark.parametrize("mode", ["outdoor", "in_shop", "both"])
    def test_persist_service_mode(self, mode):
        me0 = self._get_me()
        original_mode = me0.get("service_mode", "both")
        r = requests.put(f"{API}/profile", headers=AUTH_H, json={"service_mode": mode}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["service_mode"] == mode
        # persistence via /auth/me
        me1 = self._get_me()
        assert me1["service_mode"] == mode
        # restore
        requests.put(f"{API}/profile", headers=AUTH_H, json={"service_mode": original_mode}, timeout=15)

    def test_radius_and_mode_together(self):
        me0 = self._get_me()
        orig_r, orig_m = me0.get("radius_km", 10), me0.get("service_mode", "both")
        r = requests.put(f"{API}/profile", headers=AUTH_H, json={"radius_km": 12, "service_mode": "outdoor"}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["radius_km"] == 12 and body["service_mode"] == "outdoor"
        # restore
        requests.put(f"{API}/profile", headers=AUTH_H, json={"radius_km": orig_r, "service_mode": orig_m}, timeout=15)


# ---------------- Mission creation still works (bot auto-accept) ----------------
class TestMissionMatchingStillWorks:
    def test_create_and_match_pulizie(self):
        payload = {
            "category": "pulizie",
            "service_type": "pulizie",
            "config": {"notes": "TEST_iter6_map"},
            "duration_hours": 2,
            "address": "Via Roma 1, Treviso",
            "lat": 45.6669,
            "lng": 12.2433,
            "date": "2026-02-20",
            "time": "10:00",
        }
        r = requests.post(f"{API}/missions", headers=AUTH_H, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] in ("pending", "matched")
        assert len(m.get("invited_provider_ids", [])) > 0, "no providers invited"
        mid = m["mission_id"]

        matched = False
        for _ in range(15):
            time.sleep(1)
            g = requests.get(f"{API}/missions/{mid}", headers=AUTH_H, timeout=15).json()
            if g.get("status") == "matched" and len(g.get("accepted", [])) > 0:
                matched = True
                break
        assert matched, "no bot acceptance within 15s"


# ---------------- Matching excludes in_shop-only businesses ----------------
class TestMatchingExcludesInShop:
    """
    Uses admin endpoint (if available) to insert a synthetic business user; falls back to
    validating logic exists in code by checking that when demo user (client) creates a mission,
    invited_provider_ids never contain a user whose role=business AND service_mode=in_shop.

    Since we cannot easily query users, we do a functional check: we temporarily set the demo
    user (a client) irrelevant. Instead we rely on the fact that /providers/nearby now returns
    real registered providers with service_mode. We probe each returned business with
    service_mode=in_shop and confirm it is NEVER present in a fresh mission's invited list for a
    category the business supports.
    """
    def test_in_shop_business_not_invited(self):
        # 1. Get list of real registered providers/businesses
        r = requests.get(f"{API}/providers/nearby", params={"lat": 45.6669, "lng": 12.2433}, headers=AUTH_H, timeout=20)
        assert r.status_code == 200
        provs = r.json()
        in_shop_bizs = [p for p in provs if p.get("role") == "business" and p.get("service_mode") == "in_shop" and p.get("services")]

        if not in_shop_bizs:
            pytest.skip("No in_shop business currently registered — logic path not exercisable in preview data")

        target = in_shop_bizs[0]
        cat = target["services"][0]

        payload = {
            "category": cat, "service_type": cat, "config": {"notes": "TEST_iter6_inshop_exclude"},
            "duration_hours": 1, "address": "Via Roma 1, Treviso",
            "lat": 45.6669, "lng": 12.2433, "date": "2026-02-21", "time": "11:00",
        }
        r = requests.post(f"{API}/missions", headers=AUTH_H, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        m = r.json()
        assert target["user_id"] not in m.get("invited_provider_ids", []), \
            f"in_shop business {target['user_id']} should be excluded but was invited"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
