from fastapi import APIRouter, Depends
from core import db, now_utc, new_id
from deps import get_current_user

router = APIRouter()


async def push_notification(user_id: str, ntype: str, title: str, body: str,
                           ref_type: str = "", ref_id: str = ""):
    """Create an in-app notification for a user. Best-effort (never raises)."""
    if not user_id:
        return
    try:
        await db.notifications.insert_one({
            "notif_id": new_id("ntf"), "user_id": user_id, "type": ntype,
            "title": title, "body": body, "ref_type": ref_type, "ref_id": ref_id,
            "read": False, "created_at": now_utc().isoformat(),
        })
    except Exception:
        pass


@router.get("/notifications")
async def list_notifications(user=Depends(get_current_user)):
    items = await db.notifications.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = await db.notifications.count_documents({"user_id": user["user_id"], "read": False})
    return {"items": items, "unread": unread}


@router.get("/notifications/unread-count")
async def unread_count(user=Depends(get_current_user)):
    return {"unread": await db.notifications.count_documents({"user_id": user["user_id"], "read": False})}


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user=Depends(get_current_user)):
    await db.notifications.update_one({"notif_id": notif_id, "user_id": user["user_id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}
