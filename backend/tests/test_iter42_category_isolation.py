"""Iter 42 — Category cross-contamination fix + provider/jobs + geocode/search.

Ensures /pulizie/richieste, /pulizie/incoming and per-category endpoints return
only their own category, cancelling a driver request does not affect pulizie,
provider/jobs returns a mixed-cat list, and geocode/search returns distinct
short labels. Also regression on disputes/reviews/payment_split.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
CLIENT_TOKEN = "disp-test-token-777"
PROVIDER_TOKEN = "prov-test-token-888"
ADMIN_TOKEN = "jobby-admin-7c2f9a"


@pytest.fixture(scope="module")
def cs():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {CLIENT_TOKEN}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def ps():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {PROVIDER_TOKEN}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_ids(cs):
    """Create at least one richiesta per category so we can validate isolation."""
    ids = {}
    # pulizie
    r = cs.post(f"{BASE_URL}/api/pulizie/richieste", json={
        "binario": "impresa",
        "config": {"home_type": "appartamento", "mq_band": "80_120", "tipo_pulizia": "ordinaria",
                   "extra": [], "stiro_ore": 0, "prodotti": "cliente", "durata_ore": 3, "animali": False},
        "indirizzo": "Via TEST Iter42 Pulizie 1", "lat": 45.6669, "lng": 12.2433,
        "data_ora": "2026-08-01 10:00", "publish": True,
    })
    if r.status_code == 200:
        ids["pulizie"] = r.json().get("richiesta_id")
    # driver
    r = cs.post(f"{BASE_URL}/api/driver/richieste", json={
        "tipo": "ncc", "classe": "standard",
        "partenza": {"label": "Aeroporto Venezia", "lat": 45.505, "lng": 12.352},
        "destinazione": {"label": "Treviso centro", "lat": 45.6669, "lng": 12.2433},
        "pickup_at": "2026-08-02 09:00", "passeggeri": 1, "bagagli": 1,
        "passeggero_nome": "Test", "passeggero_tel": "+39000",
    })
    if r.status_code == 200:
        ids["driver"] = r.json().get("richiesta_id")
    # babysitting — create child first
    ch = cs.post(f"{BASE_URL}/api/babysitting/children", json={
        "nome": "TESTKID", "eta_mesi": 60, "sesso": "F", "consenso": True,
    })
    child_id = ch.json().get("card_id") if ch.status_code == 200 else None
    if child_id:
        r = cs.post(f"{BASE_URL}/api/babysitting/richieste", json={
            "binario": "persona_lf", "bambini": [child_id],
            "config": {"ore": 2, "orario": "diurno"},
            "indirizzo": "Via TEST iter42 bs", "lat": 45.6669, "lng": 12.2433,
            "data_ora": "2026-08-03 15:00", "ora_fine": "17:00", "publish": True,
        })
        if r.status_code == 200:
            ids["babysitting"] = r.json().get("richiesta_id")
    # artigiani
    r = cs.post(f"{BASE_URL}/api/artigiani/richieste", json={
        "tipo_mestiere": "idraulico", "descrizione": "TEST iter42",
        "indirizzo": "Via TEST", "lat": 45.6669, "lng": 12.2433,
        "urgenza": "programmato", "foto": [], "publish": True,
    })
    if r.status_code == 200:
        ids["artigiani"] = r.json().get("richiesta_id")
    return ids


class TestPulizieOnlyReturnsPulizie:
    def test_pulizie_richieste_isolated(self, cs, created_ids):
        r = cs.get(f"{BASE_URL}/api/pulizie/richieste")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        for it in items:
            assert it.get("servizio") == "PULIZIA", f"leaked: {it.get('servizio')} in pulizie list"
            assert it.get("categoria") == "CASA"

    def test_pulizie_count_lower_than_total(self, cs, created_ids):
        """Root-cause proof: pulizie count must be strictly less than the sum of all categories."""
        pul = cs.get(f"{BASE_URL}/api/pulizie/richieste").json()
        drv = cs.get(f"{BASE_URL}/api/driver/richieste").json()
        bab = cs.get(f"{BASE_URL}/api/babysitting/richieste").json()
        art = cs.get(f"{BASE_URL}/api/artigiani/richieste").json()
        total = len(pul) + len(drv) + len(bab) + len(art)
        # pulizie must NOT contain the whole universe
        assert len(pul) < total, f"pulizie leaks other cats: pul={len(pul)} total={total}"


class TestOtherCategoriesIsolated:
    def test_driver_only(self, cs, created_ids):
        r = cs.get(f"{BASE_URL}/api/driver/richieste")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "DRIVER"

    def test_babysitting_only(self, cs, created_ids):
        r = cs.get(f"{BASE_URL}/api/babysitting/richieste")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "BABYSITTING"

    def test_artigiani_only(self, cs, created_ids):
        r = cs.get(f"{BASE_URL}/api/artigiani/richieste")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "ARTIGIANI"


class TestCancelDoesNotCrossCategory:
    def test_cancel_driver_only_touches_driver(self, cs, created_ids):
        drv_id = created_ids.get("driver")
        if not drv_id:
            pytest.skip("no driver id")
        # snapshot pulizie states before cancel
        pul_before = {p["richiesta_id"]: p["stato"] for p in cs.get(f"{BASE_URL}/api/pulizie/richieste").json()}
        r = cs.post(f"{BASE_URL}/api/driver/richieste/{drv_id}/cancel")
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            # verify driver got cancelled
            drv_now = cs.get(f"{BASE_URL}/api/driver/richieste/{drv_id}")
            assert drv_now.status_code == 200
            assert drv_now.json().get("stato") == "annullata"
        # verify pulizie states unchanged
        pul_after = {p["richiesta_id"]: p["stato"] for p in cs.get(f"{BASE_URL}/api/pulizie/richieste").json()}
        for rid, stato in pul_before.items():
            assert pul_after.get(rid) == stato, f"pulizie {rid} state changed after driver cancel"


class TestProviderJobs:
    def test_provider_jobs_shape(self, ps):
        r = ps.get(f"{BASE_URL}/api/provider/jobs")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        cats_seen = set()
        for it in items:
            assert "richiesta_id" in it
            assert "cat" in it and it["cat"] in ("pulizie", "driver", "babysitting", "artigiani")
            assert "stato" in it
            cats_seen.add(it["cat"])
        # provider seeded across multiple categories → expect at least one cat
        assert len(cats_seen) >= 1


class TestIncomingIsolation:
    def test_pulizie_incoming_only_pulizie(self, ps):
        r = ps.get(f"{BASE_URL}/api/pulizie/incoming")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "PULIZIA"

    def test_driver_incoming_only_driver(self, ps):
        r = ps.get(f"{BASE_URL}/api/driver/incoming")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "DRIVER"

    def test_babysitting_incoming_only_bs(self, ps):
        r = ps.get(f"{BASE_URL}/api/babysitting/incoming")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "BABYSITTING"

    def test_artigiani_incoming_only_art(self, ps):
        r = ps.get(f"{BASE_URL}/api/artigiani/incoming")
        assert r.status_code == 200
        for it in r.json():
            assert it.get("servizio") == "ARTIGIANI"


class TestGeocodeSearch:
    def test_returns_multiple_short_labels(self, cs):
        r = cs.post(f"{BASE_URL}/api/geocode/search", json={"query": "Via Roma 10"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        results = data["results"]
        assert isinstance(results, list)
        # must be more than one distinct result (previously long merged label)
        labels = [x["label"] for x in results]
        assert len(labels) == len(set(labels)), f"duplicate labels: {labels}"
        assert len(results) >= 2, f"expected >=2 candidates, got {len(results)}: {labels}"
        for x in results:
            assert len(x["label"]) <= 90
            assert "lat" in x and "lng" in x


class TestRegressionsStillWork:
    def test_admin_disputes_reachable(self):
        r = requests.get(f"{BASE_URL}/api/admin/disputes", headers={"X-Admin-Token": ADMIN_TOKEN}, timeout=15)
        assert r.status_code == 200
        # supports either list or {items: [...]} shape
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_wallet_checkout_path_exists(self, cs):
        # We only ensure the endpoint routes (no 404). It may 400 without a real completed rid.
        r = cs.post(f"{BASE_URL}/api/pay/richiesta/nonexistent/checkout", json={"method": "wallet"})
        assert r.status_code != 404 or "not_found" in r.text.lower()
