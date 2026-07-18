"""Iteration 8 - Map (providers+businesses trust + approval_status) & Payments split from Wallet.

Covers:
- GET /api/providers/nearby returns providers AND businesses with role/approval_status/trust_score
- GET /api/businesses?category=lavanderia returns businesses (trust_score, approval_status)
- PUT /api/wallet/crypto-wallet accepts valid tokens, rejects invalid (400)
- GET /api/wallet returns crypto_wallets array
- PUT /api/profile role switch sets approval_status=pending (unless provider_approved)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://jobby-mvp-update.preview.emergentagent.com").rstrip("/")
CLIENT_TOKEN = "demo-preview-token-123"
BUSINESS_TOKEN = "biz-test-token-999"
TREVISO = {"lat": 45.6669, "lng": 12.2433}


@pytest.fixture
def client_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {CLIENT_TOKEN}"})
    return s


@pytest.fixture
def business_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {BUSINESS_TOKEN}"})
    return s


# --- providers/nearby: providers AND businesses -------------------------------
class TestProvidersNearby:
    def test_nearby_returns_role_and_trust_fields(self, client_session):
        r = client_session.get(f"{BASE_URL}/api/providers/nearby", params={"lat": TREVISO["lat"], "lng": TREVISO["lng"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Francesco (business) is expected to be online -> should show up here since providers/nearby now includes businesses
        roles = {p.get("role") for p in data}
        assert data, "Expected at least one nearby entry (Francesco business should be online)"
        for p in data:
            assert "role" in p and p["role"] in ("provider", "business"), p
            assert "trust_score" in p
            assert "approval_status" in p
            assert p["approval_status"] in ("approved", "pending", "rejected")
        # At least the business is included
        assert "business" in roles, f"Expected role=business in nearby response, got roles={roles}"

    def test_nearby_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/providers/nearby", params={"lat": TREVISO["lat"], "lng": TREVISO["lng"]})
        assert r.status_code in (401, 403), r.status_code


# --- businesses category ------------------------------------------------------
class TestBusinessesCategory:
    def test_lavanderia_has_trust_and_approval(self, client_session):
        r = client_session.get(f"{BASE_URL}/api/businesses", params={"category": "lavanderia"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Expected Francesco Franzin to be listed for lavanderia"
        for b in data:
            assert "trust_score" in b
            assert "approval_status" in b
            assert "rating" in b
            assert "distance_km" in b
            assert "lat" in b and "lng" in b


# --- crypto wallet ------------------------------------------------------------
VALID_TOKENS = ["BTC", "USDT_TRC20", "USDC_ERC20", "USDT_ERC20", "XRP"]


class TestCryptoWallet:
    @pytest.mark.parametrize("token", VALID_TOKENS)
    def test_valid_token_sets_address(self, business_session, token):
        addr = f"TEST_addr_{token}_abc123"
        r = business_session.put(f"{BASE_URL}/api/wallet/crypto-wallet", json={"token": token, "address": addr})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "crypto_wallets" in data
        entry = next((w for w in data["crypto_wallets"] if w["token"] == token), None)
        assert entry, f"Token {token} not persisted"
        assert entry["address"] == addr

    def test_invalid_token_returns_400(self, business_session):
        r = business_session.put(f"{BASE_URL}/api/wallet/crypto-wallet", json={"token": "DOGE", "address": "test"})
        assert r.status_code == 400

    def test_wallet_returns_crypto_wallets_array(self, business_session):
        r = business_session.get(f"{BASE_URL}/api/wallet")
        assert r.status_code == 200, r.text
        w = r.json()
        assert "crypto_wallets" in w
        assert isinstance(w["crypto_wallets"], list)
        tokens_set = {x["token"] for x in w["crypto_wallets"]}
        # All 5 tokens should be persisted from the parametrized test above
        for tk in VALID_TOKENS:
            assert tk in tokens_set, f"Missing token {tk} in {tokens_set}"

    def test_empty_address_removes_entry(self, business_session):
        # Set then unset BTC
        r1 = business_session.put(f"{BASE_URL}/api/wallet/crypto-wallet", json={"token": "BTC", "address": "TEST_btc_remove"})
        assert r1.status_code == 200
        r2 = business_session.put(f"{BASE_URL}/api/wallet/crypto-wallet", json={"token": "BTC", "address": "   "})
        assert r2.status_code == 200
        wallets = r2.json()["crypto_wallets"]
        assert not any(w["token"] == "BTC" for w in wallets)
        # Restore for later runs
        business_session.put(f"{BASE_URL}/api/wallet/crypto-wallet", json={"token": "BTC", "address": "TEST_btc_restore"})


# --- profile role switch → approval_status pending ---------------------------
class TestProfileRoleApproval:
    def test_client_switch_to_provider_sets_pending(self, client_session):
        # Ensure current provider_approved status is known
        me = client_session.get(f"{BASE_URL}/api/auth/me").json()
        original_role = me.get("role")
        provider_approved = me.get("provider_approved", False)

        try:
            r = client_session.put(f"{BASE_URL}/api/profile", json={"role": "provider"})
            assert r.status_code == 200, r.text
            data = r.json()
            expected = "approved" if provider_approved else "pending"
            assert data["approval_status"] == expected, data.get("approval_status")

            # Switch to business too
            r2 = client_session.put(f"{BASE_URL}/api/profile", json={"role": "business"})
            assert r2.status_code == 200
            assert r2.json()["approval_status"] == expected

            # Switch back to client -> approved
            r3 = client_session.put(f"{BASE_URL}/api/profile", json={"role": "client"})
            assert r3.status_code == 200
            assert r3.json()["approval_status"] == "approved"
        finally:
            # restore original role
            client_session.put(f"{BASE_URL}/api/profile", json={"role": original_role or "client"})
