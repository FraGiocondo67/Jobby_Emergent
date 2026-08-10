"""Blocco 2 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent (Spec 1 —
configuratore Pulizie: motore prezzi deterministico, doppio binario
IMPRESA/PERSONA_LF, matching, listino provider, matching manuale admin).

Stesso modello dati/convenzioni già stabilite in routers/artigiani.py (Blocco
2, leggere quel modulo per il contesto completo): le "richieste" Pulizie sono
righe di public.missions (category_id = service_categories dove
slug='housekeeping' — la categoria storica si chiama così anche se il
dominio si chiama "Pulizie"/"PULIZIA"), con lo stato di dettaglio del flusso
in missions.brief_answers (jsonb). Il catalogo extra a pagamento (forno,
frigo, finestre, balconi) è ora public.pulizie_extra, admin-editabile via
Retool — stessa decisione dell'utente già applicata a artigiani_mestieri/
artigiani_paniere. Le altre costanti (home_types, mq_bands, tipi_pulizia,
ricorrenze, flessibilita, binari, variation_reasons, ore_table) restano
invece in richieste_config.py: sono tassonomia/logica di flusso a costo
fisso, non un "menu" con prezzi admin-editabili come mestieri/paniere/extra.

BLOCCO 3 (Wallet/pagamenti/escrow) — `confirm`/`complete`/`review` e il
"borsellino" Libretto Famiglia sono ora implementati (verticale di
riferimento per il pattern, poi replicato su artigiani/babysitting/driver):

- binario `impresa`: vero escrow Stripe Connect (vedi stripe_pg.py) —
  `confirm` addebita la carta salvata del cliente (hold sul saldo JOBBY,
  nessun transfer_data) e chiama `create_escrow_hold()`; `complete` trasferisce
  il netto al connected account del provider e chiama `release_escrow()`;
  `cancel` (se già confermata) rimborsa e chiama `refund_escrow()`. Nessun
  fallback a wallet interno: il provider deve avere
  `stripe_payouts_enabled=true` e il cliente una carta salvata
  (`/pay/setup-card`) prima di poter confermare.
- binario `persona_lf`: NON un vero escrow — solo il registro
  `public.lf_ledger` (vedi lf_pg.py) che traccia i massimali INPS per coppia
  famiglia-lavoratore; `confirm` verifica i tetti e registra l'uso,
  `cancel` (se già confermata) lo storna, `complete` non tocca alcun gateway.

Il resto del flusso (config, stima prezzi, creazione/lista/dettaglio
richiesta, "in arrivo" lato provider, proposte, avvio lavoro, listino,
amministrazione, il cruscotto cross-categoria /provider/jobs) resta invariato
dal Blocco 2.
"""
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import lf_pg as LF
import richieste_config as C
import stripe_pg as SP
from core_pg import db, now_iso, now_utc, notify, record_trust_event, to_geography_point, parse_scheduled_at
from deps_pg import get_current_user, require_admin

router = APIRouter()

STATI_APERTI = ("pubblicata", "in_matching", "con_proposte")
_CATEGORY_SLUG = "housekeeping"     # "Pulizie" nello storico — slug ereditato, non rinominato
_FEE_SETTING_KEY = "pulizie_fee_pct"


# ---------------- models ----------------
class Listino(BaseModel):
    binario: str = "impresa"
    tariffa_ordinaria: float = 16.0
    tariffa_afondo: float = 19.0
    tariffa_posttrasloco: float = 22.0
    prodotti_propri: bool = True
    supplemento_prodotti: float = 5.0
    extra: dict = {}
    stiro_ora: float = C.STIRO_DEFAULT_PRICE
    sconto_ricorrenza_pct: float = 10.0
    raggio_km: float = 15.0
    minimo_ore: int = 2


class Config(BaseModel):
    home_type: str = "appartamento"
    mq_band: str = "80_120"
    tipo_pulizia: str = "ordinaria"
    extra: List[str] = []
    stiro_ore: int = 0
    prodotti: str = "cliente"
    durata_ore: float = 3
    animali: bool = False


