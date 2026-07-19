"""Iter 26 — Spec 7 ARTIGIANI E2E tests (backend).
Full two-stage flow (paniere + diagnosi) with client / provider / admin actors.
"""
import os
import time
import uuid
import requests
import pytest
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"

CLIENT_TOKEN = "disp-test-token-777"     # user_disptest01
PROVIDER_TOKEN = "prov-test-token-888"   # prov_cfbd9805ce97 (Giulia — idraulico art listino)
ADMIN_TOKEN = "jobby-admin-7c2f9a"
PROVIDER_ID = "prov_cfbd9805ce97"
TREVISO = {"lat": 45.6669, "lng": 12.2433}


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _ah():
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


# ---------- config / listino / estimate ----------
class TestConfigAndListino:
    def test_config_shape(self):
        r = requests.get(f"{BASE}/artigiani/config", headers=_h(CLIENT_TOKEN))
        assert r.status_code == 200, r.text
        d = r.json()
        assert {m["id"] for m in d["mestieri"]} >= {"idraulico", "elettricista", "caldaista", "climatizzazione", "giardiniere", "tuttofare"}
        assert "idraulico" in d["paniere"] and any(x["id"] == "miscelatore" for x in d["paniere"]["idraulico"])
        assert {e["id"] for e in d["esiti"]} == {"preventivo", "risolto_diagnosi", "non_riparabile"}
        assert {b["id"] for b in d["binari"]} == {"impresa", "persona_lf"}
        assert d["garanzia_giorni"] == 30
        assert d["preventivo_giorni"] == 7

    def test_put_and_get_listino(self):
        """Ensure provider Giulia's idraulico listino is fully set (paniere + chiamata_fee + urgenze)."""
        payload = {
            "mestiere": "idraulico",
            "listino": {
                "binario": "impresa", "chiamata_fee": 50, "tariffa_oraria": 35,
                "paniere": [{"id": "miscelatore", "prezzo": 70}, {"id": "sanitario", "prezzo": 120}, {"id": "scarico", "prezzo": 60}],
                "urgenze": True, "urgenze_pct": 20, "fasce_urgenza": ["immediato"],
                "raggio_km": 30, "tempi_tipici": "entro 24h", "abilitazione_numero": "IT-IDR-0001",
            },
        }
        r = requests.put(f"{BASE}/artigiani/listino", headers=_h(PROVIDER_TOKEN), json=payload)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE}/artigiani/listino", headers=_h(PROVIDER_TOKEN))
        assert g.status_code == 200
        d = g.json()
        assert "idraulico" in d["art_listini"]
        assert d["art_listini"]["idraulico"]["chiamata_fee"] == 50
        assert d["abilitazioni"]["verified"] is True

    def test_client_cannot_put_listino(self):
        r = requests.put(f"{BASE}/artigiani/listino", headers=_h(CLIENT_TOKEN),
                         json={"mestiere": "idraulico", "listino": {"binario": "impresa", "chiamata_fee": 40}})
        assert r.status_code == 403

    def test_estimate_paniere(self):
        r = requests.post(f"{BASE}/artigiani/estimate", headers=_h(CLIENT_TOKEN),
                          json={"mestiere": "idraulico", "modalita": "paniere", "intervento_id": "miscelatore",
                                "binario": "impresa", "urgente": False, **TREVISO})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["providers"] >= 1 and d["min"] == 70.0

    def test_estimate_diagnosi(self):
        r = requests.post(f"{BASE}/artigiani/estimate", headers=_h(CLIENT_TOKEN),
                          json={"mestiere": "idraulico", "modalita": "diagnosi", "binario": "impresa",
                                "urgente": False, **TREVISO})
        assert r.status_code == 200
        d = r.json()
        assert d["providers"] >= 1 and d["min"] == 50.0

    def test_route_check_hints_impianto(self):
        r = requests.post(f"{BASE}/artigiani/route-check", headers=_h(CLIENT_TOKEN),
                          json={"descrizione": "Ho una perdita d'acqua dal rubinetto"})
        assert r.status_code == 200
        assert r.json()["suggested_mestiere"] == "idraulico"


