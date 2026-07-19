"""ITER-28: PULIZIE fee-split (Spec 3) — client half-fee on IMPRESA,
full fee still on client for PERSONA_LF. Also regression on full flow
so confirm() writes the correct fee_client/fee_provider/provider_net.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ["EXPO_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"

CLIENT_TOKEN = "disp-test-token-777"
PROV_IMPRESA_TOKEN = "req-prov-token"
PROV_LF_TOKEN = "lf-prov-token"
ADMIN_HDR = {"X-Admin-Token": "jobby-admin-7c2f9a"}
PROV_IMPRESA_ID = "user_2f996c8a010a"
PROV_LF_ID = "user_63e358a12980"


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


CFG = {
    "home_type": "appartamento", "mq_band": "80_120", "tipo_pulizia": "ordinaria",
    "extra": ["forno"], "stiro_ore": 0, "prodotti": "provider", "durata_ore": 3,
    "animali": False,
}


@pytest.fixture(scope="module")
def s():
    return requests.Session()


def _create_richiesta(s, binario):
    r = s.post(f"{API}/pulizie/richieste", headers=H(CLIENT_TOKEN), json={
        "binario": binario, "config": CFG, "indirizzo": "Via Test iter28",
        "lat": 45.6669, "lng": 12.2433, "data_ora": "2026-02-15T10:00",
        "flessibilita": "fascia", "ricorrenza": "una_tantum",
        "note": "TEST_iter28", "publish": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["richiesta_id"]


def _invite(s, rid, pid):
    r = s.post(f"{API}/admin/pulizie/richieste/{rid}/invite", headers=ADMIN_HDR,
               json={"provider_ids": [pid]}, timeout=15)
    assert r.status_code == 200, r.text


class TestConfigFeePct:
    def test_config_exposes_fee_pct(self, s):
        r = s.get(f"{API}/pulizie/config", headers=H(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "fee_pct" in d and float(d["fee_pct"]) > 0
        # store for other tests
        pytest.fee_pct = float(d["fee_pct"])


class TestImpresaBreakdownFiftyFifty:
    """Provider's incoming price must split the jobby_fee 50/50."""

    def test_incoming_breakdown_half_fee(self, s):
        rid = _create_richiesta(s, "impresa")
        _invite(s, rid, PROV_IMPRESA_ID)
        inc = s.get(f"{API}/pulizie/incoming", headers=H(PROV_IMPRESA_TOKEN), timeout=15).json()
        me = next(x for x in inc if x["richiesta_id"] == rid)
        pb = me["price"]
        work = pb["work_total"]
        fee = pb["jobby_fee"]
        # 50/50 split with cents-safe rounding
        assert pb["fee_client"] == round(fee / 2.0, 2), pb
        assert pb["fee_provider"] == round(fee - pb["fee_client"], 2), pb
        assert pb["provider_net"] == round(work - pb["fee_provider"], 2), pb
        assert pb["total_client"] == round(work + pb["fee_client"], 2), pb
        # Explicit numeric example: tariffa=13*3 + supplemento=5 + forno=10 = 54
        # jobby_fee 15% = 8.10 -> fee_client=4.05, fee_provider=4.05,
        # provider_net=49.95, total_client=58.05
        assert work == 54.0
        assert fee == 8.10
        assert pb["fee_client"] == 4.05
        assert pb["fee_provider"] == 4.05
        assert pb["provider_net"] == 49.95
        assert pb["total_client"] == 58.05


class TestPersonaLfBreakdownFullFeeClient:
    """LF: fee 100% on client on top of nominale; provider gets full netto (voucher)."""

    def test_incoming_lf_full_fee_on_client(self, s):
        rid = _create_richiesta(s, "persona_lf")
        _invite(s, rid, PROV_LF_ID)
        inc = s.get(f"{API}/pulizie/incoming", headers=H(PROV_LF_TOKEN), timeout=15).json()
        me = next(x for x in inc if x["richiesta_id"] == rid)
        pb = me["price"]
        assert pb["fee_provider"] == 0.0, pb
        assert pb["provider_net"] == 0.0, pb   # LF: netto is via voucher, not PSP
        assert pb["fee_client"] == pb["jobby_fee"], pb
        assert pb["total_client"] == round(pb["lf_nominale"] + pb["jobby_fee"], 2), pb


