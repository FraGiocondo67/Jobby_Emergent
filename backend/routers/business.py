from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id, haversine, TREVISO
from deps import get_current_user
from models import BusinessRequestIn, BusinessResponseIn
from routers.chat import open_thread

router = APIRouter()


@router.get("/businesses")
async def list_businesses(category: str, lat: float = TREVISO["lat"], lng: float = TREVISO["lng"], user=Depends(get_current_user)):
    """Real registered businesses (no bots) that offer the given category, sorted by distance."""
    biz = await db.users.find(
        {"role": "business", "online": True, "is_bot": {"$ne": True}, "services": category},
        {"_id": 0}).to_list(300)
    result = []
    for b in biz:
        dist = haversine(lat, lng, b.get("lat", TREVISO["lat"]), b.get("lng", TREVISO["lng"]))
        result.append({
            "user_id": b["user_id"], "name": b.get("business_name") or b["name"], "picture": b.get("picture", ""),
            "rating": b.get("rating", 0), "reviews_count": b.get("reviews_count", 0), "bio": b.get("bio", ""),
            "verified": b.get("verified", False), "trust_score": b.get("trust_score", 0),
            "service_mode": b.get("service_mode", "both"), "distance_km": dist,
            "lat": b.get("lat"), "lng": b.get("lng"),
        })
    result.sort(key=lambda x: x["distance_km"])
    return result


@router.post("/business-requests")
async def create_business_request(body: BusinessRequestIn, user=Depends(get_current_user)):
    biz = await db.users.find_one({"user_id": body.business_id, "role": "business"}, {"_id": 0})
    if not biz:
        raise HTTPException(status_code=404, detail="business_not_found")
    cat = await db.categories.find_one({"cat_id": body.category}, {"_id": 0})
    label = cat["label"] if cat else {"it": body.category, "en": body.category}
    rid = new_id("breq")
    doc = {
        "request_id": rid, "kind": "business_request", "client_id": user["user_id"], "client_name": user["name"],
        "business_id": body.business_id, "business_name": biz.get("business_name") or biz["name"],
        "business_picture": biz.get("picture", ""), "category": body.category, "category_label": label,
        "note": body.note, "address": body.address, "lat": body.lat, "lng": body.lng,
        "status": "pending", "response": None,
        "created_at": now_utc().isoformat(), "updated_at": now_utc().isoformat(),
    }
    await db.business_requests.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/business-requests")
async def my_business_requests(user=Depends(get_current_user)):
    return await db.business_requests.find({"client_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/business-requests/incoming")
async def incoming_business_requests(user=Depends(get_current_user)):
    if user["role"] != "business":
        return []
    return await db.business_requests.find({"business_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/business-requests/{request_id}")
async def get_business_request(request_id: str, user=Depends(get_current_user)):
    r = await db.business_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    if user["user_id"] not in (r["client_id"], r["business_id"]):
        raise HTTPException(status_code=403, detail="forbidden")
    return r


@router.post("/business-requests/{request_id}/respond")
async def respond_business_request(request_id: str, body: BusinessResponseIn, user=Depends(get_current_user)):
    r = await db.business_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    if r["business_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail="already_handled")
    if not body.accept:
        await db.business_requests.update_one({"request_id": request_id},
                                              {"$set": {"status": "declined", "updated_at": now_utc().isoformat()}})
        return {"status": "declined"}
    response = {"eta": body.eta, "mode": body.mode, "delivery_cost": round(body.delivery_cost, 2),
                "price": round(body.price, 2), "note": body.note}
    await db.business_requests.update_one({"request_id": request_id},
                                          {"$set": {"status": "confirmed", "response": response, "updated_at": now_utc().isoformat()}})
    # Open a chat thread and post the confirmation summary as the first message.
    mode_txt = "Consegna a domicilio" if body.mode == "delivery" else "Ritiro in sede"
    summary = (f"Richiesta confermata ✅\n{mode_txt}\nTempo: {body.eta or 'da concordare'}\n"
               f"Prezzo: €{response['price']:.2f} + consegna €{response['delivery_cost']:.2f}"
               + (f"\nNota: {body.note}" if body.note else ""))
    await open_thread(r["client_id"], r["client_name"], r["business_id"], r["business_name"],
                      r.get("business_picture", ""), first_message=summary)
    return {"status": "confirmed", "response": response}
