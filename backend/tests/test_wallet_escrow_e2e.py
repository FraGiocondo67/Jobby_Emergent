"""Iter 46 — WALLET ESCROW at CONFIRM (+ 24h hold + QR consegna) e2e tests.

Covers pulizie, driver, listino, QR arm/confirm, insufficient wallet, cancel refund,
auto-release. Restores balances after each test.
"""
import os
import time
import pytest
import requests
import pymongo
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                      "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN = {"X-Admin-Token": "jobby-admin-7c2f9a"}

CLIENT_TOK   = "disp-test-token-777"      # user_disptest01
IMPRESA_TOK  = "req-prov-token"           # user_2f996c8a010a (role=business, pulizie listino)
GIULIA_TOK   = "prov-test-token-888"      # prov_cfbd9805ce97 (provider, driver ncc + pulizie)
BIZ_TOK      = "biz-test-token-999"       # user_2f996c8a010a (same user as impresa: role=business)

MONGO = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB    = MONGO[os.environ.get("DB_NAME", "test_database")]


def _h(tok): return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _me(tok):
    r = requests.get(f"{BASE}/auth/me", headers=_h(tok))
    return r.json() if r.ok else {}


def _wallet_state(user_id: str) -> dict:
    u = DB.users.find_one({"user_id": user_id},
                          {"_id": 0, "wallet_balance": 1, "bonus_credit": 1,
                           "pending_balance": 1, "role": 1, "qr_confirm_enabled": 1})
    return {k: (u or {}).get(k) for k in ("wallet_balance", "bonus_credit",
                                          "pending_balance", "role", "qr_confirm_enabled")}


@pytest.fixture(scope="module")
def ids():
    """user_ids for each bearer used."""
    r = {}
    for name, tok in [("client", CLIENT_TOK), ("impresa", IMPRESA_TOK),
                      ("giulia", GIULIA_TOK), ("biz", BIZ_TOK)]:
        s = DB.user_sessions.find_one({"session_token": tok}, {"_id": 0, "user_id": 1})
        assert s, f"missing session for {tok}"
        r[name] = s["user_id"]
    print("user_ids:", r)
    return r


@pytest.fixture(autouse=True)
def _reset_qr_off():
    """Ensure QR pref starts OFF for the client (each test flips it as needed)."""
    requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK),
                  json={"enabled": False})
    yield
    requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK),
                  json={"enabled": False})


