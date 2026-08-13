"""BLOCCO 7b (jobby-web -> client puro) - nuovo endpoint pubblico di sola
lettura per le categorie di servizio attive. Prima non esisteva alcun router
che esponesse `service_categories` in lettura: jobby-web (via
app/api/categories/route.ts) leggeva la tabella direttamente via Supabase,
bypassando questo backend. Stesso identico contratto di quella route (stessi
campi, stesso ordinamento, richiede solo un utente autenticato qualsiasi
ruolo) cosi la conversione a proxy non cambia comportamento per chi la
chiama gia oggi."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_pg import db
from deps_pg import get_current_user, require_admin

router = APIRouter()


@router.get("/categories")
async def list_categories(_=Depends(get_current_user)):
    res = (
        db.table("service_categories")
        .select("id, slug, name_it, name_en, icon, category_type, requires_kyc, questions")
        .eq("is_active", True)
        .order("category_type")
        .order("sort_order")
        .order("name_en")
        .execute()
    )
    return {"categories": res.data or []}


# BLOCCO 9 (fix bug "mancano le categorie/prossimita/pagamenti" nell'app
# mobile) - la app Expo (Jobby_Emergent/frontend) NON usa /categories qui
# sopra: quella route e' stata riscritta nel Blocco 7b con un contratto
# pensato solo per jobby-web ({"categories": [...]} piatto). L'app mobile
# (src/api.ts -> app/(tabs)/index.tsx CustomerHome/ProviderHome) si aspetta
# ancora il contratto raggruppato dell'epoca Emergent/Mongo (catalog.py,
# ora ritirato): {standard, proximity, payment, providers_online}, con
# cat_id/label/emoji per tile. Invece di duplicare quel vecchio formato o
# rompere jobby-web cambiando /categories, si espone qui una seconda route
# dedicata alla app, con lo stesso identico dato sorgente (service_categories)
# ma raggruppato nella forma che il frontend mobile legge davvero (verificato
# via grep in app/(tabs)/index.tsx: c.standard/c.proximity/c.payment/
# c.providers_online, x.cat_id, x.label[lang]).
#
# _CAT_ID_OVERRIDES: la app ha un solo routing speciale hardcoded per cat_id
# (vedi openCategory() in index.tsx: "pulizie"/"babysitting"/"driver"/
# "artigiani" aprono il configuratore dedicato di quella verticale). Lo slug
# Postgres storico per Pulizie e' rimasto "housekeeping" (mai rinominato,
# vedi commento in routers/richieste.py) quindi va tradotto qui; gli altri
# 3 slug coincidono gia'.
_CAT_ID_OVERRIDES = {"housekeeping": "pulizie"}


def _shape_for_app(row: dict) -> dict:
    slug = row["slug"]
    return {
        "cat_id": _CAT_ID_OVERRIDES.get(slug, slug),
        "slug": slug,
        "emoji": row.get("icon") or "🔹",
        "label": {"it": row.get("name_it") or slug, "en": row.get("name_en") or slug},
        "questions": row.get("questions") or [],
    }


@router.get("/categories/home")
async def list_categories_for_app(_=Depends(get_current_user)):
    res = (
        db.table("service_categories")
        .select("id, slug, name_it, name_en, icon, category_type, requires_kyc, questions")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    rows = res.data or []
    standard = [_shape_for_app(r) for r in rows if r["category_type"] == "standard"]
    proximity = [_shape_for_app(r) for r in rows if r["category_type"] == "proximity"]
    payment = [_shape_for_app(r) for r in rows if r["category_type"] == "payment_service"]
    try:
        online_res = (
            db.table("profiles_provider")
            .select("user_id", count="exact")
            .eq("availability_status", "online")
            .execute()
        )
        providers_online = online_res.count or 0
    except Exception:
        providers_online = 0
    return {"standard": standard, "proximity": proximity, "payment": payment, "providers_online": providers_online}


# ---------------- admin (pannello jobby-admin, Blocco 9) ----------------
# Prima di questo blocco NON esisteva alcuna gestione admin delle categorie
# su Postgres: l'unica esistente (routers/catalog_routes.py: admin_list/
# toggle/set/commission) è Mongo-based e RITIRATA nel Blocco 7 (vedi il suo
# docstring). Riscritta qui da zero sullo schema service_categories reale —
# niente commission_pct (non esiste come colonna in questo schema, a
# differenza del vecchio modello Mongo: le fee sono gestite per-verticale in
# public.app_settings, fuori scope di un editor categorie).

class CategoryAdminPatchIn(BaseModel):
    name_it: Optional[str] = None
    name_en: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    requires_kyc: Optional[bool] = None
    is_active: Optional[bool] = None


@router.get("/admin/categories")
async def admin_list_categories(_=Depends(require_admin)):
    res = (
        db.table("service_categories")
        .select("id, slug, name_it, name_en, icon, category_type, requires_kyc, is_active, sort_order")
        .order("category_type")
        .order("sort_order")
        .execute()
    )
    return {"categories": res.data or []}


@router.post("/admin/categories/{category_id}/toggle")
async def admin_toggle_category(category_id: str, _=Depends(require_admin)):
    row = db.table("service_categories").select("id, is_active").eq("id", category_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="not_found")
    new_active = not row.data[0]["is_active"]
    db.table("service_categories").update({"is_active": new_active}).eq("id", category_id).execute()
    return {"id": category_id, "is_active": new_active}


@router.put("/admin/categories/{category_id}")
async def admin_update_category(category_id: str, body: CategoryAdminPatchIn, _=Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="no_fields_to_update")
    res = db.table("service_categories").update(updates).eq("id", category_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="not_found")
    return res.data[0]
