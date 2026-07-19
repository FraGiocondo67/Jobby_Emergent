"""Iteration 21 — In-app Notifications + Stripe Connect (test-mode) backend tests.

Covers:
- Notifications: dispute_opened auto-notification, unread-count, mark read, mark all,
  dispute_message and dispute_resolved auto-notifications.
- Stripe Connect: GET /connect/status, POST /connect/onboarding-link (providers only,
  502 clean error expected as Connect not enabled), POST /wallet/withdraw/stripe clean 400.
- Regression: demo POST is blocked with demo_readonly.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                          "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT_TOKEN = "disp-test-token-777"   # user_disptest01 (client, wallet 200, non-demo)
PROVIDER_TOKEN = "prov-test-token-888"  # prov_cfbd9805ce97 (provider)
DEMO_TOKEN = "demo-preview-token-123"
ADMIN_HEADER = {"X-Admin-Token": "jobby-admin-7c2f9a"}
BOOKING_ID = "bkg_disptest01"


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def dispute_id():
    """Ensure there is exactly one open/active dispute for BOOKING_ID by the client and
    return its dispute_id. If one already exists, reuse it.
    """
    # Try to create; if already exists, list disputes and pick the newest for that booking.
    r = requests.post(f"{API}/disputes", headers=_h(CLIENT_TOKEN), json={
        "booking_id": BOOKING_ID, "reason_code": "NOT_PERFORMED", "description": "test iter21"
    }, timeout=30)
    if r.status_code == 200:
        return r.json()["dispute_id"]
    # If "dispute_exists" or booking already disputed → fetch existing
    lst = requests.get(f"{API}/disputes", headers=_h(CLIENT_TOKEN), timeout=30)
    assert lst.status_code == 200, f"list disputes failed: {lst.status_code} {lst.text}"
    for d in lst.json():
        if d.get("booking_id") == BOOKING_ID:
            return d["dispute_id"]
    pytest.skip(f"could not create nor find dispute for {BOOKING_ID}: {r.status_code} {r.text}")


# -------- NOTIFICATIONS --------

class TestNotifications:
    def test_provider_list_has_dispute_opened(self, dispute_id):
        r = requests.get(f"{API}/notifications", headers=_h(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "unread" in data
        types = [n.get("type") for n in data["items"]]
        assert "dispute_opened" in types, f"missing dispute_opened; types={types}"

    def test_provider_unread_count_positive(self):
        r = requests.get(f"{API}/notifications/unread-count", headers=_h(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("unread"), int)
        assert r.json()["unread"] >= 1

    def test_mark_one_read_decreases_unread(self):
        listr = requests.get(f"{API}/notifications", headers=_h(PROVIDER_TOKEN), timeout=15).json()
        unread_items = [n for n in listr["items"] if not n.get("read")]
        if not unread_items:
            pytest.skip("no unread items to mark")
        before = listr["unread"]
        nid = unread_items[0]["notif_id"]
        r = requests.post(f"{API}/notifications/{nid}/read", headers=_h(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200 and r.json().get("ok") is True
        after = requests.get(f"{API}/notifications/unread-count",
                             headers=_h(PROVIDER_TOKEN), timeout=15).json()["unread"]
        assert after == before - 1

    def test_dispute_message_creates_notification(self, dispute_id):
        # baseline unread for provider
        before = requests.get(f"{API}/notifications/unread-count",
                              headers=_h(PROVIDER_TOKEN), timeout=15).json()["unread"]
        # client posts a message
        m = requests.post(f"{API}/disputes/{dispute_id}/message",
                          headers=_h(CLIENT_TOKEN), json={"text": "hello provider iter21"},
                          timeout=20)
        assert m.status_code == 200, m.text
        time.sleep(0.5)
        after = requests.get(f"{API}/notifications/unread-count",
                             headers=_h(PROVIDER_TOKEN), timeout=15).json()["unread"]
        assert after >= before + 1
        # verify a dispute_message notification exists referencing this dispute
        items = requests.get(f"{API}/notifications",
                             headers=_h(PROVIDER_TOKEN), timeout=15).json()["items"]
        assert any(n["type"] == "dispute_message" and n.get("ref_id") == dispute_id for n in items)

    def test_read_all_zeros_unread(self):
        r = requests.post(f"{API}/notifications/read-all",
                          headers=_h(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200 and r.json().get("ok") is True
        n = requests.get(f"{API}/notifications/unread-count",
                         headers=_h(PROVIDER_TOKEN), timeout=15).json()["unread"]
        assert n == 0

    def test_admin_resolve_notifies_both_parties(self, dispute_id):
        # zero out both sides so we can detect the deltas cleanly
        requests.post(f"{API}/notifications/read-all", headers=_h(PROVIDER_TOKEN), timeout=15)
        requests.post(f"{API}/notifications/read-all", headers=_h(CLIENT_TOKEN), timeout=15)
        # admin resolves — use reject (pct=0) so it doesn't disturb wallet balances
        rr = requests.post(f"{API}/admin/disputes/{dispute_id}/resolve",
                           headers={**ADMIN_HEADER, "Content-Type": "application/json"},
                           json={"decision": "reject", "refund_pct": 0, "note": "iter21"},
                           timeout=30)
        # If already resolved from a previous run, skip the delta but check code<500
        assert rr.status_code < 500, rr.text
        time.sleep(0.5)
        prov_items = requests.get(f"{API}/notifications",
                                  headers=_h(PROVIDER_TOKEN), timeout=15).json()["items"]
        cli_items = requests.get(f"{API}/notifications",
                                 headers=_h(CLIENT_TOKEN), timeout=15).json()["items"]
        if rr.status_code == 200:
            assert any(n["type"] == "dispute_resolved" and n.get("ref_id") == dispute_id
                       for n in prov_items), "provider missing dispute_resolved"
            assert any(n["type"] == "dispute_resolved" and n.get("ref_id") == dispute_id
                       for n in cli_items), "client missing dispute_resolved"


# -------- STRIPE CONNECT --------

class TestStripeConnect:
    def test_status_provider_ok(self):
        r = requests.get(f"{API}/connect/status", headers=_h(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(["connected", "details_submitted", "payouts_enabled"]).issubset(j.keys())
        assert isinstance(j["connected"], bool)

    def test_onboarding_link_client_forbidden(self):
        r = requests.post(f"{API}/connect/onboarding-link", headers=_h(CLIENT_TOKEN),
                          json={"origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 403, r.text
        assert "providers_only" in r.text

    def test_onboarding_link_provider_clean_error(self):
        """Currently Stripe Connect is not enabled on the platform account → expect
        a 502 with a clean 'Connect' error message. MUST NOT be 500."""
        r = requests.post(f"{API}/connect/onboarding-link", headers=_h(PROVIDER_TOKEN),
                          json={"origin_url": BASE_URL}, timeout=30)
        assert r.status_code != 500, f"500 crash: {r.text}"
        # Accept a happy 200 (if user enabled Connect since docs written) OR clean 502
        if r.status_code == 200:
            assert "url" in r.json()
        else:
            assert r.status_code == 502
            # The public URL sits behind Cloudflare, which replaces upstream 502s
            # with its own HTML "Bad gateway" page. The backend itself returns a
            # clean JSON detail with "Connect" — verified separately via localhost
            # (see test_onboarding_link_backend_clean_json below). So here we just
            # accept either the backend JSON body OR the Cloudflare 502 HTML.
            body = r.text
            assert ("Connect" in body or "Bad gateway" in body), body

    def test_onboarding_link_backend_clean_json(self):
        """Direct hit to the backend (bypassing ingress) — verifies the FastAPI
        HTTPException surfaces as a real JSON body with a clean Stripe error."""
        try:
            rr = requests.post("http://localhost:8001/api/connect/onboarding-link",
                               headers=_h(PROVIDER_TOKEN),
                               json={"origin_url": BASE_URL}, timeout=30)
        except requests.RequestException:
            pytest.skip("localhost backend not reachable from test runner")
        assert rr.status_code != 500, rr.text
        if rr.status_code == 502:
            assert "Connect" in rr.text

    def test_withdraw_stripe_clean_400_when_not_onboarded(self):
        # Get status; if not connected/payouts_enabled, expect 400 no_connect_account
        # or payouts_not_enabled — never 500.
        r = requests.post(f"{API}/wallet/withdraw/stripe", headers=_h(PROVIDER_TOKEN),
                          json={"amount": 10}, timeout=30)
        assert r.status_code != 500, f"500 crash: {r.text}"
        assert r.status_code in (400, 502), r.text
        detail = r.text
        assert ("no_connect_account" in detail
                or "payouts_not_enabled" in detail
                or "insufficient_available" in detail
                or "Connect" in detail), detail

    def test_withdraw_stripe_client_forbidden(self):
        r = requests.post(f"{API}/wallet/withdraw/stripe", headers=_h(CLIENT_TOKEN),
                          json={"amount": 10}, timeout=15)
        assert r.status_code == 403
        assert "providers_only" in r.text


# -------- REGRESSION: demo readonly --------

class TestDemoReadOnly:
    def test_demo_post_blocked(self):
        r = requests.post(f"{API}/notifications/read-all", headers=_h(DEMO_TOKEN), timeout=15)
        assert r.status_code == 403, f"demo should be readonly; got {r.status_code} {r.text}"
        assert "demo_readonly" in r.text

    def test_demo_get_notifications_allowed(self):
        r = requests.get(f"{API}/notifications", headers=_h(DEMO_TOKEN), timeout=15)
        assert r.status_code == 200