# ---------- helpers to run a pulizie flow up to a given point ----------
def _pulizie_create(publish=True):
    """Client creates a pulizie richiesta. Returns richiesta doc."""
    payload = {
        "binario": "impresa",
        "config": {"home_type": "appartamento", "mq_band": "80_120", "tipo_pulizia": "ordinaria",
                   "extra": [], "stiro_ore": 0, "prodotti": "cliente",
                   "durata_ore": 3, "animali": False},
        "indirizzo": "Via Roma 1, Treviso", "lat": 45.6669, "lng": 12.2433,
        "data_ora": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "flessibilita": "fascia", "ricorrenza": "una_tantum", "publish": publish,
    }
    r = requests.post(f"{BASE}/pulizie/richieste", headers=_h(CLIENT_TOK), json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _admin_invite(rid, provider_ids):
    r = requests.post(f"{BASE}/admin/pulizie/richieste/{rid}/invite",
                      headers=ADMIN, json={"provider_ids": provider_ids})
    assert r.status_code == 200, r.text
    return r.json()


def _propose(rid, prov_tok):
    r = requests.post(f"{BASE}/pulizie/richieste/{rid}/propose",
                      headers=_h(prov_tok), json={"accept": True})
    assert r.status_code == 200, r.text
    return r.json()


def _confirm(rid, provider_id, expect_status=200):
    r = requests.post(f"{BASE}/pulizie/richieste/{rid}/confirm",
                      headers=_h(CLIENT_TOK), json={"provider_id": provider_id})
    assert r.status_code == expect_status, r.text
    return r.json()


def _complete(rid, tok):
    r = requests.post(f"{BASE}/pulizie/richieste/{rid}/complete", headers=_h(tok))
    assert r.status_code == 200, r.text
    return r.json()


# =============== TESTS ===============

class TestPulizieEscrowQrOff:
    def test_confirm_blocks_and_complete_releases(self, ids):
        pre = _wallet_state(ids["client"])
        r = _pulizie_create()
        rid = r["richiesta_id"]
        _admin_invite(rid, [ids["impresa"]])
        prop = _propose(rid, IMPRESA_TOK)
        price = prop["price"]
        assert price > 0

        # Confirm → funds must be blocked (bonus first, then wallet)
        pre_impresa = _wallet_state(ids["impresa"])
        _confirm(rid, ids["impresa"])
        after_client = _wallet_state(ids["client"])
        # bonus should be spent first
        exp_bonus = round(max(0.0, pre["bonus_credit"] - price), 2)
        # amount still to take from balance
        taken_from_bonus = round(pre["bonus_credit"] - exp_bonus, 2)
        exp_bal = round(pre["wallet_balance"] - (price - taken_from_bonus), 2)
        assert abs(after_client["bonus_credit"] - exp_bonus) < 0.01, \
            f"bonus expected {exp_bonus} got {after_client['bonus_credit']}"
        assert abs(after_client["wallet_balance"] - exp_bal) < 0.01, \
            f"wallet expected {exp_bal} got {after_client['wallet_balance']}"

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc["escrow"]["stato"] == "held"
        assert abs(doc["escrow"]["held"] - price) < 0.01

        # Complete → earner credited. Note: req-prov-token user is role=business, so
        # net is credited to wallet_balance immediately (no wallet_holds).
        _complete(rid, IMPRESA_TOK)
        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["escrow"]["stato"] == "released", doc2.get("escrow")
        net = doc2["escrow"]["net_provider"]
        assert net > 0

        after_impresa = _wallet_state(ids["impresa"])
        if pre_impresa["role"] == "business":
            assert abs(after_impresa["wallet_balance"] - (pre_impresa["wallet_balance"] + net)) < 0.01, \
                f"business earner should get immediate wallet credit"
            holds = list(DB.wallet_holds.find({"richiesta_id": rid, "status": "pending"}))
            assert not holds, "business must not have wallet_holds"
        else:
            assert abs(after_impresa["pending_balance"] - (pre_impresa["pending_balance"] + net)) < 0.01
            holds = list(DB.wallet_holds.find({"richiesta_id": rid, "status": "pending"}))
            assert holds, "provider must have a wallet_holds doc"

        # Restore client wallet (best-effort — client already paid, but we keep test data)
        _restore_client(ids["client"])


class TestPulizieEscrowQrOn:
    def test_complete_arms_delivery_confirmation(self, ids):
        # Turn ON QR pref
        r = requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK),
                          json={"enabled": True})
        assert r.status_code == 200

        req = _pulizie_create()
        rid = req["richiesta_id"]
        _admin_invite(rid, [ids["impresa"]])
        prop = _propose(rid, IMPRESA_TOK)
        _confirm(rid, ids["impresa"])
        # Complete → should ARM, not release
        pre_impresa = _wallet_state(ids["impresa"])
        _complete(rid, IMPRESA_TOK)

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc.get("conferma_pending") is True, doc.get("conferma_pending")
        assert doc["escrow"]["stato"] == "held", "must still be held (not released yet)"

        conf = DB.delivery_confirmations.find_one({"ref_id": rid, "released": False})
        assert conf, "delivery_confirmations must exist after arm"
        assert conf["earner_id"] == ids["impresa"]
        assert conf["client_id"] == ids["client"]

        # Client GET /delivery/ref/{rid}
        ref = requests.get(f"{BASE}/delivery/ref/{rid}", headers=_h(CLIENT_TOK))
        assert ref.status_code == 200
        rj = ref.json()
        assert "token" in rj and "code" in rj

        # Wrong code → 400 invalid_code (from earner)
        bad = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(IMPRESA_TOK),
                            json={"ref_id": rid, "code": "000000"})
        assert bad.status_code == 400, bad.text
        assert "invalid_code" in bad.text

        # Non-earner (Giulia) → 403
        wrong_earner = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(GIULIA_TOK),
                                     json={"ref_id": rid, "code": rj["code"]})
        assert wrong_earner.status_code == 403, wrong_earner.text

        # Correct code → released
        ok = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(IMPRESA_TOK),
                           json={"ref_id": rid, "code": rj["code"]})
        assert ok.status_code == 200, ok.text
        assert ok.json().get("confirmed") is True

        after = _wallet_state(ids["impresa"])
        net = ok.json()["released"]
        assert net > 0
        if pre_impresa["role"] == "business":
            assert abs(after["wallet_balance"] - (pre_impresa["wallet_balance"] + net)) < 0.01
        else:
            assert abs(after["pending_balance"] - (pre_impresa["pending_balance"] + net)) < 0.01
        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["escrow"]["stato"] == "released"
        assert not doc2.get("conferma_pending")

        _restore_client(ids["client"])


