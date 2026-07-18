from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id
from deps import get_current_user
from models import WalletIn, PaymentIn, PaymentMethodIn, BankAccountIn, CryptoWalletIn

router = APIRouter()

ALLOWED_TOKENS = {"BTC", "USDT_TRC20", "USDC_ERC20", "USDT_ERC20", "XRP"}


@router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    txs = await db.transactions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"balance": round(user.get("wallet_balance", 0), 2), "transactions": txs,
            "payment_method": user.get("payment_method"), "bank_account": user.get("bank_account"),
            "crypto_wallets": user.get("crypto_wallets", []), "mock": True}


@router.post("/wallet/add")
async def add_funds(body: WalletIn, user=Depends(get_current_user)):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    new_balance = round(user.get("wallet_balance", 0) + body.amount, 2)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    await db.transactions.insert_one({"tx_id": new_id("tx"), "user_id": user["user_id"], "type": "topup",
                                      "label": "Wallet top-up (simulated)", "amount": body.amount, "created_at": now_utc().isoformat()})
    return {"balance": new_balance}


@router.put("/wallet/payment-method")
async def set_payment_method(body: PaymentMethodIn, user=Depends(get_current_user)):
    pm = body.dict()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"payment_method": pm}})
    return {"payment_method": pm}


@router.put("/wallet/bank-account")
async def set_bank_account(body: BankAccountIn, user=Depends(get_current_user)):
    masked = body.iban[-6:].rjust(len(body.iban), "*") if len(body.iban) > 6 else body.iban
    ba = {"account_holder": body.account_holder, "iban": masked}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"bank_account": ba}})
    return {"bank_account": ba}


@router.put("/wallet/crypto-wallet")
async def set_crypto_wallet(body: CryptoWalletIn, user=Depends(get_current_user)):
    if body.token not in ALLOWED_TOKENS:
        raise HTTPException(status_code=400, detail="invalid_token")
    wallets = [w for w in user.get("crypto_wallets", []) if w.get("token") != body.token]
    if body.address.strip():
        wallets.append({"token": body.token, "address": body.address.strip()})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"crypto_wallets": wallets}})
    return {"crypto_wallets": wallets}


@router.post("/payments")
async def make_payment(body: PaymentIn, user=Depends(get_current_user)):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    balance = user.get("wallet_balance", 0)
    if body.amount > balance:
        raise HTTPException(status_code=400, detail="insufficient_funds")
    new_balance = round(balance - body.amount, 2)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    tx = {"tx_id": new_id("tx"), "user_id": user["user_id"], "type": "payment", "service_id": body.service_id,
          "label": body.label, "amount": -body.amount, "answers": body.answers, "created_at": now_utc().isoformat()}
    await db.transactions.insert_one(tx)
    await db.service_requests.insert_one({"request_id": new_id("req"), "user_id": user["user_id"], "kind": "payment",
                                          "category_id": body.service_id, "label": body.label, "amount": body.amount,
                                          "answers": body.answers, "status": "completed", "created_at": now_utc().isoformat()})
    return {"balance": new_balance, "tx": {k: v for k, v in tx.items() if k != "_id"}}


@router.get("/requests")
async def list_requests(user=Depends(get_current_user)):
    reqs = await db.service_requests.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    missions = await db.missions.find({"customer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"payments": [r for r in reqs if r.get("kind") == "payment"], "missions": missions}
