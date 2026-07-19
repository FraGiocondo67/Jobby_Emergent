"""JOBBY — Spec 7 ARTIGIANI della casa (replaces 'tuttofare'). Two-stage flow."""

DEFAULT_FEE_PCT = 15.0
PROPOSAL_WINDOW_HOURS = 24
PREVENTIVO_VALIDITY_DAYS = 7
GARANZIA_DAYS = 30
BIG_JOB_THRESHOLD_EUR = 1500.0

# 6 mestieri (perimetro di lancio)
MESTIERI = [
    {"id": "idraulico", "it": "Idraulico", "en": "Plumber", "icon": "🔧",
     "abilitazione": True, "fgas": False, "libretto": False, "stage2": True, "stagionale": False},
    {"id": "elettricista", "it": "Elettricista", "en": "Electrician", "icon": "⚡",
     "abilitazione": True, "fgas": False, "libretto": False, "stage2": True, "stagionale": False},
    {"id": "caldaista", "it": "Caldaista", "en": "Boiler technician", "icon": "🔥",
     "abilitazione": True, "fgas": True, "libretto": False, "stage2": True, "stagionale": True},
    {"id": "climatizzazione", "it": "Climatizzazione", "en": "HVAC / A/C", "icon": "❄️",
     "abilitazione": True, "fgas": True, "libretto": False, "stage2": True, "stagionale": True},
    {"id": "giardiniere", "it": "Giardiniere", "en": "Gardener", "icon": "🌿",
     "abilitazione": False, "fgas": False, "libretto": False, "stage2": True, "stagionale": True},
    {"id": "tuttofare", "it": "Tuttofare", "en": "Handyman", "icon": "🛠️",
     "abilitazione": False, "fgas": False, "libretto": True, "stage2": True, "stagionale": False},
]

# default paniere (standard interventions) per mestiere — admin can extend
PANIERE = {
    "idraulico": [
        {"id": "miscelatore", "it": "Sostituzione miscelatore", "en": "Mixer tap replacement", "prezzo": 70},
        {"id": "sanitario", "it": "Sostituzione sanitario", "en": "Sanitary fixture replacement", "prezzo": 120},
        {"id": "scarico", "it": "Sblocco scarico semplice", "en": "Simple drain unblock", "prezzo": 60},
    ],
    "elettricista": [
        {"id": "punto_luce", "it": "Installazione punto luce", "en": "Light point install", "prezzo": 65},
        {"id": "lampadario", "it": "Sostituzione lampadario", "en": "Chandelier replacement", "prezzo": 55},
        {"id": "presa", "it": "Installazione presa", "en": "Socket install", "prezzo": 50},
    ],
    "caldaista": [
        {"id": "revisione", "it": "Revisione annuale caldaia", "en": "Annual boiler service", "prezzo": 90},
    ],
    "climatizzazione": [
        {"id": "ricarica", "it": "Ricarica e sanificazione climatizzatore", "en": "A/C recharge & sanitize", "prezzo": 80},
    ],
    "giardiniere": [
        {"id": "prato_s", "it": "Taglio prato (fino a 100 m²)", "en": "Lawn mowing (up to 100 m²)", "prezzo": 40},
        {"id": "prato_m", "it": "Taglio prato (100-300 m²)", "en": "Lawn mowing (100-300 m²)", "prezzo": 70},
        {"id": "siepe", "it": "Potatura siepe (al metro)", "en": "Hedge trimming (per meter)", "prezzo": 12},
    ],
    "tuttofare": [
        {"id": "mobile", "it": "Montaggio mobile/pensile", "en": "Furniture assembly", "prezzo": 50},
        {"id": "mensole", "it": "Montaggio mensole/quadri", "en": "Shelves/frames mounting", "prezzo": 35},
        {"id": "tende", "it": "Montaggio tende", "en": "Curtain mounting", "prezzo": 40},
    ],
}

# esiti di chiusura chiamata-diagnosi
ESITI = [
    {"id": "preventivo", "it": "Preventivo composto", "en": "Quote composed"},
    {"id": "risolto_diagnosi", "it": "Risolto in diagnosi", "en": "Solved during diagnosis"},
    {"id": "non_riparabile", "it": "Non riparabile", "en": "Not repairable"},
]

# keyword che instradano il tuttofare verso un mestiere abilitato
IMPIANTI_ROUTING = {
    "idraulico": ["acqua", "tubo", "tubi", "perdita", "rubinetto", "scarico", "wc", "water", "sifone", "caldaia acqua", "boiler"],
    "elettricista": ["corrente", "elettric", "presa", "interruttore", "quadro", "corto", "impianto elettrico", "contatore", "salvavita"],
    "caldaista": ["caldaia", "termosifone", "riscaldamento", "boiler"],
    "climatizzazione": ["climatizzatore", "condizionatore", "aria condizionata", "split", "pompa di calore"],
}

BINARI = [
    {"id": "impresa", "it": "Impresa / P.IVA", "en": "Business / VAT"},
    {"id": "persona_lf", "it": "Persona (Libretto Famiglia)", "en": "Individual (Family Booklet)"},
]

FASCE_URGENZA = [
    {"id": "immediato", "it": "Immediato (oggi)", "en": "Immediate (today)"},
    {"id": "serale", "it": "Serale", "en": "Evening"},
    {"id": "festivo", "it": "Festivo", "en": "Holiday"},
]
