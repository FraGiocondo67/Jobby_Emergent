"""Spec 4 — Cancellazioni a scaglioni, no-show, recensioni, punteggio privato cliente, affidabilità.
Motore generico sul collection condiviso db.richieste (Pulizie/Babysitting/Driver/Artigiani)."""
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, now_utc
from deps import get_current_user, require_admin
from routers.notifications import push_notification
import richieste_config as C

router = APIRouter()


async def spec4_config() -> dict:
    s = await db.settings.find_one({"key": "spec4_config"})
    cfg = dict(C.SPEC4_DEFAULTS)
    if s and isinstance(s.get("value"), dict):
        cfg.update(s["value"])
    return cfg


def _service_dt(r: dict) -> Optional[datetime]:
    do = r.get("data_ora") or ""
    if not do:
        return None
    try:
        if "T" in do:
            return datetime.fromisoformat(do.replace("Z", ""))
        d = datetime.fromisoformat(do[:10])
        fascia = (r.get("config") or {}).get("fascia_oraria") or r.get("fascia_oraria") or "mattina"
        return d.replace(hour=C.FASCIA_START_HOUR.get(fascia, 9))
    except Exception:
        return None


def _hours_until(r: dict) -> Optional[float]:
    dt = _service_dt(r)
    if not dt:
        return None
    return (dt - datetime.now()).total_seconds() / 3600.0


async def _wallet_credit(user_id: str, amount: float):
    if amount <= 0:
        return
    await db.users.update_one({"user_id": user_id}, {"$inc": {"wallet_balance": round(amount, 2)}})


async def _add_reliability_event(user_id: str, kind: str, rid: str, role: str):
    """kind: cancel_late | no_show | provider_cancel | provider_no_show"""
    await db.users.update_one({"user_id": user_id}, {"$push": {"reliability_events": {
        "kind": kind, "richiesta_id": rid, "role": role, "at": now_utc().isoformat()}}})


async def _count_client_strikes(user_id: str, window_days: int) -> int:
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "reliability_events": 1})
    if not u:
        return 0
    cutoff = now_utc() - timedelta(days=window_days)
    n = 0
    for e in (u.get("reliability_events") or []):
        if e.get("role") != "client" or e.get("kind") not in ("cancel_late", "no_show"):
            continue
        try:
            if datetime.fromisoformat(e["at"].replace("Z", "")) >= cutoff.replace(tzinfo=None):
                n += 1
        except Exception:
            n += 1
    return n


async def _admin_alert(kind: str, rid: str, detail: str):
    await db.admin_alerts.insert_one({"kind": kind, "richiesta_id": rid, "detail": detail,
                                      "resolved": False, "at": now_utc().isoformat()})


# ==================== FASE A — cancellazioni / no-show ====================
@router.get("/richieste/{rid}/cancel-policy")
async def cancel_policy(rid: str, user=Depends(get_current_user)):
    """Testo regole + tier corrente da mostrare PRIMA della conferma / al momento della cancellazione."""
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "not_found")
    cfg = await spec4_config()
    h = _hours_until(r)
    binario = r.get("binario", "impresa")
    dt = _service_dt(r)
    free_label = dt.strftime("%d/%m %H:%M") if dt else "—"
    if binario == "persona_lf":
        tier = "free" if (h is None or h >= cfg["lf_free_hours"]) else "lf_late"
    elif h is None or h >= cfg["cancel_free_hours"]:
        tier = "free"
    elif h >= cfg["cancel_fee_only_hours"]:
        tier = "fee_only"
    else:
        tier = "late"
    return {"tier": tier, "hours_until": round(h, 1) if h is not None else None,
            "binario": binario, "free_until": free_label, "config": cfg}


class CancelIn(BaseModel):
    reason: str = ""