class RichiestaIn(BaseModel):
    binario: str = "impresa"
    config: Config
    indirizzo: str = ""
    lat: float
    lng: float
    data_ora: str = ""
    flessibilita: str = "fascia"
    ricorrenza: str = "una_tantum"
    giorni_preferiti: List[str] = []
    note: str = ""
    foto: List[str] = []
    parcheggio: str = ""
    publish: bool = True


class ProposeIn(BaseModel):
    accept: bool
    variation_reason: Optional[str] = None
    variation_price: Optional[float] = None
    message: str = ""


class ConfirmIn(BaseModel):
    provider_id: str


class InviteIn(BaseModel):
    provider_ids: List[str]


# ---------------- cataloghi / settings ----------------
def _category_id() -> str:
    res = db.table("service_categories").select("id").eq("slug", _CATEGORY_SLUG).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="pulizie_category_missing")
    return res.data[0]["id"]


async def fee_pct() -> float:
    res = db.table("app_settings").select("value").eq("key", _FEE_SETTING_KEY).limit(1).execute()
    if res.data:
        try:
            return float(res.data[0]["value"])
        except Exception:
            pass
    return C.DEFAULT_FEE_PCT


def _extra_items() -> List[dict]:
    res = db.table("pulizie_extra").select("*").eq("is_active", True).order("sort_order").execute()
    return res.data or []


def _extra_items_out() -> List[dict]:
    """Stesso shape della vecchia costante C.EXTRA_ITEMS."""
    return [{"id": e["slug"], "it": e["name_it"], "en": e["name_en"], "default_price": float(e["default_price"])} for e in _extra_items()]


# ---------------- price engine (logica pura — resta Python) ----------------
def _extra_price(listino: dict, key: str) -> float:
    ov = (listino.get("extra") or {}).get(key)
    if ov is not None:
        return float(ov)
    for e in _extra_items_out():
        if e["id"] == key:
            return float(e["default_price"])
    return 0.0


def compute_work_total(listino: dict, config: dict) -> float:
    tipo = config.get("tipo_pulizia", "ordinaria")
    tariffa = {
        "ordinaria": listino.get("tariffa_ordinaria", 16.0),
        "afondo": listino.get("tariffa_afondo", 19.0),
        "posttrasloco": listino.get("tariffa_posttrasloco", 22.0),
    }.get(tipo, listino.get("tariffa_ordinaria", 16.0))
    ore = float(config.get("durata_ore", 3) or 0)
    total = float(tariffa) * ore
    if config.get("prodotti") == "provider":
        total += float(listino.get("supplemento_prodotti", 0))
    for ex in config.get("extra", []):
        if ex == "stiro":
            continue
        total += _extra_price(listino, ex)
    if "stiro" in config.get("extra", []):
        total += float(listino.get("stiro_ora", C.STIRO_DEFAULT_PRICE)) * int(config.get("stiro_ore", 0) or 0)
    ric = config.get("_ricorrenza", "una_tantum")
    if ric in ("settimanale", "quindicinale"):
        total *= (1 - float(listino.get("sconto_ricorrenza_pct", 0)) / 100.0)
    return round(total, 2)


def price_breakdown(listino: dict, config: dict, binario: str, fee: float) -> dict:
    work = compute_work_total(listino, config)
    jobby_fee = round(work * fee / 100.0, 2)
    fee_client = round(jobby_fee / 2.0, 2)
    fee_provider = round(jobby_fee - fee_client, 2)
    provider_net = round(work - fee_provider, 2)
    out = {"work_total": work, "jobby_fee": jobby_fee, "fee_pct": fee,
           "fee_client": fee_client, "fee_provider": fee_provider, "provider_net": provider_net,
           "total_client": round(work + fee_client, 2)}
    if binario == "persona_lf":
        nominale = C.lf_round_nominale(work)
        out.update({
            "lf_nominale": nominale, "lf_voucher": int(nominale / 10),
            "lf_netto_lavoratrice": round(nominale * C.LF_VOUCHER_NET_RATE, 2),
            "fee_client": jobby_fee, "fee_provider": 0.0, "provider_net": 0.0,
            "total_client": round(nominale + jobby_fee, 2),
        })
    return out


def _compatible_providers(binario: str, config: dict, lat: Optional[float], lng: Optional[float]) -> List[dict]:
    res = db.rpc(
        "pulizie_compatible_providers",
        {
            "p_binario": binario, "p_lat": lat, "p_lng": lng,
            "p_prodotti_provider": config.get("prodotti") == "provider",
            "p_durata_ore": float(config.get("durata_ore", 0) or 0),
        },
    ).execute()
    return res.data or []


