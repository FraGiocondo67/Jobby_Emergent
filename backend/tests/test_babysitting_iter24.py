"""Spec 6 Babysitting subsystem — end-to-end backend tests.

Runs against the public preview URL (EXPO_PUBLIC_BACKEND_URL).
Covers: child cards CRUD + validation, config/estimate, full lifecycle
(persona_lf), garanzia primo incontro, emergency, provider profile/listino/casellario,
admin manual matching & casellario verification.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")

CLIENT_TOKEN = "disp-test-token-777"
PROVIDER_TOKEN = "prov-test-token-888"
PROVIDER_ID = "prov_cfbd9805ce97"
ADMIN_TOKEN = "jobby-admin-7c2f9a"


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


ADMIN_H = {"X-Admin-Token": ADMIN_TOKEN, "Content-Type": "application/json"}


# -------- helpers / cleanup --------
@pytest.fixture(scope="module", autouse=True)
def cleanup_children():
    yield
    try:
        r = requests.get(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), timeout=15)
        for c in r.json():
            if c.get("nome", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/babysitting/children/{c['card_id']}", headers=H(CLIENT_TOKEN), timeout=15)
    except Exception:
        pass


# ================= CHILD CARDS =================
class TestChildCards:
    def test_consent_required(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), timeout=15,
                          json={"nome": "TEST_Bob", "eta_mesi": 36, "consenso": False})
        assert r.status_code == 400
        assert r.json().get("detail") == "consent_required"

    def test_name_required(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), timeout=15,
                          json={"nome": "  ", "eta_mesi": 36, "consenso": True})
        assert r.status_code == 400
        assert r.json().get("detail") == "name_required"

    def test_create_list_update_delete(self):
        payload = {"nome": "TEST_Luca", "eta_mesi": 48, "sesso": "m", "allergie": "arachidi",
                   "abitudini": "dorme dopo pranzo", "note": "amichevole", "consenso": True}
        r = requests.post(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        cid = r.json()["card_id"]
        assert r.json()["nome"] == "TEST_Luca"
        assert r.json()["eta_mesi"] == 48
        # list
        lst = requests.get(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), timeout=15).json()
        assert any(c["card_id"] == cid for c in lst)
        # update
        upd = requests.put(f"{BASE_URL}/api/babysitting/children/{cid}", headers=H(CLIENT_TOKEN), timeout=15,
                           json={**payload, "note": "aggiornato"})
        assert upd.status_code == 200
        assert upd.json()["note"] == "aggiornato"
        # delete
        d = requests.delete(f"{BASE_URL}/api/babysitting/children/{cid}", headers=H(CLIENT_TOKEN), timeout=15)
        assert d.status_code == 200
        # not found on second delete
        d2 = requests.delete(f"{BASE_URL}/api/babysitting/children/{cid}", headers=H(CLIENT_TOKEN), timeout=15)
        assert d2.status_code == 404


# ================= CONFIG + ESTIMATE =================
class TestConfigEstimate:
    def test_config(self):
        r = requests.get(f"{BASE_URL}/api/babysitting/config", headers=H(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("subjects", "school_levels", "certifications", "binari", "emergency_numbers"):
            assert k in d and len(d[k]) > 0
        nums = {e["number"] for e in d["emergency_numbers"]}
        assert "112" in nums and "118" in nums
        assert d["min_child_age_months"] == 12

    def test_estimate(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/estimate", headers=H(CLIENT_TOKEN), timeout=15,
                          json={"binario": "persona_lf", "lat": 45.6669, "lng": 12.2433,
                                "config": {"n_bambini": 1, "durata_ore": 4, "serale": True, "festivo": False}})
        assert r.status_code == 200
        d = r.json()
        assert "ranges" in d
        assert "persona_lf" in d["ranges"] and "piva" in d["ranges"]
        # at least Giulia should be found for persona_lf
        assert d["ranges"]["persona_lf"]["providers"] >= 1


# ================= LIFECYCLE =================
@pytest.fixture(scope="module")
def child_id():
    # ensure clean starting borsellino (must be >=  ~72 to survive engage of ~70)
    payload = {"nome": "TEST_LucaLC", "eta_mesi": 60, "sesso": "m", "consenso": True}
    r = requests.post(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), json=payload, timeout=15)
    assert r.status_code == 200
    return r.json()["card_id"]


@pytest.fixture(scope="module")
def young_child_id():
    payload = {"nome": "TEST_Baby", "eta_mesi": 6, "sesso": "f", "consenso": True}
    r = requests.post(f"{BASE_URL}/api/babysitting/children", headers=H(CLIENT_TOKEN), json=payload, timeout=15)
    assert r.status_code == 200
    return r.json()["card_id"]


class TestLifecycle:
    rid = None

    def test_child_too_young(self, young_child_id):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste", headers=H(CLIENT_TOKEN), timeout=15, json={
            "binario": "persona_lf", "bambini": [young_child_id],
            "config": {"durata_ore": 3, "serale": True},
            "indirizzo": "Via Roma 12, Treviso", "lat": 45.6669, "lng": 12.2433,
            "data_ora": "2026-07-25T20:00:00", "ora_fine": "2026-07-25T23:00:00",
            "publish": True,
        })
        assert r.status_code == 400
        assert r.json().get("detail") == "child_too_young"

    def test_01_create_publish(self, child_id):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste", headers=H(CLIENT_TOKEN), timeout=15, json={
            "binario": "persona_lf", "bambini": [child_id],
            "config": {"durata_ore": 4, "serale": True, "festivo": False},
            "indirizzo": "Via Roma 12, Treviso", "lat": 45.6669, "lng": 12.2433,
            "data_ora": "2026-07-25T20:00:00", "ora_fine": "2026-07-26T00:00:00",
            "urgente": False, "ricorrenza": "una_tantum", "publish": True,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stato"] == "pubblicata"
        # provider incoming should not include name/address (two-level visibility)
        assert d["bambini_generic"][0].get("eta_band") in ("3_6", "6_10")
        TestLifecycle.rid = d["richiesta_id"]

    def test_02_provider_incoming_before_invite(self):
        r = requests.get(f"{BASE_URL}/api/babysitting/incoming", headers=H(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200
        assert not any(x["richiesta_id"] == TestLifecycle.rid for x in r.json())

    def test_03_admin_invite(self):
        r = requests.post(f"{BASE_URL}/api/admin/babysitting/richieste/{TestLifecycle.rid}/invite",
                          headers=ADMIN_H, json={"provider_ids": [PROVIDER_ID]}, timeout=15)
        assert r.status_code == 200
        assert r.json()["invited"] == 1

    def test_04_provider_sees_generic_only(self):
        r = requests.get(f"{BASE_URL}/api/babysitting/incoming", headers=H(PROVIDER_TOKEN), timeout=15)
        item = next(x for x in r.json() if x["richiesta_id"] == TestLifecycle.rid)
        # generic children info only - no name/address/bambini card ids
        assert "indirizzo" not in item
        assert "bambini" not in item
        assert item.get("bambini_generic")
        assert "price" in item

    def test_05_provider_propose(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/propose",
                          headers=H(PROVIDER_TOKEN), json={"accept": True, "message": "Disponibile"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["provider_id"] == PROVIDER_ID
        assert d["price"] > 0
        # sanity: 4h evening at 10 + 10% = 44, no wait ; but Giulia has serale +10% so nominale 44 -> LF rounded
        assert "breakdown" in d

    def test_06_client_confirm(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/confirm",
                          headers=H(CLIENT_TOKEN), json={"provider_id": PROVIDER_ID}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stato"] == "confermata"
        assert d["provider_scelto"] == PROVIDER_ID
        assert d["pagamento_fee"]["stato"] == "charged"
        pl = d["pagamento_lavoro"]
        assert pl.get("impegnato", 0) > 0
        assert pl.get("margine", 0) > 0

    def test_07_confirmed_provider_sees_full(self):
        r = requests.get(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}",
                         headers=H(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "indirizzo" in d and d["indirizzo"]
        assert d.get("bambini_full") and d["bambini_full"][0]["nome"].startswith("TEST_")

    def test_08_incontro_video_jitsi(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/incontro",
                          headers=H(CLIENT_TOKEN), json={"mode": "video", "slot": "2026-07-24T18:00:00"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "video"
        assert "meet.jit.si" in d["link"]

    def test_09_emergency_returns_112_118(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/emergency",
                          headers=H(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        d = r.json()
        nums = {e["number"] for e in d["emergency_numbers"]}
        assert "112" in nums and "118" in nums
        assert "parent_contact" in d

    def test_10_provider_inizio(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/inizio",
                          headers=H(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200
        assert len(r.json()["code"]) == 4

    def test_11_client_inizio_confirm(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/inizio/confirm",
                          headers=H(CLIENT_TOKEN), json={}, timeout=15)
        assert r.status_code == 200
        assert r.json()["stato"] == "in_corso"

    def test_12_provider_fine_and_wrong_code(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/fine",
                          headers=H(PROVIDER_TOKEN), timeout=15)
        assert r.status_code == 200
        code = r.json()["code"]
        # wrong code first
        bad = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/fine/confirm",
                            headers=H(CLIENT_TOKEN), json={"code": "9999" if code != "9999" else "0000"}, timeout=15)
        assert bad.status_code == 400
        assert bad.json().get("detail") == "invalid_code"
        ok = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/fine/confirm",
                           headers=H(CLIENT_TOKEN), json={"code": code}, timeout=15)
        assert ok.status_code == 200
        assert ok.json()["stato"] == "completata"
        cons = ok.json()["consuntivo"]
        assert cons["billable_ore"] >= cons["booked_ore"]  # min guaranteed

    def test_13_client_review(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{TestLifecycle.rid}/review",
                          headers=H(CLIENT_TOKEN), json={"rating": 5, "comment": "TEST_ottima"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["rating"] == 5


# ================= GARANZIA PRIMO INCONTRO =================
class TestGaranzia:
    def test_cancel_refund(self, child_id):
        # create + invite + propose + confirm + incontro + cancel-refund
        c = requests.post(f"{BASE_URL}/api/babysitting/richieste", headers=H(CLIENT_TOKEN), timeout=15, json={
            "binario": "persona_lf", "bambini": [child_id],
            "config": {"durata_ore": 3, "serale": True},
            "indirizzo": "Via Test 5, Treviso", "lat": 45.6669, "lng": 12.2433,
            "data_ora": "2026-08-01T20:00:00", "ora_fine": "2026-08-01T23:00:00",
            "publish": True,
        })
        assert c.status_code == 200, c.text
        rid = c.json()["richiesta_id"]

        # borsellino before
        me1 = requests.get(f"{BASE_URL}/api/auth/me", headers=H(CLIENT_TOKEN), timeout=15).json()
        bors_before = me1.get("lf_borsellino")

        assert requests.post(f"{BASE_URL}/api/admin/babysitting/richieste/{rid}/invite",
                             headers=ADMIN_H, json={"provider_ids": [PROVIDER_ID]}, timeout=15).status_code == 200
        assert requests.post(f"{BASE_URL}/api/babysitting/richieste/{rid}/propose",
                             headers=H(PROVIDER_TOKEN), json={"accept": True}, timeout=15).status_code == 200
        assert requests.post(f"{BASE_URL}/api/babysitting/richieste/{rid}/confirm",
                             headers=H(CLIENT_TOKEN), json={"provider_id": PROVIDER_ID}, timeout=15).status_code == 200

        me2 = requests.get(f"{BASE_URL}/api/auth/me", headers=H(CLIENT_TOKEN), timeout=15).json()
        bors_after_confirm = me2.get("lf_borsellino")
        # engagement subtracted
        if bors_before is not None and bors_after_confirm is not None:
            assert bors_after_confirm < bors_before

        # need incontro first
        assert requests.post(f"{BASE_URL}/api/babysitting/richieste/{rid}/incontro",
                             headers=H(CLIENT_TOKEN), json={"mode": "persona", "slot": "2026-07-30T18:00:00"}, timeout=15).status_code == 200

        # garanzia
        r = requests.post(f"{BASE_URL}/api/babysitting/richieste/{rid}/incontro/cancel-refund",
                          headers=H(CLIENT_TOKEN), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["stato"] == "annullata"

        me3 = requests.get(f"{BASE_URL}/api/auth/me", headers=H(CLIENT_TOKEN), timeout=15).json()
        bors_after_refund = me3.get("lf_borsellino")
        if bors_before is not None and bors_after_refund is not None:
            # restored fully to (or above) pre-engage level
            assert bors_after_refund >= bors_before - 0.01


# ================= PROVIDER PROFILE / LISTINO / CASELLARIO =================
class TestProviderConfig:
    def test_profile_get_put(self):
        p = requests.get(f"{BASE_URL}/api/babysitting/profile", headers=H(PROVIDER_TOKEN), timeout=15)
        assert p.status_code == 200
        assert "bs_profile" in p.json() and "casellario" in p.json()
        r = requests.put(f"{BASE_URL}/api/babysitting/profile", headers=H(PROVIDER_TOKEN), timeout=15, json={
            "esperienza_anni": 5, "lingue": ["italiano", "inglese"],
            "certificazioni": ["primo_soccorso_pediatrico"], "materie": ["matematica"],
            "livelli": ["elementari", "medie"], "fasce_eta": ["3_6", "6_10"],
            "presentazione": {"perche": "amo i bambini"}, "disponibilita": ["pomeriggi"],
        })
        assert r.status_code == 200
        assert r.json()["bs_profile"]["esperienza_anni"] == 5

    def test_listino_get_put(self):
        g = requests.get(f"{BASE_URL}/api/babysitting/listino", headers=H(PROVIDER_TOKEN), timeout=15)
        assert g.status_code == 200
        base = g.json().get("listino") or {}
        payload = {
            "binario": "persona_lf",
            "listino": {
                "binario": "persona_lf",
                "tariffa_oraria": 10.0,
                "tariffa_ripetizioni": {"elementari": 12.0, "medie": 16.0, "superiori": 20.0},
                "materie": ["matematica", "italiano", "inglese"],
                "maggiorazione_serale_pct": 10.0,
                "maggiorazione_festiva_pct": 20.0,
                "supplemento_bambino": 5.0,
                "raggio_km": 20.0,
                "minimo_ore": 2.0,
            },
        }
        r = requests.put(f"{BASE_URL}/api/babysitting/listino", headers=H(PROVIDER_TOKEN), json=payload, timeout=15)
        assert r.status_code == 200
        assert r.json()["listino"]["tariffa_oraria"] == 10.0

    def test_casellario_upload(self):
        r = requests.post(f"{BASE_URL}/api/babysitting/casellario", headers=H(PROVIDER_TOKEN),
                          json={"image": "data:image/png;base64,iVBORw0KGgo="}, timeout=15)
        assert r.status_code == 200
        assert r.json()["uploaded"] is True

    def test_admin_casellario_verify(self):
        r = requests.post(f"{BASE_URL}/api/admin/babysitting/{PROVIDER_ID}/casellario",
                          headers=ADMIN_H, json={"verified": True}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["casellario_verified"] is True
        assert d.get("expires_at")


# ================= ADMIN LISTING =================
class TestAdmin:
    def test_admin_list_urgent_first_with_compatible(self, child_id):
        # create urgent request
        c = requests.post(f"{BASE_URL}/api/babysitting/richieste", headers=H(CLIENT_TOKEN), timeout=15, json={
            "binario": "persona_lf", "bambini": [child_id],
            "config": {"durata_ore": 3, "serale": True},
            "indirizzo": "Via Urgente 1, Treviso", "lat": 45.6669, "lng": 12.2433,
            "data_ora": "2026-08-10T20:00:00", "ora_fine": "2026-08-10T23:00:00",
            "urgente": True, "publish": True,
        })
        assert c.status_code == 200
        r = requests.get(f"{BASE_URL}/api/admin/babysitting/richieste", headers=ADMIN_H, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        assert "compatible" in items[0]
        # first should be urgent-flagged
        if any(x.get("urgente") for x in items):
            assert items[0]["urgente"] is True
        # cleanup: cancel this
        rid = c.json()["richiesta_id"]
        requests.post(f"{BASE_URL}/api/babysitting/richieste/{rid}/cancel", headers=H(CLIENT_TOKEN), timeout=15)