@router.post("/richieste/{rid}/cancel")
async def client_cancel(rid: str, body: CancelIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(404, "not_found")
    if r["stato"] in ("completata", "recensita", "annullata"):
        raise HTTPException(400, "already_done")
    cfg = await spec4_config()
    h = _hours_until(r)
    binario = r.get("binario", "impresa")
    provider_id = r.get("provider_scelto")
    pl = r.get("pagamento_lavoro") or {}
    pf = r.get("pagamento_fee") or {}
    fee_amt = float(pf.get("importo", 0) or 0)
    labor_amt = float(pl.get("importo", 0) or r.get("prezzo_finale", 0) or 0)
    result = {"refund_client": 0.0, "withheld_fee": 0.0, "indennizzo_provider": 0.0, "strike": False, "tier": ""}

    if binario == "persona_lf":
        # libera i voucher committati al borsellino (prestazione non svolta)
        nominale = float((r.get("config") or {}).get("lf_nominale", 0) or pl.get("nominale", 0) or 0)
        if nominale:
            await db.users.update_one({"user_id": r["cliente_id"]}, {"$inc": {"lf_borsellino": nominale}})
        if h is not None and h < cfg["lf_free_hours"]:
            result.update({"tier": "lf_late", "withheld_fee": fee_amt, "strike": True})
            await _add_reliability_event(r["cliente_id"], "cancel_late", rid, "client")
            if provider_id:
                await db.users.update_one({"user_id": provider_id}, {"$set": {"rematch_priority_at": now_utc().isoformat()}})
        else:
            result.update({"tier": "free", "refund_client": fee_amt})
            await _wallet_credit(r["cliente_id"], fee_amt)
    else:
        if h is None or h >= cfg["cancel_free_hours"]:
            result.update({"tier": "free", "refund_client": round(fee_amt + labor_amt, 2)})
            await _wallet_credit(r["cliente_id"], fee_amt + labor_amt)
        elif h >= cfg["cancel_fee_only_hours"]:
            result.update({"tier": "fee_only", "withheld_fee": fee_amt, "refund_client": labor_amt})
            await _wallet_credit(r["cliente_id"], labor_amt)
        else:
            indennizzo = round(labor_amt * float(cfg["cancel_late_labor_pct"]) / 100.0, 2)
            result.update({"tier": "late", "withheld_fee": fee_amt, "indennizzo_provider": indennizzo,
                           "refund_client": round(labor_amt - indennizzo, 2), "strike": True})
            await _wallet_credit(r["cliente_id"], labor_amt - indennizzo)
            if provider_id:
                await _wallet_credit(provider_id, indennizzo)
            await _add_reliability_event(r["cliente_id"], "cancel_late", rid, "client")

    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {
        "stato": "annullata", "cancellazione": {"by": "client", "reason": body.reason, **result,
                                                 "at": now_utc().isoformat()},
        "updated_at": now_utc().isoformat()}})
    if provider_id:
        await push_notification(provider_id, "richiesta_annullata", "Prenotazione annullata",
                                f"Il cliente ha annullato. {'Indennizzo €%.2f accreditato.' % result['indennizzo_provider'] if result['indennizzo_provider'] else ''}",
                                r.get("categoria", "richiesta"), rid)
    if result["strike"]:
        n = await _count_client_strikes(r["cliente_id"], cfg["client_strike_window_days"])
        if n >= cfg["client_strike_threshold"]:
            await _admin_alert("client_strikes", rid, f"Cliente {r['cliente_id']} ha {n} strike in {cfg['client_strike_window_days']}g")
    return result


@router.post("/richieste/{rid}/provider-cancel")
async def provider_cancel(rid: str, body: CancelIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(404, "not_found")
    if r["stato"] in ("completata", "recensita", "annullata"):
        raise HTTPException(400, "already_done")
    pl = r.get("pagamento_lavoro") or {}
    pf = r.get("pagamento_fee") or {}
    refund = round(float(pf.get("importo", 0) or 0) + float(pl.get("importo", 0) or 0), 2)
    binario = r.get("binario", "impresa")
    if binario == "persona_lf":
        nominale = float((r.get("config") or {}).get("lf_nominale", 0) or 0)
        if nominale:
            await db.users.update_one({"user_id": r["cliente_id"]}, {"$inc": {"lf_borsellino": nominale}})
        refund = float(pf.get("importo", 0) or 0)
    await _wallet_credit(r["cliente_id"], refund)
    await _add_reliability_event(user["user_id"], "provider_cancel", rid, "provider")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {
        "stato": "in_matching", "provider_scelto": None,
        "cancellazione": {"by": "provider", "reason": body.reason, "refund_client": refund, "at": now_utc().isoformat()},
        "risostituzione": True, "updated_at": now_utc().isoformat()}})
    await _admin_alert("provider_cancel", rid, f"Provider {user['user_id']} ha cancellato — avvia risostituzione")
    await push_notification(r["cliente_id"], "provider_annulla", "L'operatore ha dovuto cancellare",
                            "Ti abbiamo già rimborsato e stiamo cercando un sostituto: ti aggiorniamo entro poche ore.",
                            r.get("categoria", "richiesta"), rid)
    return {"refund_client": refund, "risostituzione": True}


class NoShowIn(BaseModel):
    against: str  # "client" | "provider"


@router.post("/richieste/{rid}/no-show")
async def report_no_show(rid: str, body: NoShowIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "not_found")
    uid = user["user_id"]
    if uid not in (r.get("cliente_id"), r.get("provider_scelto")):
        raise HTTPException(403, "not_party")
    cfg = await spec4_config()
    h = _hours_until(r)
    if h is not None and h > -(cfg["noshow_grace_min"] / 60.0):
        raise HTTPException(400, "too_early")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {
        "no_show": {"against": body.against, "reported_by": uid, "verified": False, "at": now_utc().isoformat()},
        "updated_at": now_utc().isoformat()}})
    await _admin_alert("no_show", rid, f"No-show segnalato contro {body.against} (da {uid}) — verifica telefonica")
    return {"reported": True, "against": body.against, "note": "admin_will_verify"}