class TestImpresaConfirmPersistsFeeSplit:
    def test_full_flow_impresa_persistence(self, s):
        rid = _create_richiesta(s, "impresa")
        _invite(s, rid, PROV_IMPRESA_ID)

        pr = s.post(f"{API}/pulizie/richieste/{rid}/propose", headers=H(PROV_IMPRESA_TOKEN),
                    json={"accept": True}, timeout=15)
        assert pr.status_code == 200, pr.text
        proposal = pr.json()
        pb = proposal["breakdown"]

        # ensure proposal breakdown is 50/50
        assert pb["fee_client"] == round(pb["jobby_fee"] / 2.0, 2), pb
        assert pb["fee_provider"] == round(pb["jobby_fee"] - pb["fee_client"], 2), pb

        cf = s.post(f"{API}/pulizie/richieste/{rid}/confirm", headers=H(CLIENT_TOKEN),
                    json={"provider_id": PROV_IMPRESA_ID}, timeout=15)
        assert cf.status_code == 200, cf.text
        d = cf.json()

        # pagamento_fee must record fee_client (half) and jobby_fee_total (full)
        assert d["pagamento_fee"]["stato"] == "charged"
        assert d["pagamento_fee"]["importo"] == pb["fee_client"], d["pagamento_fee"]
        assert d["pagamento_fee"]["jobby_fee_total"] == pb["jobby_fee"], d["pagamento_fee"]

        # pagamento_lavoro must record provider_net + fee_provider
        assert d["pagamento_lavoro"]["stato"] == "psp_pending"
        assert d["pagamento_lavoro"]["importo"] == pb["provider_net"], d["pagamento_lavoro"]
        assert d["pagamento_lavoro"]["fee_provider"] == pb["fee_provider"], d["pagamento_lavoro"]

        # persistence via GET
        r = s.get(f"{API}/pulizie/richieste/{rid}", headers=H(CLIENT_TOKEN), timeout=15).json()
        assert r["pagamento_fee"]["importo"] == pb["fee_client"]
        assert r["pagamento_lavoro"]["fee_provider"] == pb["fee_provider"]


class TestPersonaLfConfirmUnaffected:
    def test_lf_full_flow_still_works(self, s):
        rid = _create_richiesta(s, "persona_lf")
        _invite(s, rid, PROV_LF_ID)

        pr = s.post(f"{API}/pulizie/richieste/{rid}/propose", headers=H(PROV_LF_TOKEN),
                    json={"accept": True}, timeout=15)
        assert pr.status_code == 200, pr.text
        prop = pr.json()
        nom = prop["breakdown"]["lf_nominale"]

        # ensure borsellino
        bors = s.get(f"{API}/pulizie/lf/borsellino", headers=H(CLIENT_TOKEN), timeout=15).json()
        if bors["borsellino"] < nom:
            s.post(f"{API}/pulizie/lf/topup", headers=H(CLIENT_TOKEN),
                   json={"amount": nom + 20}, timeout=15)

        cf = s.post(f"{API}/pulizie/richieste/{rid}/confirm", headers=H(CLIENT_TOKEN),
                    json={"provider_id": PROV_LF_ID}, timeout=15)
        assert cf.status_code == 200, cf.text
        d = cf.json()
        # LF: pagamento_fee.importo == full jobby_fee (client pays entire fee)
        assert d["pagamento_fee"]["stato"] == "charged"
        assert d["pagamento_fee"]["importo"] == prop["breakdown"]["jobby_fee"], d["pagamento_fee"]
        # pagamento_lavoro is LF-based, not psp_pending
        assert d["pagamento_lavoro"]["stato"] in ("lf", "coperto")
        assert d["pagamento_lavoro"]["nominale"] == nom
