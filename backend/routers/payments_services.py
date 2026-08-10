"""RITIRATO nel Blocco 7 (migrazione Emergent -> Supabase/Render) — non più
importato/esposto da server.py, su conferma esplicita dell'utente. "Servizi
di pagamento" (ricariche telefoniche/bollette/beneficiari, Mongo-based, mai
collegato ad aggregatori reali) — la nuova categoria "servizi di pagamento"
prevista dal piano resta esplicitamente fuori scope dal Blocco 3 in poi (mai
riscritta su Postgres). File lasciato nel repo come riferimento storico
(Mongo, non funzionante senza MONGO_URL)."""
from fastapi import APIRouter, HTTPException, Depends, Query

from core import db, now_utc, new_id
from deps import get_current_user
from models import BeneficiaryIn, ServicePaymentIn

router = APIRouter()

# ---- Country catalogues (start with Italy). Real aggregator APIs (Aimon/OpenAPI/YOB PAY) wired later. ----
OPERATORS = {
    "IT": [
        {"id": "tim", "name": "TIM"},
        {"id": "vodafone", "name": "Vodafone"},
        {"id": "windtre", "name": "WINDTRE"},
        {"id": "iliad", "name": "Iliad"},
        {"id": "fastweb", "name": "Fastweb Mobile"},
        {"id": "postemobile", "name": "PosteMobile"},
        {"id": "ho", "name": "ho. Mobile"},
        {"id": "kena", "name": "Kena Mobile"},
        {"id": "very", "name": "Very Mobile"},
        {"id": "coopvoce", "name": "CoopVoce"},
    ],
}

BILLERS = {
    "IT": [
        {"id": "enel", "name": "Enel Energia", "type": "luce"},
        {"id": "sen", "name": "Servizio Elettrico Nazionale", "type": "luce"},
        {"id": "eni", "name": "Eni Plenitude", "type": "gas_luce"},
        {"id": "a2a", "name": "A2A Energia", "type": "gas_luce"},
        {"id": "hera", "name": "Hera Comm", "type": "gas_luce"},
        {"id": "iren", "name": "Iren Mercato", "type": "gas_luce"},
        {"id": "acea", "name": "Acea Energia", "type": "luce"},
        {"id": "sorgenia", "name": "Sorgenia", "type": "gas_luce"},
        {"id": "edison", "name": "Edison Energia", "type": "gas_luce"},
        {"id": "italgas", "name": "Italgas", "type": "gas"},
        {"id": "acquedotto", "name": "Acquedotto / Servizio Idrico", "type": "acqua"},
        {"id": "tari", "name": "TARI (Rifiuti)", "type": "rifiuti"},
        {"id": "tim_fisso", "name": "TIM (Telefono/Internet)", "type": "telefono"},
        {"id": "vodafone_fisso", "name": "Vodafone Casa", "type": "telefono"},
    ],
}

# JOBBY commission ("retrocessione") applied per service kind — configurable later.
BENEFIT = {"topup": 0.04, "bill": 0.01, "abroad": 0.01, "local": 0.005}
FIXED_FEE = {"topup": 0.0, "bill": 0.0, "abroad": 2.0, "local": 0.5}

LABELS = {"topup": "Ricarica telefonica", "bill": "Pagamento bolletta",
          "abroad": "Invio denaro estero", "local": "Bonifico SEPA locale"}


@router.get("/payments/options")
async def payment_options(country: str = Query("IT")):
    country = (country or "IT").upper()
    return {"country": country,
            "operators": OPERATORS.get(country, OPERATORS["IT"]),
            "billers": BILLERS.get(country, BILLERS["IT"])}


# ---- Beneficiaries ----
@router.get("/beneficiaries")
async def list_beneficiaries(type: str = Query(None), user=Depends(get_current_user)):
    q = {"user_id": user["user_id"]}
    if type:
        q["type"] = type
    items = await db.beneficiaries.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    return items


