"""BLOCCO 4 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent (non un
semplice re-platforming: il modello dati storico è diverso da quello
Emergent, vedi sotto).

Modello dati (già esistente nello schema Postgres storico, non creato in
questo blocco — vedi piano di migrazione, sezione 4.5/4.6):

  public.claims    — un cliente segnala un problema su una missione
                      (`phase`: in che fase della missione è successo;
                      `reason`/`description`: testo libero, non più un
                      `reason_code` chiuso come nel modello Emergent — vedi
                      GET /claims/reason-suggestions per suggerimenti non
                      vincolanti). Stati: open -> under_review/escalated/
                      dismissed/resolved_without_dispute/resolved_via_dispute.
  public.disputes  — una vera contestazione formale (mission_id UNIQUE: una
                      sola alla volta per missione), nata direttamente
                      dall'admin o per escalation di un claim. Contiene la
                      raccomandazione AI (colonna `ai_recommendation`,
                      aggiunta in questo blocco) e la decisione finale admin.
                      Stati: open -> under_review -> resolved_client/
                      resolved_provider/cancelled.

A differenza del sistema Emergent, qui NON esiste un log messaggi annidato
nella dispute: la discussione cliente<->fornitore usa la stessa
public.messages per-missione già scritta in routers/chat.py (POST/GET
/chat/{mission_id}) — un unico canale invece di duplicarne uno apposito per
le dispute.

Risoluzione economica (fatta con i primitivi Stripe di Blocco 3, vedi
stripe_pg.py/richieste.py per il pattern "chiama la RPC escrow una sola
volta per missione anche con più hold"): binaria, a favore del cliente
(refund_escrow) o del fornitore (release_escrow) — non esiste nello schema
un concetto di rimborso parziale per una missione già finalizzata (l'enum
`dispute_status` stesso è resolved_client/resolved_provider, niente di
intermedio), quindi non lo si inventa qui. Funziona SOLO per il binario
Stripe (impresa/piva): l'informazione su quanto è stato registrato nel
Libretto Famiglia (persona_lf) vive in missions.brief_answers, che è
specifico di ogni verticale e non leggibile in modo generico da qui — se una
missione persona_lf finisce in dispute, l'eventuale storno del registro LF
resta un'azione amministrativa manuale (segnalato nella risposta di
admin_resolve_dispute quando succede).
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import stripe_pg as SP
from core_pg import db, now_iso, notify, record_trust_event, record_client_trust_event
from deps_pg import get_current_user, require_admin
from dispute_ai import ai_analyze, REASON_CODES

router = APIRouter()

CLAIM_PHASES = ("pre_execution", "during_execution", "post_execution_unpaid", "post_execution_paid")


class ClaimCreate(BaseModel):
    mission_id: str
    phase: str
    reason: str
    description: str = ""


class AdminResolveIn(BaseModel):
    decision: str          # "client" | "provider"
    resolution_notes: str = ""


class AdminClaimResolveIn(BaseModel):
    outcome: str            # "dismiss" | "resolve_client" | "resolve_provider" | "resolve_no_action"
    resolution_notes: str = ""


# ---------------- helpers ----------------
def _load_mission(mission_id: str) -> dict:
    res = db.table("missions").select("*").eq("id", mission_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="mission_not_found")
    return res.data[0]


def _apply_money_resolution(mission: dict, favor: str) -> dict:
    """favor: "client" (refund) | "provider" (release). Opera solo sugli hold
    Stripe reali in public.payments (type=escrow_hold, status=held) — vedi
    docstring del modulo per il binario persona_lf (non gestito qui)."""
    mission_id = mission["id"]
    held = (
        db.table("payments").select("*")
        .eq("mission_id", mission_id).eq("type", "escrow_hold").eq("status", "held").execute()
    ).data or []

    if not held:
        return {"gateway_action": "none", "note": "Nessun hold Stripe attivo (missione già saldata, "
                "annullata, o binario Libretto Famiglia — in quest'ultimo caso l'eventuale storno del "
                "registro LF va fatto manualmente)."}

    if favor == "provider":
        prov = db.table("profiles_provider").select("stripe_connect_account_id") \
            .eq("user_id", mission["provider_id"]).limit(1).execute()
        acct_id = prov.data[0].get("stripe_connect_account_id") if prov.data else None
        if not acct_id:
            return {"gateway_action": "failed", "note": "Provider senza stripe_connect_account_id: "
                    "release non eseguita, richiede intervento manuale."}
        payout = float(mission.get("provider_payout") or 0)
        transfer = SP.transfer_to_provider(acct_id, payout, {"mission_id": mission_id, "reason": "dispute_resolution"})
        db.rpc("release_escrow", {
            "p_mission_id": mission_id, "p_gateway_transaction_id": transfer["transfer_id"],
            "p_gateway_response": {}, "p_gateway_name": "stripe",
        }).execute()
        return {"gateway_action": "released", "transfer_id": transfer["transfer_id"]}

    # favor == "client"
    refund_ids = []
    for h in held:
        pi = (h.get("metadata") or {}).get("gateway_transaction_id")
        if not pi:
            continue
        refund_ids.append(SP.refund_payment_intent(pi)["refund_id"])
    if not refund_ids:
        return {"gateway_action": "failed", "note": "Hold trovati ma senza gateway_transaction_id in metadata: "
                "refund non eseguito, richiede intervento manuale."}
    db.rpc("refund_escrow", {
        "p_mission_id": mission_id, "p_reason": "dispute_resolution",
        "p_gateway_transaction_id": refund_ids[-1], "p_gateway_response": {"refund_ids": refund_ids},
        "p_gateway_name": "stripe",
    }).execute()
    return {"gateway_action": "refunded", "refund_ids": refund_ids}


def _record_trust_effect(mission: dict, favor: str, delta_provider: float, delta_client: float, notes: str) -> None:
    event = "dispute_won" if favor == "provider" else "dispute_lost"
    client_event = "dispute_won" if favor == "client" else "dispute_lost"
    if mission.get("provider_id"):
        record_trust_event(mission["provider_id"], event, delta_provider, dimension="cancellation", notes=notes)
    record_client_trust_event(mission["client_id"], client_event, delta_client, dimension="payment_punctuality", notes=notes)


# ---------------- claims (cliente) ----------------
@router.get("/claims/reason-suggestions")
async def reason_suggestions():
    """Suggerimenti non vincolanti per il form claim lato app — `claims.reason`
    resta testo libero (vedi docstring modulo)."""
    return [{"code": c, "label": m} for c, m in REASON_CODES.items()]


@router.post("/claims")
async def create_claim(body: ClaimCreate, user=Depends(get_current_user)):
    if body.phase not in CLAIM_PHASES:
        raise HTTPException(status_code=400, detail="invalid_phase")
    mission = _load_mission(body.mission_id)
    if mission["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    existing = (
        db.table("claims").select("id")
        .eq("mission_id", body.mission_id).in_("status", ["open", "under_review", "escalated"])
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=400, detail="claim_already_open")

    ins = db.table("claims").insert({
        "mission_id": body.mission_id, "client_id": user["id"], "phase": body.phase,
        "reason": body.reason, "description": body.description,
    }).execute()
    claim = ins.data[0] if ins.data else None

    if mission.get("provider_id"):
        await notify(mission["provider_id"], "claim_opened", "Nuova segnalazione",
                    f"Un cliente ha segnalato un problema: {body.reason[:120]}", "mission", body.mission_id)
    return claim


@router.get("/claims")
async def my_claims(user=Depends(get_current_user)):
    uid = user["id"]
    mine = db.table("claims").select("*").eq("client_id", uid).order("created_at", desc=True).execute().data or []
    my_missions = db.table("missions").select("id").eq("provider_id", uid).execute().data or []
    mids = [m["id"] for m in my_missions]
    against_me = []
    if mids:
        against_me = (
            db.table("claims").select("*").in_("mission_id", mids)
            .order("created_at", desc=True).execute().data or []
        )
    seen = {c["id"] for c in mine}
    return mine + [c for c in against_me if c["id"] not in seen]


@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str, user=Depends(get_current_user)):
    res = db.table("claims").select("*").eq("id", claim_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    claim = res.data[0]
    mission = _load_mission(claim["mission_id"])
    if user["id"] not in (claim["client_id"], mission.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    return claim


@router.post("/claims/{claim_id}/escalate")
async def escalate_claim(claim_id: str, user=Depends(get_current_user)):
    """Il cliente o il fornitore coinvolto chiede l'intervento di un admin —
    apre una vera dispute (se non già presente) e ci gira sopra l'AI per una
    prima raccomandazione non vincolante."""
    res = db.table("claims").select("*").eq("id", claim_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    claim = res.data[0]
    mission = _load_mission(claim["mission_id"])
    if user["id"] not in (claim["client_id"], mission.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    if claim["status"] in ("dismissed", "resolved_without_dispute", "resolved_via_dispute"):
        raise HTTPException(status_code=400, detail="already_closed")

    existing_dispute = db.table("disputes").select("*").eq("mission_id", claim["mission_id"]).limit(1).execute()
    if existing_dispute.data:
        dispute = existing_dispute.data[0]
    else:
        ins = db.table("disputes").insert({
            "mission_id": claim["mission_id"], "opened_by": user["id"],
            "reason": claim["reason"], "evidence_urls": [], "claim_id": claim_id,
        }).execute()
        dispute = ins.data[0]
        db.table("missions").update({"status": "disputed"}).eq("id", claim["mission_id"]).execute()
        rec = await ai_analyze(dispute, mission)
        db.table("disputes").update({"ai_recommendation": rec}).eq("id", dispute["id"]).execute()
        dispute["ai_recommendation"] = rec

    db.table("claims").update({"status": "escalated", "dispute_id": dispute["id"]}).eq("id", claim_id).execute()

    for uid in (claim["client_id"], mission.get("provider_id")):
        await notify(uid, "claim_escalated", "Contestazione aperta",
                    "La segnalazione è stata escalata a una contestazione formale, in revisione da JOBBY.",
                    "mission", claim["mission_id"])
    return dispute


# ---------------- disputes (lettura) ----------------
@router.get("/disputes")
async def my_disputes(user=Depends(get_current_user)):
    uid = user["id"]
    opened = db.table("disputes").select("*").eq("opened_by", uid).order("created_at", desc=True).execute().data or []
    my_missions = (
        db.table("missions").select("id").or_(f"client_id.eq.{uid},provider_id.eq.{uid}").execute().data or []
    )
    mids = [m["id"] for m in my_missions]
    others = []
    if mids:
        others = db.table("disputes").select("*").in_("mission_id", mids).order("created_at", desc=True).execute().data or []
    seen = {d["id"] for d in opened}
    return opened + [d for d in others if d["id"] not in seen]


@router.get("/disputes/{dispute_id}")
async def get_dispute(dispute_id: str, user=Depends(get_current_user)):
    res = db.table("disputes").select("*").eq("id", dispute_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    dispute = res.data[0]
    mission = _load_mission(dispute["mission_id"])
    if user["id"] not in (dispute["opened_by"], mission["client_id"], mission.get("provider_id")):
        raise HTTPException(status_code=403, detail="forbidden")
    return dispute


# ---------------- admin ----------------
@router.get("/admin/claims")
async def admin_list_claims(_=Depends(require_admin)):
    return db.table("claims").select("*").order("created_at", desc=True).limit(200).execute().data or []


@router.post("/admin/claims/{claim_id}/resolve")
async def admin_resolve_claim(claim_id: str, body: AdminClaimResolveIn, admin=Depends(require_admin)):
    """Chiusura di un claim SENZA passare da una dispute formale (es. caso
    semplice, o il claim viene respinto). Se outcome è resolve_client/
    resolve_provider viene comunque applicata l'azione economica (stessa
    logica binaria di admin_resolve_dispute)."""
    if body.outcome not in ("dismiss", "resolve_client", "resolve_provider", "resolve_no_action"):
        raise HTTPException(status_code=400, detail="invalid_outcome")
    res = db.table("claims").select("*").eq("id", claim_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    claim = res.data[0]
    if claim["status"] in ("dismissed", "resolved_without_dispute", "resolved_via_dispute"):
        raise HTTPException(status_code=400, detail="already_closed")
    mission = _load_mission(claim["mission_id"])

    money = {"gateway_action": "none"}
    new_status = "dismissed" if body.outcome == "dismiss" else "resolved_without_dispute"
    if body.outcome in ("resolve_client", "resolve_provider"):
        favor = "client" if body.outcome == "resolve_client" else "provider"
        money = _apply_money_resolution(mission, favor)
        _record_trust_effect(mission, favor, delta_provider=-6 if favor == "client" else 2,
                             delta_client=-4 if favor == "provider" else 1,
                             notes=f"Claim {claim_id} risolto senza dispute formale: {body.resolution_notes}"[:500])

    db.table("claims").update({
        "status": new_status, "reviewed_by": admin["id"], "reviewed_at": now_iso(),
        "resolution_notes": body.resolution_notes,
    }).eq("id", claim_id).execute()

    for uid in (claim["client_id"], mission.get("provider_id")):
        await notify(uid, "claim_resolved", "Segnalazione chiusa",
                    f"Esito: {body.outcome.replace('_', ' ')}.", "mission", claim["mission_id"])
    return {"status": new_status, "money": money}


@router.get("/admin/disputes")
async def admin_list_disputes(_=Depends(require_admin)):
    return db.table("disputes").select("*").order("created_at", desc=True).limit(200).execute().data or []


@router.post("/admin/disputes/{dispute_id}/resolve")
async def admin_resolve_dispute(dispute_id: str, body: AdminResolveIn, admin=Depends(require_admin)):
    if body.decision not in ("client", "provider"):
        raise HTTPException(status_code=400, detail="invalid_decision")
    res = db.table("disputes").select("*").eq("id", dispute_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    dispute = res.data[0]
    if dispute["status"] in ("resolved_client", "resolved_provider", "cancelled"):
        raise HTTPException(status_code=400, detail="already_resolved")
    mission = _load_mission(dispute["mission_id"])

    money = _apply_money_resolution(mission, body.decision)

    # Bug noto nel sistema storico (vedi piano di migrazione, sezione 4.6):
    # status e resolution finivano impostati allo stesso valore. Qui restano
    # distinti apposta: `status` è l'enum chiuso, `resolution` è una frase
    # leggibile per l'audit/il frontend.
    status = "resolved_client" if body.decision == "client" else "resolved_provider"
    resolution = ("Rimborso al cliente" if body.decision == "client" else "Pagamento confermato al fornitore") \
        + (f" — {body.resolution_notes}" if body.resolution_notes else "")
    db.table("disputes").update({
        "status": status, "resolution": resolution, "resolution_notes": body.resolution_notes,
        "resolved_by": admin["id"], "resolved_at": now_iso(),
    }).eq("id", dispute_id).execute()

    if dispute.get("claim_id"):
        db.table("claims").update({
            "status": "resolved_via_dispute", "reviewed_by": admin["id"], "reviewed_at": now_iso(),
            "resolution_notes": body.resolution_notes,
        }).eq("id", dispute["claim_id"]).execute()

    _record_trust_effect(mission, body.decision, delta_provider=-8 if body.decision == "client" else 3,
                         delta_client=-5 if body.decision == "provider" else 2,
                         notes=f"Dispute {dispute_id} risolta da admin: {resolution}"[:500])

    for uid in (mission["client_id"], mission.get("provider_id")):
        await notify(uid, "dispute_resolved", "Contestazione risolta",
                    f"Decisione JOBBY: {resolution}", "mission", dispute["mission_id"])
    return {"status": status, "resolution": resolution, "money": money}
