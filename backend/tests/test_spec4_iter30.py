"""Iter 30 — Spec 4: Cancellations / no-show / reviews / private client score / reliability.
Generic engine over db.richieste (Pulizie category). Payments are simulated (wallet_balance / lf_borsellino).
"""
import os
from datetime import datetime, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "https://jobby-mvp-update.preview.emergentagent.com"
API = f"{BASE}/api"
ADMIN = {"X-Admin-Token": "jobby-admin-7c2f9a"}
CLIENT = {"Authorization": "Bearer disp-test-token-777"}
BIZ_PROV = {"Authorization": "Bearer req-prov-token"}      # impresa pulizie provider
LF_PROV = {"Authorization": "Bearer lf-prov-token"}        # persona_lf pulizie provider
GIULIA = {"Authorization": "Bearer prov-test-token-888"}

MONGO = MongoClient("mongodb://localhost:27017")["test_database"]

CLIENT_ID = "user_disptest01"
BIZ_PROV_ID = "user_2f996c8a010a"
LF_PROV_ID = "user_63e358a12980"


# ---------- helpers ----------
def _get_wallet(uid):
    u = MONGO.users.find_one({"user_id": uid}, {"_id": 0, "wallet_balance": 1, "lf_borsellino": 1})
    return {"wallet": round(u.get("wallet_balance", 0) or 0, 2),
            "lf": round(u.get("lf_borsellino", 0) or 0, 2)}


def _create_impresa_richiesta(data_ora_iso=None):
    """Create a pulizie impresa richiesta and drive it to 'confermata' via invite+propose+confirm."""
    if not data_ora_iso:
        data_ora_iso = (datetime.now() + timedelta(days=10)).isoformat()
    payload = {
        "binario": "impresa",
        "config": {"mq_band": "80_120", "home_type": "appartamento", "tipo": "ordinaria",
                   "bagni": 2, "camere": 2, "durata_ore": 3, "extra": [], "stiro_ore": 0,
                   "fascia_oraria": "mattina"},
        "indirizzo": "Via Test 1, Treviso", "lat": 45.6669, "lng": 12.2433,
        "data_ora": data_ora_iso, "flessibilita": "fascia", "ricorrenza": "una_tantum",
        "giorni_preferiti": [], "note": "TEST_iter30", "foto": [], "parcheggio": "libero", "publish": True,
    }
    r = requests.post(f"{API}/pulizie/richieste", json=payload, headers=CLIENT)
    assert r.status_code == 200, r.text
    rid = r.json()["richiesta_id"]

    inv = requests.post(f"{API}/admin/pulizie/richieste/{rid}/invite",
                        json={"provider_ids": [BIZ_PROV_ID]}, headers=ADMIN)
    assert inv.status_code == 200, inv.text

    p = requests.post(f"{API}/pulizie/richieste/{rid}/propose",
                      json={"accept": True}, headers=BIZ_PROV)
    assert p.status_code == 200, p.text

    c = requests.post(f"{API}/pulizie/richieste/{rid}/confirm",
                      json={"provider_id": BIZ_PROV_ID}, headers=CLIENT)
    assert c.status_code == 200, c.text
    return rid


def _create_lf_richiesta(data_ora_iso=None):
    if not data_ora_iso:
        data_ora_iso = (datetime.now() + timedelta(days=10)).isoformat()
    # LF: nominale round up to multiples of 10, needs borsellino coverage
    payload = {
        "binario": "persona_lf",
        "config": {"mq_band": "fino50", "home_type": "appartamento", "tipo": "ordinaria",
                   "bagni": 1, "camere": 1, "durata_ore": 2, "extra": [], "stiro_ore": 0,
                   "fascia_oraria": "mattina"},
        "indirizzo": "Via Test 2, Treviso", "lat": 45.6669, "lng": 12.2433,
        "data_ora": data_ora_iso, "flessibilita": "fascia", "ricorrenza": "una_tantum",
        "giorni_preferiti": [], "note": "TEST_iter30_lf", "foto": [], "parcheggio": "libero", "publish": True,
    }
    r = requests.post(f"{API}/pulizie/richieste", json=payload, headers=CLIENT)
    assert r.status_code == 200, r.text
    rid = r.json()["richiesta_id"]
    inv = requests.post(f"{API}/admin/pulizie/richieste/{rid}/invite",
                        json={"provider_ids": [LF_PROV_ID]}, headers=ADMIN)
    assert inv.status_code == 200, inv.text
    p = requests.post(f"{API}/pulizie/richieste/{rid}/propose",
                      json={"accept": True}, headers=LF_PROV)
    assert p.status_code == 200, p.text
    c = requests.post(f"{API}/pulizie/richieste/{rid}/confirm",
                      json={"provider_id": LF_PROV_ID}, headers=CLIENT)
    assert c.status_code == 200, c.text
    return rid


