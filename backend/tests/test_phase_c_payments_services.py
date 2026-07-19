"""Phase C — Payment Services backend tests.

Covers /api/payments/options, /api/beneficiaries CRUD, /api/payments/service
(topup / bill / abroad / local), wallet vs card charge, and /api/payments/history.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
TOKEN = "demo-preview-token-123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def s():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", **AUTH})
    return session


# --- track ids created here for teardown ---
CREATED = {"beneficiaries": []}


def teardown_module(_):
    for bid in CREATED["beneficiaries"]:
        try:
            requests.delete(f"{BASE_URL}/api/beneficiaries/{bid}", headers=AUTH, timeout=15)
        except Exception:
            pass


# ---------------------------------------------------------------- catalog
def test_payment_options_it(s):
    r = s.get(f"{BASE_URL}/api/payments/options?country=IT", timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["country"] == "IT"
    ops = j["operators"]
    bills = j["billers"]
    assert isinstance(ops, list) and len(ops) == 10, f"expected 10 operators, got {len(ops)}"
    assert isinstance(bills, list) and len(bills) == 14, f"expected 14 billers, got {len(bills)}"
    assert any(o["id"] == "iliad" for o in ops)
    assert any(b["id"] == "enel" for b in bills)


def test_payment_options_default_falls_back_to_it(s):
    r = s.get(f"{BASE_URL}/api/payments/options", timeout=20)
    assert r.status_code == 200
    assert r.json()["country"] == "IT"


# ---------------------------------------------------------------- beneficiaries
def test_beneficiary_create_invalid_type(s):
    r = s.post(f"{BASE_URL}/api/beneficiaries",
               json={"name": "TEST bad", "type": "foo", "iban": "DE89370400440532013000"},
               timeout=20)
    assert r.status_code == 400
    assert "invalid_type" in r.text


def test_beneficiary_create_missing_iban(s):
    r = s.post(f"{BASE_URL}/api/beneficiaries",
               json={"name": "TEST no iban", "type": "abroad"},
               timeout=20)
    assert r.status_code == 400
    assert "iban_required" in r.text


def test_beneficiary_create_abroad_ok(s):
    payload = {"name": "TEST Alice DE", "type": "abroad",
               "iban": "DE89370400440532013000", "swift": "COBADEFFXXX",
               "bank_name": "Commerzbank", "country": "DE"}
    r = s.post(f"{BASE_URL}/api/beneficiaries", json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    j = r.json()
    assert "ben_id" in j and j["type"] == "abroad" and j["iban"] == payload["iban"]
    assert j["name"] == payload["name"]
    CREATED["beneficiaries"].append(j["ben_id"])


def test_beneficiary_list_abroad(s):
    r = s.get(f"{BASE_URL}/api/beneficiaries?type=abroad", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert any(b["ben_id"] in CREATED["beneficiaries"] for b in items)


def test_beneficiary_delete(s):
    # create one dedicated to delete
    payload = {"name": "TEST DEL", "type": "local", "iban": "IT60X0542811101000000123456"}
    r = s.post(f"{BASE_URL}/api/beneficiaries", json=payload, timeout=20)
    assert r.status_code in (200, 201)
    bid = r.json()["ben_id"]
    d = s.delete(f"{BASE_URL}/api/beneficiaries/{bid}", timeout=20)
    assert d.status_code == 200 and d.json().get("ok") is True
    # verify removed via list
    r2 = s.get(f"{BASE_URL}/api/beneficiaries", timeout=20)
    assert all(b["ben_id"] != bid for b in r2.json())


# ---------------------------------------------------------------- helper: balance
def _balance(s):
    return s.get(f"{BASE_URL}/api/wallet", timeout=20).json().get("balance", 0)


# ---------------------------------------------------------------- service: topup
def test_topup_missing_operator(s):
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "topup", "amount": 5, "source": "wallet"},
               timeout=20)
    assert r.status_code == 400 and "operator_required" in r.text


def test_topup_invalid_amount(s):
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "topup", "amount": 0, "source": "wallet",
                     "operator_id": "iliad", "phone_number": "+39333"},
               timeout=20)
    assert r.status_code == 400 and "invalid_amount" in r.text


def test_topup_success_and_balance_decrease(s):
    before = _balance(s)
    assert before >= 10, "test account needs >=10 balance"
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "topup", "amount": 10, "source": "wallet",
                     "operator_id": "iliad", "phone_number": "+39333"},
               timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    tx = j["transaction"]
    assert tx["kind"] == "topup"
    assert tx["label"] == "Ricarica Iliad"
    assert tx["amount"] == -10.0
    assert abs(j["balance"] - round(before - 10, 2)) < 0.01


# ---------------------------------------------------------------- service: bill
def test_bill_missing_biller(s):
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "bill", "amount": 30, "source": "wallet"},
               timeout=20)
    assert r.status_code == 400 and "biller_required" in r.text


def test_bill_success(s):
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "bill", "amount": 5, "source": "wallet",
                     "biller_id": "enel", "bill_ref": "123"},
               timeout=20)
    assert r.status_code == 200, r.text
    tx = r.json()["transaction"]
    assert tx["kind"] == "bill" and "Enel" in tx["label"]
    assert tx["meta"]["bill_ref"] == "123"


# ---------------------------------------------------------------- service: abroad
def test_abroad_missing_beneficiary(s):
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "abroad", "amount": 50, "source": "wallet",
                     "beneficiary_id": "nope"},
               timeout=20)
    assert r.status_code == 400 and "beneficiary_required" in r.text


def test_abroad_success(s):
    # Create a beneficiary just for this call
    b = s.post(f"{BASE_URL}/api/beneficiaries",
               json={"name": "TEST Beneficiary Abroad", "type": "abroad",
                     "iban": "DE89370400440532013000", "bank_name": "Commerzbank"},
               timeout=20).json()
    CREATED["beneficiaries"].append(b["ben_id"])
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "abroad", "amount": 5, "source": "wallet",
                     "beneficiary_id": b["ben_id"]},
               timeout=20)
    assert r.status_code == 200, r.text
    tx = r.json()["transaction"]
    assert tx["kind"] == "abroad" and b["name"] in tx["label"]


# ---------------------------------------------------------------- guards
def test_wallet_insufficient_funds(s):
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "topup", "amount": 999999, "source": "wallet",
                     "operator_id": "iliad", "phone_number": "+39333"},
               timeout=20)
    assert r.status_code == 400 and "insufficient_funds" in r.text


def test_card_no_card(s):
    # demo-preview account has no payment_method
    r = s.post(f"{BASE_URL}/api/payments/service",
               json={"kind": "topup", "amount": 5, "source": "card",
                     "operator_id": "iliad", "phone_number": "+39333"},
               timeout=20)
    # If test account has been given a card by prior tests, skip
    if r.status_code == 200:
        pytest.skip("account has payment_method; cannot assert no_card")
    assert r.status_code == 400 and "no_card" in r.text


# ---------------------------------------------------------------- history
def test_history_all_lists_service_txs(s):
    r = s.get(f"{BASE_URL}/api/payments/history?kind=all", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 1
    assert all(x.get("type") == "service" for x in items)


def test_history_filter_topup(s):
    r = s.get(f"{BASE_URL}/api/payments/history?kind=topup", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 1
    assert all(x.get("kind") == "topup" for x in items)
