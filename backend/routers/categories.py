"""BLOCCO 7b (jobby-web -> client puro) - nuovo endpoint pubblico di sola
lettura per le categorie di servizio attive. Prima non esisteva alcun router
che esponesse `service_categories` in lettura: jobby-web (via
app/api/categories/route.ts) leggeva la tabella direttamente via Supabase,
bypassando questo backend. Stesso identico contratto di quella route (stessi
campi, stesso ordinamento, richiede solo un utente autenticato qualsiasi
ruolo) cosi la conversione a proxy non cambia comportamento per chi la
chiama gia oggi."""
from fastapi import APIRouter, Depends

from core_pg import db
from deps_pg import get_current_user

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
