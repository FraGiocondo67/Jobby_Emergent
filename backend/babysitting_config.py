"""JOBBY — Spec 6 Babysitting configurator defaults (all admin-overridable via settings)."""

MIN_CHILD_AGE_MONTHS = 12          # under 12 months not available yet
AUTO_CONFIRM_MIN = 15              # parent auto-confirm window after provider ends
ROUNDING_MIN = 15                 # billable time rounded to 15-minute steps
VOUCHER_MARGIN_HOURS = 1.0         # prudential margin engaged on LF confirm
DEFAULT_FEE_PCT = 15.0
PROPOSAL_WINDOW_HOURS = 24

# Emergency numbers shown on the in-booking help button (Italy)
EMERGENCY_NUMBERS = [
    {"label_it": "Emergenza unica europea", "label_en": "European emergency", "number": "112"},
    {"label_it": "Emergenza sanitaria", "label_en": "Medical emergency", "number": "118"},
]

SCHOOL_LEVELS = [
    {"id": "elementari", "it": "Elementari", "en": "Primary"},
    {"id": "medie", "it": "Medie", "en": "Middle"},
    {"id": "superiori", "it": "Superiori", "en": "High school"},
]

SUBJECTS = [
    {"id": "matematica", "it": "Matematica", "en": "Maths"},
    {"id": "italiano", "it": "Italiano", "en": "Italian"},
    {"id": "inglese", "it": "Inglese", "en": "English"},
    {"id": "scienze", "it": "Scienze", "en": "Science"},
    {"id": "storia_geo", "it": "Storia e Geografia", "en": "History & Geography"},
    {"id": "latino", "it": "Latino", "en": "Latin"},
    {"id": "fisica", "it": "Fisica", "en": "Physics"},
    {"id": "chimica", "it": "Chimica", "en": "Chemistry"},
]

LANGUAGES = [
    {"id": "italiano", "it": "Italiano", "en": "Italian"},
    {"id": "inglese", "it": "Inglese", "en": "English"},
    {"id": "francese", "it": "Francese", "en": "French"},
    {"id": "spagnolo", "it": "Spagnolo", "en": "Spanish"},
    {"id": "tedesco", "it": "Tedesco", "en": "German"},
    {"id": "arabo", "it": "Arabo", "en": "Arabic"},
]

CERTIFICATIONS = [
    {"id": "primo_soccorso_pediatrico", "it": "Primo soccorso pediatrico", "en": "Pediatric first aid", "highlight": True},
    {"id": "bls_d", "it": "BLS-D", "en": "BLS-D", "highlight": True},
    {"id": "laurea_educazione", "it": "Laurea in ambito educativo", "en": "Education degree", "highlight": False},
    {"id": "corso_babysitting", "it": "Corso babysitting", "en": "Babysitting course", "highlight": False},
]

# Age bands the babysitter can declare experience with
AGE_BANDS = [
    {"id": "1_3", "it": "1–3 anni", "en": "1–3 years"},
    {"id": "3_6", "it": "3–6 anni", "en": "3–6 years"},
    {"id": "6_10", "it": "6–10 anni", "en": "6–10 years"},
    {"id": "10_14", "it": "10–14 anni", "en": "10–14 years"},
    {"id": "over14", "it": "Oltre 14 anni", "en": "Over 14"},
]

AVAILABILITY_SLOTS = [
    {"id": "pomeriggi", "it": "Pomeriggi", "en": "Afternoons"},
    {"id": "sere", "it": "Sere", "en": "Evenings"},
    {"id": "weekend", "it": "Weekend", "en": "Weekends"},
    {"id": "mattine", "it": "Mattine", "en": "Mornings"},
]

RICORRENZE = [
    {"id": "una_tantum", "it": "Una tantum", "en": "One-off"},
    {"id": "settimanale", "it": "Pomeriggi fissi (settimanale)", "en": "Fixed afternoons (weekly)"},
    {"id": "quindicinale", "it": "Ogni due settimane", "en": "Every 2 weeks"},
]

GUIDED_QUESTIONS = [
    {"id": "perche", "it": "Perché fai la babysitter?", "en": "Why are you a babysitter?"},
    {"id": "pomeriggio", "it": "Come organizzi un pomeriggio con un bambino di sei anni?",
     "en": "How do you organise an afternoon with a six-year-old?"},
    {"id": "genitori", "it": "Cosa devono sapere i genitori di te?", "en": "What should parents know about you?"},
]

BINARI = [
    {"id": "persona_lf", "it": "Babysitter (Libretto Famiglia)", "en": "Babysitter (Family Booklet)",
     "desc_it": "Con borsellino INPS guidato — studentesse e privati", "desc_en": "Guided INPS wallet — students & individuals"},
    {"id": "piva", "it": "Professionista con P.IVA", "en": "Professional (VAT)",
     "desc_it": "Fattura, pagamento in app", "desc_en": "Invoice, in-app payment"},
]

LF_VOUCHER_NET_RATE = 0.8
LF_YEAR_CEILING_EUR = 2500.0
LF_YEAR_CEILING_HOURS = 280.0
