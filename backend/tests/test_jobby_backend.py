"""JOBBY backend regression tests.
Auth = Emergent Google OAuth; to test protected endpoints, we insert a synthetic
user + user_sessions doc directly into MongoDB and use the session_token as Bearer.
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path("/app/backend/.env"))

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE_URL:
    # fall back to frontend/.env
    load_dotenv(Path("/app/frontend/.env"))
    BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")

API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

TREVISO = {"lat": 45.6669, "lng": 12.2433}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def _mk_user(mongo, role="customer", lat=TREVISO["lat"], lng=TREVISO["lng"], services=None, online=True):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    token = f"tok_{uuid.uuid4().hex}"
    email = f"TEST_{uid}@jobby.test"
    mongo.users.insert_one({
        "user_id": uid, "email": email, "name": f"TEST {role}",
        "picture": "", "role": role, "language": "it", "bio": "",
        "hourly_rate": 13.0, "radius_km": 15.0,
        "services": services or ["cleaning", "ironing"],
        "online": online, "rating": 0.0, "reviews_count": 0,
        "verified": role == "provider", "lat": lat, "lng": lng,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "session_token": token, "user_id": uid,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    })
    return uid, token, email


@pytest.fixture(scope="session")
def customer(mongo):
    uid, token, email = _mk_user(mongo, role="customer")
    yield {"user_id": uid, "token": token, "email": email}
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})


@pytest.fixture(scope="session")
def provider(mongo):
    uid, token, email = _mk_user(mongo, role="provider", services=["cleaning", "ironing"])
    yield {"user_id": uid, "token": token, "email": email}
    mongo.users.delete_one({"user_id": uid})
    mongo.user_sessions.delete_many({"user_id": uid})
    mongo.bookings.delete_many({"provider_id": uid})


def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Health / basics ----------------
class TestBasics:
    def test_providers_nearby_seeded(self):
        r = requests.get(f"{API}/providers/nearby", params={"lat": TREVISO["lat"], "lng": TREVISO["lng"], "category": "cleaning"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1, "expected seeded cleaning bots"
        # Sorted by distance asc
        dists = [p["distance_km"] for p in data]
        assert dists == sorted(dists)
        for p in data:
            assert p["verified"] is True
            assert "cleaning" in p["services"]
            for k in ("user_id", "name", "hourly_rate", "rating"):
                assert k in p

    def test_providers_nearby_ironing(self):
        r = requests.get(f"{API}/providers/nearby", params={"lat": TREVISO["lat"], "lng": TREVISO["lng"], "category": "ironing"})
        assert r.status_code == 200
        for p in r.json():
            assert "ironing" in p["services"]


# ---------------- Auth ----------------
class TestAuth:
    def test_me_without_token_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_missions_list_without_token_401(self):
        r = requests.get(f"{API}/missions")
        assert r.status_code == 401

    def test_bookings_list_without_token_401(self):
        r = requests.get(f"{API}/bookings")
        assert r.status_code == 401

    def test_invalid_bearer_token_401(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_session_with_invalid_token_401(self):
        r = requests.post(f"{API}/auth/session", json={"session_token": "invalid-xyz"})
        assert r.status_code == 401

    def test_me_with_seeded_token(self, customer):
        r = requests.get(f"{API}/auth/me", headers=hdr(customer["token"]))
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == customer["user_id"]
        assert data["email"] == customer["email"]


# ---------------- Modello D matching ----------------
class TestMatching:
    def test_create_mission_and_bots_auto_accept(self, customer, mongo):
        payload = {
            "category": "cleaning", "service_type": "home",
            "config": {"rooms": 3}, "address": "Via Roma 1, Treviso",
            "lat": TREVISO["lat"], "lng": TREVISO["lng"],
            "date": "2026-02-01", "time": "10:00",
            "duration_hours": 2.0, "recurrence": "once",
        }
        r = requests.post(f"{API}/missions", json=payload, headers=hdr(customer["token"]))
        assert r.status_code == 200, r.text
        mission = r.json()
        assert mission["status"] == "broadcasting"
        assert mission["customer_id"] == customer["user_id"]
        assert len(mission["invited_provider_ids"]) >= 1, "should invite at least 1 bot"
        mission_id = mission["mission_id"]

        # Wait for bots to auto-accept (2-9s)
        accepted = []
        for _ in range(15):
            time.sleep(1)
            g = requests.get(f"{API}/missions/{mission_id}", headers=hdr(customer["token"]))
            assert g.status_code == 200
            accepted = g.json().get("accepted", [])
            if len(accepted) >= 1:
                break
        assert len(accepted) >= 1, f"no bot accepted mission after 15s: {accepted}"
        a = accepted[0]
        for k in ("provider_id", "name", "price", "eta_min", "distance_km"):
            assert k in a
        assert a["price"] > 0

        # Select provider -> booking with 15% fee
        sel = requests.post(f"{API}/missions/{mission_id}/select",
                            json={"provider_id": a["provider_id"]},
                            headers=hdr(customer["token"]))
        assert sel.status_code == 200, sel.text
        b = sel.json()
        assert b["status"] == "confirmed"
        assert b["labor_cost"] == round(a["price"], 2)
        assert b["jobby_fee"] == round(a["price"] * 0.15, 2)
        assert b["total"] == round(b["labor_cost"] + b["jobby_fee"], 2)
        assert b["provider_id"] == a["provider_id"]

        # Mission marked booked
        g2 = requests.get(f"{API}/missions/{mission_id}", headers=hdr(customer["token"]))
        assert g2.json()["status"] == "booked"
        assert g2.json()["chosen_provider_id"] == a["provider_id"]

        # Cleanup
        mongo.missions.delete_one({"mission_id": mission_id})
        mongo.bookings.delete_one({"booking_id": b["booking_id"]})


# ---------------- Provider flow ----------------
class TestProviderFlow:
    def test_incoming_accept_decline_and_review(self, customer, provider, mongo):
        # Create mission (provider is invited because online + services match + near Treviso)
        payload = {
            "category": "cleaning", "service_type": "home", "config": {},
            "address": "Via Test 2", "lat": TREVISO["lat"], "lng": TREVISO["lng"],
            "date": "2026-02-02", "time": "11:00",
            "duration_hours": 3.0, "recurrence": "once",
        }
        r = requests.post(f"{API}/missions", json=payload, headers=hdr(customer["token"]))
        assert r.status_code == 200
        mission_id = r.json()["mission_id"]
        assert provider["user_id"] in r.json()["invited_provider_ids"]

        # Incoming list
        inc = requests.get(f"{API}/missions/incoming/list", headers=hdr(provider["token"]))
        assert inc.status_code == 200
        assert any(m["mission_id"] == mission_id for m in inc.json())

        # Provider accepts
        acc = requests.post(f"{API}/missions/{mission_id}/accept",
                            json={"price": 50.0}, headers=hdr(provider["token"]))
        assert acc.status_code == 200

        # Verify accept appears
        g = requests.get(f"{API}/missions/{mission_id}", headers=hdr(customer["token"])).json()
        assert any(a["provider_id"] == provider["user_id"] and a["price"] == 50.0 for a in g["accepted"])

        # Customer selects
        sel = requests.post(f"{API}/missions/{mission_id}/select",
                            json={"provider_id": provider["user_id"]},
                            headers=hdr(customer["token"]))
        assert sel.status_code == 200
        booking = sel.json()
        assert booking["labor_cost"] == 50.0
        assert booking["jobby_fee"] == 7.5
        assert booking["total"] == 57.5
        booking_id = booking["booking_id"]

        # Complete booking
        comp = requests.post(f"{API}/bookings/{booking_id}/complete", headers=hdr(customer["token"]))
        assert comp.status_code == 200
        assert comp.json()["status"] == "completed"

        # Review updates provider rating
        rev = requests.post(f"{API}/bookings/{booking_id}/review",
                            json={"rating": 5, "comment": "TEST great"},
                            headers=hdr(customer["token"]))
        assert rev.status_code == 200
        prov_doc = mongo.users.find_one({"user_id": provider["user_id"]})
        assert prov_doc["reviews_count"] >= 1
        assert prov_doc["rating"] == 5.0

        # Earnings aggregation for provider
        ern = requests.get(f"{API}/earnings", headers=hdr(provider["token"]))
        assert ern.status_code == 200
        e = ern.json()
        assert e["jobs_count"] >= 1
        assert e["completed_count"] >= 1
        assert e["total_earned"] >= 50.0

        # Test decline: create another mission, decline it
        r2 = requests.post(f"{API}/missions", json=payload, headers=hdr(customer["token"]))
        mid2 = r2.json()["mission_id"]
        dec = requests.post(f"{API}/missions/{mid2}/decline", headers=hdr(provider["token"]))
        assert dec.status_code == 200
        m2 = mongo.missions.find_one({"mission_id": mid2})
        assert provider["user_id"] not in m2["invited_provider_ids"]

        # Cleanup
        mongo.missions.delete_many({"mission_id": {"$in": [mission_id, mid2]}})
        mongo.bookings.delete_many({"booking_id": booking_id})
        mongo.reviews.delete_many({"booking_id": booking_id})
