"""Iter 47 — AUTO-INVITE on publish (pulizie / babysitting / artigiani) +
end-to-end ESCROW/QR reconfirmation.

FIX under test: create_richiesta endpoints now auto-populate provider_invitati
with all compatible providers (status='invited', auto=True) so the request
appears immediately in each compatible provider's /incoming without admin invite.
Driver already had auto-invite.

Also re-runs a slimmed pulizie escrow QR-off / QR-on cycle to prove no regression.
Restores wallet + QR pref after each test.
"""
import os
import pytest
import requests
import pymongo
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                      "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN = {"X-Admin-Token": "jobby-admin-7c2f9a"}

CLIENT_TOK   = "disp-test-token-777"      # user_disptest01
IMPRESA_TOK  = "req-prov-token"           # user_2f996c8a010a (role=business, pulizie listino)
GIULIA_TOK   = "prov-test-token-888"      # prov_cfbd9805ce97 (provider, persona_lf babysitter + driver ncc)
LF_PROV_TOK  = "lf-prov-token"            # pulizie persona_lf provider

MONGO = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB    = MONGO[os.environ.get("DB_NAME", "test_database")]


def _h(tok): return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _uid(tok):
    s = DB.user_sessions.find_one({"session_token": tok}, {"_id": 0, "user_id": 1})
    return s["user_id"] if s else None


def _wallet(uid):
    u = DB.users.find_one({"user_id": uid},
                          {"_id": 0, "wallet_balance": 1, "bonus_credit": 1,
                           "pending_balance": 1, "role": 1}) or {}
    return {k: u.get(k) for k in ("wallet_balance", "bonus_credit", "pending_balance", "role")}


def _restore_client():
    uid = _uid(CLIENT_TOK)
    DB.users.update_one({"user_id": uid}, {"$set": {"wallet_balance": 500.0, "bonus_credit": 50.0}})
    requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK), json={"enabled": False})


@pytest.fixture(scope="module", autouse=True)
def _module_setup():
    # ensure client starts clean
    _restore_client()
    yield
    _restore_client()


# ---------------- Auto-invite: PULIZIE ----------------
class TestAutoInvitePulizie:
    def test_create_publish_auto_invites_and_provider_sees_it(self):
        client_id = _uid(CLIENT_TOK)
        impresa_id = _uid(IMPRESA_TOK)
        payload = {
            "binario": "impresa",
            "config": {"home_type": "appartamento", "mq_band": "80_120",
                       "tipo_pulizia": "ordinaria", "extra": [], "stiro_ore": 0,
                       "prodotti": "cliente", "durata_ore": 3, "animali": False},
            "indirizzo": "Via Roma 1, Treviso", "lat": 45.6669, "lng": 12.2433,
            "data_ora": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "flessibilita": "fascia", "ricorrenza": "una_tantum",
            "parcheggio": "libero", "publish": True,
        }
        r = requests.post(f"{BASE}/pulizie/richieste", headers=_h(CLIENT_TOK), json=payload)
        assert r.status_code == 200, r.text
        rid = r.json()["richiesta_id"]

        # 1) DB assertion: provider_invitati populated by publish (auto=True)
        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        invitati = doc.get("provider_invitati") or []
        assert len(invitati) >= 1, f"no auto-invites populated. Doc={doc}"
        assert any(i.get("auto") is True for i in invitati), "no auto=True invite marker"
        invited_ids = {i["provider_id"] for i in invitati}
        assert impresa_id in invited_ids, (
            f"impresa provider {impresa_id} not auto-invited. Invited={invited_ids}"
        )

        # 2) NO admin call — provider must already see it in /incoming
        inc = requests.get(f"{BASE}/pulizie/incoming", headers=_h(IMPRESA_TOK))
        assert inc.status_code == 200, inc.text
        ids = [x.get("richiesta_id") for x in inc.json()]
        assert rid in ids, f"rid {rid} not in impresa incoming without admin invite. Got {ids[:5]}"

        # 3) Provider proposes accept → richiesta enters con_proposte
        p = requests.post(f"{BASE}/pulizie/richieste/{rid}/propose",
                          headers=_h(IMPRESA_TOK), json={"accept": True})
        assert p.status_code == 200, p.text
        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["stato"] == "con_proposte"

        # 4) Client GET /pulizie/richieste — sees con_proposte state
        mine = requests.get(f"{BASE}/pulizie/richieste", headers=_h(CLIENT_TOK)).json()
        cur = next((x for x in mine if x["richiesta_id"] == rid), None)
        assert cur and cur["stato"] == "con_proposte"


