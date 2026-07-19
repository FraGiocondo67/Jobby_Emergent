"""JOBBY — Spec 8 DRIVER end-to-end backend tests (NCC + TAXI).

Covers:
- Config, geocode, estimate (ncc range + taxi meter estimate + note)
- Cancellation schema (>4h, <4h, <30min bands)
- Full NCC lifecycle (create → admin invite → provider incoming → propose (upward w/o motivo → 400; then with motivo) → client confirm (prepaid, fee 12%) → depart → extra add + approve → complete → importo_totale = prezzo + extras → review)
- Full TAXI lifecycle (create → admin invite → propose (accept, is_estimate true, meter_pending) → depart → complete w/o meter_amount → 400; then with meter_amount → pay/settle)
- Admin listing & authorization endpoint
"""
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

CLIENT = {"Authorization": "Bearer disp-test-token-777"}
NCC_DRV = {"Authorization": "Bearer prov-test-token-888"}   # Giulia (ncc)
TAXI_DRV = {"Authorization": "Bearer onb-token"}            # Marco / user_onbtest01 (taxi)
ADMIN = {"X-Admin-Token": "jobby-admin-7c2f9a"}

TV = {"label": "Stazione Treviso", "lat": 45.6669, "lng": 12.2433}
VCE = {"label": "Aeroporto Venezia", "lat": 45.5053, "lng": 12.3519}