class TestInsufficientFunds:
    def test_confirm_fails_when_wallet_empty(self, ids):
        # Zero out client funds
        prev = DB.users.find_one({"user_id": ids["client"]},
                                 {"_id": 0, "wallet_balance": 1, "bonus_credit": 1})
        try:
            DB.users.update_one({"user_id": ids["client"]},
                                {"$set": {"wallet_balance": 0.0, "bonus_credit": 0.0}})
            req = _pulizie_create()
            rid = req["richiesta_id"]
            _admin_invite(rid, [ids["impresa"]])
            _propose(rid, IMPRESA_TOK)
            r = requests.post(f"{BASE}/pulizie/richieste/{rid}/confirm",
                              headers=_h(CLIENT_TOK), json={"provider_id": ids["impresa"]})
            assert r.status_code == 400, r.text
            assert "insufficient_wallet" in r.text

            # richiesta must NOT be confirmed, no escrow
            doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
            assert doc["stato"] != "confermata"
            assert not doc.get("escrow"), doc.get("escrow")

            after = _wallet_state(ids["client"])
            assert after["wallet_balance"] == 0.0 and after["bonus_credit"] == 0.0
        finally:
            DB.users.update_one({"user_id": ids["client"]},
                                {"$set": {"wallet_balance": prev["wallet_balance"],
                                          "bonus_credit": prev["bonus_credit"]}})


class TestCancelRefund:
    def test_cancel_refunds_held_funds(self, ids):
        pre = _wallet_state(ids["client"])
        req = _pulizie_create()
        rid = req["richiesta_id"]
        _admin_invite(rid, [ids["impresa"]])
        _propose(rid, IMPRESA_TOK)
        _confirm(rid, ids["impresa"])
        mid = _wallet_state(ids["client"])
        assert mid["wallet_balance"] + mid["bonus_credit"] < pre["wallet_balance"] + pre["bonus_credit"]

        c = requests.post(f"{BASE}/pulizie/richieste/{rid}/cancel", headers=_h(CLIENT_TOK))
        assert c.status_code == 200, c.text

        after = _wallet_state(ids["client"])
        assert abs(after["bonus_credit"] - pre["bonus_credit"]) < 0.01, \
            f"bonus not restored: pre {pre['bonus_credit']} vs after {after['bonus_credit']}"
        assert abs(after["wallet_balance"] - pre["wallet_balance"]) < 0.01, \
            f"wallet not restored: pre {pre['wallet_balance']} vs after {after['wallet_balance']}"

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc["escrow"]["stato"] == "refunded"


