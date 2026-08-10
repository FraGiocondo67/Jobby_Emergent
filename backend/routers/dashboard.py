"""RITIRATO nel Blocco 7 (migrazione Emergent -> Supabase/Render) — non più
importato/esposto da server.py, su conferma esplicita dell'utente. Dashboard
Mongo-based (wallet/provider stats) — la dashboard admin passa a Retool
(Blocco 6); l'equivalente lato app (home cliente/provider) va ricostruito
sopra le tabelle Postgres se/quando serve, non riportato qui. File lasciato
nel repo come riferimento storico (Mongo, non funzionante senza MONGO_URL).

Docstring originale sotto, invariata: "Spec 5 — Navigation, Home (two
states), Wallet dashboard, Provider dashboard, support number."."""
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core import db, now_utc
from deps import get_current_user, require_admin
import richieste_config as C

router = APIRouter()

DEFAULT_SUPPORT_WHATSAPP = "+393481136876"
ACTIVE_REL_STATES = ["confermata", "in_corso", "completata", "recensita"]
PROBLEM_STATES = ["con_proposte"]  # awaiting client choice
LF_AGEVOLATE = {"studente", "pensionato", "disoccupato"}


# ---------------- support / settings ----------------
class SupportIn(BaseModel):
    whatsapp: str


async def _support_number() -> str:
    s = await db.settings.find_one({"key": "support_whatsapp"})
    return (s or {}).get("value") or DEFAULT_SUPPORT_WHATSAPP


@router.get("/settings/support")
async def get_support():
    return {"whatsapp": await _support_number()}


@router.post("/admin/settings/support")
async def set_support(body: SupportIn, _=Depends(require_admin)):
    await db.settings.update_one({"key": "support_whatsapp"},
                                 {"$set": {"value": body.whatsapp.strip()}}, upsert=True)
    return {"whatsapp": body.whatsapp.strip()}


# ---------------- helpers ----------------
def _today_str() -> str:
    return date.today().isoformat()


def _year() -> int:
    return date.today().year


def _amount_of(r: dict) -> float:
    """Work/nominal amount used for legal counters."""
    pl = r.get("pagamento_lavoro") or {}
    if r.get("binario") == "persona_lf":
        return float(pl.get("nominale") or (r.get("proposte") and 0) or 0) or float((r.get("config") or {}).get("lf_nominale", 0) or 0)
    return float(r.get("prezzo_finale") or 0)


async def _provider_brief(pid: str) -> dict:
    u = await db.users.find_one({"user_id": pid}, {"_id": 0, "name": 1, "business_name": 1, "photo": 1, "rating": 1, "role": 1})
    u = u or {}
    return {"provider_id": pid, "nome": u.get("business_name") or u.get("name") or "Collaboratore",
            "photo": u.get("photo"), "rating": round(float(u.get("rating", 0)), 1),
            "is_business": u.get("role") == "business"}


# ---------------- HOME state ----------------
@router.get("/home/state")
async def home_state(user=Depends(get_current_user)):
    uid = user["user_id"]
    rich = await db.richieste.find({"cliente_id": uid}, {"_id": 0}).sort("data_ora", 1).to_list(500)
    has_completed = any(r.get("stato") in ("completata", "recensita") for r in rich)
    today = _today_str()

    # group active relationships by chosen provider
    by_prov: dict = {}
    for r in rich:
        pid = r.get("provider_scelto")
        if not pid or r.get("stato") not in ACTIVE_REL_STATES:
            continue
        by_prov.setdefault(pid, []).append(r)

    relationships = []
    for pid, items in by_prov.items():
        brief = await _provider_brief(pid)
        upcoming = [r for r in items if r.get("stato") in ("confermata", "in_corso") and (r.get("data_ora") or "") >= today]
        upcoming.sort(key=lambda r: r.get("data_ora") or "")
        nxt = upcoming[0] if upcoming else None
        problem = next((r for r in items if r.get("stato") in PROBLEM_STATES
                        or (r.get("pagamento_fee") or {}).get("stato") == "failed"), None)
        brief.update({
            "categoria": (nxt or items[-1]).get("categoria", "CASA"),
            "next_visit": (nxt or {}).get("data_ora"),
            "next_fascia": ((nxt or {}).get("config") or {}).get("fascia_oraria") or (nxt or {}).get("fascia_oraria"),
            "next_richiesta_id": (nxt or {}).get("richiesta_id"),
            "last_richiesta_id": items[-1].get("richiesta_id"),
            "visits_count": len([r for r in items if r.get("stato") in ("completata", "recensita")]),
            "problem": bool(problem),
            "problem_richiesta_id": (problem or {}).get("richiesta_id"),
            "problem_kind": ("scelta_proposta" if (problem or {}).get("stato") == "con_proposte"
                             else "pagamento" if problem else None),
        })
        relationships.append(brief)

    relationships.sort(key=lambda x: (x["next_visit"] is None, x["next_visit"] or "9999"))
    return {"state": "recurring" if has_completed else "new", "relationships": relationships}


