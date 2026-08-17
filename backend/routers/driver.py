"""Blocco 2 (migrazione Emergent -> Supabase/Render) — riscrittura Postgres di
questo router. Sostituisce interamente la versione Mongo/Emergent (Spec 8 —
DRIVER: sottotipi NCC + TAXI, preventivo fermo parametrico per NCC, tassametro
ufficiale per TAXI, passeggero diverso dal pagante, minorenni non accompagnati
16+ a doppio consenso, tracking condiviso, cancellazione a fasce 4h/30min,
onboarding per classe veicolo).

Stesse convenzioni già stabilite in routers/artigiani.py, routers/richieste.py
e routers/babysitting.py (Blocco 2 — leggere quei moduli per il contesto
completo): le "richieste" Driver sono righe di public.missions (category_id =
service_categories dove slug='driver'), con lo stato di dettaglio del flusso
in missions.brief_answers (jsonb). A differenza di Pulizie/Babysitting questo
dominio non ha un binario Libretto Famiglia (solo Impresa/P.IVA, come nel
sistema Mongo): nessun borsellino INPS simulato da colmare qui.

Le costanti di dominio (vehicle_classes, shortcuts, ritocco_motivi,
special_needs, cancellation, default_listino, taxi_tariffa) restano in
driver_config.py — stessa distinzione tassonomia/logica-di-flusso-a-costo-
fisso vs "menu" admin-editabile già applicata alle altre verticali. Questo
dominio non ha un catalogo equivalente a mestieri/paniere/pulizie_extra, quindi
non è stata creata nessuna nuova tabella Postgres: solo la RPC di matching
(vedi sotto).

Listino, veicoli e tipo (ncc/taxi) del driver vivono in
profiles_provider.price_list->'driver' (chiavi 'tipo'/'listino'/'vehicles' —
i veicoli sono una lista jsonb con un vehicle_id generato lato Python, non
righe di una tabella dedicata: non hanno bisogno di RLS/query indipendenti dal
profilo provider). L'autorizzazione NCC/licenza TAXI vive in
profiles_provider.documents (chiavi driver_auth_numero/driver_auth_doc/
driver_auth_verified/driver_auth_uploaded_at) — stessa convenzione
"documents" già usata da artigiani.py e babysitting.py.

Il matching usa la nuova RPC public.driver_compatible_providers(p_tipo,
p_classe, p_lat, p_lng) (PostGIS ST_DWithin su profiles_provider.location,
stessa cautela sulla colonna geography non ancora verificata in scrittura
delle altre verticali — vedi TODO in onboarding.py/Blocco 1).

SEMPLIFICAZIONE RISPETTO ALLA VERSIONE MONGO: `propose()` nel sistema Emergent
aveva una scorciatoia — richiesta diretta a un driver specifico + accettazione
al prezzo di listino (nessun contro-prezzo) innescava un blocco fondi
automatico (we.hold) e una conferma automatica della corsa, saltando
/confirm. Quella scorciatoia tocca soldi ed è stata rimossa qui: propose()
ora aggiunge sempre la proposta e porta la richiesta a 'con_proposte',
indipendentemente dal fatto che l'invito fosse diretto o automatico — il
cliente deve sempre passare da /confirm (attualmente uno stub, vedi sotto) per
confermare la corsa. `cancel_richiesta` è stato invece riclassificato come
"solo informativo": calcola e ritorna l'esito della cancellazione (fascia/
importo/percentuale rimborso secondo driver_config.CANCELLATION) ma NON tenta
alcuna chiamata di rimborso/penale reale, per lo stesso motivo già documentato
nelle altre tre verticali — /confirm è uno stub, quindi nessuna richiesta può
arrivare a bloccare fondi in questo blocco.

BLOCCO 3 (Wallet/pagamenti/escrow) — `confirm`, `extra/approve`, `noshow`,
`complete`, `pay` e `review` sono ora implementati sullo stesso layer di
routers/richieste.py (Pulizie, verticale di riferimento — vedi
stripe_pg.py per il dettaglio del pattern). Qui NON esiste un binario
Libretto Famiglia (solo impresa/P.IVA, come già notato sopra): un solo
percorso, sempre Stripe Connect.

Particolarità di questo dominio rispetto alle altre tre verticali:
- **NCC**: il prezzo è noto al momento della proposta — stesso pattern a
  hold singolo di Pulizie (`confirm` blocca l'intero importo).
- **TAXI**: il prezzo finale dipende dal tassametro ufficiale, noto solo a
  fine corsa — `confirm` qui NON blocca nulla (non c'è ancora un importo).
  `complete(meter_amount)` chiude la corsa e registra la lettura finale,
  portando la richiesta in uno stato intermedio `in_pagamento`; è `pay` a
  bloccare e rilasciare l'importo del tassametro (+ eventuali extra già
  approvati durante la corsa). `review` resta bloccata (richiede stato
  `completata`) finché `pay` non chiude il pagamento.
- **extra** (attesa/fermata/cambio, entrambi i sottotipi): l'approvazione
  blocca l'importo subito, durante la corsa (stesso pattern extra di
  artigiani.py), non aspetta il completamento.
- **noshow**: nessuna regola esplicita nel sistema Emergent per l'importo
  della penale — trattato qui come cancellazione tardiva a addebito pieno
  (fascia "<30min" di `driver_config.CANCELLATION`): se la corsa aveva già
  un importo bloccato (NCC) viene rilasciato per intero al driver; per TAXI
  (dove non c'è ancora un hold) si addebita una penale minima pari alla
  tariffa minima del tassametro (`TAXI_TARIFFA.min_corsa`) — assunzione di
  prodotto esplicita, non presente nel sistema Emergent, da validare.
- **cancel_richiesta**: ora rimborsa per intero quanto eventualmente già
  bloccato (stesso comportamento delle altre tre verticali). **Semplifi-
  cazione deliberata**: le fasce di `driver_config.CANCELLATION` (rimborso
  parziale/trattenuta in base al preavviso) restano solo un valore
  INFORMATIVO restituito al chiamante (`outcome`, come già nel Blocco 2) —
  non pilotano ancora un rimborso parziale reale, che richiederebbe una RPC
  di refund parziale non ancora scritta. Da riprendere in un giro successivo
  se serve applicarle davvero.

Il resto del flusso (config, geocode, estimate, listino, veicoli,
autorizzazione, creazione/lista/dettaglio richiesta, "in arrivo" lato
provider, proposte, partenza/tracking, creazione extra, amministrazione)
resta invariato dal Blocco 2.

NOTA: la categoria service_categories 'driver' risulta attualmente
is_active=false nel database (verificato via query prima di scrivere questo
modulo) — non è stata cambiata silenziosamente qui. È una decisione di
prodotto (probabilmente questa verticale non è ancora stata lanciata
pubblicamente) che va confermata esplicitamente dall'utente prima del deploy,
non presunta da questo blocco di migrazione.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import driver_config as D
import spec4_pg as S4
import stripe_pg as SP
from core_pg import db, now_iso, now_utc, notify, haversine, record_trust_event, to_geography_point, parse_scheduled_at
from deps_pg import get_current_user, require_admin

router = APIRouter()

STATI_APERTI = ("pubblicata", "in_matching", "con_proposte")
_CATEGORY_SLUG = "driver"
_FEE_SETTING_KEY = "driver_fee_pct"


def _category_id() -> str:
    res = db.table("service_categories").select("id").eq("slug", _CATEGORY_SLUG).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="driver_category_missing")
    return res.data[0]["id"]


async def fee_pct() -> float:
    res = db.table("app_settings").select("value").eq("key", _FEE_SETTING_KEY).limit(1).execute()
    if res.data:
        try:
            return float(res.data[0]["value"])
        except Exception:
            pass
    return D.DEFAULT_FEE_PCT


def _parse(dt: str) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


# ---------------- price engine (logica pura — resta Python) ----------------
def estimate_route(a_lat, a_lng, b_lat, b_lng) -> dict:
    geo = haversine(a_lat, a_lng, b_lat, b_lng)
    km = round(geo * D.ROAD_FACTOR, 1)
    minutes = int(round(km / D.AVG_SPEED_KMH * 60)) if km else 0
    return {"distance_km": km, "duration_min": minutes}


def _is_notturno(pickup: Optional[datetime]) -> bool:
    if not pickup:
        return False
    return pickup.hour >= 22 or pickup.hour < 6


def _is_festivo(pickup: Optional[datetime]) -> bool:
    return bool(pickup) and pickup.weekday() == 6   # domenica (festivi approssimati)


def ncc_price(listino: dict, classe: str, route: dict, pickup: Optional[datetime], ritorno: Optional[dict]) -> float:
    cl = (listino.get("classi") or {}).get(classe) or D.DEFAULT_LISTINO.get(classe, D.DEFAULT_LISTINO["standard"])
    base = float(cl.get("base", 8)) + float(cl.get("per_km", 1.4)) * float(route.get("distance_km", 0))
    if ritorno and ritorno.get("distance_km"):
        leg2 = float(cl.get("base", 8)) + float(cl.get("per_km", 1.4)) * float(ritorno.get("distance_km", 0))
        base += leg2 * (1 - float(listino.get("sconto_ar_pct", 0)) / 100.0)
    if _is_notturno(pickup):
        base *= (1 + float(listino.get("notturno_pct", 0)) / 100.0)
    if _is_festivo(pickup):
        base *= (1 + float(listino.get("festivo_pct", 0)) / 100.0)
    return round(base, 2)


def taxi_estimate(route: dict, pickup: Optional[datetime]) -> float:
    tf = D.TAXI_TARIFFA
    amt = tf["scatto"] + tf["per_km"] * float(route.get("distance_km", 0))
    if _is_notturno(pickup):
        amt *= (1 + tf["notturno_pct"] / 100.0)
    if _is_festivo(pickup):
        amt *= (1 + tf["festivo_pct"] / 100.0)
    return round(max(amt, tf["min_corsa"]), 2)


def _compatible_providers(tipo: str, classe: str, lat: Optional[float], lng: Optional[float]) -> List[dict]:
    res = db.rpc("driver_compatible_providers", {"p_tipo": tipo, "p_classe": classe, "p_lat": lat, "p_lng": lng}).execute()
    return res.data or []


def _cancellation_outcome(pickup: Optional[datetime], prezzo: float) -> dict:
    if not pickup:
        return {"charge": 0.0, "refund_pct": 100}
    delta = (pickup - now_utc()).total_seconds() / 60.0
    if delta >= D.CANCELLATION["full_refund_hours"] * 60:
        return {"charge": 0.0, "refund_pct": 100, "band": ">4h"}
    if delta >= D.CANCELLATION["full_charge_under_min"]:
        return {"charge": round(prezzo * 0.5, 2), "refund_pct": 50, "band": "<4h"}
    return {"charge": round(prezzo, 2), "refund_pct": 0, "band": "<30min"}


def _richiesta_out(row: dict) -> dict:
    brief = row.get("brief_answers") or {}
    out = dict(brief)
    out.update({
        "richiesta_id": row["id"],
        "cliente_id": row["client_id"],
        "categoria": "MOBILITA",
        "servizio": "DRIVER",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    })
    return out


# ---------------- config / geocode / estimate ----------------
@router.get("/driver/config")
async def get_config(user=Depends(get_current_user)):
    return {
        "vehicle_classes": D.VEHICLE_CLASSES, "shortcuts": D.SHORTCUTS, "ritocco_motivi": D.RITOCCO_MOTIVI,
        "special_needs": D.SPECIAL_NEEDS, "cancellation": D.CANCELLATION, "min_age": D.MIN_UNACCOMPANIED_AGE,
        "included_wait_min": D.INCLUDED_WAIT_MIN, "taxi_tariffa": D.TAXI_TARIFFA, "fee_pct": await fee_pct(),
    }


class GeocodeIn(BaseModel):
    query: str


@router.post("/driver/geocode")
async def geocode(body: GeocodeIn, user=Depends(get_current_user)):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": body.query, "format": "json", "limit": 1, "countrycodes": "it"},
                         headers={"User-Agent": "JOBBY-app/1.0"}, timeout=8)
        js = r.json()
        if js:
            return {"lat": float(js[0]["lat"]), "lng": float(js[0]["lon"]),
                    "label": js[0].get("display_name", body.query)[:80]}
    except Exception:
        pass
    return {"lat": 45.6669, "lng": 12.2433, "label": body.query, "fallback": True}


class EstimateIn(BaseModel):
    tipo: str = "ncc"
    classe: str = "standard"
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    pickup_at: str = ""
    ritorno: Optional[dict] = None


@router.post("/driver/estimate")
async def estimate(body: EstimateIn, user=Depends(get_current_user)):
    route = estimate_route(body.from_lat, body.from_lng, body.to_lat, body.to_lng)
    pickup = _parse(body.pickup_at)
    ritorno_route = None
    if body.ritorno:
        ritorno_route = estimate_route(body.to_lat, body.to_lng, body.from_lat, body.from_lng)
    if body.tipo == "taxi":
        est = taxi_estimate(route, pickup)
        provs = _compatible_providers("taxi", body.classe, body.from_lat, body.from_lng)
        return {"route": route, "tipo": "taxi", "estimate": est, "providers": len(provs),
                "note": "Tariffa regolata dal tassametro ufficiale. Importo finale a fine corsa."}
    provs = _compatible_providers("ncc", body.classe, body.from_lat, body.from_lng)
    prices = [ncc_price(pp.get("listino") or {}, body.classe, route, pickup, ritorno_route) for pp in provs]
    return {"route": route, "ritorno_route": ritorno_route, "tipo": "ncc", "providers": len(provs),
            "min": round(min(prices), 2) if prices else None, "max": round(max(prices), 2) if prices else None}


# ---------------- listino / veicoli / autorizzazione provider ----------------
@router.get("/driver/listino")
async def get_listino(user=Depends(get_current_user)):
    row = db.table("profiles_provider").select("price_list, documents").eq("user_id", user["id"]).limit(1).execute()
    price_list = row.data[0].get("price_list") if row.data else {}
    documents = (row.data[0].get("documents") if row.data else {}) or {}
    drv = price_list.get("driver", {}) if isinstance(price_list, dict) else {}
    return {
        "driver_tipo": drv.get("tipo", "ncc"), "listino": drv.get("listino"), "vehicles": drv.get("vehicles", []),
        "authorization": {"numero": documents.get("driver_auth_numero"),
                          "verified": bool(documents.get("driver_auth_verified")),
                          "uploaded": bool(documents.get("driver_auth_doc"))},
    }


class ListinoIn(BaseModel):
    tipo: str = "ncc"
    classi: dict = {}                # {standard: {base, per_km, per_hour, attesa_per_hour}, ...}
    notturno_pct: float = 0.0
    festivo_pct: float = 0.0
    sconto_ar_pct: float = 0.0
    raggio_km: float = 30.0
    trasporto_minori: bool = False
    animali: bool = False
    fasce: List[str] = []


@router.put("/driver/listino")
async def set_listino(body: ListinoIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    row = db.table("profiles_provider").select("price_list, skills").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    current = row.data[0].get("price_list")
    price_list = dict(current) if isinstance(current, dict) else {}
    drv = dict(price_list.get("driver", {}))
    drv["tipo"] = body.tipo
    drv["listino"] = body.dict()
    price_list["driver"] = drv
    skills = sorted(set((row.data[0].get("skills") or []) + ["driver"]))
    db.table("profiles_provider").update({"price_list": price_list, "skills": skills}).eq("user_id", user["id"]).execute()
    return {"driver_tipo": body.tipo, "listino": drv["listino"]}


class VehicleIn(BaseModel):
    classe: str
    targa: str
    posti: int = 4
    foto: str = ""
    assicurazione: bool = False
    modello: str = ""


@router.post("/driver/vehicles")
async def add_vehicle(body: VehicleIn, user=Depends(get_current_user)):
    if user.get("role") not in ("provider", "both"):
        raise HTTPException(status_code=403, detail="providers_only")
    row = db.table("profiles_provider").select("price_list").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    current = row.data[0].get("price_list")
    price_list = dict(current) if isinstance(current, dict) else {}
    drv = dict(price_list.get("driver", {}))
    vehicles = list(drv.get("vehicles", []))
    # I veicoli sono voci di una lista jsonb, non righe di una tabella
    # dedicata — id generato qui lato Python, come già fatto in Mongo.
    v = {"vehicle_id": f"veh_{uuid.uuid4().hex[:10]}", **body.dict()}
    vehicles.append(v)
    drv["vehicles"] = vehicles
    price_list["driver"] = drv
    db.table("profiles_provider").update({"price_list": price_list}).eq("user_id", user["id"]).execute()
    return v


@router.delete("/driver/vehicles/{vid}")
async def del_vehicle(vid: str, user=Depends(get_current_user)):
    row = db.table("profiles_provider").select("price_list").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="not_found")
    current = row.data[0].get("price_list")
    price_list = dict(current) if isinstance(current, dict) else {}
    drv = dict(price_list.get("driver", {}))
    vehicles = [v for v in drv.get("vehicles", []) if v.get("vehicle_id") != vid]
    drv["vehicles"] = vehicles
    price_list["driver"] = drv
    db.table("profiles_provider").update({"price_list": price_list}).eq("user_id", user["id"]).execute()
    return {"deleted": True}


class AuthIn(BaseModel):
    tipo: str = "ncc"           # ncc autorizzazione | taxi licenza
    numero: str
    image: str


@router.post("/driver/authorization")
async def upload_auth(body: AuthIn, user=Depends(get_current_user)):
    if not body.image.strip() or not body.numero.strip():
        raise HTTPException(status_code=400, detail="invalid_authorization")
    row = db.table("profiles_provider").select("documents, price_list").eq("user_id", user["id"]).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=400, detail="provider_profile_missing")
    documents = dict(row.data[0].get("documents") or {})
    documents.update({"driver_auth_numero": body.numero, "driver_auth_doc": body.image,
                      "driver_auth_verified": False, "driver_auth_uploaded_at": now_iso()})
    current = row.data[0].get("price_list")
    price_list = dict(current) if isinstance(current, dict) else {}
    drv = dict(price_list.get("driver", {}))
    drv["tipo"] = body.tipo
    price_list["driver"] = drv
    db.table("profiles_provider").update({"documents": documents, "price_list": price_list}).eq("user_id", user["id"]).execute()
    return {"uploaded": True}


# ---------------- richiesta CRUD ----------------
class Waypoint(BaseModel):
    label: str = ""
    lat: float
    lng: float


class RichiestaIn(BaseModel):
    tipo: str = "ncc"                 # ncc | taxi
    classe: str = "standard"
    partenza: Waypoint
    destinazione: Waypoint
    pickup_at: str
    flight_number: str = ""
    passeggeri: int = 1
    bagagli: int = 0
    passeggero_nome: str = ""         # se diverso dal pagante
    passeggero_tel: str = ""
    minore: bool = False
    minore_consenso: bool = False
    special: List[str] = []
    ritorno: Optional[dict] = None    # {pickup_at}
    note: str = ""
    target_provider_id: str = ""      # richiesta diretta a un driver specifico


@router.post("/driver/richieste")
async def create_richiesta(body: RichiestaIn, user=Depends(get_current_user)):
    if body.tipo not in ("ncc", "taxi"):
        raise HTTPException(status_code=400, detail="invalid_tipo")
    if body.minore and not body.minore_consenso:
        raise HTTPException(status_code=400, detail="minor_consent_required")
    route = estimate_route(body.partenza.lat, body.partenza.lng, body.destinazione.lat, body.destinazione.lng)
    pickup = _parse(body.pickup_at)
    ritorno = None
    if body.ritorno:
        rr = estimate_route(body.destinazione.lat, body.destinazione.lng, body.partenza.lat, body.partenza.lng)
        ritorno = {**rr, "pickup_at": body.ritorno.get("pickup_at", "")}
    taxi_est = taxi_estimate(route, pickup) if body.tipo == "taxi" else None

    brief = {
        "tipo": body.tipo, "classe": body.classe,
        "partenza": body.partenza.dict(), "destinazione": body.destinazione.dict(),
        "route": route, "ritorno": ritorno, "pickup_at": body.pickup_at,
        "flight_number": body.flight_number, "passeggeri": body.passeggeri, "bagagli": body.bagagli,
        "passeggero": {"nome": body.passeggero_nome, "tel": body.passeggero_tel} if body.passeggero_nome else None,
        "minore": body.minore, "minore_consenso": body.minore_consenso, "special": body.special,
        "taxi_estimate": taxi_est, "note": body.note,
        "stato": "pubblicata", "provider_invitati": [], "proposte": [], "provider_scelto": None,
        "extra": [], "tracking": None, "pagamento": {"stato": "none"}, "recensione": None,
    }

    invited: List[dict] = []
    seen = set()
    if body.target_provider_id:
        tp = db.table("profiles_provider").select("skills").eq("user_id", body.target_provider_id).limit(1).execute()
        if tp.data and "driver" in (tp.data[0].get("skills") or []):
            invited.append({"provider_id": body.target_provider_id, "at": now_iso(), "status": "invited", "direct": True})
            seen.add(body.target_provider_id)
    try:
        provs = _compatible_providers(body.tipo, body.classe, body.partenza.lat, body.partenza.lng)
    except Exception:
        provs = []
    for p in provs[:25]:
        pid = p["provider_id"]
        if pid in seen:
            continue
        seen.add(pid)
        invited.append({"provider_id": pid, "at": now_iso(), "status": "invited", "auto": True})
    if invited:
        brief["provider_invitati"] = invited
        brief["stato"] = "in_matching"
        brief["scade_at"] = (now_utc() + timedelta(hours=D.PROPOSAL_WINDOW_HOURS)).isoformat()

    row = {
        "client_id": user["id"], "category_id": _category_id(),
        "title": f"Driver — {body.tipo.upper()}", "description": body.note,
        "status": "published", "address": body.partenza.label or "",
        "location": to_geography_point(body.partenza.lat, body.partenza.lng),
        "scheduled_at": parse_scheduled_at(body.pickup_at),
        "platform_fee_pct": await fee_pct(),
        "brief_answers": brief,
    }
    res = db.table("missions").insert(row).execute()
    created = res.data[0]

    for inv in invited:
        await notify(inv["provider_id"], "driver_invito", "🚘 Nuova richiesta corsa",
                    f"{body.partenza.label} → {body.destinazione.label}", "driver", created["id"])
    return _richiesta_out(created)


@router.get("/driver/richieste")
async def my_richieste(user=Depends(get_current_user)):
    res = (
        db.table("missions").select("*")
        .eq("client_id", user["id"]).eq("category_id", _category_id())
        .order("created_at", desc=True).limit(100).execute()
    )
    return [_richiesta_out(r) for r in (res.data or [])]


def _preview_driver_price(brief: dict, uid: str) -> Optional[float]:
    """Stesso identico calcolo di propose() (vedi sopra) ma usato per
    mostrare al provider invitato-non-ancora-proposto il prezzo PRIMA che
    prema "Accetta al prezzo di listino" (BLOCCO 10: segnalato dall'utente,
    stesso bug di richieste.py — il provider doveva accettare alla cieca)."""
    if brief.get("tipo") == "ncc":
        prov_row = db.table("profiles_provider").select("price_list").eq("user_id", uid).limit(1).execute()
        pdata = prov_row.data[0] if prov_row.data else {}
        price_list = pdata.get("price_list")
        drv = price_list.get("driver", {}) if isinstance(price_list, dict) else {}
        lst = drv.get("listino") or {}
        if not lst:
            return None
        classe = brief.get("classe", "standard")
        pickup = _parse(brief.get("pickup_at", ""))
        return ncc_price(lst, classe, brief.get("route", {}), pickup, brief.get("ritorno"))
    return brief.get("taxi_estimate")


@router.get("/driver/richieste/{rid}")
async def get_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    uid = user["id"]
    is_owner = row["client_id"] == uid
    is_confirmed = brief.get("provider_scelto") == uid
    is_invited = uid in [p.get("provider_id") for p in brief.get("provider_invitati", [])]
    if not (is_owner or is_invited or is_confirmed):
        raise HTTPException(status_code=403, detail="forbidden")
    out = _richiesta_out(row)
    out["role"] = "client" if is_owner else "provider"
    if not is_owner:
        already_proposed = uid in [p.get("provider_id") for p in brief.get("proposte", [])]
        if not already_proposed and brief.get("stato") in STATI_APERTI:
            try:
                out["prezzo_listino"] = _preview_driver_price(brief, uid)
            except Exception:
                out["prezzo_listino"] = None
    return out


@router.post("/driver/richieste/{rid}/cancel")
async def cancel_richiesta(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") in ("completata", "recensita", "annullata"):
        raise HTTPException(status_code=400, detail="already_closed")
    prezzo = float(brief.get("prezzo_finale", 0) or 0)
    outcome = _cancellation_outcome(_parse(brief.get("pickup_at", "")), prezzo)
    # BLOCCO 5 (spec4_pg.py): `outcome` (fascia/percentuale di
    # driver_config.CANCELLATION — 4h/30min, non le soglie generiche di
    # spec4_config usate dalle altre 3 verticali) ora pilota davvero il
    # rimborso, invece di restare solo informativo come nel Blocco 2/3 (vedi
    # docstring modulo). `outcome["charge"]` diventa indennizzo al driver
    # (rilasciato per intero, JOBBY non trattiene fee su questa transazione
    # — stessa scelta già documentata sopra per la fascia "<30min").
    pagamento = brief.get("pagamento") or {}
    settlement = None
    if pagamento.get("stato") == "held" and (pagamento.get("holds") or pagamento.get("payment_intent_id")):
        price_agreed = float(row.get("price_agreed") or prezzo or 0)
        indennizzo = min(round(float(outcome.get("charge") or 0), 2), price_agreed)
        refund_amount = round(price_agreed - indennizzo, 2)
        settled = S4.settle_gateway_cancellation(row, pagamento, refund_amount, indennizzo, 0.0,
                                                 f"driver_{outcome.get('band', 'na')}")
        pagamento.update(settled["pagamento_updates"])
        brief["pagamento"] = pagamento
        settlement = {"refund_amount": settled["refund_amount"], "indennizzo": settled["indennizzo"],
                     "band": outcome.get("band")}
        if indennizzo > 0:
            S4.record_strike_if_late(row["client_id"], rid, "late", S4.spec4_config())
    brief["stato"] = "annullata"
    brief["cancellazione"] = outcome
    db.table("missions").update({"status": "cancelled", "brief_answers": brief}).eq("id", rid).execute()
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "driver_annullata", "Corsa annullata",
                    "Il cliente ha annullato la corsa.", "driver", rid)
    return {**outcome, "settlement": settlement}


# ---------------- lato provider ----------------
@router.get("/driver/incoming")
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
    drv = price_list.get("driver", {}) if isinstance(price_list, dict) else {}
    lst = drv.get("listino") or {}

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
        pickup = _parse(brief.get("pickup_at", ""))
        if brief.get("tipo") == "ncc":
            item["suggested_price"] = ncc_price(lst, brief.get("classe", "standard"), brief.get("route", {}), pickup, brief.get("ritorno"))
        else:
            item["taxi_estimate"] = brief.get("taxi_estimate")
        item["my_proposal"] = next((p for p in brief.get("proposte", []) if p.get("provider_id") == uid), None)
        out.append(item)
    return out


class ProposeIn(BaseModel):
    accept: bool
    prezzo: Optional[float] = None
    ritocco_motivo: str = ""
    message: str = ""


@router.post("/driver/richieste/{rid}/propose")
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

    prov_row = db.table("profiles_provider").select("price_list, business_data, avg_rating, trust_score").eq("user_id", uid).limit(1).execute()
    pdata = prov_row.data[0] if prov_row.data else {}
    price_list = pdata.get("price_list")
    drv = price_list.get("driver", {}) if isinstance(price_list, dict) else {}
    lst = drv.get("listino") or {}
    vehicles = drv.get("vehicles") or []
    business_data = pdata.get("business_data") or {}
    classe = brief.get("classe", "standard")
    pickup = _parse(brief.get("pickup_at", ""))
    vehicle = next((v for v in vehicles if v.get("classe") == classe), {})

    if brief.get("tipo") == "ncc":
        base = ncc_price(lst, classe, brief.get("route", {}), pickup, brief.get("ritorno"))
        prezzo = round(float(body.prezzo), 2) if body.prezzo is not None else base
        ritocco = None
        if prezzo > base:
            if body.ritocco_motivo not in [m["id"] for m in D.RITOCCO_MOTIVI]:
                raise HTTPException(status_code=400, detail="ritocco_requires_reason")
            ritocco = {"delta": round(prezzo - base, 2), "motivo": body.ritocco_motivo}
    else:
        prezzo = brief.get("taxi_estimate")
        ritocco = None

    proposal = {
        "provider_id": uid, "provider_nome": business_data.get("business_name") or user.get("full_name", ""),
        "provider_rating": pdata.get("avg_rating") or 0, "provider_trust": pdata.get("trust_score") or 0,
        "vehicle": vehicle, "classe": classe, "prezzo": prezzo, "ritocco": ritocco,
        "is_estimate": brief.get("tipo") == "taxi", "message": body.message, "at": now_iso(),
    }
    proposte = [p for p in brief.get("proposte", []) if p.get("provider_id") != uid]
    proposte.append(proposal)
    brief["proposte"] = proposte
    brief["stato"] = "con_proposte"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    prezzo_txt = f"€{prezzo:.2f}" if isinstance(prezzo, (int, float)) else "una stima"
    await notify(row["client_id"], "driver_proposta", "Nuova proposta corsa",
                f"{proposal['provider_nome']}: {prezzo_txt}", "driver", rid)
    return proposal


# ---------------- conferma + esecuzione (Blocco 3 — vedi docstring modulo) ----------------
async def _add_hold(rid: str, brief: dict, kind: str, amount: float, client: dict, provider_id: str) -> dict:
    """Stesso pattern di artigiani.py's _add_hold (vedi quel modulo per il
    dettaglio commentato) — qui un solo binario, sempre Stripe Connect."""
    if amount <= 0:
        return brief
    pagamento = brief.get("pagamento") or {}
    if pagamento.get("stato") != "held":
        pagamento = {"holds": [], "totale_bloccato": 0.0, "fee_totale": 0.0, "payout_totale": 0.0, "stato": "held"}

    prov_row = db.table("profiles_provider").select("stripe_payouts_enabled").eq("user_id", provider_id).limit(1).execute()
    if not prov_row.data or not prov_row.data[0].get("stripe_payouts_enabled"):
        raise HTTPException(status_code=400, detail="provider_not_onboarded")
    customer_id = client.get("stripe_customer_id")
    pm_id = client.get("default_payment_method_id")
    if not customer_id or not pm_id:
        raise HTTPException(status_code=400, detail="client_payment_method_missing")

    pct = await fee_pct()
    jobby_fee = round(amount * pct / 100.0, 2)
    payout = round(amount - jobby_fee, 2)

    db.table("missions").update({"provider_id": provider_id, "price_agreed": amount}).eq("id", rid).execute()
    charge = SP.charge_hold(customer_id, pm_id, amount, {"mission_id": rid, "category": "driver", "kind": kind})
    db.rpc("create_escrow_hold", {
        "p_mission_id": rid, "p_gateway_transaction_id": charge["payment_intent_id"],
        "p_gateway_response": {"status": charge["status"], "kind": kind}, "p_gateway_name": "stripe",
    }).execute()

    pagamento["holds"].append({"kind": kind, "amount": amount, "payment_intent_id": charge["payment_intent_id"], "at": now_iso()})
    pagamento["totale_bloccato"] = round(pagamento["totale_bloccato"] + amount, 2)
    pagamento["fee_totale"] = round(pagamento["fee_totale"] + jobby_fee, 2)
    pagamento["payout_totale"] = round(pagamento["payout_totale"] + payout, 2)
    db.table("missions").update({
        "price_agreed": pagamento["totale_bloccato"], "platform_fee": pagamento["fee_totale"], "provider_payout": pagamento["payout_totale"],
    }).eq("id", rid).execute()

    brief["pagamento"] = pagamento
    return brief


async def _finalize_release(rid: str, brief: dict) -> dict:
    """Rilascia il totale bloccato in tutte le fasi al driver. release_escrow
    marca 'released' TUTTE le righe payments di tipo escrow_hold della
    missione in un colpo solo — va chiamata una sola volta."""
    pagamento = brief.get("pagamento") or {}
    provider_id = brief.get("provider_scelto")
    if pagamento.get("stato") == "held":
        prov_row = db.table("profiles_provider").select("stripe_connect_account_id").eq("user_id", provider_id).limit(1).execute()
        acct_id = prov_row.data[0].get("stripe_connect_account_id") if prov_row.data else None
        if not acct_id:
            raise HTTPException(status_code=400, detail="provider_not_onboarded")
        payout = float(pagamento.get("payout_totale") or 0)
        if payout > 0:
            transfer = SP.transfer_to_provider(acct_id, payout, {"mission_id": rid, "category": "driver"})
            db.rpc("release_escrow", {
                "p_mission_id": rid, "p_gateway_transaction_id": transfer["transfer_id"],
                "p_gateway_response": {}, "p_gateway_name": "stripe",
            }).execute()
            pagamento["transfer_id"] = transfer["transfer_id"]
        pagamento["stato"] = "released"
        brief["pagamento"] = pagamento
    brief["stato"] = "completata"
    return brief


class ConfirmIn(BaseModel):
    provider_id: str


@router.post("/driver/richieste/{rid}/confirm")
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

    brief["provider_scelto"] = provider_id
    if brief.get("tipo") != "taxi":
        # NCC: prezzo noto ora, si blocca subito.
        amount = float(proposal.get("prezzo") or 0)
        brief = await _add_hold(rid, brief, "corsa", amount, user, provider_id)
    # TAXI: nessun hold qui — il tassametro decide l'importo a fine corsa (vedi /pay).
    brief["stato"] = "confermata"
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()

    await notify(provider_id, "driver_confermata", "Corsa confermata",
                "Il cliente ha confermato la tua proposta.", "driver", rid)
    await notify(row["client_id"], "driver_confermata", "Corsa confermata",
                "Hai confermato la corsa.", "driver", rid)
    return {"stato": "confermata", "pagamento": brief.get("pagamento")}


@router.post("/driver/richieste/{rid}/depart")
async def depart(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "confermata":
        raise HTTPException(status_code=400, detail="not_confirmed")
    tracking = {"started_at": now_iso(), "lat": None, "lng": None}
    brief["stato"] = "in_corso"
    brief["tracking"] = tracking
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "driver_in_arrivo", "Il driver è in arrivo",
                "Puoi seguire la corsa in tempo reale.", "driver", rid)
    if (brief.get("passeggero") or {}).get("tel"):
        await notify(row["client_id"], "driver_passeggero", "Driver in arrivo",
                    f"{user.get('full_name', '')} sta arrivando.", "driver", rid)
    return tracking


class TrackIn(BaseModel):
    lat: float
    lng: float


@router.post("/driver/richieste/{rid}/track")
async def track(rid: str, body: TrackIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    tracking = dict(brief.get("tracking") or {})
    tracking.update({"lat": body.lat, "lng": body.lng, "updated_at": now_iso()})
    brief["tracking"] = tracking
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"ok": True}


class ExtraIn(BaseModel):
    tipo: str            # attesa | fermata | cambio
    importo: float
    motivo: str = ""


@router.post("/driver/richieste/{rid}/extra")
async def add_extra(rid: str, body: ExtraIn, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") != "in_corso":
        raise HTTPException(status_code=400, detail="not_in_progress")
    # Solo la creazione è pura (nessun blocco fondi qui): l'approvazione
    # invece tocca soldi (we.hold) ed è uno stub, vedi sotto.
    extra = {"extra_id": f"ex_{uuid.uuid4().hex[:10]}", "tipo": body.tipo, "importo": round(body.importo, 2),
             "motivo": body.motivo, "stato": "pending", "at": now_iso()}
    extras = list(brief.get("extra", []))
    extras.append(extra)
    brief["extra"] = extras
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "driver_extra", "Extra da approvare",
                f"{body.tipo}: €{body.importo:.2f}", "driver", rid)
    return extra


class ExtraApprove(BaseModel):
    extra_id: str
    approve: bool


@router.post("/driver/richieste/{rid}/extra/approve")
async def approve_extra(rid: str, body: ExtraApprove, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    extras = brief.get("extra") or []
    extra = next((e for e in extras if e["extra_id"] == body.extra_id), None)
    if not extra or extra.get("stato") != "pending":
        raise HTTPException(status_code=404, detail="extra_not_found")

    if body.approve:
        brief = await _add_hold(rid, brief, "extra", float(extra["importo"]), user, brief["provider_scelto"])
        extra["stato"] = "approvato"
    else:
        extra["stato"] = "rifiutato"
    brief["extra"] = [extra if e["extra_id"] == extra["extra_id"] else e for e in extras]
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(brief["provider_scelto"], "driver_extra", "Extra " + ("approvato" if body.approve else "rifiutato"),
                f"Il cliente ha {'approvato' if body.approve else 'rifiutato'} l'extra: {extra['tipo']}", "driver", rid)
    return extra


@router.post("/driver/richieste/{rid}/noshow")
async def noshow(rid: str, user=Depends(get_current_user)):
    # Segnalato dal driver: il passeggero non si è presentato. Nessuna regola
    # esplicita nel sistema Emergent per l'importo della penale — vedi
    # docstring modulo per l'assunzione di prodotto adottata qui.
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or (res.data[0].get("brief_answers") or {}).get("provider_scelto") != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("stato") not in ("confermata", "in_corso"):
        raise HTTPException(status_code=400, detail="not_active")

    if (brief.get("pagamento") or {}).get("stato") != "held":
        client_res = db.table("users").select("*").eq("id", row["client_id"]).limit(1).execute()
        client = client_res.data[0] if client_res.data else {"id": row["client_id"]}
        penale = D.TAXI_TARIFFA["min_corsa"]
        brief = await _add_hold(rid, brief, "penale_noshow", penale, client, user["id"])
    brief = await _finalize_release(rid, brief)
    brief["noshow"] = True
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    await notify(row["client_id"], "driver_noshow", "Corsa chiusa per mancata presentazione",
                "Il driver ha segnalato che non ti sei presentato. La corsa è stata chiusa.", "driver", rid)
    return {"stato": "completata", "noshow": True}


class CompleteIn(BaseModel):
    meter_amount: Optional[float] = None       # taxi: importo finale tassametro


@router.post("/driver/richieste/{rid}/complete")
async def complete(rid: str, body: CompleteIn, user=Depends(get_current_user)):
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

    if brief.get("tipo") == "taxi":
        if body.meter_amount is None or body.meter_amount <= 0:
            raise HTTPException(status_code=400, detail="meter_amount_required")
        brief["taxi_meter_finale"] = round(float(body.meter_amount), 2)
        brief["stato"] = "in_pagamento"
        await notify(row["client_id"], "driver_completata", "Corsa terminata",
                    f"Importo tassametro: €{brief['taxi_meter_finale']:.2f}. Completa il pagamento.", "driver", rid)
    else:
        brief = await _finalize_release(rid, brief)
        await notify(row["client_id"], "driver_completata", "Corsa completata",
                    "La corsa è stata completata.", "driver", rid)
        if brief.get("provider_scelto"):
            await notify(brief["provider_scelto"], "driver_completata", "Corsa completata",
                        "Hai completato la corsa.", "driver", rid)
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"stato": brief["stato"]}


@router.post("/driver/richieste/{rid}/pay")
async def pay_taxi(rid: str, user=Depends(get_current_user)):
    res = db.table("missions").select("*").eq("id", rid).limit(1).execute()
    if not res.data or res.data[0]["client_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="not_found")
    row = res.data[0]
    brief = row.get("brief_answers") or {}
    if brief.get("tipo") != "taxi":
        raise HTTPException(status_code=400, detail="not_taxi")
    if brief.get("stato") != "in_pagamento":
        raise HTTPException(status_code=400, detail="not_ready")
    meter = float(brief.get("taxi_meter_finale") or 0)
    if meter <= 0:
        raise HTTPException(status_code=400, detail="invalid_meter")

    brief = await _add_hold(rid, brief, "tassametro", meter, user, brief["provider_scelto"])
    brief = await _finalize_release(rid, brief)
    db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    if brief.get("provider_scelto"):
        await notify(brief["provider_scelto"], "driver_completata", "Pagamento ricevuto",
                    "Il cliente ha completato il pagamento della corsa.", "driver", rid)
    return {"stato": "completata"}


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.post("/driver/richieste/{rid}/review")
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
                       dimension="quality", notes=f"Recensione {body.rating}★ su richiesta driver {rid}")

    await notify(provider_id, "driver_completata", "Nuova recensione",
                f"Hai ricevuto {body.rating}★ dal cliente.", "driver", rid)
    return brief["recensione"]


# ---------------- amministrazione ----------------
@router.get("/admin/driver/richieste")
async def admin_richieste(_=Depends(require_admin)):
    res = (
        db.table("missions").select("*")
        .eq("category_id", _category_id()).eq("status", "published")
        .order("created_at", desc=True).limit(200).execute()
    )
    out = []
    for row in (res.data or []):
        brief = row.get("brief_answers") or {}
        if brief.get("stato") not in STATI_APERTI:
            continue
        invitati = brief.get("provider_invitati", [])
        pickup = _parse(brief.get("pickup_at", ""))
        partenza = brief.get("partenza") or {}
        try:
            provs = _compatible_providers(brief.get("tipo", "ncc"), brief.get("classe", "standard"), partenza.get("lat"), partenza.get("lng"))
        except Exception:
            provs = []
        item = _richiesta_out(row)
        item["compatible"] = [{
            "provider_id": p["provider_id"], "nome": p.get("business_name") or p.get("full_name"),
            "distance": p.get("distance_km"), "rating": p.get("avg_rating") or 0, "trust": p.get("trust_score") or 0,
            "auth_ok": bool(p.get("auth_verified")),
            "price": (ncc_price(p.get("listino") or {}, brief.get("classe", "standard"), brief.get("route", {}), pickup, brief.get("ritorno"))
                      if brief.get("tipo") == "ncc" else brief.get("taxi_estimate")),
            "invited": p["provider_id"] in [i.get("provider_id") for i in invitati],
            "invite_status": next((i.get("status") for i in invitati if i.get("provider_id") == p["provider_id"]), None),
            "confirmed": brief.get("provider_scelto") == p["provider_id"],
        } for p in provs]
        out.append(item)
    return out


class InviteIn(BaseModel):
    provider_ids: List[str]


@router.post("/admin/driver/richieste/{rid}/invite")
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
                    await notify(pid, "driver_invito", "Nuova richiesta corsa",
                                "Hai ricevuto di nuovo una richiesta di corsa.", "driver", rid)
            continue
        invitati.append({"provider_id": pid, "at": now_iso(), "status": "invited"})
        new_count += 1
        await notify(pid, "driver_invito", "Nuova richiesta corsa",
                    "Hai ricevuto una richiesta di corsa compatibile.", "driver", rid)
    if new_count or reset_count:
        brief["provider_invitati"] = invitati
        brief["stato"] = "in_matching"
        db.table("missions").update({"brief_answers": brief}).eq("id", rid).execute()
    return {"invited": new_count, "reactivated": reset_count}


class AuthDecisionIn(BaseModel):
    verified: bool


@router.post("/admin/driver/{user_id}/authorization")
async def admin_auth(user_id: str, body: AuthDecisionIn, _=Depends(require_admin)):
    row = db.table("profiles_provider").select("documents").eq("user_id", user_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="not_found")
    documents = dict(row.data[0].get("documents") or {})
    documents["driver_auth_verified"] = body.verified
    db.table("profiles_provider").update({"documents": documents}).eq("user_id", user_id).execute()
    msg = "Autorizzazione/licenza verificata (badge attivo)." if body.verified else "Autorizzazione non validata. Ricaricala."
    await notify(user_id, "driver_auth", "Verifica autorizzazione", msg, "profile", user_id)
    return {"user_id": user_id, "driver_auth_verified": body.verified}


class FeeIn(BaseModel):
    fee_pct: float


# BLOCCO 9: vedi nota gemella in routers/richieste.py — mancava un GET per
# rileggere la commissione già impostata.
@router.get("/admin/driver/fee")
async def get_fee(_=Depends(require_admin)):
    return {"fee_pct": await fee_pct()}


@router.post("/admin/driver/fee")
async def set_fee(body: FeeIn, _=Depends(require_admin)):
    db.table("app_settings").upsert({"key": _FEE_SETTING_KEY, "value": float(body.fee_pct)}).execute()
    return {"fee_pct": body.fee_pct}
