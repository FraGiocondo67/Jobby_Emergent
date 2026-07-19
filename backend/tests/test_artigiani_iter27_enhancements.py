"""Iter 27 — Spec 7 ARTIGIANI enhancements (backend):
- config exposes 'parametri', 'fasce_orarie', 'chiamata_default'
- provider listino new fields: chiamata_base/per_km/km_inclusi/urgenza_pct/minimo
- variable call-out fee (distance-based) via /estimate and /incoming my_price
- structured 'parametri' + 'fascia_oraria' + 'data_ora' stored on richiesta
- provider two-stage close with scomputo_chiamata toggle
- paniere modalita still works end-to-end (regression)
"""
import os
import math
import requests
import pytest
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"

CLIENT_TOKEN = "disp-test-token-777"
PROVIDER_TOKEN = "prov-test-token-888"
ADMIN_TOKEN = "jobby-admin-7c2f9a"
PROVIDER_ID = "prov_cfbd9805ce97"
TREVISO = {"lat": 45.6669, "lng": 12.2433}
FAR_LNG_OFFSET = 0.20  # ~15 km east at this latitude


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _ah():
    return {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


def _haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


CHIAMATA_BASE = 40.0
CHIAMATA_PER_KM = 1.5
CHIAMATA_KM_INCLUSI = 5.0
CHIAMATA_URGENZA_PCT = 20.0
CHIAMATA_MINIMO = 40.0


def _expected_fee(distance_km, urgente):
    extra = max(0.0, distance_km - CHIAMATA_KM_INCLUSI)
    fee = CHIAMATA_BASE + CHIAMATA_PER_KM * extra
    if urgente:
        fee = fee * (1 + CHIAMATA_URGENZA_PCT / 100.0)
    return round(max(fee, CHIAMATA_MINIMO), 2)


# --- Fixture: set provider listino with structured chiamata_* fields, wide radius --
@pytest.fixture(scope="module", autouse=True)
def setup_provider_listino():
    payload = {
        "mestiere": "idraulico",
        "listino": {
            "binario": "impresa",
            "chiamata_fee": 40,     # legacy fallback (unused when new fields present)
            "chiamata_base": CHIAMATA_BASE,
            "chiamata_per_km": CHIAMATA_PER_KM,
            "chiamata_km_inclusi": CHIAMATA_KM_INCLUSI,
            "chiamata_urgenza_pct": CHIAMATA_URGENZA_PCT,
            "chiamata_minimo": CHIAMATA_MINIMO,
            "tariffa_oraria": 35,
            "paniere": [{"id": "miscelatore", "prezzo": 70}, {"id": "sanitario", "prezzo": 120}, {"id": "scarico", "prezzo": 60}],
            "urgenze": True, "urgenze_pct": 20, "fasce_urgenza": ["immediato"],
            "raggio_km": 60, "tempi_tipici": "entro 24h", "abilitazione_numero": "IT-IDR-0001",
        },
    }
    r = requests.put(f"{BASE}/artigiani/listino", headers=_h(PROVIDER_TOKEN), json=payload)
    assert r.status_code == 200, r.text
    yield


# ---- 1) CONFIG new fields ----
class TestConfigNewFields:
    def test_config_exposes_parametri_fasce_and_chiamata_default(self):
        r = requests.get(f"{BASE}/artigiani/config", headers=_h(CLIENT_TOKEN))
        assert r.status_code == 200, r.text
        d = r.json()
        # parametri per mestiere
        assert "parametri" in d, "missing parametri key"
        for m in ("idraulico", "elettricista", "caldaista", "climatizzazione", "giardiniere", "tuttofare"):
            assert m in d["parametri"], f"missing parametri for {m}"
        # idraulico cascade shape check
        idr = d["parametri"]["idraulico"]
        assert any(p.get("type") == "cascade" for p in idr)
        # fasce_orarie
        assert "fasce_orarie" in d
        ids = {f["id"] for f in d["fasce_orarie"]}
        assert ids == {"mattina", "pomeriggio", "sera"}
        # chiamata_default has the 5 fields
        cd = d["chiamata_default"]
        for k in ("chiamata_base", "chiamata_per_km", "chiamata_km_inclusi", "chiamata_urgenza_pct", "chiamata_minimo"):
            assert k in cd, f"missing {k} in chiamata_default"


# ---- 2) LISTINO stores + returns new chiamata_* ----
class TestListinoNewFields:
    def test_get_listino_returns_new_chiamata_fields(self):
        r = requests.get(f"{BASE}/artigiani/listino", headers=_h(PROVIDER_TOKEN))
        assert r.status_code == 200, r.text
        idr = r.json()["art_listini"]["idraulico"]
        assert idr["chiamata_base"] == CHIAMATA_BASE
        assert idr["chiamata_per_km"] == CHIAMATA_PER_KM
        assert idr["chiamata_km_inclusi"] == CHIAMATA_KM_INCLUSI
        assert idr["chiamata_urgenza_pct"] == CHIAMATA_URGENZA_PCT
        assert idr["chiamata_minimo"] == CHIAMATA_MINIMO
        assert idr["tariffa_oraria"] == 35
        assert idr["raggio_km"] == 60


# ---- 3) VARIABLE CALL-OUT FEE by distance (estimate + provider incoming) ----
class TestVariableChiamataFee:
    def test_estimate_near_vs_far(self):
        near = requests.post(f"{BASE}/artigiani/estimate", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi", "binario": "impresa",
            "urgente": False, "lat": TREVISO["lat"], "lng": TREVISO["lng"],
        }).json()
        far_lng = TREVISO["lng"] + FAR_LNG_OFFSET
        far = requests.post(f"{BASE}/artigiani/estimate", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi", "binario": "impresa",
            "urgente": False, "lat": TREVISO["lat"], "lng": far_lng,
        }).json()
        # exact distances (server rounds to 1 decimal)
        d_far_real = _haversine(TREVISO["lat"], TREVISO["lng"], TREVISO["lat"], far_lng)
        d_far = round(d_far_real, 1)
        exp_near = _expected_fee(0.0, False)   # 40 base clamped
        exp_far = _expected_fee(d_far, False)
        assert near["min"] == exp_near, (near, exp_near)
        assert far["min"] == exp_far, (far, exp_far, d_far)
        # sanity: far > near
        assert far["min"] > near["min"]

    def test_estimate_urgenza_applies(self):
        far_lng = TREVISO["lng"] + FAR_LNG_OFFSET
        r = requests.post(f"{BASE}/artigiani/estimate", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi", "binario": "impresa",
            "urgente": True, "lat": TREVISO["lat"], "lng": far_lng,
        }).json()
        d = round(_haversine(TREVISO["lat"], TREVISO["lng"], TREVISO["lat"], far_lng), 1)
        assert r["min"] == _expected_fee(d, True)

    def test_provider_incoming_my_price_matches(self):
        far_lng = TREVISO["lng"] + FAR_LNG_OFFSET
        # create a far diagnosi request
        cr = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "diagnosi",
            "descrizione": "TEST_iter27 far distance diagnosi",
            "binario": "impresa", "indirizzo": "Via Far, Treviso",
            "lat": TREVISO["lat"], "lng": far_lng, "urgente": False,
        })
        assert cr.status_code == 200, cr.text
        rid = cr.json()["richiesta_id"]
        # invite provider
        inv = requests.post(f"{BASE}/admin/artigiani/richieste/{rid}/invite", headers=_ah(),
                            json={"provider_ids": [PROVIDER_ID]})
        assert inv.status_code == 200, inv.text
        # provider incoming
        inc = requests.get(f"{BASE}/artigiani/incoming", headers=_h(PROVIDER_TOKEN)).json()
        item = next((x for x in inc if x["richiesta_id"] == rid), None)
        assert item is not None
        # incoming() uses RAW haversine (no rounding), unlike estimate() which uses
        # the rounded distance from compatible_providers. Compute expected accordingly.
        d_raw = _haversine(TREVISO["lat"], TREVISO["lng"], TREVISO["lat"], far_lng)
        assert item["my_price"] == _expected_fee(d_raw, False)
        # And still greater than the near baseline (40 min)
        assert item["my_price"] > 40.0