# ---------- Flow A: PANIERE (fixed price) ----------
class TestPaniereFlow:
    rid = None

    def test_01_create_paniere_request(self):
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "paniere", "intervento_id": "miscelatore",
            "descrizione": "TEST_paniere sostituzione miscelatore", "binario": "impresa",
            "indirizzo": "Via Roma 12, Treviso", "accesso": "citofono Rossi",
            **TREVISO, "data_ora": "",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stato"] == "pubblicata"
        assert d["config"]["modalita"] == "paniere"
        assert d["config"]["intervento"]["id"] == "miscelatore"
        TestPaniereFlow.rid = d["richiesta_id"]

    def test_02_admin_lists_with_compatible(self):
        r = requests.get(f"{BASE}/admin/artigiani/richieste", headers=_ah())
        assert r.status_code == 200
        found = next((x for x in r.json() if x["richiesta_id"] == TestPaniereFlow.rid), None)
        assert found is not None
        cids = [c["provider_id"] for c in found["compatible"]]
        assert PROVIDER_ID in cids

    def test_03_admin_invite_provider(self):
        r = requests.post(f"{BASE}/admin/artigiani/richieste/{TestPaniereFlow.rid}/invite",
                          headers=_ah(), json={"provider_ids": [PROVIDER_ID]})
        assert r.status_code == 200 and r.json()["invited"] == 1

    def test_04_provider_incoming_shows_price(self):
        r = requests.get(f"{BASE}/artigiani/incoming", headers=_h(PROVIDER_TOKEN))
        assert r.status_code == 200
        item = next((x for x in r.json() if x["richiesta_id"] == TestPaniereFlow.rid), None)
        assert item is not None
        assert item["my_price"] == 70  # paniere miscelatore
        assert "indirizzo" not in item  # provider view masks address until confirmed

    def test_05_provider_accepts(self):
        r = requests.post(f"{BASE}/artigiani/richieste/{TestPaniereFlow.rid}/propose",
                          headers=_h(PROVIDER_TOKEN), json={"accept": True, "message": "posso oggi"})
        assert r.status_code == 200
        assert r.json()["prezzo"] == 70

    def test_06_client_confirms_paniere(self):
        r = requests.post(f"{BASE}/artigiani/richieste/{TestPaniereFlow.rid}/confirm",
                          headers=_h(CLIENT_TOKEN), json={"provider_id": PROVIDER_ID})
        assert r.status_code == 200, r.text
        d = r.json()
        # PANIERE: intervento is paid up-front, so state confermata
        assert d["stato"] == "confermata"
        assert d["provider_scelto"] == PROVIDER_ID
        assert d["pagamento"]["stato"] == "intervento_pagato"
        assert d["chiamata_fee"] == 0

    def test_07_get_request_owner_sees_address(self):
        r = requests.get(f"{BASE}/artigiani/richieste/{TestPaniereFlow.rid}", headers=_h(CLIENT_TOKEN))
        assert r.status_code == 200 and r.json()["indirizzo"] == "Via Roma 12, Treviso"

    def test_08_forbidden_for_random_user(self):
        # No third user available — skip forbidden probe (would require another session)
        pytest.skip("no third test user available")


