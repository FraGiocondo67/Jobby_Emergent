from core import db, L, now_utc, new_id


def q_duration(default=2, mx=8):
    return {"id": "duration", "label": L("Durata (ore)", "Duration (hours)"), "type": "number", "min": 1, "max": mx, "default": default}


def q_note():
    return {"id": "note", "label": L("Descrivi cosa ti serve", "Describe what you need"), "type": "text",
            "placeholder": L("Dettagli", "Details")}


STANDARD_SERVICES = [
    {"cat_id": "sarta", "emoji": "🪡", "label": L("Sarta", "Seamstress"), "questions": [q_note(), q_duration(1)]},
    {"cat_id": "pulizie", "emoji": "🧹", "label": L("Pulizie", "Housekeeping"), "questions": [
        {"id": "homeType", "label": L("Tipo di abitazione", "Home type"), "type": "select",
         "options": [{"id": "apartment", "label": L("Appartamento", "Apartment")}, {"id": "house", "label": L("Casa", "House")}]},
        {"id": "rooms", "label": L("Numero di stanze", "Rooms"), "type": "number", "min": 1, "max": 12, "default": 3},
        q_duration(2)]},
    {"cat_id": "babysitting", "emoji": "👶", "label": L("Babysitting", "Babysitting"), "questions": [
        {"id": "children", "label": L("Numero di bambini", "Children"), "type": "number", "min": 1, "max": 5, "default": 1}, q_duration(3, 10)]},
    {"cat_id": "petsitting", "emoji": "🐾", "label": L("Pet Sitting", "Pet Sitting"), "questions": [
        {"id": "petType", "label": L("Tipo di animale", "Pet type"), "type": "select",
         "options": [{"id": "dog", "label": L("Cane", "Dog")}, {"id": "cat", "label": L("Gatto", "Cat")}, {"id": "other", "label": L("Altro", "Other")}]}, q_duration(2, 10)]},
    {"cat_id": "driver", "emoji": "🚗", "label": L("Driver", "Driver"), "questions": [q_note(), q_duration(2)]},
    {"cat_id": "artigiani", "emoji": "🛠️", "label": L("Artigiani della casa", "Home craftsmen"), "questions": [q_note(), q_duration(2)]},
    {"cat_id": "tuttofare", "emoji": "🔧", "label": L("Tuttofare", "Handyman"), "questions": [q_note(), q_duration(2)]},
    {"cat_id": "hospitality", "emoji": "🍽️", "label": L("Hospitality", "Hospitality support"), "questions": [
        {"id": "guests", "label": L("Numero di ospiti", "Guests"), "type": "number", "min": 1, "max": 50, "default": 4}, q_duration(3, 10)]},
    {"cat_id": "assistenza", "emoji": "❤️", "label": L("Assistenza", "Home assistance"), "questions": [q_note(), q_duration(3, 10)]},
    {"cat_id": "tecnico", "emoji": "💻", "label": L("Tecnico", "Technical services"), "questions": [q_note(), q_duration(1, 6)]},
]

PROXIMITY_BUSINESS = [
    ("lavanderia", "👕", "Lavanderia", "Laundry"), ("calzolaio", "👟", "Calzolaio", "Cobbler"),
    ("noleggio_auto", "🚙", "Noleggio Auto", "Car Rental"), ("barbiere", "✂️", "Barbiere / Parrucchiere", "Barber / Hairdresser"),
    ("idraulico", "🚿", "Idraulico", "Plumber"), ("elettricista", "⚡", "Elettricista", "Electrician"),
    ("estetista", "💅", "Estetista / Centro spa", "Beauty / Spa"), ("veterinario", "🐾", "Veterinario", "Veterinarian"),
    ("ottico", "👓", "Ottico", "Optician"), ("food_delivery", "🍕", "Food Delivery", "Food Delivery"),
    ("alimentari", "🛒", "Alimentari", "Grocery"), ("fioreria", "💐", "Fioreria", "Florist"),
    ("sartoria", "🧵", "Sartoria", "Tailor"), ("farmacia", "💊", "Farmacia", "Pharmacy"),
    ("falegname", "🪵", "Falegname", "Carpenter"), ("officina", "🔩", "Riparazione / Officina", "Repair shop"),
]

