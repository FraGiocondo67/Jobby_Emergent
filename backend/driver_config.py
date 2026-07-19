"""JOBBY — Spec 8 DRIVER category (sub-types: NCC + TAXI). Admin-overridable defaults."""

# distance/time estimate (free, no external routing provider)
ROAD_FACTOR = 1.3          # geographic distance -> road distance multiplier
AVG_SPEED_KMH = 55.0       # average speed for duration estimate
DEFAULT_FEE_PCT = 12.0
PROPOSAL_WINDOW_HOURS = 6
INCLUDED_WAIT_MIN = 30
MIN_UNACCOMPANIED_AGE = 16
LONG_DISTANCE_THRESHOLD_EUR = 250.0   # above -> flagged to admin

# only Impresa / P.IVA track (NCC/Taxi are authorized operators)
VEHICLE_CLASSES = [
    {"id": "standard", "it": "Standard", "en": "Standard", "seats": 4, "icon": "🚗"},
    {"id": "business", "it": "Berlina Business", "en": "Business sedan", "seats": 3, "icon": "🚘"},
    {"id": "van", "it": "Van (7-8 posti)", "en": "Van (7-8 seats)", "seats": 8, "icon": "🚐"},
]

# quick-tap shortcuts (known places with fixed coordinates) — Treviso/Venezia area
SHORTCUTS = [
    {"id": "vce", "it": "Aeroporto Venezia Marco Polo", "en": "Venice Marco Polo Airport", "lat": 45.5053, "lng": 12.3519, "airport": True, "icon": "✈️"},
    {"id": "tsf", "it": "Aeroporto Treviso Canova", "en": "Treviso Canova Airport", "lat": 45.6484, "lng": 12.1944, "airport": True, "icon": "✈️"},
    {"id": "tv_st", "it": "Stazione Treviso Centrale", "en": "Treviso Central Station", "lat": 45.6636, "lng": 12.2447, "airport": False, "icon": "🚉"},
    {"id": "mestre_st", "it": "Stazione Venezia Mestre", "en": "Venezia Mestre Station", "lat": 45.4823, "lng": 12.2320, "airport": False, "icon": "🚉"},
    {"id": "ve_sl", "it": "Stazione Venezia Santa Lucia", "en": "Venice Santa Lucia Station", "lat": 45.4415, "lng": 12.3209, "airport": False, "icon": "🚉"},
    {"id": "ca_foncello", "it": "Ospedale Ca' Foncello", "en": "Ca' Foncello Hospital", "lat": 45.6790, "lng": 12.2530, "airport": False, "icon": "🏥"},
]

# closed-list motivations for NCC price adjustment (only upward with a reason)
RITOCCO_MOTIVI = [
    {"id": "bagagli", "it": "Bagagli voluminosi", "en": "Bulky luggage"},
    {"id": "seggiolino", "it": "Seggiolino richiesto", "en": "Child seat requested"},
    {"id": "attesa", "it": "Attesa programmata", "en": "Scheduled wait"},
    {"id": "pedaggi", "it": "Pedaggi/ZTL particolari", "en": "Special tolls/ZTL"},
]

SPECIAL_NEEDS = [
    {"id": "seggiolino", "it": "Seggiolino bambino", "en": "Child seat"},
    {"id": "animale", "it": "Animale al seguito", "en": "Pet on board"},
]

CANCELLATION = {"full_refund_hours": 4, "half_charge_under_hours": 4, "full_charge_under_min": 30}

# default parametric price list per class (drivers customize in onboarding)
DEFAULT_LISTINO = {
    "standard": {"base": 8.0, "per_km": 1.4, "per_hour": 35.0, "attesa_per_hour": 30.0},
    "business": {"base": 15.0, "per_km": 2.0, "per_hour": 50.0, "attesa_per_hour": 40.0},
    "van": {"base": 20.0, "per_km": 2.4, "per_hour": 60.0, "attesa_per_hour": 45.0},
}

# official taximeter reference tariff (estimate only; final amount from meter)
TAXI_TARIFFA = {"scatto": 3.5, "per_km": 1.1, "per_hour": 27.0, "notturno_pct": 20.0, "festivo_pct": 15.0, "min_corsa": 6.0}