def _set_data_ora(rid, dt: datetime):
    MONGO.richieste.update_one({"richiesta_id": rid}, {"$set": {"data_ora": dt.isoformat()}})


# =============== ADMIN config ================
class TestAdminConfig:
    def test_get_config(self):
        r = requests.get(f"{API}/admin/spec4/config", headers=ADMIN)
        assert r.status_code == 200
        cfg = r.json()
        for k in ("cancel_free_hours", "cancel_fee_only_hours", "cancel_late_labor_pct",
                  "lf_free_hours", "noshow_grace_min", "client_strike_window_days",
                  "client_strike_threshold", "review_window_days", "new_provider_reviews"):
            assert k in cfg, f"missing {k}"
        assert cfg["cancel_free_hours"] == 48
        assert cfg["cancel_fee_only_hours"] == 24

    def test_update_and_restore(self):
        upd = requests.post(f"{API}/admin/spec4/config",
                            json={"cancel_late_labor_pct": 60}, headers=ADMIN)
        assert upd.status_code == 200
        assert upd.json()["cancel_late_labor_pct"] == 60
        # verify persistence
        got = requests.get(f"{API}/admin/spec4/config", headers=ADMIN).json()
        assert got["cancel_late_labor_pct"] == 60
        # restore
        requests.post(f"{API}/admin/spec4/config",
                      json={"cancel_late_labor_pct": 50}, headers=ADMIN)
        got2 = requests.get(f"{API}/admin/spec4/config", headers=ADMIN).json()
        assert got2["cancel_late_labor_pct"] == 50

    def test_unauthorized(self):
        r = requests.get(f"{API}/admin/spec4/config")
        assert r.status_code in (401, 403)


