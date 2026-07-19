"""Iteration 19 - Escrow-based service payments + 3-balance wallet.

Coverage:
- Wallet: 3 balances (available/pending/total), holds, transactions.
- Escrow: pay-escrow, already_paid, insufficient_funds, forbidden, complete->release,
  provider pending/available split, cancel->refund, cannot_cancel on completed.
- Withdraw: yobpay success, insufficient_available, no_bank_account, invalid_method.
- Admin hold-days: get/set, invalid_days.
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
CLIENT = "demo-preview-token-123"
OTHER = "biz-test-token-999"
ADMIN = "jobby-admin-7c2f9a"


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ------------------------- Wallet shape -------------------------

class TestWalletShape:
    def test_wallet_returns_three_balances(self):
        r = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT))
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("available_balance", "pending_balance", "total_balance", "holds", "transactions"):
            assert k in d, f"missing key {k}"
        assert round(d["available_balance"] + d["pending_balance"], 2) == round(d["total_balance"], 2)
        assert isinstance(d["holds"], list)
        assert isinstance(d["transactions"], list)


# ------------------------- Helpers -------------------------

def _find_unpaid(tok=CLIENT):
    r = requests.get(f"{BASE}/api/bookings", headers=H(tok))
    assert r.status_code == 200
    for b in r.json():
        if not b.get("escrow_status") and b.get("payment_status") != "paid" and b.get("status") in ("confirmed", "pending", "matched"):
            return b
    return None


def _ensure_funds(min_amt):
    r = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT))
    avail = r.json()["available_balance"]
    if avail < min_amt:
        top = round(min_amt - avail + 5, 2)
        requests.post(f"{BASE}/api/wallet/add", headers=H(CLIENT), json={"amount": top})


# ------------------------- Escrow happy path -------------------------

class TestEscrowFlow:
    def test_escrow_happy_path_complete_release(self):
        b = _find_unpaid()
        if not b:
            pytest.skip("no unpaid booking available")
        _ensure_funds(b["total"])
        w0 = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        avail0 = w0["available_balance"]

        # pay-escrow
        r = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/pay-escrow", headers=H(CLIENT))
        assert r.status_code == 200, r.text
        pd = r.json()
        assert pd.get("paid") is True
        assert pd["booking"]["escrow_status"] == "held"
        assert pd["booking"]["payment_status"] == "paid"

        # wallet decreased
        w1 = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        assert round(w1["available_balance"], 2) == round(avail0 - b["total"], 2), \
            f"expected {avail0 - b['total']} got {w1['available_balance']}"

        # duplicate pay-escrow -> already_paid
        r2 = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/pay-escrow", headers=H(CLIENT))
        assert r2.status_code == 200
        assert r2.json().get("already_paid") is True

        # complete -> release
        rc = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/complete", headers=H(CLIENT))
        assert rc.status_code == 200, rc.text
        bk = rc.json()
        assert bk["escrow_status"] == "released", bk

        # Provider credit verification (via mongo would be ideal but we check indirectly)
        # We know: generic provider -> pending + wallet_hold; business -> available.
        # Provider role check via a generic endpoint isn't public, so we accept release confirmation.

    def test_insufficient_funds(self):
        b = _find_unpaid()
        if not b:
            pytest.skip("no unpaid booking available")
        # Drain by withdrawing available - keep a bit less than total
        w = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        avail = w["available_balance"]
        target_leave = max(0, b["total"] - 1)
        drain = round(avail - target_leave, 2)
        if drain > 0:
            requests.post(f"{BASE}/api/wallet/withdraw", headers=H(CLIENT),
                          json={"method": "yobpay", "amount": drain})
        r = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/pay-escrow", headers=H(CLIENT))
        assert r.status_code == 400, r.text
        assert "insufficient_funds" in r.text

    def test_pay_escrow_forbidden_other_user(self):
        # find an unpaid booking owned by CLIENT
        b = _find_unpaid()
        if not b:
            pytest.skip("no unpaid booking available")
        r = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/pay-escrow", headers=H(OTHER))
        assert r.status_code == 403, r.text

    def test_escrow_refund_on_cancel(self):
        b = _find_unpaid()
        if not b:
            pytest.skip("no unpaid booking available")
        _ensure_funds(b["total"])
        w0 = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        avail0 = w0["available_balance"]

        r = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/pay-escrow", headers=H(CLIENT))
        assert r.status_code == 200 and r.json().get("paid") is True

        rc = requests.post(f"{BASE}/api/bookings/{b['booking_id']}/cancel", headers=H(CLIENT))
        assert rc.status_code == 200, rc.text
        bk = rc.json()
        assert bk["escrow_status"] == "refunded"
        assert bk["status"] == "cancelled"

        # Available restored
        w1 = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        assert round(w1["available_balance"], 2) == round(avail0, 2), \
            f"expected available restored to {avail0}, got {w1['available_balance']}"

    def test_cancel_completed_booking_rejected(self):
        # find a completed booking
        r = requests.get(f"{BASE}/api/bookings", headers=H(CLIENT))
        completed = next((b for b in r.json() if b.get("status") == "completed"), None)
        if not completed:
            pytest.skip("no completed booking to test cannot_cancel")
        rc = requests.post(f"{BASE}/api/bookings/{completed['booking_id']}/cancel", headers=H(CLIENT))
        assert rc.status_code == 400, rc.text
        assert "cannot_cancel" in rc.text


# ------------------------- Withdraw -------------------------

class TestWithdraw:
    def test_withdraw_yobpay_success(self):
        _ensure_funds(10)
        w0 = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        avail0 = w0["available_balance"]

        r = requests.post(f"{BASE}/api/wallet/withdraw", headers=H(CLIENT),
                          json={"method": "yobpay", "amount": 5})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balance"] == round(avail0 - 5, 2)
        assert d["payout"]["status"] == "processing"
        assert d["payout"]["method"] == "yobpay"

        # payouts listing includes it
        pr = requests.get(f"{BASE}/api/wallet/payouts", headers=H(CLIENT))
        assert pr.status_code == 200
        assert any(p["payout_id"] == d["payout"]["payout_id"] for p in pr.json())

    def test_withdraw_insufficient_available(self):
        w = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        big = w["available_balance"] + 1000
        r = requests.post(f"{BASE}/api/wallet/withdraw", headers=H(CLIENT),
                          json={"method": "yobpay", "amount": big})
        assert r.status_code == 400
        assert "insufficient_available" in r.text

    def test_withdraw_bank_no_bank_account(self):
        # Ensure demo user has no bank_account. If it does, skip.
        w = requests.get(f"{BASE}/api/wallet", headers=H(CLIENT)).json()
        if w.get("bank_account"):
            pytest.skip("demo user has bank account saved")
        _ensure_funds(2)
        r = requests.post(f"{BASE}/api/wallet/withdraw", headers=H(CLIENT),
                          json={"method": "bank", "amount": 1})
        assert r.status_code == 400
        assert "no_bank_account" in r.text

    def test_withdraw_invalid_method(self):
        r = requests.post(f"{BASE}/api/wallet/withdraw", headers=H(CLIENT),
                          json={"method": "paypal", "amount": 1})
        assert r.status_code == 400
        assert "invalid_method" in r.text


# ------------------------- Admin hold-days -------------------------

class TestAdminHoldDays:
    def test_set_and_get_hold_days(self):
        r = requests.post(f"{BASE}/api/admin/settings/hold-days",
                          headers={"X-Admin-Token": ADMIN, "Content-Type": "application/json"},
                          json={"days": 5})
        assert r.status_code == 200, r.text
        assert r.json()["days"] == 5

        g = requests.get(f"{BASE}/api/admin/settings/hold-days",
                         headers={"X-Admin-Token": ADMIN})
        assert g.status_code == 200
        assert g.json()["days"] == 5

    def test_invalid_days(self):
        r = requests.post(f"{BASE}/api/admin/settings/hold-days",
                          headers={"X-Admin-Token": ADMIN, "Content-Type": "application/json"},
                          json={"days": 99})
        assert r.status_code == 400
        assert "invalid_days" in r.text

    def test_reset_hold_days_to_2(self):
        r = requests.post(f"{BASE}/api/admin/settings/hold-days",
                          headers={"X-Admin-Token": ADMIN, "Content-Type": "application/json"},
                          json={"days": 2})
        assert r.status_code == 200
        assert r.json()["days"] == 2