def _richiesta_out(row: dict) -> dict:
    brief = row.get("brief_answers") or {}
    out = dict(brief)
    out.update({
        "richiesta_id": row["id"],
        "cliente_id": row["client_id"],
        "categoria": "CASA",
        "servizio": "PULIZIA",
        "indirizzo": row.get("address"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    })
    return out


# ---------------- config / estimate ----------------
@router.get("/pulizie/config")
async def get_pulizie_config(user=Depends(get_current_user)):
    return {
        "home_types": C.HOME_TYPES, "mq_bands": C.MQ_BANDS, "tipi_pulizia": C.TIPI_PULIZIA,
        "extra_items": _extra_items_out(), "stiro_default_price": C.STIRO_DEFAULT_PRICE,
        "ricorrenze": C.RICORRENZE, "flessibilita": C.FLESSIBILITA, "binari": C.BINARI,
        "variation_reasons": C.VARIATION_REASONS, "ore_table": C.ORE_TABLE, "fee_pct": await fee_pct(),
    }


class EstimateIn(BaseModel):
    binario: str = "impresa"
    config: Config
    lat: float = 45.6669
    lng: float = 12.2433
    ricorrenza: str = "una_tantum"


@router.post("/pulizie/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    cfg = body.config.dict()
    cfg["_ricorrenza"] = body.ricorrenza
    fee = await fee_pct()
    result = {}
    for binario in ("impresa", "persona_lf"):
        provs = _compatible_providers(binario, cfg, body.lat, body.lng)
        prices = [price_breakdown(pp.get("listino") or {}, cfg, binario, fee)["total_client"] for pp in provs]
        result[binario] = {
            "providers": len(provs),
            "min": round(min(prices), 2) if prices else None,
            "max": round(max(prices), 2) if prices else None,
        }
    return {"recommended_hours": C.recommended_hours(cfg.get("mq_band"), cfg.get("tipo_pulizia")),
            "fee_pct": fee, "ranges": result}


# ---------------- richiesta CRUD ----------------
@router.post("/pulizie/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    if body.binario not in ("impresa", "persona_lf"):
        raise HTTPException(status_code=400, detail="invalid_binario")
    cfg = body.config.dict()
    cfg["_ricorrenza"] = body.ricorrenza

    brief = {
        "binario": body.binario, "config": cfg,
        "flessibilita": body.flessibilita, "ricorrenza": body.ricorrenza,
        "giorni_preferiti": body.giorni_preferiti, "durata_ore": cfg.get("durata_ore"),
        "note": body.note, "foto": body.foto, "parcheggio": body.parcheggio,
        "data_ora": body.data_ora,
        "stato": "pubblicata" if body.publish else "bozza",
        "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "pagamento_fee": {"stato": "authorized" if body.publish else "none"},
        "pagamento_lavoro": {"stato": "none"},
        "recensione": None,
    }
    if body.publish:
        brief["scade_at"] = (now_utc() + timedelta(hours=C.PROPOSAL_WINDOW_HOURS)).isoformat()
        provs = _compatible_providers(body.binario, cfg, body.lat, body.lng)
        brief["provider_invitati"] = [{"provider_id": pp["provider_id"], "at": now_iso(), "status": "invited", "auto": True} for pp in provs]

    row = {
        "client_id": user["id"], "category_id": _category_id(),
        "title": "Pulizie", "description": body.note,
        "status": "published" if body.publish else "draft", "address": body.indirizzo,
        "location": to_geography_point(body.lat, body.lng),
        "scheduled_at": parse_scheduled_at(body.data_ora),
        "platform_fee_pct": await fee_pct(),
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    created = res.data[0]

    if body.publish:
        for inv in brief["provider_invitati"]:
            await notify(inv["provider_id"], "nuova_richiesta", "Nuova richiesta pulizie",
                        "Hai una nuova richiesta compatibile in arrivo.", "richiesta", created["id"])
    return _richiesta_out(created)


@router.get("/pulizie/richieste")
async def my_richieste(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*")
        .eq("client_id", user["id"]).eq("category_id", _category_id())
        .order("created_at", desc=True).limit(100).execute()
    )
    return [_richiesta_out(r) for r in (res.data or [])]


@router.get("/pulizie/richieste/{rid}")
async def get_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    is_owner = row["client_id"] == uid
    is_invited = uid in [p.get("provider_id") for p in brief.get("provider_invitati", [])]
    if not (is_owner or is_invited):
        raise HTTPException(status_code=403, detail="forbidden")
    out = _richiesta_out(row)
    out["role"] = "client" if is_owner else "provider"
    if not is_owner:
        out.pop("indirizzo", None)
    return out


@router.post("/pulizie/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") in ("completata", "recensita"):
        raise HTTPException(status_code=400, detail="already_done")

    binario = brief.get("binario", "impresa")
    if brief.get("stato") in ("confermata", "in_corso"):
        pagamento = brief.get("pagamento_lavoro") or {}
        if binario == "impresa" and pagamento.get("stato") == "held":
            refund = SP.refund_payment_intent(pagamento["payment_intent_id"])
            db.rpc("refund_escrow", {
                "p_mission_id": rid, "p_reason": "cancellazione_cliente",
                "p_gateway_transaction_id": refund["refund_id"],
                "p_gateway_response": {}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["stato"] = "refunded"
            pagamento["refund_id"] = refund["refund_id"]
            brief["pagamento_lavoro"] = pagamento
        elif binario == "persona_lf" and pagamento.get("stato") == "lf_registrato":
            provider_id = brief.get("provider_scelto")
            if provider_id:
                LF.record_usage(row["client_id"], provider_id,
                                -float(pagamento.get("lf_nominale") or 0),
                                -float(pagamento.get("lf_ore") or 0))
            pagamento["stato"] = "annullato"
            brief["pagamento_lavoro"] = pagamento

    brief["stato"] = "annullata"
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "annullata"}


# ---------------- provider side ----------------
@router.get("/pulizie/incoming")
async def incoming(user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        return []
    uid = user["id"]
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("created_at", desc=True).limit(200).execute()
    )
    prov_row = db.table("profiles_provider").select("price_list").eq("user_id", uid).limit(1).execute()
    price_list = prov_row.data[0].get("price_list") if prov_row.data else {}
    lst = price_list.get("pulizie", {}) if isinstance(price_list, dict) else {}
    fee = await fee_pct()

    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        invitati = brief.get("provider_invitati", [])
        my_invite = next((p for p in invitati if p.get("provider_id") == uid), None)
        is_chosen = brief.get("provider_scelto") == uid
        if brief.get("stato") not in STATI_APERTI and not (is_chosen and brief.get("stato") in ("confermata", "in_corso")):
            continue
        if not my_invite and not is_chosen:
            continue
        if my_invite and my_invite.get("status") == "declined" and not is_chosen:
            continue
        item = _richiesta_out(row)
        item.pop("indirizzo", None)
        item["price"] = price_breakdown(lst, brief.get("config", {}), brief.get("binario", "impresa"), fee)
        item["my_proposal"] = next((p for p in brief.get("proposte", []) if p.get("provider_id") == uid), None)
        out.append(item)
    return out


@router.post("/pulizie/richieste/{rid}/propose")
async def propose(rid: str, body: ProposeIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    invitati = brief.get("provider_invitati", [])
    uid = user["id"]
    if uid not in [p.get("provider_id") for p in invitati]:
        raise HTTPException(status_code=403, detail="not_invited")
    if brief.get("stato") not in STATI_APERTI:
        raise HTTPException(status_code=400, detail="not_open")

    if not body.accept:
        for p in invitati:
            if p.get("provider_id") == uid:
                p["status"] = "declined"
        brief["provider_invitati"] = invitati
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
        return {"declined": True}

    if body.variation_price is not None and body.variation_reason not in [v["id"] for v in C.VARIATION_REASONS]:
        raise HTTPException(status_code=400, detail="invalid_variation_reason")

    prov_row = db.table("profiles_provider").select("price_list, business_data, avg_rating, trust_score").eq("user_id", uid).limit(1).execute()
    pdata = prov_row.data[0] if prov_row.data else {}
    price_list = pdata.get("price_list")
    lst = price_list.get("pulizie", {}) if isinstance(price_list, dict) else {}
    business_data = pdata.get("business_data") or {}
    fee = await fee_pct()
    pb = price_breakdown(lst, brief.get("config", {}), brief.get("binario", "impresa"), fee)
    price = round(float(body.variation_price), 2) if body.variation_price is not None else pb["total_client"]

    proposal = {
        "provider_id": uid, "provider_nome": business_data.get("business_name") or user.get("full_name", ""),
        "provider_rating": pdata.get("avg_rating") or 0, "provider_trust": pdata.get("trust_score") or 0,
        "listino_price": pb["total_client"], "price": price, "breakdown": pb,
        "variation_reason": body.variation_reason, "message": body.message, "at": now_iso(),
    }
    proposte = [p for p in brief.get("proposte", []) if p.get("provider_id") != uid]
    proposte.append(proposal)
    brief["proposte"] = proposte
    brief["stato"] = "con_proposte"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(row["client_id"], "richiesta_proposta", "Nuova proposta Pulizie",
                f"{proposal['provider_nome']} ha proposto €{price:.2f}.", "richiesta", rid)
    return proposal


# ---------------- client confirm + lifecycle (Blocco 3 — vedi docstring modulo) ----------------
@router.post("/pulizie/richieste/{rid}/confirm")
async def confirm(rid: str, body: ConfirmIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") not in STATI_APERTI:
        raise HTTPException(status_code=400, detail="not_open")
    provider_id = body.provider_id
    proposal = next((p for p in brief.get("proposte", []) if p.get("provider_id") == provider_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")

    binario = brief.get("binario", "impresa")
    pb = proposal.get("breakdown") or {}
    amount = float(proposal.get("price") or pb.get("total_client") or 0)

    if binario == "impresa":
        prov_row = db.table("profiles_provider").select("stripe_payouts_enabled").eq("user_id", provider_id).limit(1).execute()
        if not prov_row.data or not prov_row.data[0].get("stripe_payouts_enabled"):
            raise HTTPException(status_code=400, detail="provider_not_onboarded")
        customer_id = user.get("stripe_customer_id")
        pm_id = user.get("default_payment_method_id")
        if not customer_id or not pm_id:
            raise HTTPException(status_code=400, detail="client_payment_method_missing")

        # La variazione di prezzo (se presente) è lavoro extra per il provider,
        # non tocca la fee JOBBY (calcolata sul listino base al momento della proposta).
        delta = amount - float(pb.get("total_client") or amount)
        fee = float(pb.get("jobby_fee") or 0)
        payout = float(pb.get("provider_net") or 0) + delta

        db.table("missions").update({
            "provider_id": provider_id, "price_agreed": amount,
            "platform_fee": fee, "provider_payout": payout,
        }).eq("id", rid).execute()

        charge = SP.charge_hold(customer_id, pm_id, amount, {"mission_id": rid, "category": "pulizie"})
        db.rpc("create_escrow_hold", {
            "p_mission_id": rid, "p_gateway_transaction_id": charge["payment_intent_id"],
            "p_gateway_response": {"status": charge["status"]}, "p_gateway_name": "stripe",
        }).execute()
        brief["pagamento_lavoro"] = {"stato": "held", "payment_intent_id": charge["payment_intent_id"], "amount": amount}

    elif binario == "persona_lf":
        cfg = brief.get("config", {}) or {}
        durata_ore = float(cfg.get("durata_ore") or brief.get("durata_ore") or 0)
        nominale = float(pb.get("lf_nominale") or C.lf_round_nominale(amount))
        LF.check_ceilings(
            family_id=row["client_id"], worker_id=provider_id, add_nominale=nominale, add_hours=durata_ore,
            couple_ceiling_eur=C.LF_COUPLE_CEILING_EUR, family_ceiling_eur=C.LF_FAMILY_ANNUAL_EUR,
            worker_ceiling_eur=C.LF_PROVIDER_ANNUAL_EUR, worker_ceiling_hours=C.LF_PROVIDER_HOURS,
        )
        LF.record_usage(row["client_id"], provider_id, nominale, durata_ore)

        db.table("missions").update({
            "provider_id": provider_id, "price_agreed": nominale, "platform_fee": 0, "provider_payout": 0,
        }).eq("id", rid).execute()
        brief["pagamento_lavoro"] = {"stato": "lf_registrato", "lf_nominale": nominale, "lf_ore": durata_ore}
    else:
        raise HTTPException(status_code=400, detail="invalid_binario")

    brief["stato"] = "confermata"
    brief["provider_scelto"] = provider_id
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(provider_id, "richiesta_confermata", "Richiesta confermata",
                "Il cliente ha confermato la tua proposta.", "richiesta", rid)
    await notify(row["client_id"], "richiesta_confermata", "Richiesta confermata",
                "Hai confermato la richiesta.", "richiesta", rid)
    return {"stato": "confermata", "pagamento_lavoro": brief["pagamento_lavoro"]}


@router.post("/pulizie/richieste/{rid}/start")
async def start(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    if uid not in (row["client_id"], brief.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    if brief.get("stato") != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    brief["stato"] = "in_corso"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"stato": "in_corso"}


@router.post("/pulizie/richieste/{rid}/complete")
async def complete(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    if uid not in (row["client_id"], brief.get("provider_scelto")):
        raise HTTPException(status_code=404, detail="not_found")
    if brief.get("stato") != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")

    binario = brief.get("binario", "impresa")
    if binario == "impresa":
        pagamento = brief.get("pagamento_lavoro") or {}
        if pagamento.get("stato") != "held":
            raise HTTPException(status_code=400, detail="payment_not_held")
        prov_row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", row["provider_id"]).limit(1).execute()
        acct_id = prov_row.data[0].get("stripe_connect_account_id") if prov_row.data else None
        if not acct_id:
            raise HTTPException(status_code=400, detail="provider_not_onboarded")
        payout = float(row.get("provider_payout") or 0)
        transfer = SP.transfer_to_provider(acct_id, payout, {"mission_id": rid, "category": "pulizie"})
        db.rpc("release_escrow", {
            "p_mission_id": rid, "p_gateway_transaction_id": transfer["transfer_id"],
            "p_gateway_response": {}, "p_gateway_name": "stripe",
        }).execute()
        pagamento["stato"] = "released"
        pagamento["transfer_id"] = transfer["transfer_id"]
        brief["pagamento_lavoro"] = pagamento
    # persona_lf: nessuna azione gateway — l'uso è già stato registrato al confirm

    brief["stato"] = "completata"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "richiesta_completata", "Lavoro completato",
                "Il lavoro è stato segnato come completato.", "richiesta", rid)
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "richiesta_completata", "Lavoro completato",
                    "Hai completato il lavoro.", "richiesta", rid)
    return {"stato": "completata"}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/pulizie/richieste/{rid}/review")
async def review(rid: str, body: ReviewIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "completata":
        raise HTTPException(status_code=400, detail="not_completed")
    if not (1 <= body.rating <= 5):
        raise HTTPException(status_code=400, detail="invalid_rating")
    provider_id = brief.get("provider_scelto")
    if not provider_id:
        raise HTTPException(status_code=400, detail="no_provider")

    db.table("reviews").insert({
        "mission_id": rid, "reviewer_id": user["id"], "reviewee_id": provider_id,
        "rating": body.rating, "comment": body.comment,
    }).execute()

    agg = db.table("reviews").select("rating").eq("reviewee_id", provider_id).execute()
    ratings = [r["rating"] for r in (agg.data or [])]
    if ratings:
        new_avg = round(sum(ratings) / len(ratings), 2)
        db.table("profiles_provider").update({"avg_rating": new_avg}).eq("user_id", provider_id).execute()

    brief["recensione"] = {"rating": body.rating, "comment": body.comment, "at": now_iso()}
    brief["stato"] = "recensita"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    # Blocco 4: fa scattare recalculate_trust_score (vedi core_pg.record_trust_event).
    record_trust_event(provider_id, "review_received", round((body.rating - 3) * 2, 2),
                       dimension="quality", notes=f"Recensione {body.rating}★ su richiesta pulizie {rid}")

    await notify(provider_id, "richiesta_completata", "Nuova recensione",
                f"Hai ricevuto {body.rating}★ dal cliente.", "richiesta", rid)
    return brief["recensione"]


# ---------------- Libretto Famiglia borsellino (Blocco 3 — registro, non wallet) ----------------
@router.get("/pulizie/lf/borsellino")
async def lf_borsellino(user=Depends(get_current_user)):
    uid = user["id"]
    family_total = LF.get_family_total(uid)
    worker_totals = LF.get_worker_totals(uid)
    return {
        "as_family": {"nominale_used": round(family_total, 2), "ceiling_eur": C.LF_FAMILY_ANNUAL_EUR},
        "as_worker": {
            "nominale_used": round(worker_totals["nominale_used"], 2),
            "hours_used": round(worker_totals["hours_used"], 2),
            "ceiling_eur": C.LF_PROVIDER_ANNUAL_EUR, "ceiling_hours": C.LF_PROVIDER_HOURS,
        },
        "couple_ceiling_eur": C.LF_COUPLE_CEILING_EUR,
    }


@router.post("/pulizie/lf/topup")
async def lf_topup():
    # Decisione presa con l'utente (Blocco 3): il Libretto Famiglia non è un
    # portafoglio — i compensi si muovono fuori JOBBY tramite voucher INPS, mai
    # tramite un saldo pre-caricato. Endpoint del sistema Emergent (wallet
    # simulato) rimosso: non ha equivalente nel nuovo modello a registro.
    raise HTTPException(
        status_code=410,
        detail="Il Libretto Famiglia non è un portafoglio ricaricabile: i compensi si muovono fuori JOBBY "
               "tramite voucher INPS. Vedi GET /pulizie/lf/borsellino per i massimali residui.",
    )


# ---------------- provider listino ----------------
@router.get("/pulizie/listino")
async def get_listino(user=Depends(get_current_user)):
    row = db.table("profiles_provider").select("price_list").eq("user_id", user["id"]).limit(1).execute()
    price_list = row.data[0].get("price_list") if row.data else {}
    lst = price_list.get("pulizie") if isinstance(price_list, dict) else None
    default_binario = "impresa" if user.get("role") == "both" else "persona_lf"
    return {"pulizie_binario": (lst or {}).get("binario", default_binario), "listino": lst}


class ListinoIn(BaseModel):
    binario: str = "impresa"
    listino: Listino


@router.put("/pulizie/listino")
async def set_listino(body: ListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    row = db.table("profiles_provider").select("price_list, skills").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    current = row.data[0].get("price_list")
    price_list = dict(current) if isinstance(current, dict) else {}
    lst = body.listino.dict()
    lst["binario"] = body.binario
    price_list["pulizie"] = lst
    skills = sorted(set((row.data[0].get("skills") or []) + ["pulizie"]))
    db.table("profiles_provider").update({"price_list": price_list, "skills": skills}).eq("user_id", user["id"]).execute()
    return {"pulizie_binario": body.binario, "listino": lst}


# ---------------- admin manuale matching ----------------
@router.get("/admin/pulizie/richieste")
async def admin_richieste(_=Depends(require_admin)):
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("created_at", desc=True).limit(200).execute()
    )
    fee = await fee_pct()
    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        if brief.get("stato") not in STATI_APERTI:
            continue
        invitati = brief.get("provider_invitati", [])
        provs = _compatible_providers(brief.get("binario", "impresa"), brief.get("config", {}), row.get("lat"), row.get("lng"))
        item = _richiesta_out(row)
        item["compatible"] = [{
            "provider_id": p["provider_id"], "nome": p.get("business_name") or p.get("full_name"),
            "distance": p.get("distance_km"), "rating": p.get("avg_rating") or 0, "trust": p.get("trust_score") or 0,
            "price": price_breakdown(p.get("listino") or {}, brief.get("config", {}), brief.get("binario", "impresa"), fee)["total_client"],
            "invited": p["provider_id"] in [i.get("provider_id") for i in invitati],
            "invite_status": next((i.get("status") for i in invitati if i.get("provider_id") == p["provider_id"]), None),
            "confirmed": brief.get("provider_scelto") == p["provider_id"],
        } for p in provs]
        out.append(item)
    return out


@router.post("/admin/pulizie/richieste/{rid}/invite")
async def admin_invite(rid: str, body: InviteIn, _=Depends(require_admin)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    invitati = brief.get("provider_invitati", [])
    already = [i.get("provider_id") for i in invitati]
    new_count, reset_count = 0, 0
    for pid in body.provider_ids:
        if pid in already:
            for i in invitati:
                if i.get("provider_id") == pid and i.get("status") == "declined":
                    i["status"] = "invited"
                    i["reinvited_at"] = now_iso()
                    reset_count += 1
                    await notify(pid, "richiesta_invito", "Nuova richiesta di pulizia",
                                "Hai ricevuto di nuovo una richiesta compatibile.", "richiesta", rid)
            continue
        invitati.append({"provider_id": pid, "at": now_iso(), "status": "invited"})
        new_count += 1
        await notify(pid, "richiesta_invito", "Nuova richiesta di pulizia",
                    "Hai ricevuto una richiesta compatibile. Rispondi entro 24h.", "richiesta", rid)
    if new_count or reset_count:
        brief["provider_invitati"] = invitati
        brief["stato"] = "in_matching"
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"invited": new_count, "reactivated": reset_count}


class FeeIn(BaseModel):
    fee_pct: float


@router.post("/admin/pulizie/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    db.table("app_settings").upsert({"key": _FEE_SETTING_KEY, "value": float(body.fee_pct)}).execute()
    return {"fee_pct": body.fee_pct}


# ---------------- cruscotto cross-categoria ----------------
_CROSS_CATEGORY_SLUGS = ("housekeeping", "babysitting", "driver", "artigiani")


@router.get("/provider/jobs")
async def provider_jobs(user=Depends(get_current_user)):
    """Tutti i lavori del provider su ogni categoria migrata a questo pattern
    (missions + brief_answers con provider_invitati/proposte/provider_scelto):
    Pulizie, Babysitting, Driver, Artigiani. Ogni card rimanda al dettaglio
    (dove risiedono pagamento e recensione)."""
    if user.get("role") not in ("provider", "both"):
        return []
    uid = user["id"]
    cat_res = db.table("service_categories").select("id, slug").in_("slug", list(_CROSS_CATEGORY_SLUGS)).execute()
    slug_by_id = {c["id"]: c["slug"] for c in (cat_res.data or [])}
    if not slug_by_id:
        return []
    res = (
        db.table("missions").select("*")
        .in_("category_id", list(slug_by_id.keys()))
        .order("updated_at", desc=True).limit(300).execute()
    )
    rows = res.data or []
    client_ids = sorted({r["client_id"] for r in rows if r.get("client_id")})
    name_by_client = {}
    if client_ids:
        u_res = db.table("users").select("id, full_name").in_("id", client_ids).execute()
        name_by_client = {u["id"]: u.get("full_name") for u in (u_res.data or [])}

    # slug Postgres -> etichetta "servizio" usata dal vecchio contratto Mongo
    _SLUG_TO_CAT = {"housekeeping": "pulizie", "babysitting": "babysitting", "driver": "driver", "artigiani": "artigiani"}

    out = []
    for row in rows:
        brief = row.get("brief_answers") or {}
        invitati = brief.get("provider_invitati", [])
        inv = next((p for p in invitati if p.get("provider_id") == uid), None)
        is_chosen = brief.get("provider_scelto") == uid
        if not inv and not is_chosen:
            continue
        if inv and inv.get("status") == "declined" and not is_chosen:
            continue
        mine = next((p for p in brief.get("proposte", []) if p.get("provider_id") == uid), None)
        out.append({
            "richiesta_id": row["id"], "cat": _SLUG_TO_CAT.get(slug_by_id.get(row["category_id"])),
            "stato": brief.get("stato"), "config": brief.get("config"),
            "created_at": row.get("created_at"), "updated_at": row.get("updated_at"),
            "data_ora": brief.get("data_ora"), "pickup_at": brief.get("pickup_at"),
            "partenza": brief.get("partenza"), "destinazione": brief.get("destinazione"),
            "prezzo_finale": brief.get("prezzo_finale"), "importo_totale": row.get("price_agreed"),
            "urgente": brief.get("urgente"), "invite_status": (inv or {}).get("status"),
            "is_chosen": is_chosen, "my_proposal": bool(mine),
            "pagamento": brief.get("pagamento_lavoro") or brief.get("pagamento"),
            "cliente_nome": name_by_client.get(row.get("client_id")),
        })
    return out