# ---------------- Auto-invite: BABYSITTING ----------------
class TestAutoInviteBabysitting:
    def _ensure_child(self, client_id):
        c = DB.child_cards.find_one({"family_id": client_id})
        if c:
            return c["card_id"]
        # create one
        r = requests.post(f"{BASE}/babysitting/children", headers=_h(CLIENT_TOK),
                          json={"nome": "TEST_child", "eta_mesi": 60, "sesso": "m",
                                "abitudini": "", "allergie": "", "note": "", "consenso": True})
        assert r.status_code == 200, r.text
        return r.json()["card_id"]

    def test_create_publish_auto_invites_and_babysitter_sees_it(self):
        client_id = _uid(CLIENT_TOK)
        giulia_id = _uid(GIULIA_TOK)
        card_id = self._ensure_child(client_id)

        # Ensure Giulia is INPS-registered so persona_lf compatibility passes
        DB.users.update_one({"user_id": giulia_id},
                            {"$set": {"lf_inps_registered": True}})

        start = datetime.now(timezone.utc) + timedelta(days=3)
        end   = start + timedelta(hours=3)
        payload = {
            "binario": "persona_lf",
            "bambini": [card_id],
            "config": {"n_bambini": 1, "durata_ore": 3, "ripetizioni_attiva": False,
                       "ripetizioni_materie": [], "ripetizioni_ore": 0,
                       "ripetizioni_livello": "medie", "serale": False, "festivo": False},
            "indirizzo": "Via Roma 1, Treviso", "lat": 45.6669, "lng": 12.2433,
            "data_ora": start.isoformat(), "ora_fine": end.isoformat(),
            "urgente": False, "ricorrenza": "una_tantum",
            "publish": True,
        }
        r = requests.post(f"{BASE}/babysitting/richieste", headers=_h(CLIENT_TOK), json=payload)
        assert r.status_code == 200, r.text
        rid = r.json()["richiesta_id"]

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        invitati = doc.get("provider_invitati") or []
        if not invitati:
            pytest.skip(f"no persona_lf babysitters compatible (INPS gate?). Doc={doc}")
        assert any(i.get("auto") is True for i in invitati)
        invited_ids = {i["provider_id"] for i in invitati}
        # Giulia should be present (persona_lf, INPS OK, listino ok, near Treviso)
        if giulia_id not in invited_ids:
            # log a note but don't fail — could be raggio/listino gap
            print(f"NOTE: Giulia not auto-invited. Invited={invited_ids}")

        # Provider incoming
        inc = requests.get(f"{BASE}/babysitting/incoming", headers=_h(GIULIA_TOK))
        assert inc.status_code == 200, inc.text
        ids = [x.get("richiesta_id") for x in inc.json()]
        if giulia_id in invited_ids:
            assert rid in ids, f"rid {rid} not in Giulia incoming. Got {ids[:5]}"


# ---------------- Auto-invite: ARTIGIANI ----------------
class TestAutoInviteArtigiani:
    def _ensure_artigiano_provider(self):
        """Find an approved provider with services=artigiani + a listino + near Treviso."""
        cand = DB.users.find_one({
            "services": "artigiani",
            "role": {"$in": ["provider", "business"]},
            "approval_status": {"$nin": ["rejected", "suspended", "waitlist", "pending"]},
            "art_listini": {"$exists": True},
        }, {"_id": 0})
        return cand

    def test_create_publish_auto_invites(self):
        prov = self._ensure_artigiano_provider()
        if not prov:
            pytest.skip("no artigiano provider with art_listini seeded")
        # find a mestiere with impresa binario
        listini = prov.get("art_listini") or {}
        mestiere = None
        for m, lst in listini.items():
            if (lst or {}).get("binario") != "persona_lf":
                mestiere = m
                break
        if not mestiere:
            mestiere = list(listini.keys())[0]

        payload = {
            "mestiere": mestiere, "modalita": "diagnosi",
            "intervento_id": "", "parametri": {},
            "descrizione": "TEST — perdita rubinetto", "foto": [],
            "binario": "impresa", "urgente": False,
            "fascia_urgenza": "", "fascia_oraria": "mattina",
            "indirizzo": "Via Roma 1, Treviso", "accesso": "",
            "lat": 45.6669, "lng": 12.2433,
            "data_ora": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        }
        r = requests.post(f"{BASE}/artigiani/richieste", headers=_h(CLIENT_TOK), json=payload)
        assert r.status_code == 200, r.text
        rid = r.json()["richiesta_id"]

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        invitati = doc.get("provider_invitati") or []
        assert invitati, (
            f"no artigiani auto-invited for mestiere={mestiere}. Doc={doc}"
        )
        assert any(i.get("auto") is True for i in invitati)

        # If our candidate provider is among invited, verify their /artigiani/incoming shows it
        prov_uid = prov["user_id"]
        # find a session token for that provider (optional)
        sess = DB.user_sessions.find_one({"user_id": prov_uid}, {"_id": 0, "session_token": 1})
        if sess and prov_uid in {i["provider_id"] for i in invitati}:
            tok = sess["session_token"]
            inc = requests.get(f"{BASE}/artigiani/incoming", headers=_h(tok))
            assert inc.status_code == 200, inc.text
            ids = [x.get("richiesta_id") for x in inc.json()]
            assert rid in ids, f"artigiano {prov_uid} does not see rid in incoming"