# ---- 4) Structured parametri + fascia_oraria + data_ora stored ----
class TestStructuredParameters:
    def test_richiesta_stores_config_extras(self):
        future = (date.today() + timedelta(days=3)).isoformat()
        payload = {
            "mestiere": "idraulico", "modalita": "diagnosi",
            "descrizione": "TEST_iter27 params doccia mattina",
            "binario": "impresa",
            "parametri": {"ambiente": {"categoria": "bagno", "elemento": "doccia"}},
            "fascia_oraria": "mattina", "data_ora": future,
            "indirizzo": "Via Params, Treviso", **TREVISO,
        }
        cr = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json=payload)
        assert cr.status_code == 200, cr.text
        rid = cr.json()["richiesta_id"]
        g = requests.get(f"{BASE}/artigiani/richieste/{rid}", headers=_h(CLIENT_TOKEN)).json()
        cfg = g["config"]
        assert cfg["parametri"] == {"ambiente": {"categoria": "bagno", "elemento": "doccia"}}
        assert cfg["fascia_oraria"] == "mattina"
        assert g["data_ora"] == future


# ---- 5) SCOMPUTO toggle on preventivo ----
def _seed_and_confirm_diagnosi(far=False):
    """Create -> invite -> propose -> confirm diagnosi. Returns (rid, chiamata_fee)."""
    lng = TREVISO["lng"] + (FAR_LNG_OFFSET if far else 0)
    cr = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
        "mestiere": "idraulico", "modalita": "diagnosi",
        "descrizione": "TEST_iter27 scomputo seed", "binario": "impresa",
        "indirizzo": "Via S, Treviso", "lat": TREVISO["lat"], "lng": lng, "urgente": False,
    }).json()
    rid = cr["richiesta_id"]
    requests.post(f"{BASE}/admin/artigiani/richieste/{rid}/invite", headers=_ah(),
                  json={"provider_ids": [PROVIDER_ID]})
    p = requests.post(f"{BASE}/artigiani/richieste/{rid}/propose",
                      headers=_h(PROVIDER_TOKEN), json={"accept": True}).json()
    requests.post(f"{BASE}/artigiani/richieste/{rid}/confirm",
                  headers=_h(CLIENT_TOKEN), json={"provider_id": PROVIDER_ID})
    return rid, p["prezzo"]


