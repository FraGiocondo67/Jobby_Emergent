"""Defaults for the Pulizie configurator — all admin-overridable via settings."""
import math

MQ_BANDS = [
    {"id": "fino50", "it": "Fino a 50 m²", "en": "Up to 50 m²"},
    {"id": "50_80", "it": "50–80 m²", "en": "50–80 m²"},
    {"id": "80_120", "it": "80–120 m²", "en": "80–120 m²"},
    {"id": "120_180", "it": "120–180 m²", "en": "120–180 m²"},
    {"id": "oltre180", "it": "Oltre 180 m²", "en": "Over 180 m²"},
]

HOME_TYPES = [
    {"id": "appartamento", "it": "Appartamento", "en": "Apartment"},
    {"id": "casa", "it": "Casa indipendente", "en": "Detached house"},
    {"id": "villa", "it": "Villa", "en": "Villa"},
    {"id": "ufficio", "it": "Ufficio / Studio", "en": "Office / Studio"},
]

TIPI_PULIZIA = [
    {"id": "ordinaria", "it": "Ordinaria", "en": "Standard", "desc_it": "Mantenimento: pavimenti, superfici, bagni, cucina", "desc_en": "Upkeep: floors, surfaces, bathrooms, kitchen"},
    {"id": "afondo", "it": "A fondo", "en": "Deep", "desc_it": "Interni mobili, battiscopa, sanificazione bagni/cucina", "desc_en": "Inside furniture, skirting, sanitising"},
    {"id": "posttrasloco", "it": "Post trasloco / ristrutturazione", "en": "Post-move / renovation", "desc_it": "Casa vuota o cantiere: tariffa e durata dedicate", "desc_en": "Empty home or site: dedicated rate"},
]

EXTRA_ITEMS = [
    {"id": "forno", "it": "Forno", "en": "Oven", "default_price": 10.0},
    {"id": "frigo", "it": "Frigo", "en": "Fridge", "default_price": 8.0},
    {"id": "finestre", "it": "Interno finestre", "en": "Inside windows", "default_price": 15.0},
    {"id": "balconi", "it": "Balconi / Terrazzo", "en": "Balconies / Terrace", "default_price": 12.0},
]
STIRO_DEFAULT_PRICE = 12.0  # €/ora

# Recommended hours per (mq_band, tipo). Cliente can adjust ±1h.
ORE_TABLE = {
    "fino50":   {"ordinaria": 2, "afondo": 3, "posttrasloco": 4},
    "50_80":    {"ordinaria": 3, "afondo": 4, "posttrasloco": 5},
    "80_120":   {"ordinaria": 3, "afondo": 5, "posttrasloco": 6},
    "120_180":  {"ordinaria": 4, "afondo": 6, "posttrasloco": 8},
    "oltre180": {"ordinaria": 5, "afondo": 7, "posttrasloco": 9},
}

RICORRENZE = [
    {"id": "una_tantum", "it": "Una tantum", "en": "One-off", "sconto": False},
    {"id": "settimanale", "it": "Settimanale", "en": "Weekly", "sconto": True},
    {"id": "quindicinale", "it": "Quindicinale", "en": "Every 2 weeks", "sconto": True},
    {"id": "mensile", "it": "Mensile", "en": "Monthly", "sconto": False},
]

FLESSIBILITA = [
    {"id": "orario_esatto", "it": "Ora esatta", "en": "Exact time"},
    {"id": "fascia", "it": "Fascia (mattina/pomeriggio)", "en": "Time slot (AM/PM)"},
    {"id": "qualsiasi", "it": "Prima disponibilità", "en": "First availability"},
]

VARIATION_REASONS = [
    {"id": "molto_sporca", "it": "Casa molto sporca", "en": "Very dirty home"},
    {"id": "urgenza", "it": "Urgenza", "en": "Urgency"},
    {"id": "materiale_extra", "it": "Materiale extra", "en": "Extra materials"},
]

BINARI = [
    {"id": "impresa", "it": "Impresa di pulizie", "en": "Cleaning company",
     "desc_it": "Fattura, pagamento in app", "desc_en": "Invoice, in-app payment"},
    {"id": "persona_lf", "it": "Collaboratrice in regola", "en": "Registered helper",
     "desc_it": "Con borsellino INPS guidato (Libretto Famiglia)", "desc_en": "Guided INPS wallet (Family Booklet)"},
]

DEFAULT_FEE_PCT = 15.0          # JOBBY fee (percentage on the work total)
PROPOSAL_WINDOW_HOURS = 24      # asta passiva
LF_VOUCHER_NET_RATE = 0.8       # net to worker per nominal euro (INPS)
LF_YEAR_CEILING_EUR = 2500.0    # per couple
LF_YEAR_CEILING_HOURS = 280.0

# --- Spec 5: limiti di legge (Libretto Famiglia) ---
LF_FAMILY_ANNUAL_EUR = 10000.0   # tetto annuo complessivo della famiglia
LF_COUPLE_CEILING_EUR = 2500.0   # tetto per collaboratrice (coppia)
LF_PROVIDER_ANNUAL_EUR = 5000.0  # tetto annuo del lavoratore
LF_PROVIDER_HOURS = 280.0        # tetto ore annue del lavoratore
LF_AGEVOLATE_WEIGHT = 0.75       # peso compensi categorie agevolate (studente<25/pensionato/disoccupato)
LF_WARN_THRESHOLD = 0.8          # soglia avvisi preventivi (80%)


def recommended_hours(mq_band: str, tipo: str) -> int:
    return ORE_TABLE.get(mq_band, ORE_TABLE["80_120"]).get(tipo, 3)


def lf_round_nominale(total: float) -> float:
    """Round the work total up to the next multiple of 10€ (>= at least 10)."""
    return float(max(10, math.ceil(total / 10.0) * 10))
