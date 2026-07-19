"""JOBBY — Spec 3.1 tests for split payments (Stripe Connect destination charge +
PayPal Orders v2 platform_fees + simulated wallet escrow fallback).

Covers:
 • wallet(simulated) happy path: checkout->held, release->credit provider net
 • wallet insufficient_wallet
 • stripe guard: provider_not_onboarded_stripe
 • paypal guard: provider_not_onboarded_paypal
 • persona_lf blocked (lf_uses_voucher_not_psp)
 • already_paid guard
 • admin refund on simulated held payment
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

CLIENT_TOKEN = "disp-test-token-777"
CLIENT_ID = "user_disptest01"
PROVIDER_TOKEN = "req-prov-token"
PROVIDER_ID = "user_2f996c8a010a"
ADMIN_TOKEN = "jobby-admin-7c2f9a"

TREVISO_LAT = 45.6669
TREVISO_LNG = 12.2433


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _admin_h():
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


def _make_confirmed_richiesta(binario="impresa"):
    """Create a fresh confirmed richiesta ready for payment."""
    payload = {
        "binario": binario,
        "config": {
            "home_type": "appartamento", "mq_band": "80_120", "tipo_pulizia": "ordinaria",
            "extra": [], "stiro_ore": 0, "prodotti": "cliente", "durata_ore": 3, "animali": False,
        },
        "indirizzo": "Via Test 1", "lat": TREVISO_LAT, "lng": TREVISO_LNG,
        "data_ora": "2026-02-01 10:00", "flessibilita": "fascia",
        "ricorrenza": "una_tantum", "publish": True,
    }
    r = requests.post(f"{API}/pulizie/richieste", json=payload, headers=_h(CLIENT_TOKEN), timeout=30)
    assert r.status_code == 200, f"create richiesta failed: {r.status_code} {r.text}"
    rid = r.json()["richiesta_id"]

    # Admin invite provider
    r2 = requests.post(f"{API}/admin/pulizie/richieste/{rid}/invite",
                       json={"provider_ids": [PROVIDER_ID]}, headers=_admin_h(), timeout=30)
    assert r2.status_code == 200, f"invite failed: {r2.status_code} {r2.text}"

    # Provider propose accept
    r3 = requests.post(f"{API}/pulizie/richieste/{rid}/propose",
                       json={"accept": True}, headers=_h(PROVIDER_TOKEN), timeout=30)
    assert r3.status_code == 200, f"propose failed: {r3.status_code} {r3.text}"

    # Client confirm
    r4 = requests.post(f"{API}/pulizie/richieste/{rid}/confirm",
                       json={"provider_id": PROVIDER_ID}, headers=_h(CLIENT_TOKEN), timeout=30)
    assert r4.status_code == 200, f"confirm failed: {r4.status_code} {r4.text}"
    return rid, r4.json()


def _get_richiesta(rid, token=CLIENT_TOKEN):
    r = requests.get(f"{API}/pulizie/richieste/{rid}", headers=_h(token), timeout=30)
    assert r.status_code == 200
    return r.json()


def _get_wallet(token=CLIENT_TOKEN):
    r = requests.get(f"{API}/wallet", headers=_h(token), timeout=30)
    assert r.status_code == 200, f"wallet failed: {r.text}"
    j = r.json()
    return float(j.get("wallet_balance") or j.get("balance") or 0)


# --------------------------------------------------------------------------
# 1) Wallet (simulated) happy path: checkout -> held, release -> credited
# --------------------------------------------------------------------------
class TestWalletHappyPath:
    def test_wallet_checkout_held_and_release(self):
        rid, ric = _make_confirmed_richiesta()
        prezzo = float(ric.get("prezzo_finale"))
        prop = next(p for p in ric["proposte"] if p["provider_id"] == PROVIDER_ID)
        bd = prop["breakdown"]
        expected_net = float(bd["provider_net"])
        expected_fee = float(bd["jobby_fee"])
        # cliente fee_client == jobby_fee/2 (impresa split). total_client == work+fee_client.
        expected_client_debit = prezzo  # what client pays now (matches _amounts.charge)

        client_bal_before = _get_wallet(CLIENT_TOKEN)
        prov_bal_before = _get_wallet(PROVIDER_TOKEN)

        # ---- Checkout wallet ----
        r = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                          json={"method": "wallet"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 200, f"wallet checkout failed: {r.status_code} {r.text}"
        j = r.json()
        assert j.get("status") == "held" and j.get("simulated") is True
        assert abs(float(j.get("provider_net", 0)) - expected_net) < 0.02

        # Verify pagamento_lavoro.stato = held
        ric2 = _get_richiesta(rid)
        assert ric2["pagamento_lavoro"]["stato"] == "held"
        assert ric2["pagamento_lavoro"]["psp"] == "simulato"

        # Client wallet debited
        client_bal_after_hold = _get_wallet(CLIENT_TOKEN)
        assert abs((client_bal_before - client_bal_after_hold) - expected_client_debit) < 0.02, \
            f"client debit mismatch: before={client_bal_before} after={client_bal_after_hold} expected={expected_client_debit}"

        # ---- already_paid guard ----
        r2 = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                           json={"method": "wallet"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert r2.status_code == 400 and "already_paid" in r2.text

        # ---- Release ----
        r3 = requests.post(f"{API}/pay/richiesta/{rid}/release", headers=_h(CLIENT_TOKEN), timeout=30)
        assert r3.status_code == 200, f"release failed: {r3.status_code} {r3.text}"
        rj = r3.json()
        assert rj["stato"] == "released"

        ric3 = _get_richiesta(rid)
        assert ric3["pagamento_lavoro"]["stato"] == "released"

        # Provider wallet credited with provider_net
        prov_bal_after = _get_wallet(PROVIDER_TOKEN)
        assert abs((prov_bal_after - prov_bal_before) - expected_net) < 0.02, \
            f"provider net mismatch: before={prov_bal_before} after={prov_bal_after} expected={expected_net}"

        # JOBBY keeps the fee: client_debit - provider_credit == jobby_fee_total (approx)
        jobby_kept = (client_bal_before - client_bal_after_hold) - (prov_bal_after - prov_bal_before)
        assert abs(jobby_kept - expected_fee) < 0.02, \
            f"JOBBY fee mismatch: kept={jobby_kept} expected={expected_fee}"


# --------------------------------------------------------------------------
# 2) Wallet insufficient balance
# --------------------------------------------------------------------------
class TestInsufficientWallet:
    def test_insufficient_wallet(self):
        # Drain client wallet by paying multiple huge richieste until short.
        # Instead: create richiesta, then withdraw client wallet to near 0 via wallet endpoint,
        # but simplest = create many richieste until balance below charge.
        # Alternative: use provider's own wallet_balance which is smaller. But provider isn't the client.
        # We create the richiesta and force wallet to be too low by first paying multiple times
        # (each pay eats ~34 EUR). Client starts around 324. To force insufficient, we spam several checkouts.
        # Simpler: run checkout, then immediately drain balance via /wallet endpoints if available.
        # We'll simulate by creating a richiesta then intentionally lowering wallet w/ /wallet/withdraw.
        # If not available, we just skip.
        rid, ric = _make_confirmed_richiesta()
        prezzo = float(ric["prezzo_finale"])

        # Get current balance and withdraw enough to leave less than prezzo
        bal = _get_wallet(CLIENT_TOKEN)
        need_to_leave_below = prezzo - 0.5
        if bal > need_to_leave_below:
            amt = round(bal - need_to_leave_below, 2)
            # Try to withdraw via simulated wallet
            wr = requests.post(f"{API}/wallet/withdraw",
                               json={"method": "bank", "amount": amt},
                               headers=_h(CLIENT_TOKEN), timeout=30)
            if wr.status_code != 200:
                pytest.skip(f"cannot drain wallet to test insufficient ({wr.status_code} {wr.text[:100]})")

        r = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                          json={"method": "wallet"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 400, f"expected 400 insufficient_wallet, got {r.status_code} {r.text}"
        assert "insufficient_wallet" in r.text


# --------------------------------------------------------------------------
# 3) Stripe & PayPal onboarding guards
# --------------------------------------------------------------------------
class TestPspGuards:
    def test_stripe_guard_provider_not_onboarded(self):
        rid, _ = _make_confirmed_richiesta()
        r = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                          json={"method": "stripe"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"
        assert "provider_not_onboarded_stripe" in r.text

    def test_paypal_guard_provider_not_onboarded(self):
        rid, _ = _make_confirmed_richiesta()
        r = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                          json={"method": "paypal"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"
        assert "provider_not_onboarded_paypal" in r.text


# --------------------------------------------------------------------------
# 4) Refund on simulated held payment
# --------------------------------------------------------------------------
class TestRefund:
    def test_admin_refund_simulated_held(self):
        rid, ric = _make_confirmed_richiesta()
        prezzo = float(ric["prezzo_finale"])

        # Ensure sufficient wallet — top up if needed
        bal = _get_wallet(CLIENT_TOKEN)
        if bal < prezzo:
            requests.post(f"{API}/wallet/add", json={"amount": prezzo + 10},
                          headers=_h(CLIENT_TOKEN), timeout=30)

        # Pay via wallet -> held
        r = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                          json={"method": "wallet"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 200, f"checkout: {r.text}"

        bal_after_hold = _get_wallet(CLIENT_TOKEN)

        # Admin refund
        rf = requests.post(f"{API}/pay/richiesta/{rid}/refund",
                           json={"reason": "test_refund"}, headers=_admin_h(), timeout=30)
        assert rf.status_code == 200, f"refund failed: {rf.status_code} {rf.text}"
        j = rf.json()
        assert j.get("refunded") is True and j.get("psp") == "simulato"

        # Verify richiesta state
        ric2 = _get_richiesta(rid)
        assert ric2["pagamento_lavoro"]["stato"] == "refunded"

        # Client wallet credited back
        bal_after_refund = _get_wallet(CLIENT_TOKEN)
        assert (bal_after_refund - bal_after_hold) >= (prezzo - 0.02), \
            f"client not refunded: hold={bal_after_hold} refund={bal_after_refund} prezzo={prezzo}"


# --------------------------------------------------------------------------
# 5) persona_lf binario blocked (voucher path, not PSP)
# --------------------------------------------------------------------------
class TestLfBlocked:
    def test_lf_binario_not_allowed_for_psp(self):
        # Attempt to create an LF richiesta with same client (needs an LF provider onboarded to confirm).
        # If we can't build a confirmed LF richiesta, skip. We just try the endpoint on any LF richiesta.
        # Instead, we search among client's richieste for an LF one; if none, skip.
        r = requests.get(f"{API}/pulizie/richieste", headers=_h(CLIENT_TOKEN), timeout=30)
        assert r.status_code == 200
        lf_conf = [x for x in r.json() if x.get("binario") == "persona_lf" and x.get("provider_scelto")
                   and x.get("pagamento_lavoro", {}).get("stato") not in ("held", "charged", "released")]
        if not lf_conf:
            pytest.skip("no confirmed LF richiesta available to exercise lf_uses_voucher_not_psp")
        rid = lf_conf[0]["richiesta_id"]
        rr = requests.post(f"{API}/pay/richiesta/{rid}/checkout",
                           json={"method": "wallet"}, headers=_h(CLIENT_TOKEN), timeout=30)
        assert rr.status_code == 400 and "lf_uses_voucher_not_psp" in rr.text
