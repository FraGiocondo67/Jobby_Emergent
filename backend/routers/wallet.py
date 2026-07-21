from fastapi import APIRouter, HTTPException, Depends

from core import db, now_utc, new_id
from deps import get_current_user
from models import WalletIn, PaymentIn, PaymentMethodIn, BankAccountIn, CryptoWalletIn, WithdrawIn
from escrow import mature_holds

router = APIRouter()

ALLOWED_TOKENS = {"USDT_TRC", "USDT_ETH", "USDC_ETH", "XRP", "BTC"}


@router.get("/wallet")
async def get_wallet(user=Depends(get_current_user)):
    from confirm_delivery import auto_release_expired
    await auto_release_expired()
    await mature_holds(user["user_id"])
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    txs = await db.transactions.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    holds = await db.wallet_holds.find({"user_id": user["user_id"], "status": "pending"}, {"_id": 0}).sort("release_at", 1).to_list(100)
    available = round(u.get("wallet_balance", 0), 2)
    pending = round(u.get("pending_balance", 0), 2)
    return {"balance": available, "available_balance": available, "pending_balance": pending,
            "total_balance": round(available + pending, 2), "holds": holds, "transactions": txs,
            "payment_method": u.get("payment_method"), "bank_account": u.get("bank_account"),
            "crypto_wallets": u.get("crypto_wallets", []), "paypal_email": u.get("paypal_email", ""), "mock": True}


@router.post("/wallet/withdraw")
async def withdraw_funds(body: WithdrawIn, user=Depends(get_current_user)):
    if body.method not in ("bank", "crypto", "yobpay"):
        raise HTTPException(status_code=400, detail="invalid_method")
    amount = round(float(body.amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    await mature_holds(user["user_id"])
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    available = round(u.get("wallet_balance", 0), 2)
    if amount > available:
        raise HTTPException(status_code=400, detail="insufficient_available")
    # Validate the chosen destination exists.
    dest = ""
    if body.method == "bank":
        if not u.get("bank_account"):
            raise HTTPException(status_code=400, detail="no_bank_account")
        dest = u["bank_account"].get("iban", "IBAN")
    elif body.method == "crypto":
        w = next((c for c in u.get("crypto_wallets", []) if c.get("wallet_id") == body.target_id), None) if body.target_id else (u.get("crypto_wallets") or [None])[0]
        if not w:
            raise HTTPException(status_code=400, detail="no_crypto_wallet")
        dest = f"{w.get('token','')} · {w.get('address','')[:10]}…"
    else:  # yobpay (structure only — real API wired later)
        dest = "YOB PAY card"
    new_balance = round(available - amount, 2)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    payout = {"payout_id": new_id("pyt"), "user_id": user["user_id"], "method": body.method, "destination": dest,
              "amount": amount, "status": "processing" if body.method == "yobpay" else "sent",
              "created_at": now_utc().isoformat()}
    await db.payouts.insert_one(payout)
    await db.transactions.insert_one({"tx_id": new_id("tx"), "user_id": user["user_id"], "type": "withdrawal",
                                      "label": f"Prelievo {body.method} €{amount:.2f}", "amount": -amount,
                                      "status": payout["status"], "created_at": now_utc().isoformat()})
    return {"balance": new_balance, "payout": {k: v for k, v in payout.items() if k != "_id"}}


@router.get("/wallet/payouts")
async def list_payouts(user=Depends(get_current_user)):
    return await db.payouts.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


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
    pm = body.dict(exclude={"cvv"})  # never persist CVV
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
    if not body.address.strip():
        raise HTTPException(status_code=400, detail="address_required")
    wallets = list(user.get("crypto_wallets", []))
    wallets.append({
        "wallet_id": new_id("cw"), "token": body.token,
        "name": body.name.strip() or body.token, "address": body.address.strip(),
        "network": body.network.strip(),
    })
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"crypto_wallets": wallets}})
    return {"crypto_wallets": wallets}


@router.delete("/wallet/crypto-wallet/{wallet_id}")
async def delete_crypto_wallet(wallet_id: str, user=Depends(get_current_user)):
    wallets = [w for w in user.get("crypto_wallets", []) if w.get("wallet_id") != wallet_id]
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
