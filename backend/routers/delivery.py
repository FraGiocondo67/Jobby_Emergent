"""BLOCCO 10 — endpoint generici (cross-verticale) per la conferma QR/codice
a fine servizio. Vedi delivery_pg.py per il design completo e per il perché
esiste (porting Postgres del vecchio confirm_delivery.py, mai funzionante
su questo deploy perché Mongo-based). Router "dumb": nessuna logica di
dominio qui, solo autorizzazione + delega a delivery_pg."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import delivery_pg as D
from deps_pg import get_current_user

router = APIRouter()


@router.get("/delivery/mine")
async def my_confirmations(user=Depends(get_current_user)):
    """I QR/codici che il cliente deve mostrare ai professionisti (attivi,
    non ancora confermati)."""
    from core_pg import db
    res = (
        db.table("delivery_confirmations").select("*")
        .eq("client_id", user["id"]).eq("released", False)
        .order("created_at", desc=True).limit(50).execute()
    )
    return res.data or []


@router.get("/delivery/ref/{ref_id}")
async def confirmation_for_ref(ref_id: str, user=Depends(get_current_user)):
    conf = D.get_active_confirmation(ref_id)
    if not conf or conf["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    return {"token": conf["token"], "code": conf["code"], "deadline": conf["deadline"],
            "label": conf["label"]}


class TokenIn(BaseModel):
    token: str


class CodeIn(BaseModel):
    ref_id: str
    code: str


@router.post("/delivery/confirm")
async def confirm_by_token(body: TokenIn, user=Depends(get_current_user)):
    """Il professionista ha scansionato il QR del cliente."""
    try:
        return await D.confirm_by_token(body.token, user["id"])
    except ValueError:
        raise HTTPException(status_code=404, detail="not_found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="not_your_delivery")


@router.post("/delivery/confirm-code")
async def confirm_by_code(body: CodeIn, user=Depends(get_current_user)):
    """Il professionista ha digitato a mano il codice a 6 cifre del cliente
    (fallback quando la fotocamera non è disponibile)."""
    try:
        return await D.confirm_by_code(body.ref_id, body.code, user["id"])
    except ValueError as e:
        detail = "invalid_code" if str(e) == "invalid_code" else "not_found"
        raise HTTPException(status_code=400 if detail == "invalid_code" else 404, detail=detail)
    except PermissionError:
        raise HTTPException(status_code=403, detail="not_your_delivery")


@router.get("/delivery/status/{ref_id}")
async def confirmation_status(ref_id: str, user=Depends(get_current_user)):
    """Il professionista fa polling per sapere se il cliente ha confermato."""
    await D.auto_release_expired(ref_id)
    from core_pg import db
    row = db.table("delivery_confirmations").select("*").eq("ref_id", ref_id).order("created_at", desc=True).limit(1).execute()
    if not row.data:
        return {"pending": False}
    conf = row.data[0]
    return {"pending": not conf.get("released"), "verified": conf.get("verified", False),
            "released": conf.get("released", False), "deadline": conf.get("deadline")}