PAYMENT_SERVICES = [
    {"cat_id": "estero", "emoji": "🌍", "label": L("Manda soldi all'estero", "Send money abroad"), "questions": [
        {"id": "country", "label": L("Paese di destinazione", "Destination country"), "type": "text", "placeholder": L("Es. Marocco", "e.g. Morocco")},
        {"id": "recipient", "label": L("Destinatario", "Recipient"), "type": "text", "placeholder": L("Nome", "Name")},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 5, "max": 2000, "default": 50}]},
    {"cat_id": "ricarica", "emoji": "📱", "label": L("Ricarica Telefonica", "Mobile top-up"), "questions": [
        {"id": "phone", "label": L("Numero di telefono", "Phone number"), "type": "text", "placeholder": "+39 ..."},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 5, "max": 100, "default": 10}]},
    {"cat_id": "bollette", "emoji": "🧾", "label": L("Paga Bollette", "Pay bills"), "questions": [
        {"id": "biller", "label": L("Ente/Bolletta", "Biller"), "type": "text", "placeholder": L("Es. Enel", "e.g. Enel")},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 5, "max": 2000, "default": 60}]},
    {"cat_id": "locale", "emoji": "🔄", "label": L("Manda e Richiedi Soldi localmente", "Send & request money locally"), "questions": [
        {"id": "recipient", "label": L("Destinatario", "Recipient"), "type": "text", "placeholder": L("Nome o telefono", "Name or phone")},
        {"id": "amount", "label": L("Importo (€)", "Amount (€)"), "type": "number", "min": 1, "max": 1000, "default": 25}]},
]

MANIFESTO = [
    L("Il lavoro si adatta alla vita, non la vita al lavoro.", "Work should adapt to life, not life to work."),
    L("Ogni persona ha tempo, competenze e valore.", "Every person has time, skills and value."),
    L("La tecnologia deve dare più libertà, non meno.", "Technology should give people more freedom, not less."),
    L("La reputazione conta più della gerarchia.", "Reputation matters more than hierarchy."),
    L("Il reddito non deve dipendere da un solo datore di lavoro.", "Income should not depend on a single employer."),
    L("Il tempo disponibile può diventare opportunità.", "Available time can become opportunity."),
]

BOT_PROVIDERS = [
    ("Giulia Bianchi", ["pulizie", "sarta"], 14.0, 4.9, 128, 45.668, 12.245),
    ("Marco Rossi", ["tuttofare", "driver"], 13.0, 4.7, 86, 45.662, 12.240),
    ("Elena Ferrari", ["babysitting", "assistenza"], 12.0, 4.8, 64, 45.670, 12.250),
    ("Sara Conti", ["pulizie", "hospitality"], 15.0, 5.0, 203, 45.665, 12.238),
    ("Luca Moretti", ["tecnico", "driver"], 13.5, 4.6, 51, 45.660, 12.255),
    ("Anna Greco", ["petsitting", "babysitting"], 14.5, 4.9, 174, 45.672, 12.230),
    ("Paolo Riva", ["tuttofare", "tecnico"], 13.0, 4.5, 39, 45.658, 12.248),
    ("Chiara Esposito", ["sarta", "hospitality"], 12.5, 4.8, 92, 45.669, 12.235),
]


async def seed_categories():
    order = 0
    for s in STANDARD_SERVICES:
        order += 1
        await db.categories.update_one({"cat_id": s["cat_id"]},
            {"$setOnInsert": {**s, "kind": "standard", "active": True, "order": order, "commission_pct": 10.0}}, upsert=True)
    for pid, emoji, it, en in PROXIMITY_BUSINESS:
        order += 1
        await db.categories.update_one({"cat_id": pid},
            {"$setOnInsert": {"cat_id": pid, "emoji": emoji, "label": L(it, en), "kind": "proximity",
                              "active": True, "order": order, "questions": [q_note()], "commission_pct": 10.0}}, upsert=True)
    for p in PAYMENT_SERVICES:
        order += 1
        await db.categories.update_one({"cat_id": p["cat_id"]},
            {"$setOnInsert": {**p, "kind": "payment", "active": True, "order": order}}, upsert=True)
    # Migration: ensure every service/proximity category has a commission (default 10%).
    await db.categories.update_many(
        {"kind": {"$in": ["standard", "proximity"]}, "commission_pct": {"$exists": False}},
        {"$set": {"commission_pct": 10.0}})
    # Migration: deprecated/hidden standard categories must stay inactive on fresh DBs
    # (sarta & petsitting retired; tuttofare replaced by artigiani) — mirrors Preview state.
    await db.categories.update_many({"cat_id": {"$in": ["tuttofare", "sarta", "petsitting"]}},
                                    {"$set": {"active": False}})
