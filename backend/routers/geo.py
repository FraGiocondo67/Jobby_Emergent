"""JOBBY — Geocoding generico (OpenStreetMap Nominatim, gratuito, senza API key).

- POST /api/geocode          {query}          -> {lat, lng, label}
- POST /api/reverse-geocode  {lat, lng}       -> {label}
Usato da tutte le schermate con indirizzo manuale o "posizione attuale".
"""
import requests
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deps import get_current_user

router = APIRouter()

TREVISO = {"lat": 45.6669, "lng": 12.2433}
UA = {"User-Agent": "JOBBY-app/1.0"}


class GeocodeIn(BaseModel):
    query: str


class ReverseIn(BaseModel):
    lat: float
    lng: float


@router.post("/geocode")
async def geocode(body: GeocodeIn, user=Depends(get_current_user)):
    q = (body.query or "").strip()
    if not q:
        return {"lat": TREVISO["lat"], "lng": TREVISO["lng"], "label": q, "fallback": True}
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 1, "countrycodes": "it", "addressdetails": 0},
                         headers=UA, timeout=8)
        js = r.json()
        if js:
            return {"lat": float(js[0]["lat"]), "lng": float(js[0]["lon"]),
                    "label": js[0].get("display_name", q)[:120]}
    except Exception:
        pass
    return {"lat": TREVISO["lat"], "lng": TREVISO["lng"], "label": q, "fallback": True}


@router.post("/reverse-geocode")
async def reverse_geocode(body: ReverseIn, user=Depends(get_current_user)):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={"lat": body.lat, "lon": body.lng, "format": "json", "zoom": 18, "addressdetails": 1},
                         headers=UA, timeout=8)
        js = r.json()
        if js:
            a = js.get("address", {})
            road = a.get("road") or a.get("pedestrian") or a.get("suburb") or ""
            num = a.get("house_number", "")
            city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or ""
            parts = [p for p in [f"{road} {num}".strip(), city] if p]
            label = ", ".join(parts) if parts else js.get("display_name", "")[:120]
            return {"label": label[:120]}
    except Exception:
        pass
    return {"label": f"{body.lat:.4f}, {body.lng:.4f}", "fallback": True}
