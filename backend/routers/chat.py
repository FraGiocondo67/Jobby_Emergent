from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id
from deps import get_current_user
from models import MessageIn

router = APIRouter()


def thread_of(a: str, b: str) -> str:
    return "thr_" + "_".join(sorted([a, b]))


async def ensure_conversation(user_id, other_id, other_name, other_picture=""):
    """Ensures the viewer (user_id) has a conversation doc pointing at other_id.
    Conversations are per-viewer, but messages are shared via thread_id so chat is two-way."""
    tid = thread_of(user_id, other_id)
    convo = await db.conversations.find_one({"user_id": user_id, "other_id": other_id}, {"_id": 0})
    if convo:
        if not convo.get("thread_id"):
            await db.conversations.update_one({"conversation_id": convo["conversation_id"]}, {"$set": {"thread_id": tid}})
        return convo["conversation_id"]
    cid = new_id("conv")
    await db.conversations.insert_one({"conversation_id": cid, "thread_id": tid, "user_id": user_id, "other_id": other_id,
                                       "other_name": other_name, "other_picture": other_picture,
                                       "last_message": "", "updated_at": now_utc().isoformat()})
    return cid


async def open_thread(client_id, client_name, business_id, business_name, business_picture="", first_message=""):
    """Creates both sides of a conversation between a client and a provider/business."""
    await ensure_conversation(client_id, business_id, business_name, business_picture)
    await ensure_conversation(business_id, client_id, client_name, "")
    if first_message:
        tid = thread_of(client_id, business_id)
        await db.messages.insert_one({"message_id": new_id("msg"), "thread_id": tid, "sender_id": business_id,
                                      "text": first_message, "created_at": now_utc().isoformat()})
        await db.conversations.update_many({"thread_id": tid},
                                           {"$set": {"last_message": first_message, "updated_at": now_utc().isoformat()}})


@router.get("/chat/conversations")
async def conversations(user=Depends(get_current_user)):
    is_provider = user["role"] in ("provider", "business")
    key = "provider_id" if is_provider else "customer_id"
    bookings = await db.bookings.find({key: user["user_id"]}, {"_id": 0}).to_list(100)
    for b in bookings:
        if is_provider:
            await ensure_conversation(user["user_id"], b["customer_id"], b["customer_name"], "")
        else:
            await ensure_conversation(user["user_id"], b["provider_id"], b["provider_name"], b.get("provider_picture", ""))
    # Confirmed proximity business requests also open a chat thread.
    if user["role"] == "business":
        brs = await db.business_requests.find({"business_id": user["user_id"], "status": "confirmed"}, {"_id": 0}).to_list(100)
        for r in brs:
            await ensure_conversation(user["user_id"], r["client_id"], r["client_name"], "")
    else:
        brs = await db.business_requests.find({"client_id": user["user_id"], "status": "confirmed"}, {"_id": 0}).to_list(100)
        for r in brs:
            await ensure_conversation(user["user_id"], r["business_id"], r["business_name"], "")
    return await db.conversations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)


@router.get("/chat/{conversation_id}")
async def get_messages(conversation_id: str, user=Depends(get_current_user)):
    convo = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Not found")
    if convo["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    tid = convo.get("thread_id") or thread_of(convo["user_id"], convo["other_id"])
    msgs = await db.messages.find({"thread_id": tid}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"conversation": convo, "messages": msgs}


@router.post("/chat/{conversation_id}")
async def send_message(conversation_id: str, body: MessageIn, user=Depends(get_current_user)):
    convo = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not convo:
        raise HTTPException(status_code=404, detail="Not found")
    if convo["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    tid = convo.get("thread_id") or thread_of(convo["user_id"], convo["other_id"])
    # Make sure the recipient also has a conversation doc for this thread.
    await ensure_conversation(convo["other_id"], user["user_id"], user["name"], user.get("picture", ""))
    msg = {"message_id": new_id("msg"), "thread_id": tid, "conversation_id": conversation_id,
           "sender_id": user["user_id"], "text": body.text, "created_at": now_utc().isoformat()}
    await db.messages.insert_one(msg)
    await db.conversations.update_many({"thread_id": tid},
                                       {"$set": {"last_message": body.text, "updated_at": now_utc().isoformat()}})
    return {k: v for k, v in msg.items() if k != "_id"}