# =============== Cancel tiers (impresa) ================
class TestCancelTiersImpresa:
    def test_free_tier(self):
        rid = _create_impresa_richiesta((datetime.now() + timedelta(days=5)).isoformat())
        pol = requests.get(f"{API}/richieste/{rid}/cancel-policy", headers=CLIENT).json()
        assert pol["tier"] == "free"

        before = _get_wallet(CLIENT_ID)
        r_doc = MONGO.richieste.find_one({"richiesta_id": rid})
        fee = float(r_doc["pagamento_fee"].get("importo", 0) or 0)
        labor = float(r_doc["pagamento_lavoro"].get("importo", 0) or 0)

        r = requests.post(f"{API}/richieste/{rid}/cancel", json={"reason": "test"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tier"] == "free"
        assert round(j["refund_client"], 2) == round(fee + labor, 2)
        after = _get_wallet(CLIENT_ID)
        assert round(after["wallet"] - before["wallet"], 2) == round(fee + labor, 2)
        # richiesta annullata
        doc = MONGO.richieste.find_one({"richiesta_id": rid})
        assert doc["stato"] == "annullata"

    def test_fee_only_tier(self):
        rid = _create_impresa_richiesta()
        # 30h in the future -> fee_only
        _set_data_ora(rid, datetime.now() + timedelta(hours=30))
        pol = requests.get(f"{API}/richieste/{rid}/cancel-policy", headers=CLIENT).json()
        assert pol["tier"] == "fee_only", pol

        r_doc = MONGO.richieste.find_one({"richiesta_id": rid})
        fee = float(r_doc["pagamento_fee"].get("importo", 0) or 0)
        labor = float(r_doc["pagamento_lavoro"].get("importo", 0) or 0)
        before = _get_wallet(CLIENT_ID)

        r = requests.post(f"{API}/richieste/{rid}/cancel", json={"reason": "t"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tier"] == "fee_only"
        assert round(j["withheld_fee"], 2) == round(fee, 2)
        assert round(j["refund_client"], 2) == round(labor, 2)
        after = _get_wallet(CLIENT_ID)
        assert round(after["wallet"] - before["wallet"], 2) == round(labor, 2)

    def test_late_tier_with_indennizzo_and_strike(self):
        rid = _create_impresa_richiesta()
        # 5h in the future -> late (< cancel_fee_only_hours 24)
        _set_data_ora(rid, datetime.now() + timedelta(hours=5))
        pol = requests.get(f"{API}/richieste/{rid}/cancel-policy", headers=CLIENT).json()
        assert pol["tier"] == "late", pol

        r_doc = MONGO.richieste.find_one({"richiesta_id": rid})
        fee = float(r_doc["pagamento_fee"].get("importo", 0) or 0)
        labor = float(r_doc["pagamento_lavoro"].get("importo", 0) or 0)
        indennizzo_exp = round(labor * 0.5, 2)
        refund_exp = round(labor - indennizzo_exp, 2)

        c_before = _get_wallet(CLIENT_ID)
        p_before = _get_wallet(BIZ_PROV_ID)

        r = requests.post(f"{API}/richieste/{rid}/cancel", json={"reason": "t"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tier"] == "late"
        assert round(j["withheld_fee"], 2) == round(fee, 2)
        assert round(j["indennizzo_provider"], 2) == indennizzo_exp
        assert round(j["refund_client"], 2) == refund_exp
        assert j["strike"] is True

        c_after = _get_wallet(CLIENT_ID)
        p_after = _get_wallet(BIZ_PROV_ID)
        assert round(c_after["wallet"] - c_before["wallet"], 2) == refund_exp
        assert round(p_after["wallet"] - p_before["wallet"], 2) == indennizzo_exp

        # reliability event
        u = MONGO.users.find_one({"user_id": CLIENT_ID}, {"_id": 0, "reliability_events": 1})
        assert any(e.get("kind") == "cancel_late" and e.get("richiesta_id") == rid
                   for e in (u.get("reliability_events") or []))


# =============== Cancel LF (Libretto Famiglia) ================
class TestCancelLF:
    def test_late_lf(self):
        rid = _create_lf_richiesta()
        # Nominale should have been debited from lf_borsellino at confirm.
        r_doc = MONGO.richieste.find_one({"richiesta_id": rid})
        pl = r_doc.get("pagamento_lavoro") or {}
        nominale = float(pl.get("nominale", 0) or 0)
        fee = float(r_doc.get("pagamento_fee", {}).get("importo", 0) or 0)
        assert nominale > 0, f"nominale should be set on confirm, got {pl}"

        _set_data_ora(rid, datetime.now() + timedelta(hours=5))
        pol = requests.get(f"{API}/richieste/{rid}/cancel-policy", headers=CLIENT).json()
        assert pol["tier"] == "lf_late"

        before = _get_wallet(CLIENT_ID)
        r = requests.post(f"{API}/richieste/{rid}/cancel", json={"reason": "t"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tier"] == "lf_late"
        assert j["strike"] is True
        assert round(j["withheld_fee"], 2) == round(fee, 2)
        after = _get_wallet(CLIENT_ID)
        assert round(after["lf"] - before["lf"], 2) == round(nominale, 2), \
            f"lf_borsellino should be credited back nominale ({nominale})"

    def test_free_lf(self):
        rid = _create_lf_richiesta((datetime.now() + timedelta(days=5)).isoformat())
        r_doc = MONGO.richieste.find_one({"richiesta_id": rid})
        pl = r_doc.get("pagamento_lavoro") or {}
        nominale = float(pl.get("nominale", 0) or 0)
        fee = float(r_doc.get("pagamento_fee", {}).get("importo", 0) or 0)

        before = _get_wallet(CLIENT_ID)
        r = requests.post(f"{API}/richieste/{rid}/cancel", json={"reason": "t"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tier"] == "free"
        assert j.get("strike", False) is False
        assert round(j["refund_client"], 2) == round(fee, 2)
        after = _get_wallet(CLIENT_ID)
        assert round(after["wallet"] - before["wallet"], 2) == round(fee, 2)
        # nominale freed
        assert round(after["lf"] - before["lf"], 2) == round(nominale, 2)


# =============== Provider cancel ================
class TestProviderCancel:
    def test_provider_cancel_full_refund(self):
        rid = _create_impresa_richiesta((datetime.now() + timedelta(days=10)).isoformat())
        r_doc = MONGO.richieste.find_one({"richiesta_id": rid})
        fee = float(r_doc["pagamento_fee"].get("importo", 0) or 0)
        labor = float(r_doc["pagamento_lavoro"].get("importo", 0) or 0)
        expected_refund = round(fee + labor, 2)

        before = _get_wallet(CLIENT_ID)
        r = requests.post(f"{API}/richieste/{rid}/provider-cancel",
                          json={"reason": "unable"}, headers=BIZ_PROV)
        assert r.status_code == 200, r.text
        j = r.json()
        assert round(j["refund_client"], 2) == expected_refund
        assert j["risostituzione"] is True

        after = _get_wallet(CLIENT_ID)
        assert round(after["wallet"] - before["wallet"], 2) == expected_refund

        doc = MONGO.richieste.find_one({"richiesta_id": rid})
        assert doc["stato"] == "in_matching"
        assert doc.get("provider_scelto") in (None, "")
        assert doc.get("risostituzione") is True
        # admin alert
        alert = MONGO.admin_alerts.find_one({"richiesta_id": rid, "kind": "provider_cancel"})
        assert alert is not None


# =============== No-show ================
class TestNoShow:
    def test_too_early(self):
        rid = _create_impresa_richiesta((datetime.now() + timedelta(days=2)).isoformat())
        r = requests.post(f"{API}/richieste/{rid}/no-show",
                          json={"against": "provider"}, headers=CLIENT)
        assert r.status_code == 400, r.text
        assert "too_early" in r.text

    def test_report_after_grace(self):
        rid = _create_impresa_richiesta()
        # set data_ora to 30 minutes ago -> allowed (grace 15 min)
        _set_data_ora(rid, datetime.now() - timedelta(minutes=30))
        r = requests.post(f"{API}/richieste/{rid}/no-show",
                          json={"against": "provider"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["reported"] is True
        assert j["against"] == "provider"
        doc = MONGO.richieste.find_one({"richiesta_id": rid})
        assert doc["no_show"]["against"] == "provider"
        assert doc["no_show"]["verified"] is False
        assert MONGO.admin_alerts.find_one({"richiesta_id": rid, "kind": "no_show"}) is not None


# =============== Reviews ================
def _complete_richiesta(rid):
    # start (client) then complete (provider)
    r1 = requests.post(f"{API}/pulizie/richieste/{rid}/start", headers=CLIENT)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{API}/pulizie/richieste/{rid}/complete", headers=BIZ_PROV)
    assert r2.status_code == 200, r2.text


class TestReviews:
    _rid = None

    def test_create_review(self):
        rid = _create_impresa_richiesta((datetime.now() + timedelta(hours=2)).isoformat())
        _complete_richiesta(rid)
        TestReviews._rid = rid

        r = requests.post(f"{API}/richieste/{rid}/review",
                          json={"rating": 5, "comment": "TEST_iter30 great job"}, headers=CLIENT)
        assert r.status_code == 200, r.text
        rev = r.json()
        assert rev["rating"] == 5
        assert rev["moderato"] is False

    def test_provider_reviews_hidden_before_approval(self):
        r = requests.get(f"{API}/providers/{BIZ_PROV_ID}/reviews")
        assert r.status_code == 200
        j = r.json()
        # since not moderated yet, not counted
        assert j["is_new"] is True or j["count"] < 3
        assert j["badge"] == "Nuovo su JOBBY" or not j["is_new"]

    def test_admin_moderation_queue_and_approve(self):
        q = requests.get(f"{API}/admin/spec4/moderation", headers=ADMIN)
        assert q.status_code == 200
        rids = [x["richiesta_id"] for x in q.json()]
        assert TestReviews._rid in rids

        r = requests.post(f"{API}/admin/spec4/moderation/{TestReviews._rid}",
                          json={"action": "approve"}, headers=ADMIN)
        assert r.status_code == 200
        assert r.json()["action"] == "approve"

        # now should show in provider reviews
        pr = requests.get(f"{API}/providers/{BIZ_PROV_ID}/reviews").json()
        assert pr["count"] >= 1
        assert any(rv["rating"] == 5 for rv in pr["reviews"])

    def test_provider_reply(self):
        r = requests.post(f"{API}/richieste/{TestReviews._rid}/review/reply",
                          json={"reply": "Grazie mille!"}, headers=BIZ_PROV)
        assert r.status_code == 200
        # second reply forbidden
        r2 = requests.post(f"{API}/richieste/{TestReviews._rid}/review/reply",
                           json={"reply": "again"}, headers=BIZ_PROV)
        assert r2.status_code == 400

    def test_client_delete_review(self):
        r = requests.delete(f"{API}/richieste/{TestReviews._rid}/review", headers=CLIENT)
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        doc = MONGO.richieste.find_one({"richiesta_id": TestReviews._rid})
        assert doc.get("recensione") in (None, {})


# =============== Client private rating ================
class TestRateClient:
    def test_rate_client_and_reliability(self):
        rid = _create_impresa_richiesta((datetime.now() + timedelta(hours=2)).isoformat())
        _complete_richiesta(rid)
        r = requests.post(f"{API}/richieste/{rid}/rate-client",
                          json={"rating": 2, "flags": ["condizioni_diverse", "invalid_flag"],
                                "note": "TEST_iter30 note"}, headers=BIZ_PROV)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "condizioni_diverse" in j["flags"]
        assert "invalid_flag" not in j["flags"]  # filtered

        # ensure valutazione_cliente stored, and NOT returned in client-visible richiesta reads
        doc = MONGO.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc.get("valutazione_cliente", {}).get("rating") == 2
        u = MONGO.users.find_one({"user_id": CLIENT_ID}, {"_id": 0, "client_private_scores": 1})
        assert any(s.get("richiesta_id") == rid for s in (u.get("client_private_scores") or []))

        # admin reliability endpoint
        rl = requests.get(f"{API}/admin/spec4/reliability", headers=ADMIN)
        assert rl.status_code == 200
        rows = rl.json()
        row = next((x for x in rows if x["user_id"] == CLIENT_ID), None)
        assert row is not None, "client should appear in reliability"
        assert "client_strikes" in row and "over_threshold" in row and "private_avg" in row