# ---------------- WALLET dashboard (client) ----------------
@router.post("/wallet/external-usage")
async def add_external_usage(body: dict, user=Depends(get_current_user)):
    amount = round(float(body.get("amount", 0)), 2)
    provider_name = str(body.get("provider_name", "")).strip()
    entry = {"amount": amount, "provider_name": provider_name, "year": _year(), "at": now_utc().isoformat()}
    await db.users.update_one({"user_id": user["user_id"]}, {"$push": {"lf_external_usages": entry}})
    return {"ok": True, "entry": entry}


@router.get("/wallet/dashboard")
async def wallet_dashboard(user=Depends(get_current_user)):
    uid = user["user_id"]
    u = await db.users.find_one({"user_id": uid}, {"_id": 0}) or {}
    today = _today_str()
    year = _year()
    rich = await db.richieste.find({"cliente_id": uid}, {"_id": 0}).to_list(1000)

    lf_rich = [r for r in rich if r.get("binario") == "persona_lf" and r.get("stato") in ACTIVE_REL_STATES]
    impresa_rich = [r for r in rich if r.get("binario") == "impresa" and r.get("stato") in ACTIVE_REL_STATES]
    show_borsellino = len(lf_rich) > 0 or float(u.get("lf_borsellino", 0)) > 0

    # Block 1 — borsellino
    caricato = round(float(u.get("lf_borsellino", 0)), 2)
    impegnato = round(sum(float((r.get("config") or {}).get("lf_nominale", 0) or
                                (r.get("pagamento_lavoro") or {}).get("nominale", 0) or 0)
                          for r in lf_rich
                          if r.get("stato") in ("confermata", "in_corso") and (r.get("data_ora") or "") >= today), 2)
    spendibile = round(caricato - impegnato, 2)
    ricariche = [x for x in (u.get("lf_ricariche_pending") or [])]

    # Block 2 — limiti di legge
    external = [e for e in (u.get("lf_external_usages") or []) if e.get("year") == year]
    ext_total = round(sum(float(e.get("amount", 0)) for e in external), 2)

    per_collaboratrice = []
    annual_weighted = ext_total
    prov_agg: dict = {}
    for r in lf_rich:
        if str(r.get("data_ora") or "")[:4] and str(r.get("data_ora"))[:4] != str(year):
            # only count current year where date is known
            if r.get("data_ora"):
                continue
        pid = r.get("provider_scelto")
        if not pid:
            continue
        prov_agg.setdefault(pid, 0.0)
        prov_agg[pid] += float((r.get("config") or {}).get("lf_nominale", 0) or
                               (r.get("pagamento_lavoro") or {}).get("nominale", 0) or 0)
    for pid, used in prov_agg.items():
        pu = await db.users.find_one({"user_id": pid}, {"_id": 0, "name": 1, "business_name": 1, "photo": 1, "lf_categoria": 1})
        pu = pu or {}
        agevolata = (pu.get("lf_categoria") in LF_AGEVOLATE)
        weight = C.LF_AGEVOLATE_WEIGHT if agevolata else 1.0
        weighted = round(used * weight, 2)
        annual_weighted += weighted
        per_collaboratrice.append({
            "provider_id": pid, "nome": pu.get("business_name") or pu.get("name") or "Collaboratore",
            "photo": pu.get("photo"), "used": round(used, 2), "used_weighted": weighted,
            "ceiling": C.LF_COUPLE_CEILING_EUR, "agevolata": agevolata,
            "categoria_agevolata": pu.get("lf_categoria"),
            "pct": min(1.0, round(weighted / C.LF_COUPLE_CEILING_EUR, 3)) if C.LF_COUPLE_CEILING_EUR else 0,
            "warn": weighted >= C.LF_COUPLE_CEILING_EUR * C.LF_WARN_THRESHOLD,
            "upsell": weighted >= C.LF_COUPLE_CEILING_EUR * C.LF_WARN_THRESHOLD,
        })
    per_collaboratrice.sort(key=lambda x: -x["used_weighted"])
    annual_weighted = round(annual_weighted, 2)

    limiti = {
        "annual_used": annual_weighted, "annual_ceiling": C.LF_FAMILY_ANNUAL_EUR,
        "annual_pct": min(1.0, round(annual_weighted / C.LF_FAMILY_ANNUAL_EUR, 3)),
        "annual_warn": annual_weighted >= C.LF_FAMILY_ANNUAL_EUR * C.LF_WARN_THRESHOLD,
        "warn_threshold": C.LF_WARN_THRESHOLD,
        "per_collaboratrice": per_collaboratrice,
        "external_total": ext_total, "external_usages": external,
    }

    # Block 3 — attività e documenti
    upcoming = [{"richiesta_id": r.get("richiesta_id"), "categoria": r.get("categoria"),
                 "data_ora": r.get("data_ora"), "binario": r.get("binario"),
                 "voucher": int(((r.get("config") or {}).get("lf_nominale", 0) or 0) / 10) if r.get("binario") == "persona_lf" else 0,
                 "importo": _amount_of(r)}
                for r in rich if r.get("stato") in ("confermata", "in_corso") and (r.get("data_ora") or "") >= today]
    upcoming.sort(key=lambda x: x.get("data_ora") or "")
    documenti = [{"richiesta_id": r.get("richiesta_id"), "categoria": r.get("categoria"),
                  "data_ora": r.get("data_ora"), "binario": r.get("binario"),
                  "fee": (r.get("pagamento_fee") or {}).get("importo"),
                  "importo": _amount_of(r), "stato": r.get("stato")}
                 for r in rich if r.get("stato") in ("completata", "recensita")]
    documenti.sort(key=lambda x: x.get("data_ora") or "", reverse=True)

    # Block 4 — recupero fiscale (stima deduzioni: contributi Libretto deducibili)
    year_nominale = round(sum(float((r.get("config") or {}).get("lf_nominale", 0) or 0)
                              for r in lf_rich) + ext_total, 2)
    # Contributo INPS ~ 1.65€/ora (deducibile); stima su nominale a 10€/ora → 1.65€/voucher
    stima_deducibile = round((year_nominale / 10.0) * 1.65, 2)

    return {
        "show_borsellino": show_borsellino,
        "borsellino": {"caricato": caricato, "impegnato": impegnato, "spendibile": spendibile,
                       "ricariche_in_transito": ricariche},
        "impresa": {"payment_method": u.get("payment_method"), "paypal_email": u.get("paypal_email", ""),
                    "bookings": len(impresa_rich)},
        "limiti": limiti,
        "attivita": {"upcoming": upcoming, "documenti": documenti},
        "recupero_fiscale": {"anno": year, "stima_deducibile": stima_deducibile, "nominale_anno": year_nominale},
    }


