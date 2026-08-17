"""BLOCCO 10 (segnalato dall'utente: "il cruscotto Portafoglio non
aggiorna nessun valore", "il TOTALE guadagno... non si aggiorna", e il
modale "usi il libretto anche fuori JOBBY" che si blocca al primo tap).

Causa comune alle tre segnalazioni: GET /wallet/dashboard, GET
/provider/dashboard, POST /wallet/external-usage e POST /provider/dnd
vivevano tutti solo in routers/dashboard.py — RITIRATO nel Blocco 7
(Mongo-based, MONGO_URL non configurato su questo deploy, mai portato a
Postgres) e non più montato su server.py -> 404 sempre. Il frontend
((tabs)/portafoglio.tsx) ignora l'errore in silenzio (try/catch), quindi la
schermata restava sempre vuota/a zero invece di mostrare un errore
esplicito — e il bottone "Salva" del modale "usi il libretto fuori JOBBY"
falliva silenziosamente ad ogni tap (nessun feedback, sembrava un problema
di tastiera/focus ma era il 404 di POST /wallet/external-usage).

Ricostruzione pragmatica su Postgres — NON un porting 1:1 del vecchio
dashboard.py, che presupponeva un'unica collezione Mongo "richieste" con
schema piatto uniforme. Qui i lavori vivono in missions + brief_answers,
con forma diversa per verticale (vedi richieste.py/driver.py/
babysitting.py/artigiani.py). Copre i campi realmente letti dal frontend
usando le colonne reali già scritte in modo affidabile da ogni verticale al
confirm (missions.price_agreed/provider_payout), + il registro Libretto
Famiglia già esistente (lf_pg.py, tabella lf_ledger) per i massimali annui —
non reinventato da zero.

Concetto NON ricostruito perché non esiste più nell'architettura attuale:
il "borsellino" prepagato (caricato/impegnato/spendibile) del vecchio
sistema Mongo — lf_pg.py documenta esplicitamente che i compensi Libretto
Famiglia si muovono fuori JOBBY tramite voucher INPS, mai un vero gateway
di pagamento, quindi non esiste un saldo prepagato reale da mostrare.
show_borsellino resta sempre False (mostra invece la card "impresa/metodo
di pagamento", onesto sui dati che esistono davvero) invece di fingere un
saldo sempre a zero — stesso principio delle altre correzioni di questa
sessione: un dato assente va segnalato, non finto."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core_pg import db
from deps_pg import get_current_user
import richieste_config as C
import lf_pg as LF

router = APIRouter()

_CROSS_CATEGORY_SLUGS = ("housekeeping", "babysitting", "driver", "artigiani")
_SLUG_TO_CAT = {"housekeeping": "pulizie", "babysitting": "babysitting", "driver": "driver", "artigiani": "artigiani"}
ACTIVE_STATI = ("confermata", "in_corso")
DONE_STATI = ("completata", "recensita")


def _year() -> int:
    return date.today().year


def _category_ids() -> list:
    res = db.table("service_categories").select("id, slug").in_("slug", list(_CROSS_CATEGORY_SLUGS)).execute()
    return res.data or []


def _amount_of(row: dict) -> float:
    return float(row.get("provider_payout") or row.get("price_agreed") or 0)


# ---------------- PROVIDER dashboard ----------------
class DndIn(BaseModel):
    dnd: bool


@router.post("/provider/dnd")
async def set_dnd(body: DndIn, user=Depends(get_current_user)):
    prov = db.table("profiles_provider").select("documents").eq("user_id", user["id"]).limit(1).execute()
    documents = ((prov.data[0].get("documents") if prov.data else None) or {})
    documents = dict(documents)
    documents["dnd"] = body.dnd
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user["id"]).execute()
    return {"dnd": body.dnd}


@router.get("/provider/dashboard")
async def provider_dashboard(user=Depends(get_current_user)):
    uid = user["id"]
    cats = _category_ids()
    slug_by_id = {c["id"]: c["slug"] for c in cats}
    cat_ids = list(slug_by_id.keys())

    rows = []
    if cat_ids:
        res = (
            db.table("missions").select("id, category_id, brief_answers, price_agreed, provider_payout, updated_at")
            .in_("category_id", cat_ids).eq("provider_id", uid).execute()
        )
        rows = res.data or []

    items = []
    incoming_total = 0.0
    for row in rows:
        brief = row.get("brief_answers") or {}
        stato = brief.get("stato")
        if stato not in ACTIVE_STATI and stato not in DONE_STATI:
            continue
        amount = _amount_of(row)
        is_lf = brief.get("binario") == "persona_lf"
        settled = stato in DONE_STATI
        items.append({
            "richiesta_id": row["id"], "amount": round(amount, 2),
            "source": "INPS" if is_lf else "impresa", "date": None,
            "stato": "trasferito" if settled else "in_attesa",
            "categoria": _SLUG_TO_CAT.get(slug_by_id.get(row.get("category_id"))),
        })
        if stato in ACTIVE_STATI:
            incoming_total += amount
    items.sort(key=lambda x: x["richiesta_id"], reverse=True)

    # Limiti personali (Libretto Famiglia) — registro reale già in uso da
    # richieste.py/babysitting.py per bloccare le richieste oltre tetto,
    # riletto qui in sola lettura invece di ricalcolare dai brief.
    worker_totals = LF.get_worker_totals(uid)
    year_earned = worker_totals["nominale_used"]
    year_hours = worker_totals["hours_used"]
    ledger_res = db.table("lf_ledger").select("family_id, nominale_used").eq("worker_id", uid).eq("year", _year()).execute()
    per_family: dict = {}
    for r in (ledger_res.data or []):
        fid = r.get("family_id")
        per_family[fid] = per_family.get(fid, 0.0) + float(r.get("nominale_used") or 0)
    max_family_used = max(per_family.values()) if per_family else 0.0

    limiti = {
        "annual_earned": round(year_earned, 2), "annual_ceiling": C.LF_PROVIDER_ANNUAL_EUR,
        "annual_pct": min(1.0, round(year_earned / C.LF_PROVIDER_ANNUAL_EUR, 3)) if C.LF_PROVIDER_ANNUAL_EUR else 0,
        "annual_warn": year_earned >= C.LF_PROVIDER_ANNUAL_EUR * C.LF_WARN_THRESHOLD,
        "hours": round(year_hours, 1), "hours_ceiling": C.LF_PROVIDER_HOURS,
        "hours_pct": min(1.0, round(year_hours / C.LF_PROVIDER_HOURS, 3)) if C.LF_PROVIDER_HOURS else 0,
        "families": len(per_family), "max_family_used": round(max_family_used, 2),
        "family_ceiling": C.LF_COUPLE_CEILING_EUR,
    }

    prov = db.table("profiles_provider").select("trust_score, documents").eq("user_id", uid).limit(1).execute()
    pdata = prov.data[0] if prov.data else {}
    reliability = float(pdata.get("trust_score") or 0)
    dnd = bool((pdata.get("documents") or {}).get("dnd"))

    # Storico (completate/recensite) + eventuale valutazione ricevuta.
    done_rows = [r for r in rows if (r.get("brief_answers") or {}).get("stato") in DONE_STATI]
    done_rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    done_rows = done_rows[:20]
    mission_ids = [r["id"] for r in done_rows]
    reviews_by_mission = {}
    if mission_ids:
        rv = db.table("reviews").select("mission_id, rating").in_("mission_id", mission_ids).execute()
        reviews_by_mission = {r["mission_id"]: r["rating"] for r in (rv.data or [])}
    storico = [{
        "richiesta_id": row["id"], "data_ora": row.get("updated_at"),
        "importo": round(_amount_of(row), 2), "recensione": reviews_by_mission.get(row["id"]),
    } for row in done_rows]

    return {
        "guadagni": {"incoming_total": round(incoming_total, 2), "items": items},
        "limiti": limiti, "reliability": reliability, "dnd": dnd, "storico": storico,
    }


# ---------------- WALLET dashboard (client) ----------------
class ExternalUsageIn(BaseModel):
    amount: float
    provider_name: str = ""


@router.post("/wallet/external-usage")
async def add_external_usage(body: ExternalUsageIn, user=Depends(get_current_user)):
    entry = {"user_id": user["id"], "amount": round(body.amount, 2),
             "provider_name": body.provider_name.strip(), "year": _year()}
    db.table("lf_external_usage").insert(entry).execute()
    return {"ok": True, "entry": entry}


@router.get("/wallet/dashboard")
async def wallet_dashboard(user=Depends(get_current_user)):
    uid = user["id"]
    year = _year()
    cats = _category_ids()
    slug_by_id = {c["id"]: c["slug"] for c in cats}
    cat_ids = list(slug_by_id.keys())

    rows = []
    if cat_ids:
        res = (
            db.table("missions").select("id, category_id, brief_answers, price_agreed, provider_payout, updated_at")
            .in_("category_id", cat_ids).eq("client_id", uid).execute()
        )
        rows = res.data or []

    lf_rows = [r for r in rows if (r.get("brief_answers") or {}).get("binario") == "persona_lf"]
    impresa_rows = [r for r in rows if (r.get("brief_answers") or {}).get("binario") == "impresa"]
    show_borsellino = False  # vedi docstring modulo: nessun saldo prepagato reale in questa architettura.

    # Limiti di legge per collaboratrice — dal registro reale lf_ledger
    # (family_id = questo cliente), non ricalcolato dai brief_answers.
    ledger_res = db.table("lf_ledger").select("worker_id, nominale_used").eq("family_id", uid).eq("year", year).execute()
    ext_res = db.table("lf_external_usage").select("amount, provider_name").eq("user_id", uid).eq("year", year).execute()
    external = ext_res.data or []
    ext_total = round(sum(float(e.get("amount") or 0) for e in external), 2)

    per_collaboratrice = []
    annual_used = ext_total
    worker_ids = sorted({r["worker_id"] for r in (ledger_res.data or []) if r.get("worker_id")})
    names = {}
    if worker_ids:
        u_res = db.table("users").select("id, full_name").in_("id", worker_ids).execute()
        names = {u["id"]: u.get("full_name") for u in (u_res.data or [])}
    for r in (ledger_res.data or []):
        used = float(r.get("nominale_used") or 0)
        annual_used += used
        per_collaboratrice.append({
            "provider_id": r["worker_id"], "nome": names.get(r["worker_id"]) or "Collaboratore",
            "used": round(used, 2), "used_weighted": round(used, 2),
            "ceiling": C.LF_COUPLE_CEILING_EUR, "agevolata": False,
            "pct": min(1.0, round(used / C.LF_COUPLE_CEILING_EUR, 3)) if C.LF_COUPLE_CEILING_EUR else 0,
            "warn": used >= C.LF_COUPLE_CEILING_EUR * C.LF_WARN_THRESHOLD, "upsell": False,
        })
    per_collaboratrice.sort(key=lambda x: -x["used_weighted"])
    annual_used = round(annual_used, 2)

    limiti = {
        "annual_used": annual_used, "annual_ceiling": C.LF_FAMILY_ANNUAL_EUR,
        "annual_pct": min(1.0, round(annual_used / C.LF_FAMILY_ANNUAL_EUR, 3)) if C.LF_FAMILY_ANNUAL_EUR else 0,
        "annual_warn": annual_used >= C.LF_FAMILY_ANNUAL_EUR * C.LF_WARN_THRESHOLD,
        "warn_threshold": C.LF_WARN_THRESHOLD, "per_collaboratrice": per_collaboratrice,
        "external_total": ext_total, "external_usages": external,
    }

    upcoming, documenti = [], []
    for row in rows:
        brief = row.get("brief_answers") or {}
        stato = brief.get("stato")
        amount = _amount_of(row)
        if stato in ACTIVE_STATI:
            upcoming.append({
                "richiesta_id": row["id"], "data_ora": row.get("updated_at"), "binario": brief.get("binario"),
                "voucher": int(amount / 10) if brief.get("binario") == "persona_lf" else 0, "importo": amount,
            })
        elif stato in DONE_STATI:
            documenti.append({
                "richiesta_id": row["id"], "data_ora": row.get("updated_at"), "binario": brief.get("binario"),
                "importo": amount, "stato": stato,
            })
    upcoming.sort(key=lambda x: x.get("data_ora") or "")
    documenti.sort(key=lambda x: x.get("data_ora") or "", reverse=True)

    # Stima recupero fiscale (contributi Libretto deducibili, ~1.65€/voucher da 10€ nominali).
    committed_lf = [r for r in lf_rows if (r.get("brief_answers") or {}).get("stato") in (ACTIVE_STATI + DONE_STATI)]
    year_nominale = round(sum(_amount_of(r) for r in committed_lf) + ext_total, 2)
    stima_deducibile = round((year_nominale / 10.0) * 1.65, 2)

    return {
        "show_borsellino": show_borsellino,
        "borsellino": {"caricato": 0, "impegnato": 0, "spendibile": 0, "ricariche_in_transito": []},
        "impresa": {"payment_method": None, "paypal_email": "", "bookings": len(impresa_rows)},
        "limiti": limiti,
        "attivita": {"upcoming": upcoming, "documenti": documenti},
        "recupero_fiscale": {"anno": year, "stima_deducibile": stima_deducibile, "nominale_anno": year_nominale},
    }