class DelayIn(BaseModel):
    minutes: int


@router.post("/richieste/{rid}/report-delay")
async def report_delay(rid: str, body: DelayIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(404, "not_found")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {
        "ritardo": {"minutes": body.minutes, "accepted": False, "at": now_utc().isoformat()}}})
    await push_notification(r["cliente_id"], "ritardo", "Lieve ritardo",
                            f"L'operatore arriverà con ~{body.minutes} min di ritardo. Accetti lo slittamento?",
                            r.get("categoria", "richiesta"), rid)
    return {"ok": True}


# --- pausa ricorrenza ---
@router.post("/richieste/{rid}/pause")
async def pause_recurrence(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(404, "not_found")
    if r.get("ricorrenza", "una_tantum") == "una_tantum":
        raise HTTPException(400, "not_recurring")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"ricorrenza_pausa": True, "updated_at": now_utc().isoformat()}})
    if r.get("provider_scelto"):
        await push_notification(r["provider_scelto"], "ricorrenza_pausa", "Ricorrenza in pausa",
                                "Il cliente ha messo in pausa la ricorrenza; la relazione resta attiva.", r.get("categoria", "richiesta"), rid)
    return {"paused": True}


@router.post("/richieste/{rid}/resume")
async def resume_recurrence(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(404, "not_found")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"ricorrenza_pausa": False, "updated_at": now_utc().isoformat()}})
    return {"paused": False}


# ==================== FASE B — recensioni ====================
class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/richieste/{rid}/review")
async def create_review(rid: str, body: ReviewIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"]:
        raise HTTPException(404, "not_found")
    if r["stato"] not in ("completata", "recensita"):
        raise HTTPException(400, "not_completed")
    if r.get("recensione"):
        raise HTTPException(400, "already_reviewed")
    cfg = await spec4_config()
    done_at = r.get("completed_at") or r.get("updated_at")
    try:
        if done_at and (datetime.now() - datetime.fromisoformat(done_at.replace("Z", "")[:19])).days > cfg["review_window_days"]:
            raise HTTPException(400, "window_closed")
    except HTTPException:
        raise
    except Exception:
        pass
    rev = {"rating": max(1, min(5, body.rating)), "comment": (body.comment or "").strip(),
           "moderato": False, "hidden": False, "reply": None, "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {
        "recensione": rev, "stato": "recensita", "updated_at": now_utc().isoformat()}})
    if r.get("provider_scelto"):
        await _admin_alert("review_moderation", rid, f"Nuova recensione {rev['rating']}★ da moderare")
    return rev


@router.delete("/richieste/{rid}/review")
async def delete_review(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r["cliente_id"] != user["user_id"] or not r.get("recensione"):
        raise HTTPException(404, "not_found")
    cfg = await spec4_config()
    at = r["recensione"].get("at")
    try:
        if at and (datetime.now() - datetime.fromisoformat(at.replace("Z", "")[:19])).days > cfg["review_window_days"]:
            raise HTTPException(400, "window_closed")
    except HTTPException:
        raise
    except Exception:
        pass
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"recensione": None, "stato": "completata"}})
    return {"deleted": True}


class ReplyIn(BaseModel):
    reply: str


@router.post("/richieste/{rid}/review/reply")
async def reply_review(rid: str, body: ReplyIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"] or not r.get("recensione"):
        raise HTTPException(404, "not_found")
    if r["recensione"].get("reply"):
        raise HTTPException(400, "already_replied")
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {
        "recensione.reply": {"text": (body.reply or "").strip(), "at": now_utc().isoformat()}}})
    return {"ok": True}


@router.get("/providers/{provider_id}/reviews")
async def provider_reviews(provider_id: str):
    cfg = await spec4_config()
    docs = await db.richieste.find({"provider_scelto": provider_id, "recensione": {"$ne": None}},
                                   {"_id": 0, "recensione": 1, "categoria": 1, "data_ora": 1}).to_list(200)
    published = [d for d in docs if d["recensione"].get("moderato") and not d["recensione"].get("hidden")]
    count = len(published)
    reviews = [{"rating": d["recensione"]["rating"], "comment": d["recensione"].get("comment"),
                "reply": d["recensione"].get("reply"), "at": d["recensione"].get("at"),
                "categoria": d.get("categoria")} for d in published]
    reviews.sort(key=lambda x: x.get("at") or "", reverse=True)
    is_new = count < cfg["new_provider_reviews"]
    avg = round(sum(x["rating"] for x in reviews) / count, 2) if count else None
    return {"count": count, "is_new": is_new, "badge": "Nuovo su JOBBY" if is_new else None,
            "average": None if is_new else avg, "reviews": reviews}