# ---------------- PROVIDER dashboard ----------------
class DndIn(BaseModel):
    dnd: bool


@router.post("/provider/dnd")
async def set_dnd(body: DndIn, user=Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"dnd": body.dnd}})
    return {"dnd": body.dnd}


def _accredito_date(data_ora: str) -> str:
    """INPS pays the worker on the 15th of the month following the service."""
    try:
        d = datetime.fromisoformat((data_ora or "")[:10]).date()
    except Exception:
        d = date.today()
    y, m = d.year, d.month + 1
    if m > 12:
        y, m = y + 1, 1
    return date(y, m, 15).isoformat()


@router.get("/provider/dashboard")
async def provider_dashboard(user=Depends(get_current_user)):
    uid = user["user_id"]
    u = await db.users.find_one({"user_id": uid}, {"_id": 0}) or {}
    today = _today_str()
    year = _year()
    rich = await db.richieste.find({"provider_scelto": uid}, {"_id": 0}).to_list(1000)

    # Block 1 — guadagni
    guadagni = []
    for r in rich:
        if r.get("stato") not in ("confermata", "in_corso", "completata", "recensita"):
            continue
        pl = r.get("pagamento_lavoro") or {}
        if r.get("binario") == "persona_lf":
            amount = float(pl.get("netto_lavoratrice") or 0)
            guadagni.append({"richiesta_id": r.get("richiesta_id"), "amount": round(amount, 2),
                             "source": "INPS", "date": _accredito_date(r.get("data_ora")),
                             "stato": r.get("stato"), "categoria": r.get("categoria")})
        else:
            amount = float(pl.get("importo") or 0)
            settled = r.get("stato") in ("completata", "recensita")
            guadagni.append({"richiesta_id": r.get("richiesta_id"), "amount": round(amount, 2),
                             "source": "impresa", "date": None,
                             "stato": "trasferito" if settled else "in_attesa", "categoria": r.get("categoria")})
    incoming_total = round(sum(g["amount"] for g in guadagni if g["stato"] in ("confermata", "in_corso", "in_attesa")), 2)

    # Block 2 — limiti personali (LF)
    lf_rich = [r for r in rich if r.get("binario") == "persona_lf" and r.get("stato") in ACTIVE_REL_STATES]
    year_earned = round(sum(float((r.get("pagamento_lavoro") or {}).get("nominale", 0) or
                                  (r.get("config") or {}).get("lf_nominale", 0) or 0) for r in lf_rich), 2)
    year_hours = round(sum(float((r.get("config") or {}).get("ore", 0) or 0) for r in lf_rich), 1)
    per_family: dict = {}
    for r in lf_rich:
        cid = r.get("cliente_id")
        per_family.setdefault(cid, 0.0)
        per_family[cid] += float((r.get("config") or {}).get("lf_nominale", 0) or 0)
    limiti = {
        "annual_earned": year_earned, "annual_ceiling": C.LF_PROVIDER_ANNUAL_EUR,
        "annual_pct": min(1.0, round(year_earned / C.LF_PROVIDER_ANNUAL_EUR, 3)),
        "annual_warn": year_earned >= C.LF_PROVIDER_ANNUAL_EUR * C.LF_WARN_THRESHOLD,
        "hours": year_hours, "hours_ceiling": C.LF_PROVIDER_HOURS,
        "hours_pct": min(1.0, round(year_hours / C.LF_PROVIDER_HOURS, 3)),
        "families": len(per_family), "family_ceiling": C.LF_COUPLE_CEILING_EUR,
        "max_family_used": round(max(per_family.values()), 2) if per_family else 0,
        "warn_threshold": C.LF_WARN_THRESHOLD,
    }

    # Block 3 — storico
    storico = [{"richiesta_id": r.get("richiesta_id"), "categoria": r.get("categoria"),
                "data_ora": r.get("data_ora"), "importo": _amount_of(r),
                "recensione": (r.get("recensione") or {}).get("rating") if r.get("recensione") else None,
                "commento": (r.get("recensione") or {}).get("commento") if r.get("recensione") else None}
               for r in rich if r.get("stato") in ("completata", "recensita")]
    storico.sort(key=lambda x: x.get("data_ora") or "", reverse=True)

    return {
        "guadagni": {"incoming_total": incoming_total, "items": sorted(guadagni, key=lambda g: g.get("date") or "9999")},
        "limiti": limiti,
        "storico": storico,
        "reliability": round(float(u.get("trust_score", 0)), 1),
        "rating": round(float(u.get("rating", 0)), 1),
        "dnd": bool(u.get("dnd", False)),
    }