class TestDriverNccEscrow:
    def test_direct_driver_confirm_and_complete(self, ids):
        pre_client = _wallet_state(ids["client"])
        pre_giulia = _wallet_state(ids["giulia"])
        pickup = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        body = {
            "tipo": "ncc", "classe": "standard",
            "partenza": {"label": "Treviso", "lat": 45.6669, "lng": 12.2433},
            "destinazione": {"label": "Venezia Aeroporto", "lat": 45.5053, "lng": 12.3519},
            "pickup_at": pickup, "flight_number": "", "passeggeri": 1, "bagagli": 1,
            "passeggero_nome": "Test", "passeggero_tel": "+390000000",
            "minore": False, "minore_consenso": False, "special": [],
            "ritorno": None, "note": "test",
            "target_provider_id": ids["giulia"],
        }
        r = requests.post(f"{BASE}/driver/richieste", headers=_h(CLIENT_TOK), json=body)
        assert r.status_code == 200, r.text
        rid = r.json()["richiesta_id"]

        # Provider accepts (auto-confirm when target-direct at listino price)
        p = requests.post(f"{BASE}/driver/richieste/{rid}/propose", headers=_h(GIULIA_TOK),
                          json={"accept": True})
        assert p.status_code == 200, p.text
        pj = p.json()

        # If auto_confirmed True, escrow already held. Else explicit confirm.
        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        auto_confirmed = pj.get("auto_confirmed") is True
        if doc["stato"] != "confermata":
            c = requests.post(f"{BASE}/driver/richieste/{rid}/confirm",
                              headers=_h(CLIENT_TOK), json={"provider_id": ids["giulia"]})
            assert c.status_code == 200, c.text
        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc.get("escrow", {}).get("stato") == "held", (
            f"escrow not held (auto_confirmed={auto_confirmed}). "
            f"BUG: driver auto-confirm path (direct target + listino accept) "
            f"does not call we.hold — see routers/driver.py lines 464-476. "
            f"Doc escrow={doc.get('escrow')}"
        )
        prezzo = doc["prezzo_finale"]
        held_now_client = _wallet_state(ids["client"])
        assert held_now_client["wallet_balance"] + held_now_client["bonus_credit"] < \
            pre_client["wallet_balance"] + pre_client["bonus_credit"]

        # depart → complete
        dp = requests.post(f"{BASE}/driver/richieste/{rid}/depart", headers=_h(GIULIA_TOK))
        assert dp.status_code == 200, dp.text
        cp = requests.post(f"{BASE}/driver/richieste/{rid}/complete", headers=_h(GIULIA_TOK),
                           json={})
        assert cp.status_code == 200, cp.text

        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["escrow"]["stato"] == "released"
        net = doc2["escrow"]["net_provider"]
        # 12% fee expected for driver
        assert abs(net - round(prezzo * 0.88, 2)) < 0.5, f"net {net} vs prezzo {prezzo}*(1-0.12)"

        after_giulia = _wallet_state(ids["giulia"])
        assert abs(after_giulia["pending_balance"] - (pre_giulia["pending_balance"] + net)) < 0.01
        holds = list(DB.wallet_holds.find({"richiesta_id": rid, "status": "pending"}))
        assert holds, "provider must have a wallet_holds doc after complete"

        _restore_client(ids["client"])