@router.post("/beneficiaries")
async def create_beneficiary(body: BeneficiaryIn, user=Depends(get_current_user)):
    if body.type not in ("abroad", "local"):
        raise HTTPException(status_code=400, detail="invalid_type")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name_required")
    if not (body.iban or "").strip():
        raise HTTPException(status_code=400, detail="iban_required")
    doc = {
        "ben_id": new_id("ben"), "user_id": user["user_id"], "name": body.name.strip(),
        "type": body.type, "iban": body.iban.strip(), "swift": (body.swift or "").strip(),
        "bank_name": (body.bank_name or "").strip(), "country": (body.country or "").strip(),
        "note": (body.note or "").strip(), "created_at": now_utc().isoformat(),
    }
    await db.beneficiaries.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.delete("/beneficiaries/{ben_id}")
async def delete_beneficiary(ben_id: str, user=Depends(get_current_user)):
    await db.beneficiaries.delete_one({"ben_id": ben_id, "user_id": user["user_id"]})
    return {"ok": True}


# ---- Execute a service payment (simulated charge) ----
@router.post("/payments/service")
async def execute_service_payment(body: ServicePaymentIn, user=Depends(get_current_user)):
    if body.kind not in ("topup", "bill", "abroad", "local"):
        raise HTTPException(status_code=400, detail="invalid_kind")
    if body.amount is None or body.amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    if body.source not in ("wallet", "card"):
        raise HTTPException(status_code=400, detail="invalid_source")

    meta = {}
    title = LABELS[body.kind]
    if body.kind == "topup":
        op = next((o for o in OPERATORS["IT"] if o["id"] == body.operator_id), None)
        if not op:
            raise HTTPException(status_code=400, detail="operator_required")
        if not (body.phone_number or "").strip():
            raise HTTPException(status_code=400, detail="phone_required")
        meta = {"operator": op["name"], "phone_number": body.phone_number.strip()}
        title = f"Ricarica {op['name']}"
    elif body.kind == "bill":
        bl = next((b for b in BILLERS["IT"] if b["id"] == body.biller_id), None)
        if not bl:
            raise HTTPException(status_code=400, detail="biller_required")
        meta = {"biller": bl["name"], "bill_ref": (body.bill_ref or "").strip()}
        title = f"Bolletta {bl['name']}"
    else:  # abroad / local
        ben = await db.beneficiaries.find_one({"ben_id": body.beneficiary_id, "user_id": user["user_id"]}, {"_id": 0})
        if not ben:
            raise HTTPException(status_code=400, detail="beneficiary_required")
        meta = {"beneficiary": ben["name"], "iban": ben["iban"], "bank_name": ben.get("bank_name", "")}
        title = f"{LABELS[body.kind]} → {ben['name']}"

    amount = round(float(body.amount), 2)
    fee = round(amount * BENEFIT[body.kind] + FIXED_FEE[body.kind], 2)  # JOBBY retrocessione/benefit

    # Charge: from wallet (block if insufficient) or from client's card (must exist).
    if body.source == "wallet":
        balance = user.get("wallet_balance", 0)
        if amount > balance:
            raise HTTPException(status_code=400, detail="insufficient_funds")
        new_balance = round(balance - amount, 2)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"wallet_balance": new_balance}})
    else:  # card (simulated — real PayPal/Stripe charge wired later)
        if not user.get("payment_method"):
            raise HTTPException(status_code=400, detail="no_card")
        new_balance = round(user.get("wallet_balance", 0), 2)

    tx = {
        "tx_id": new_id("tx"), "user_id": user["user_id"], "type": "service", "kind": body.kind,
        "label": title, "amount": -amount, "source": body.source, "jobby_benefit": fee,
        "meta": meta, "note": (body.note or "").strip(), "status": "completed",
        "created_at": now_utc().isoformat(),
    }
    await db.transactions.insert_one(tx)
    return {"balance": new_balance, "transaction": {k: v for k, v in tx.items() if k != "_id"}}


@router.get("/payments/history")
async def payment_history(kind: str = Query("all"), user=Depends(get_current_user)):
    q = {"user_id": user["user_id"], "type": "service"}
    if kind and kind != "all":
        q["kind"] = kind
    items = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items