# ---------- Flow B: DIAGNOSI (paid call + quote) ----------
class TestDiagnosiFlow:
    rid = None

    def test_01_create_diagnosi(self):
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi",
            "descrizione": "TEST_diagnosi perdita sotto lavandino", "binario": "impresa",
            "urgente": False, "indirizzo": "Via Verdi 3, Treviso", "accesso": "",
            **TREVISO,
        })
        assert r.status_code == 200
        TestDiagnosiFlow.rid = r.json()["richiesta_id"]

    def test_02_invite_propose_confirm(self):
        rid = TestDiagnosiFlow.rid
        assert requests.post(f"{BASE}/admin/artigiani/richieste/{rid}/invite",
                             headers=_ah(), json={"provider_ids": [PROVIDER_ID]}).status_code == 200
        p = requests.post(f"{BASE}/artigiani/richieste/{rid}/propose",
                          headers=_h(PROVIDER_TOKEN), json={"accept": True}).json()
        assert p["prezzo"] == 50  # chiamata_fee
        c = requests.post(f"{BASE}/artigiani/richieste/{rid}/confirm",
                          headers=_h(CLIENT_TOKEN), json={"provider_id": PROVIDER_ID}).json()
        assert c["pagamento"]["stato"] == "chiamata_pagata"
        assert c["chiamata_fee"] == 50

    def test_03_compose_preventivo_with_voci(self):
        rid = TestDiagnosiFlow.rid
        r = requests.post(f"{BASE}/artigiani/richieste/{rid}/preventivo",
                          headers=_h(PROVIDER_TOKEN), json={
                              "esito": "preventivo",
                              "voci": [
                                  {"descrizione": "Sifone nuovo", "tipo": "materiale", "qta": 1, "prezzo_unit": 30},
                                  {"descrizione": "Manodopera 1h", "tipo": "manodopera", "qta": 1, "prezzo_unit": 40},
                              ],
                              "descrizione_lavoro": "Sostituzione sifone",
                              "tempi": "1 giorno",
                          })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["totale"] == 70.0
        assert d["scomputo"] == 50.0
        assert d["da_pagare"] == 20.0

    def test_04_client_accepts_preventivo(self):
        rid = TestDiagnosiFlow.rid
        r = requests.post(f"{BASE}/artigiani/richieste/{rid}/preventivo/accept",
                          headers=_h(CLIENT_TOKEN))
        assert r.status_code == 200
        assert r.json()["stato"] == "in_corso" and r.json()["pagato"] == 20.0

    def test_05_provider_adds_extra_client_approves(self):
        rid = TestDiagnosiFlow.rid
        e = requests.post(f"{BASE}/artigiani/richieste/{rid}/extra",
                          headers=_h(PROVIDER_TOKEN),
                          json={"descrizione": "Guarnizione extra", "importo": 8}).json()
        assert e["stato"] == "pending"
        ok = requests.post(f"{BASE}/artigiani/richieste/{rid}/extra/approve",
                           headers=_h(CLIENT_TOKEN),
                           json={"extra_id": e["extra_id"], "approve": True}).json()
        assert ok["stato"] == "approved"

    def test_06_provider_completes(self):
        rid = TestDiagnosiFlow.rid
        r = requests.post(f"{BASE}/artigiani/richieste/{rid}/complete",
                          headers=_h(PROVIDER_TOKEN), json={"foto_dopo": []})
        assert r.status_code == 200, r.text
        d = r.json()
        # base (diagnosi) = da_pagare + chiamata_fee = 20 + 50 = 70; + extras 8 = 78
        assert d["importo_totale"] == 78.0
        assert d["stato"] == "completata"

    def test_07_client_reviews(self):
        rid = TestDiagnosiFlow.rid
        r = requests.post(f"{BASE}/artigiani/richieste/{rid}/review",
                          headers=_h(CLIENT_TOKEN), json={"rating": 5, "comment": "TEST ottimo"})
        assert r.status_code == 200 and r.json()["rating"] == 5


# ---------- Flow C: risolto_diagnosi (close immediately) ----------
class TestRisoltoDiagnosi:
    def test_01_full(self):
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi",
            "descrizione": "TEST_risolto rubinetto", "binario": "impresa",
            "indirizzo": "Via A, Treviso", "accesso": "", **TREVISO,
        }).json()
        rid = r["richiesta_id"]
        requests.post(f"{BASE}/admin/artigiani/richieste/{rid}/invite", headers=_ah(),
                      json={"provider_ids": [PROVIDER_ID]})
        requests.post(f"{BASE}/artigiani/richieste/{rid}/propose", headers=_h(PROVIDER_TOKEN),
                      json={"accept": True})
        requests.post(f"{BASE}/artigiani/richieste/{rid}/confirm", headers=_h(CLIENT_TOKEN),
                      json={"provider_id": PROVIDER_ID})
        res = requests.post(f"{BASE}/artigiani/richieste/{rid}/preventivo",
                            headers=_h(PROVIDER_TOKEN),
                            json={"esito": "risolto_diagnosi", "voci": []})
        assert res.status_code == 200, res.text
        assert res.json()["stato"] == "completata"
        # verify garanzia set
        g = requests.get(f"{BASE}/artigiani/richieste/{rid}", headers=_h(CLIENT_TOKEN)).json()
        assert g["esito"] == "risolto_diagnosi"
        assert g["garanzia_fino"] is not None
        assert g["importo_totale"] == 50


# ---------- Admin abilitazione toggle ----------
class TestAdminAbilitazione:
    def test_toggle(self):
        r = requests.post(f"{BASE}/admin/artigiani/{PROVIDER_ID}/abilitazione",
                          headers=_ah(), json={"verified": True})
        assert r.status_code == 200
        assert r.json()["art_abilitazione_verified"] is True


# ---------- Validation edges ----------
class TestValidation:
    def test_invalid_mestiere(self):
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "nonexistent", "modalita": "diagnosi", "descrizione": "x", **TREVISO,
        })
        assert r.status_code == 400

    def test_invalid_modalita(self):
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "wrong", "descrizione": "x", **TREVISO,
        })
        assert r.status_code == 400

    def test_persona_lf_on_impianto_rejected(self):
        # idraulico has libretto=False; binario persona_lf should be blocked
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi", "descrizione": "x",
            "binario": "persona_lf", **TREVISO,
        })
        assert r.status_code == 400