class TestListinoBusinessOrder:
    def _order_helper(self, ids, qr_on: bool):
        # QR pref
        requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK),
                      json={"enabled": qr_on})

        pre_client = _wallet_state(ids["client"])
        pre_biz = _wallet_state(ids["biz"])
        # Pick a lavanderia product (Lavaggio camicia €3.5) qty 2 → total 7
        prods = requests.get(f"{BASE}/listino/business/{ids['biz']}?category=lavanderia",
                             headers=_h(CLIENT_TOK)).json()
        assert prods
        item = prods[0]
        body = {"business_id": ids["biz"], "category": "lavanderia",
                "items": [{"item_id": item["item_id"], "qty": 2}],
                "address": "Via Roma 1", "lat": 45.66, "lng": 12.24, "note": ""}
        r = requests.post(f"{BASE}/listino/order", headers=_h(CLIENT_TOK), json=body)
        assert r.status_code == 200, r.text
        rid = r.json()["request_id"]
        total = r.json()["total"]
        assert total > 0

        # Verify funds blocked
        mid = _wallet_state(ids["client"])
        assert abs((pre_client["wallet_balance"] + pre_client["bonus_credit"]) -
                   (mid["wallet_balance"] + mid["bonus_credit"]) - total) < 0.01

        # Business accepts
        resp = requests.post(f"{BASE}/listino/order/{rid}/respond", headers=_h(BIZ_TOK),
                             json={"accept": True, "eta": "domani", "mode": "consegna", "note": ""})
        assert resp.status_code == 200, resp.text

        # Business complete
        comp = requests.post(f"{BASE}/listino/order/{rid}/complete", headers=_h(BIZ_TOK))
        assert comp.status_code == 200, comp.text
        cj = comp.json()

        if qr_on:
            assert "awaiting_confirmation" not in cj or cj.get("released") is None, cj
            # business should not be credited yet
            mid_biz = _wallet_state(ids["biz"])
            assert abs(mid_biz["wallet_balance"] - pre_biz["wallet_balance"]) < 0.01, \
                f"business must NOT be credited yet in QR-on mode"
            # conferma_pending true
            o = DB.business_requests.find_one({"request_id": rid}, {"_id": 0})
            assert o.get("conferma_pending") is True

            # Client GET code
            ref = requests.get(f"{BASE}/delivery/ref/{rid}", headers=_h(CLIENT_TOK))
            assert ref.status_code == 200, ref.text
            code = ref.json()["code"]

            # Business confirm-code
            ok = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(BIZ_TOK),
                               json={"ref_id": rid, "code": code})
            assert ok.status_code == 200, ok.text

        # Business now credited immediately (no 24h hold)
        after_biz = _wallet_state(ids["biz"])
        assert abs(after_biz["wallet_balance"] - (pre_biz["wallet_balance"] + total)) < 0.01, \
            f"biz wallet expected {pre_biz['wallet_balance'] + total} got {after_biz['wallet_balance']}"
        # No wallet_holds for business
        holds = list(DB.wallet_holds.find({"richiesta_id": rid, "status": "pending"}))
        assert not holds

        # Restore biz wallet to pre state (so subsequent test starts clean)
        DB.users.update_one({"user_id": ids["biz"]},
                            {"$set": {"wallet_balance": pre_biz["wallet_balance"]}})
        _restore_client(ids["client"])

    def test_order_qr_off_immediate_release(self, ids):
        self._order_helper(ids, qr_on=False)

    def test_order_qr_on_arm_then_release(self, ids):
        self._order_helper(ids, qr_on=True)


class TestAutoRelease:
    def test_expired_arming_auto_releases(self, ids):
        # Turn on QR for client
        requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK),
                      json={"enabled": True})
        req = _pulizie_create()
        rid = req["richiesta_id"]
        _admin_invite(rid, [ids["impresa"]])
        _propose(rid, IMPRESA_TOK)
        _confirm(rid, ids["impresa"])
        pre_biz = _wallet_state(ids["impresa"])
        _complete(rid, IMPRESA_TOK)

        conf = DB.delivery_confirmations.find_one({"ref_id": rid, "released": False})
        assert conf
        # Push deadline into the past
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        DB.delivery_confirmations.update_one({"confirm_id": conf["confirm_id"]},
                                             {"$set": {"deadline": past}})
        # Any /wallet call triggers auto_release_expired
        w = requests.get(f"{BASE}/wallet", headers=_h(CLIENT_TOK))
        assert w.status_code == 200

        conf2 = DB.delivery_confirmations.find_one({"confirm_id": conf["confirm_id"]},
                                                   {"_id": 0})
        assert conf2.get("released") is True, "auto-release did not fire"
        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc["escrow"]["stato"] == "released"

        # Earner credited (business role → wallet_balance immediate)
        after_biz = _wallet_state(ids["impresa"])
        net = doc["escrow"]["net_provider"]
        if pre_biz["role"] == "business":
            assert abs(after_biz["wallet_balance"] - (pre_biz["wallet_balance"] + net)) < 0.01
        else:
            assert abs(after_biz["pending_balance"] - (pre_biz["pending_balance"] + net)) < 0.01

        _restore_client(ids["client"])


# ---------- utilities ----------
def _restore_client(uid: str):
    """Reset client wallet to the seed defaults (500 wallet + 50 bonus)."""
    DB.users.update_one({"user_id": uid},
                        {"$set": {"wallet_balance": 500.0, "bonus_credit": 50.0}})