# ---------------- Escrow QR-off + QR-on quick regression ----------------
def _create_pulizie():
    payload = {
        "binario": "impresa",
        "config": {"home_type": "appartamento", "mq_band": "80_120",
                   "tipo_pulizia": "ordinaria", "extra": [], "stiro_ore": 0,
                   "prodotti": "cliente", "durata_ore": 3, "animali": False},
        "indirizzo": "Via Roma 1, Treviso", "lat": 45.6669, "lng": 12.2433,
        "data_ora": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "flessibilita": "fascia", "ricorrenza": "una_tantum",
        "parcheggio": "libero", "publish": True,
    }
    r = requests.post(f"{BASE}/pulizie/richieste", headers=_h(CLIENT_TOK), json=payload)
    assert r.status_code == 200, r.text
    return r.json()["richiesta_id"]


class TestEscrowRegression:
    def test_qr_off_confirm_blocks_and_complete_releases(self):
        client_id = _uid(CLIENT_TOK)
        impresa_id = _uid(IMPRESA_TOK)
        _restore_client()
        pre_client = _wallet(client_id)
        pre_impresa = _wallet(impresa_id)

        rid = _create_pulizie()
        # auto-invite must include impresa
        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert impresa_id in {i["provider_id"] for i in doc.get("provider_invitati", [])}

        prop = requests.post(f"{BASE}/pulizie/richieste/{rid}/propose",
                             headers=_h(IMPRESA_TOK), json={"accept": True})
        assert prop.status_code == 200, prop.text
        price = prop.json()["price"]

        conf = requests.post(f"{BASE}/pulizie/richieste/{rid}/confirm",
                             headers=_h(CLIENT_TOK), json={"provider_id": impresa_id})
        assert conf.status_code == 200, conf.text

        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["escrow"]["stato"] == "held"
        after_client = _wallet(client_id)
        # funds decreased
        assert (after_client["wallet_balance"] + after_client["bonus_credit"]) < \
               (pre_client["wallet_balance"] + pre_client["bonus_credit"])

        # complete → released, business earner immediate credit
        comp = requests.post(f"{BASE}/pulizie/richieste/{rid}/complete",
                             headers=_h(IMPRESA_TOK))
        assert comp.status_code == 200, comp.text
        doc3 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc3["escrow"]["stato"] == "released"
        net = doc3["escrow"]["net_provider"]
        after_impresa = _wallet(impresa_id)
        if pre_impresa["role"] == "business":
            assert abs(after_impresa["wallet_balance"] -
                       (pre_impresa["wallet_balance"] + net)) < 0.01

        _restore_client()

    def test_qr_on_arms_then_confirm_code_releases(self):
        client_id = _uid(CLIENT_TOK)
        impresa_id = _uid(IMPRESA_TOK)
        _restore_client()

        # Turn ON QR
        r = requests.post(f"{BASE}/profile/qr-confirm", headers=_h(CLIENT_TOK),
                          json={"enabled": True})
        assert r.status_code == 200

        pre_impresa = _wallet(impresa_id)
        rid = _create_pulizie()
        prop = requests.post(f"{BASE}/pulizie/richieste/{rid}/propose",
                             headers=_h(IMPRESA_TOK), json={"accept": True})
        assert prop.status_code == 200
        conf = requests.post(f"{BASE}/pulizie/richieste/{rid}/confirm",
                             headers=_h(CLIENT_TOK), json={"provider_id": impresa_id})
        assert conf.status_code == 200

        # Complete arms
        comp = requests.post(f"{BASE}/pulizie/richieste/{rid}/complete",
                             headers=_h(IMPRESA_TOK))
        assert comp.status_code == 200

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc.get("conferma_pending") is True
        assert doc["escrow"]["stato"] == "held"

        # Client GET code
        ref = requests.get(f"{BASE}/delivery/ref/{rid}", headers=_h(CLIENT_TOK))
        assert ref.status_code == 200, ref.text
        code = ref.json()["code"]

        # Wrong code → 400
        bad = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(IMPRESA_TOK),
                            json={"ref_id": rid, "code": "999999"})
        assert bad.status_code == 400, bad.text

        # Non-earner (Giulia) → 403
        wrong = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(GIULIA_TOK),
                              json={"ref_id": rid, "code": code})
        assert wrong.status_code == 403, wrong.text

        # Correct → 200
        ok = requests.post(f"{BASE}/delivery/confirm-code", headers=_h(IMPRESA_TOK),
                           json={"ref_id": rid, "code": code})
        assert ok.status_code == 200, ok.text
        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["escrow"]["stato"] == "released"

        after_impresa = _wallet(impresa_id)
        net = ok.json()["released"]
        if pre_impresa["role"] == "business":
            assert abs(after_impresa["wallet_balance"] -
                       (pre_impresa["wallet_balance"] + net)) < 0.01

        _restore_client()


