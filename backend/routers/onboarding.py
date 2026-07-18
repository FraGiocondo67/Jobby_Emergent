from fastapi import APIRouter, HTTPException, Depends

from core import db
from deps import get_current_user
from models import OnboardingIn, ImageIn
from trust import recalc_provider_trust

router = APIRouter()


@router.post("/onboarding/business/photo")
async def add_business_photo(body: ImageIn, user=Depends(get_current_user)):
    photos = list(user.get("business_photos", []))
    if len(photos) >= 4:
        raise HTTPException(status_code=400, detail="max_photos")
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="empty_image")
    photos.append(body.image)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"business_photos": photos}})
    return {"business_photos": photos, "count": len(photos)}


@router.delete("/onboarding/business/photo/{index}")
async def delete_business_photo(index: int, user=Depends(get_current_user)):
    photos = list(user.get("business_photos", []))
    if 0 <= index < len(photos):
        photos.pop(index)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"business_photos": photos}})
    return {"business_photos": photos, "count": len(photos)}


@router.post("/onboarding/business/document")
async def set_business_document(body: ImageIn, user=Depends(get_current_user)):
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="empty_image")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"license_document": body.image}})
    return {"ok": True}


@router.get("/onboarding/status")
async def onboarding_status(user=Depends(get_current_user)):
    return {
        "onboarding_completed": user.get("onboarding_completed", False),
        "vat_number": user.get("vat_number", ""),
        "has_license": bool(user.get("license_document")),
        "photos_count": len(user.get("business_photos", [])),
    }


@router.post("/onboarding/complete")
async def complete_onboarding(body: OnboardingIn, user=Depends(get_current_user)):
    role = body.role
    if role not in ("client", "provider", "business"):
        raise HTTPException(status_code=400, detail="invalid_role")
    upd = {"role": role, "onboarding_completed": True}
    if body.name:
        upd["name"] = body.name
    if body.phone is not None:
        upd["phone"] = body.phone
    if body.address is not None:
        upd["address"] = body.address
    if body.lat is not None:
        upd["lat"] = body.lat
    if body.lng is not None:
        upd["lng"] = body.lng
    if role in ("provider", "business"):
        if body.services is not None:
            upd["services"] = body.services
        if body.radius_km is not None:
            upd["radius_km"] = body.radius_km
        if body.service_mode is not None:
            upd["service_mode"] = body.service_mode
    if role == "business":
        if body.business_name:
            upd["business_name"] = body.business_name
        if body.vat_number is not None:
            upd["vat_number"] = body.vat_number
    # Clients are auto-approved; providers/businesses require admin approval unless previously approved.
    upd["approval_status"] = "approved" if (role == "client" or user.get("provider_approved")) else "pending"
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    if role in ("provider", "business"):
        await recalc_provider_trust(user["user_id"])
    return await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