def _iso_in(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# -------- config / geocode / estimate --------
class TestConfig:
    def test_config(self):
        r = requests.get(f"{API}/driver/config", headers=CLIENT, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["vehicle_classes"]) == 3
        assert any(v["id"] == "van" for v in j["vehicle_classes"])
        assert len(j["shortcuts"]) >= 4
        assert any(m["id"] == "bagagli" for m in j["ritocco_motivi"])
        assert j["taxi_tariffa"]["scatto"] == 3.5
        assert j["fee_pct"] == 12.0

    def test_geocode(self):
        r = requests.post(f"{API}/driver/geocode", headers=CLIENT,
                          json={"query": "Piazza San Marco Venezia"}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "lat" in j and "lng" in j

    def test_estimate_ncc(self):
        r = requests.post(f"{API}/driver/estimate", headers=CLIENT,
                          json={"tipo": "ncc", "classe": "standard",
                                "from_lat": TV["lat"], "from_lng": TV["lng"],
                                "to_lat": VCE["lat"], "to_lng": VCE["lng"],
                                "pickup_at": _iso_in(24)}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tipo"] == "ncc"
        assert j["route"]["distance_km"] > 15
        # If Giulia driver is available, min/max present
        if j["providers"]:
            assert j["min"] is not None and j["max"] is not None
            assert 20 <= j["min"] <= 200

    def test_estimate_taxi(self):
        r = requests.post(f"{API}/driver/estimate", headers=CLIENT,
                          json={"tipo": "taxi", "classe": "standard",
                                "from_lat": TV["lat"], "from_lng": TV["lng"],
                                "to_lat": VCE["lat"], "to_lng": VCE["lng"],
                                "pickup_at": _iso_in(24)}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["tipo"] == "taxi"
        assert j["estimate"] >= 6.0
        assert "tassametro" in j["note"].lower()


# -------- NCC lifecycle --------
class TestNCC:
    rid = None
    proposal_prezzo = None

    def test_01_create_richiesta(self):
        payload = {
            "tipo": "ncc", "classe": "standard",
            "partenza": TV, "destinazione": VCE,
            "pickup_at": _iso_in(24),  # >4h so cancel test bands hit
            "passeggeri": 2, "bagagli": 3,
            "note": "TEST_NCC"
        }
        r = requests.post(f"{API}/driver/richieste", headers=CLIENT, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["stato"] == "pubblicata"
        assert j["config"]["tipo"] == "ncc"
        assert j["config"]["route"]["distance_km"] > 0
        TestNCC.rid = j["richiesta_id"]

    def test_02_admin_invite(self):
        rid = TestNCC.rid
        # Admin lists open richieste
        r = requests.get(f"{API}/admin/driver/richieste", headers=ADMIN, timeout=15)
        assert r.status_code == 200
        items = r.json()
        mine = [x for x in items if x["richiesta_id"] == rid]
        assert mine, "our richiesta must be in open list"
        assert mine[0]["config"]["tipo"] == "ncc"

        r2 = requests.post(f"{API}/admin/driver/richieste/{rid}/invite", headers=ADMIN,
                           json={"provider_ids": ["prov_cfbd9805ce97"]}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["invited"] == 1

    def test_03_provider_incoming_shows_suggested_price(self):
        r = requests.get(f"{API}/driver/incoming", headers=NCC_DRV, timeout=15)
        assert r.status_code == 200
        mine = [x for x in r.json() if x["richiesta_id"] == TestNCC.rid]
        assert mine, "richiesta should appear in provider incoming"
        assert mine[0].get("suggested_price") is not None
        assert mine[0]["suggested_price"] > 0

    def test_04_propose_upward_without_motivo_400(self):
        rid = TestNCC.rid
        # Get suggested price first
        inc = requests.get(f"{API}/driver/incoming", headers=NCC_DRV, timeout=15).json()
        base = next(x for x in inc if x["richiesta_id"] == rid)["suggested_price"]
        r = requests.post(f"{API}/driver/richieste/{rid}/propose", headers=NCC_DRV,
                          json={"accept": True, "prezzo": base + 10.0}, timeout=15)
        assert r.status_code == 400
        assert "ritocco" in r.text.lower()

    def test_05_propose_with_motivo(self):
        rid = TestNCC.rid
        inc = requests.get(f"{API}/driver/incoming", headers=NCC_DRV, timeout=15).json()
        base = next(x for x in inc if x["richiesta_id"] == rid)["suggested_price"]
        prezzo = round(base + 10.0, 2)
        r = requests.post(f"{API}/driver/richieste/{rid}/propose", headers=NCC_DRV,
                          json={"accept": True, "prezzo": prezzo, "ritocco_motivo": "bagagli"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["prezzo"] == prezzo
        assert j["ritocco"]["motivo"] == "bagagli"
        assert j["is_estimate"] is False
        TestNCC.proposal_prezzo = prezzo

    def test_06_client_confirm_prepaid_fee(self):
        rid = TestNCC.rid
        r = requests.post(f"{API}/driver/richieste/{rid}/confirm", headers=CLIENT,
                          json={"provider_id": "prov_cfbd9805ce97"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["stato"] == "confermata"
        assert j["prezzo_finale"] == TestNCC.proposal_prezzo
        assert j["pagamento"]["stato"] == "prepaid"
        assert j["jobby_fee"] == round(TestNCC.proposal_prezzo * 0.12, 2)

    def test_07_provider_depart(self):
        r = requests.post(f"{API}/driver/richieste/{TestNCC.rid}/depart", headers=NCC_DRV, timeout=15)
        assert r.status_code == 200
        # verify state
        g = requests.get(f"{API}/driver/richieste/{TestNCC.rid}", headers=CLIENT, timeout=15).json()
        assert g["stato"] == "in_corso"
        assert g["tracking"] is not None

    def test_08_provider_add_extra_and_client_approve(self):
        rid = TestNCC.rid
        r = requests.post(f"{API}/driver/richieste/{rid}/extra", headers=NCC_DRV,
                          json={"tipo": "attesa", "importo": 15.0, "motivo": "TEST_wait"}, timeout=15)
        assert r.status_code == 200
        extra_id = r.json()["extra_id"]
        r2 = requests.post(f"{API}/driver/richieste/{rid}/extra/approve", headers=CLIENT,
                           json={"extra_id": extra_id, "approve": True}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["stato"] == "approved"

    def test_09_complete_and_totale(self):
        rid = TestNCC.rid
        r = requests.post(f"{API}/driver/richieste/{rid}/complete", headers=NCC_DRV, json={}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["stato"] == "completata"
        expected = round(TestNCC.proposal_prezzo + 15.0, 2)
        assert j["importo_totale"] == expected, f"got {j['importo_totale']} expected {expected}"

    def test_10_client_review(self):
        r = requests.post(f"{API}/driver/richieste/{TestNCC.rid}/review", headers=CLIENT,
                          json={"rating": 5, "comment": "TEST_review ottimo"}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["rating"] == 5


# -------- TAXI lifecycle --------
class TestTaxi:
    rid = None

    def test_01_create(self):
        payload = {
            "tipo": "taxi", "classe": "standard",
            "partenza": TV, "destinazione": VCE,
            "pickup_at": _iso_in(6),
            "passeggeri": 1, "note": "TEST_TAXI"
        }
        r = requests.post(f"{API}/driver/richieste", headers=CLIENT, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["config"]["tipo"] == "taxi"
        assert j["config"]["taxi_estimate"] is not None
        TestTaxi.rid = j["richiesta_id"]

    def test_02_admin_invite_taxi(self):
        r = requests.post(f"{API}/admin/driver/richieste/{TestTaxi.rid}/invite", headers=ADMIN,
                          json={"provider_ids": ["user_onbtest01"]}, timeout=15)
        assert r.status_code == 200

    def test_03_propose_accept(self):
        r = requests.post(f"{API}/driver/richieste/{TestTaxi.rid}/propose", headers=TAXI_DRV,
                          json={"accept": True}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["is_estimate"] is True
        assert j["prezzo"] is not None  # taxi_estimate

    def test_04_client_confirm_meter_pending(self):
        r = requests.post(f"{API}/driver/richieste/{TestTaxi.rid}/confirm", headers=CLIENT,
                          json={"provider_id": "user_onbtest01"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pagamento"]["stato"] == "meter_pending"

    def test_05_depart(self):
        r = requests.post(f"{API}/driver/richieste/{TestTaxi.rid}/depart", headers=TAXI_DRV, timeout=15)
        assert r.status_code == 200

    def test_06_complete_no_meter_400(self):
        r = requests.post(f"{API}/driver/richieste/{TestTaxi.rid}/complete", headers=TAXI_DRV, json={}, timeout=15)
        assert r.status_code == 400
        assert "meter" in r.text.lower()

    def test_07_complete_with_meter(self):
        r = requests.post(f"{API}/driver/richieste/{TestTaxi.rid}/complete", headers=TAXI_DRV,
                          json={"meter_amount": 42.5}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["importo_totale"] == 42.5
        # Should be meter_to_settle now
        g = requests.get(f"{API}/driver/richieste/{TestTaxi.rid}", headers=CLIENT, timeout=15).json()
        assert g["pagamento"]["stato"] == "meter_to_settle"

    def test_08_client_pay_settle(self):
        r = requests.post(f"{API}/driver/richieste/{TestTaxi.rid}/pay", headers=CLIENT, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["stato"] == "settled"
        assert j["importo"] == 42.5


# -------- cancellation schema --------
class TestCancellation:
    def _create(self, hours):
        payload = {
            "tipo": "ncc", "classe": "standard",
            "partenza": TV, "destinazione": VCE,
            "pickup_at": _iso_in(hours),
            "note": f"TEST_CANCEL_{hours}h"
        }
        r = requests.post(f"{API}/driver/richieste", headers=CLIENT, json=payload, timeout=15)
        assert r.status_code == 200
        return r.json()["richiesta_id"]

    def test_gt_4h_full_refund(self):
        rid = self._create(24)
        r = requests.post(f"{API}/driver/richieste/{rid}/cancel", headers=CLIENT, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["refund_pct"] == 100
        assert j["band"] == ">4h"
        assert j["charge"] == 0.0

    def test_lt_4h_half(self):
        rid = self._create(2)   # 2 hours ahead -> <4h band
        r = requests.post(f"{API}/driver/richieste/{rid}/cancel", headers=CLIENT, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["band"] == "<4h", j
        assert j["refund_pct"] == 50

    def test_lt_30min(self):
        # create pickup ~10 min away
        payload = {
            "tipo": "ncc", "classe": "standard",
            "partenza": TV, "destinazione": VCE,
            "pickup_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "note": "TEST_CANCEL_10min"
        }
        r0 = requests.post(f"{API}/driver/richieste", headers=CLIENT, json=payload, timeout=15)
        rid = r0.json()["richiesta_id"]
        r = requests.post(f"{API}/driver/richieste/{rid}/cancel", headers=CLIENT, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["band"] == "<30min"
        assert j["refund_pct"] == 0


# -------- admin authorization endpoint --------
class TestAdminAuth:
    def test_admin_verify_authorization(self):
        # Toggle on Marco (taxi)
        r = requests.post(f"{API}/admin/driver/user_onbtest01/authorization", headers=ADMIN,
                          json={"verified": True}, timeout=15)
        assert r.status_code == 200
        assert r.json()["driver_auth_verified"] is True
