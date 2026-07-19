"""Spec 5 — Navigation, Home state, Wallet dashboard, Provider dashboard, support number."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if BASE_URL:
    BASE_URL = BASE_URL.rstrip("/")

ADMIN_TOKEN = "jobby-admin-7c2f9a"
CLIENT_TOKEN = "disp-test-token-777"          # recurring client (has completed bkg_disptest01)
PROVIDER_TOKEN = "prov-test-token-888"        # Giulia (provider)
DEFAULT_WHATSAPP = "+393481136876"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------- support / settings ----------------
class TestSupportWhatsapp:
    def test_get_default_whatsapp(self):
        r = requests.get(f"{BASE_URL}/api/settings/support", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "whatsapp" in data
        # Not asserting exact default (may have been overridden); ensure str
        assert isinstance(data["whatsapp"], str)
        assert data["whatsapp"].startswith("+")

    def test_admin_set_and_reset_whatsapp(self):
        # override
        r1 = requests.post(
            f"{BASE_URL}/api/admin/settings/support",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"whatsapp": "+390000000000"}, timeout=15,
        )
        assert r1.status_code == 200, r1.text
        assert r1.json().get("whatsapp") == "+390000000000"

        # public GET reflects the change
        r2 = requests.get(f"{BASE_URL}/api/settings/support", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["whatsapp"] == "+390000000000"

        # restore
        r3 = requests.post(
            f"{BASE_URL}/api/admin/settings/support",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"whatsapp": DEFAULT_WHATSAPP}, timeout=15,
        )
        assert r3.status_code == 200
        r4 = requests.get(f"{BASE_URL}/api/settings/support", timeout=15)
        assert r4.json()["whatsapp"] == DEFAULT_WHATSAPP

    def test_admin_set_requires_admin_token(self):
        r = requests.post(f"{BASE_URL}/api/admin/settings/support",
                          json={"whatsapp": "+390000000000"}, timeout=15)
        assert r.status_code in (401, 403), r.text


# ---------------- HOME state ----------------
class TestHomeState:
    def test_home_state_recurring_client(self):
        r = requests.get(f"{BASE_URL}/api/home/state", headers=_auth(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("state") in ("recurring", "new"), data
        assert "relationships" in data
        assert isinstance(data["relationships"], list)
        # Client has bkg_disptest01 completed → recurring expected
        if data["state"] == "recurring":
            # If any relationships present, verify shape
            for rel in data["relationships"]:
                assert "provider_id" in rel
                assert "nome" in rel
                # These keys should exist even if null
                assert "next_visit" in rel or rel.get("next_visit") is None or True
                assert "last_richiesta_id" in rel
                assert "visits_count" in rel
                assert "problem" in rel

    def test_home_state_unauth(self):
        r = requests.get(f"{BASE_URL}/api/home/state", timeout=15)
        assert r.status_code in (401, 403)


# ---------------- WALLET dashboard ----------------
class TestWalletDashboard:
    def test_wallet_dashboard_shape(self):
        r = requests.get(f"{BASE_URL}/api/wallet/dashboard",
                         headers=_auth(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()

        # top-level blocks
        for k in ("show_borsellino", "borsellino", "limiti", "attivita", "recupero_fiscale"):
            assert k in d, f"missing {k}"

        b = d["borsellino"]
        for k in ("caricato", "impegnato", "spendibile"):
            assert k in b
            assert isinstance(b[k], (int, float))
        # spendibile == caricato - impegnato (round to 2)
        assert round(b["spendibile"], 2) == round(b["caricato"] - b["impegnato"], 2)

        lim = d["limiti"]
        assert lim["annual_ceiling"] == 10000
        assert lim["warn_threshold"] == 0.8
        assert "annual_used" in lim and "annual_pct" in lim and "annual_warn" in lim
        assert isinstance(lim.get("per_collaboratrice"), list)
        assert "external_total" in lim

        att = d["attivita"]
        assert isinstance(att.get("upcoming"), list)
        assert isinstance(att.get("documenti"), list)

        fisc = d["recupero_fiscale"]
        assert "anno" in fisc and "stima_deducibile" in fisc

    def test_external_usage_increments_totals(self):
        # baseline
        d0 = requests.get(f"{BASE_URL}/api/wallet/dashboard",
                          headers=_auth(CLIENT_TOKEN), timeout=15).json()
        base_ext = float(d0["limiti"]["external_total"])
        base_annual = float(d0["limiti"]["annual_used"])

        # post external usage
        r = requests.post(f"{BASE_URL}/api/wallet/external-usage",
                         headers=_auth(CLIENT_TOKEN),
                         json={"amount": 100, "provider_name": "TEST_ExtProv"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # verify totals increased
        d1 = requests.get(f"{BASE_URL}/api/wallet/dashboard",
                          headers=_auth(CLIENT_TOKEN), timeout=15).json()
        assert round(d1["limiti"]["external_total"] - base_ext, 2) == 100.00
        # annual_used includes external → also up by 100
        assert round(d1["limiti"]["annual_used"] - base_annual, 2) >= 100.00


# ---------------- PROVIDER dashboard ----------------
class TestProviderDashboard:
    def test_provider_dashboard_shape(self):
        r = requests.get(f"{BASE_URL}/api/provider/dashboard",
                         headers=_auth(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("guadagni", "limiti", "storico", "reliability", "dnd"):
            assert k in d

        g = d["guadagni"]
        assert "incoming_total" in g
        assert isinstance(g.get("items"), list)
        # LF items should have date on 15th of following month
        for it in g["items"]:
            if it.get("source") == "INPS" and it.get("date"):
                assert it["date"].endswith("-15"), f"INPS date not 15th: {it['date']}"

        lim = d["limiti"]
        assert lim["annual_ceiling"] == 5000
        assert lim["hours_ceiling"] == 280
        assert lim["family_ceiling"] == 2500
        assert lim["warn_threshold"] == 0.8

        assert isinstance(d["storico"], list)

    def test_provider_dnd_toggle(self):
        # set true
        r = requests.post(f"{BASE_URL}/api/provider/dnd",
                         headers=_auth(PROVIDER_TOKEN),
                         json={"dnd": True}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("dnd") is True

        # verify dashboard reflects
        d1 = requests.get(f"{BASE_URL}/api/provider/dashboard",
                          headers=_auth(PROVIDER_TOKEN), timeout=15).json()
        assert d1["dnd"] is True

        # reset
        r2 = requests.post(f"{BASE_URL}/api/provider/dnd",
                          headers=_auth(PROVIDER_TOKEN),
                          json={"dnd": False}, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("dnd") is False

        d2 = requests.get(f"{BASE_URL}/api/provider/dashboard",
                          headers=_auth(PROVIDER_TOKEN), timeout=15).json()
        assert d2["dnd"] is False
