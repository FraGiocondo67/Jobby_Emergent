from fastapi import APIRouter, HTTPException, Depends

from core import db
from deps import get_current_user, require_admin
from catalog import MANIFESTO
from trust import recalc_provider_trust, recalc_client_trust

router = APIRouter()


@router.get("/categories")
async def get_categories(user=Depends(get_current_user)):
    online = await db.users.count_documents({"role": {"$in": ["provider", "business"]}, "online": True})
    cats = await db.categories.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(200)
    grouped = {"standard": [], "proximity": [], "payment": []}
    for c in cats:
        grouped.get(c["kind"], grouped["standard"]).append(c)
    return {"standard": grouped["standard"], "proximity": grouped["proximity"], "payment": grouped["payment"],
            "providers_online": online, "manifesto": MANIFESTO}


@router.get("/categories/{cat_id}")
async def get_category(cat_id: str, user=Depends(get_current_user)):
    c = await db.categories.find_one({"cat_id": cat_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")
    return c


# ---- Admin (X-Admin-Token) ----
@router.get("/admin/categories")
async def admin_list_categories(_=Depends(require_admin)):
    return await db.categories.find({}, {"_id": 0}).sort("order", 1).to_list(300)


@router.post("/admin/categories/{cat_id}/toggle")
async def admin_toggle_category(cat_id: str, _=Depends(require_admin)):
    c = await db.categories.find_one({"cat_id": cat_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    new_active = not c.get("active", True)
    await db.categories.update_one({"cat_id": cat_id}, {"$set": {"active": new_active}})
    return {"cat_id": cat_id, "active": new_active}


@router.post("/admin/trust/recalc")
async def admin_trust_recalc(_=Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(1000)
    for u in users:
        await recalc_provider_trust(u["user_id"])
        await recalc_client_trust(u["user_id"])
    return {"recalculated": len(users)}
