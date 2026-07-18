from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id
from deps import get_current_user
from models import MessageIn

router = APIRouter()


async def ensure_conversation(user_id, other_id, other_name, other_picture=""):
    convo = await db.conversations.find_one({"user_id": user_id, "other_id": other_id}, {"_id": 0})
    if convo:
        return convo["conversation_id"]
    cid = new_id("conv")
    await db.conversations.insert_one({"conversation_id": cid, "user_id": user_id, "other_id": other_id,
                                       "other_name": other_name, "other_picture": other_picture,
                                       "last_message": "", "updated_at": now_utc().isoformat()})
    return cid


@router.get("/chat/conversations")
async def conversations(user=Depends(get_current_user)):
    key = "provider_id" if user["role"] in ("provider", "business") else "customer_id"
    bookings = await db.bookings.find({key: user["user_id"]}, {"_id": 0}).to_list(100)
    for b in bookings:
        if user["role"] in ("provider", "business"):
            await ensure_conversation(user["user_id"], b["customer_id"], b["customer_name"], "")
        else:
            await ensure_conversation(user["user_id"], b["provider_id"], b["provider_name"], b.get("provider_picture", ""))
    return await db.conversations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)


@router.get("/chat/{conversation_id}")
async def get_messages(conversation_id: str, user=Depends(get_current_user)):
    convo = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Not found")
    if convo["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    msgs = await db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"conversation": convo, "messages": msgs}


@router.post("/chat/{conversation_id}")
async def send_message(conversation_id: str, body: MessageIn, user=Depends(get_current_user)):
    convo = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Not found")
    if convo["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    msg = {"message_id": new_id("msg"), "conversation_id": conversation_id, "sender_id": user["user_id"],
           "text": body.text, "created_at": now_utc().isoformat()}
    await db.messages.insert_one(msg)
    await db.conversations.update_one({"conversation_id": conversation_id},
                                      {"$set": {"last_message": body.text, "updated_at": now_utc().isoformat()}})
    return {k: v for k, v in msg.items() if k != "_id"}