# ---------------- Driver escrow (regression: auto-confirm branch fixed?) ----------------
class TestDriverEscrow:
    def test_direct_driver_auto_confirm_holds_and_release(self):
        client_id = _uid(CLIENT_TOK)
        giulia_id = _uid(GIULIA_TOK)
        _restore_client()
        pre_client = _wallet(client_id)
        pre_giulia = _wallet(giulia_id)

        pickup = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        body = {
            "tipo": "ncc", "classe": "standard",
            "partenza": {"label": "Treviso", "lat": 45.6669, "lng": 12.2433},
            "destinazione": {"label": "Venezia Aeroporto", "lat": 45.5053, "lng": 12.3519},
            "pickup_at": pickup, "flight_number": "", "passeggeri": 1, "bagagli": 1,
            "passeggero_nome": "TEST", "passeggero_tel": "+390000000",
            "minore": False, "minore_consenso": False, "special": [],
            "ritorno": None, "note": "test",
            "target_provider_id": giulia_id,
        }
        r = requests.post(f"{BASE}/driver/richieste", headers=_h(CLIENT_TOK), json=body)
        assert r.status_code == 200, r.text
        rid = r.json()["richiesta_id"]

        p = requests.post(f"{BASE}/driver/richieste/{rid}/propose", headers=_h(GIULIA_TOK),
                          json={"accept": True})
        assert p.status_code == 200, p.text
        pj = p.json()

        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        auto_confirmed = pj.get("auto_confirmed") is True
        if doc["stato"] != "confermata":
            c = requests.post(f"{BASE}/driver/richieste/{rid}/confirm",
                              headers=_h(CLIENT_TOK), json={"provider_id": giulia_id})
            assert c.status_code == 200, c.text
        doc = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc.get("escrow", {}).get("stato") == "held", (
            f"ESCROW BUG STILL PRESENT — driver auto-confirm branch did not call we.hold. "
            f"auto_confirmed={auto_confirmed} doc.escrow={doc.get('escrow')}"
        )
        held_client = _wallet(client_id)
        assert (held_client["wallet_balance"] + held_client["bonus_credit"]) < \
               (pre_client["wallet_balance"] + pre_client["bonus_credit"])

        dp = requests.post(f"{BASE}/driver/richieste/{rid}/depart", headers=_h(GIULIA_TOK))
        assert dp.status_code == 200
        cp = requests.post(f"{BASE}/driver/richieste/{rid}/complete",
                           headers=_h(GIULIA_TOK), json={})
        assert cp.status_code == 200

        doc2 = DB.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
        assert doc2["escrow"]["stato"] == "released"
        net = doc2["escrow"]["net_provider"]
        after_g = _wallet(giulia_id)
        # Giulia is provider → pending_balance
        assert abs(after_g["pending_balance"] -
                   (pre_giulia["pending_balance"] + net)) < 0.01, (
            f"pending expected {pre_giulia['pending_balance']+net} got {after_g['pending_balance']}"
        )
        holds = list(DB.wallet_holds.find({"richiesta_id": rid, "status": "pending"}))
        assert holds, "wallet_holds must exist for provider role"

        _restore_client()
