from datetime import datetime, timezone
from core import db, now_utc, new_id

PROVIDER_WEIGHTS = {"kyc": .20, "punctuality": .20, "quality": .20, "communication": .10,
                    "cancellation": .10, "completed": .10, "dispute": .05, "tenure": .05}
CLIENT_WEIGHTS = {"identity": .20, "education": .20, "brief": .20, "payment": .15,
                  "cancellation": .15, "tips": .05, "reviews": .05}


def months_since(iso):
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (now_utc() - d).days / 30.0
    except Exception:
        return 0


async def recalc_provider_trust(user_id: str):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return
    bookings = await db.bookings.find({"provider_id": user_id}, {"_id": 0}).to_list(1000)
    completed = [b for b in bookings if b.get("status") == "completed"]
    reviews = await db.reviews.find({"provider_id": user_id}, {"_id": 0}).to_list(1000)
    disputes = await db.disputes.find({"provider_id": user_id, "against": "provider"}, {"_id": 0}).to_list(1000)
    on_time = [b for b in bookings if b.get("check_in_on_time")]

    sub = {}
    sub["kyc"] = 100 if user.get("verification_status") == "verified" else 0
    sub["punctuality"] = round(len(on_time) / len(bookings) * 100) if bookings else 90
    sub["quality"] = round(sum(r["rating"] for r in reviews) / len(reviews) / 5 * 100) if reviews else 80
    sub["communication"] = 85
    accepted = max(len(bookings), 1)
    cancelled = len([b for b in bookings if b.get("status") == "cancelled"])
    sub["cancellation"] = round(100 - cancelled / accepted * 100)
    sub["completed"] = round(min(len(completed) / 10, 1) * 100)
    sub["dispute"] = round(max(0, 100 - len(disputes) * 20))
    sub["tenure"] = round(min(months_since(user.get("created_at", now_utc().isoformat())) / 12, 1) * 100)

    score = round(sum(sub[k] * PROVIDER_WEIGHTS[k] for k in PROVIDER_WEIGHTS), 1)
    await db.users.update_one({"user_id": user_id}, {"$set": {"trust_score": score, "trust_subscores": sub}})
    return score


async def recalc_client_trust(user_id: str):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return
    events = await db.client_trust_events.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    ratings = [e["meta"].get("rating") for e in events if e.get("type") == "client_rated" and e.get("meta")]
    briefs = [e["meta"].get("brief_accuracy") for e in events if e.get("type") == "client_rated" and e.get("meta")]
    tips = [e for e in events if e.get("type") == "client_rated" and e.get("meta", {}).get("tip", 0) > 0]
    missions = await db.missions.find({"customer_id": user_id}, {"_id": 0}).to_list(1000)
    disputes = await db.disputes.find({"customer_id": user_id, "against": "client"}, {"_id": 0}).to_list(1000)

    sub = {}
    sub["identity"] = 100 if user.get("verification_status") == "verified" else 60
    sub["education"] = round(sum(ratings) / len(ratings) / 5 * 100) if ratings else 80
    sub["brief"] = round(sum(briefs) / len(briefs) / 5 * 100) if briefs else 80
    sub["payment"] = round(max(0, 100 - len(disputes) * 25))
    total_req = max(len(missions), 1)
    cancelled = len([m for m in missions if m.get("status") == "cancelled"])
    sub["cancellation"] = round(100 - cancelled / total_req * 100)
    sub["tips"] = round(min(len(tips) * 20, 100))
    sub["reviews"] = round(sum(ratings) / len(ratings) / 5 * 100) if ratings else 80

    score = round(sum(sub[k] * CLIENT_WEIGHTS[k] for k in CLIENT_WEIGHTS), 1)
    await db.users.update_one({"user_id": user_id}, {"$set": {"client_trust_score": score, "client_trust_subscores": sub}})
    return score


async def log_trust_event(collection, user_id, event_type, score_after, meta=None):
    await db[collection].insert_one({
        "event_id": new_id("te"), "user_id": user_id, "type": event_type,
        "score_after": score_after, "meta": meta or {}, "created_at": now_utc().isoformat(),
    })