class TestScomputoToggle:
    def test_scomputo_true_deducts_call_fee(self):
        rid, fee = _seed_and_confirm_diagnosi(far=True)
        r = requests.post(f"{BASE}/artigiani/richieste/{rid}/preventivo",
                          headers=_h(PROVIDER_TOKEN), json={
                              "esito": "preventivo",
                              "voci": [
                                  {"descrizione": "Manodopera", "tipo": "manodopera", "qta": 1, "prezzo_unit": 80},
                                  {"descrizione": "Materiale", "tipo": "materiale", "qta": 1, "prezzo_unit": 40},
                              ],
                              "scomputo_chiamata": True,
                          })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["totale"] == 120.0
        assert d["scomputo"] == fee  # equals chiamata_fee
        assert d["da_pagare"] == round(120.0 - fee, 2)
        assert d["scomputo_chiamata"] is True

    def test_scomputo_false_keeps_full_total(self):
        rid, fee = _seed_and_confirm_diagnosi(far=False)  # near => fee=40 (min clamped)
        r = requests.post(f"{BASE}/artigiani/richieste/{rid}/preventivo",
                          headers=_h(PROVIDER_TOKEN), json={
                              "esito": "preventivo",
                              "voci": [
                                  {"descrizione": "Manodopera", "tipo": "manodopera", "qta": 2, "prezzo_unit": 45},
                                  {"descrizione": "Materiale", "tipo": "materiale", "qta": 1, "prezzo_unit": 25},
                              ],
                              "scomputo_chiamata": False,
                          })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["totale"] == 115.0
        assert d["scomputo"] == 0.0
        assert d["da_pagare"] == 115.0
        assert d["scomputo_chiamata"] is False


# ---- 6) PANIERE still works (regression) ----
class TestPaniereRegression:
    def test_full_paniere_flow(self):
        cr = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOKEN), json={
            "mestiere": "idraulico", "modalita": "paniere", "intervento_id": "miscelatore",
            "descrizione": "TEST_iter27 paniere regression", "binario": "impresa",
            "indirizzo": "Via R, Treviso", **TREVISO,
        })
        assert cr.status_code == 200, cr.text
        rid = cr.json()["richiesta_id"]
        assert cr.json()["config"]["modalita"] == "paniere"
        requests.post(f"{BASE}/admin/artigiani/richieste/{rid}/invite", headers=_ah(),
                      json={"provider_ids": [PROVIDER_ID]})
        p = requests.post(f"{BASE}/artigiani/richieste/{rid}/propose",
                          headers=_h(PROVIDER_TOKEN), json={"accept": True}).json()
        assert p["prezzo"] == 70
        c = requests.post(f"{BASE}/artigiani/richieste/{rid}/confirm",
                          headers=_h(CLIENT_TOKEN), json={"provider_id": PROVIDER_ID}).json()
        assert c["stato"] == "confermata"
        assert c["chiamata_fee"] == 0
        assert c["pagamento"]["stato"] == "intervento_pagato"