# ==================== FASE C — punteggio privato cliente ====================
CLIENT_FLAGS = ["condizioni_diverse", "richieste_fuori_accordo", "comportamento_irrispettoso"]


class ClientRatingIn(BaseModel):
    rating: int
    flags: List[str] = []
    note: str = ""


@router.post("/richieste/{rid}/rate-client")
async def rate_client(rid: str, body: ClientRatingIn, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(404, "not_found")
    if r["stato"] not in ("completata", "recensita"):
        raise HTTPException(400, "not_completed")
    rating = max(1, min(5, body.rating))
    flags = [f for f in body.flags if f in CLIENT_FLAGS]
    entry = {"provider_id": user["user_id"], "richiesta_id": rid, "rating": rating,
             "flags": flags, "note": (body.note or "").strip(), "at": now_utc().isoformat()}
    await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"valutazione_cliente": entry}})
    await db.users.update_one({"user_id": r["cliente_id"]}, {"$push": {"client_private_scores": entry}})
    # alert admin se media bassa ricorrente
    u = await db.users.find_one({"user_id": r["cliente_id"]}, {"_id": 0, "client_private_scores": 1})
    scores = [s["rating"] for s in (u.get("client_private_scores") or [])]
    if len(scores) >= 3 and (sum(scores) / len(scores)) < 2.5:
        await _admin_alert("client_low_score", rid, f"Cliente {r['cliente_id']} media privata {round(sum(scores)/len(scores),1)}")
    return {"ok": True, "flags": flags}


@router.get("/richieste/{rid}/client-rating")
async def get_client_rating(rid: str, user=Depends(get_current_user)):
    r = await db.richieste.find_one({"richiesta_id": rid}, {"_id": 0, "valutazione_cliente": 1, "provider_scelto": 1})
    if not r or r.get("provider_scelto") != user["user_id"]:
        raise HTTPException(404, "not_found")
    return {"valutazione_cliente": r.get("valutazione_cliente"), "flags_available": CLIENT_FLAGS}


# ==================== ADMIN ====================
@router.get("/admin/spec4/config")
async def admin_get_config(_=Depends(require_admin)):
    return await spec4_config()


@router.post("/admin/spec4/config")
async def admin_set_config(body: dict, _=Depends(require_admin)):
    cur = await spec4_config()
    cur.update({k: v for k, v in body.items() if k in C.SPEC4_DEFAULTS})
    await db.settings.update_one({"key": "spec4_config"}, {"$set": {"value": cur}}, upsert=True)
    return cur


@router.get("/admin/spec4/moderation")
async def admin_moderation_queue(_=Depends(require_admin)):
    docs = await db.richieste.find({"recensione": {"$ne": None}, "recensione.moderato": False, "recensione.hidden": {"$ne": True}},
                                   {"_id": 0, "richiesta_id": 1, "recensione": 1, "cliente_nome": 1, "provider_nome": 1, "categoria": 1}).to_list(200)
    return docs


@router.post("/admin/spec4/moderation/{rid}")
async def admin_moderate(rid: str, body: dict, _=Depends(require_admin)):
    action = body.get("action")  # approve | hide
    if action == "approve":
        await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"recensione.moderato": True, "recensione.hidden": False}})
    elif action == "hide":
        await db.richieste.update_one({"richiesta_id": rid}, {"$set": {"recensione.hidden": True, "recensione.moderato": True}})
    else:
        raise HTTPException(400, "bad_action")
    return {"ok": True, "action": action}


@router.get("/admin/spec4/reliability")
async def admin_reliability(_=Depends(require_admin)):
    cfg = await spec4_config()
    users = await db.users.find({"$or": [{"reliability_events": {"$exists": True, "$ne": []}},
                                         {"client_private_scores": {"$exists": True, "$ne": []}}]},
                                {"_id": 0, "user_id": 1, "name": 1, "role": 1, "reliability_events": 1, "client_private_scores": 1}).to_list(500)
    out = []
    for u in users:
        strikes = await _count_client_strikes(u["user_id"], cfg["client_strike_window_days"])
        prov_events = [e for e in (u.get("reliability_events") or []) if e.get("role") == "provider"]
        scores = [s["rating"] for s in (u.get("client_private_scores") or [])]
        out.append({"user_id": u["user_id"], "name": u.get("name"), "role": u.get("role"),
                    "client_strikes": strikes, "over_threshold": strikes >= cfg["client_strike_threshold"],
                    "provider_events": len(prov_events),
                    "private_avg": round(sum(scores) / len(scores), 2) if scores else None,
                    "private_count": len(scores)})
    out.sort(key=lambda x: (-x["client_strikes"], x["private_avg"] or 5))
    return out
