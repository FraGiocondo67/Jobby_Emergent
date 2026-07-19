"""AI dispute-arbitration agent (Claude Sonnet 4.6 via Emergent LLM key).

Produces a NON-binding recommendation. JOBBY admin confirms before applying.
"""
import os
import json
import logging

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

REASON_CODES = {
    "NOT_PERFORMED": "Servizio/prodotto non eseguito o non consegnato",
    "PARTIAL": "Eseguito solo parzialmente",
    "QUALITY": "Qualità scadente / non conforme",
    "LATE": "Grave ritardo",
    "DAMAGE": "Danni causati",
    "NO_SHOW": "Il fornitore non si è presentato",
    "OTHER": "Altro",
}

SYSTEM_PROMPT = (
    "Sei l'arbitro AI di JOBBY, una piattaforma di servizi di prossimità. "
    "Analizza una contestazione tra cliente e fornitore e proponi una risoluzione equa. "
    "Considera: codice motivo, descrizione del cliente, risposta del fornitore, importo, "
    "categoria, puntualità del check-in. Favorisci la mediazione ma tutela il cliente quando "
    "il servizio non è stato eseguito o è gravemente carente. "
    "Rispondi SOLO con un oggetto JSON valido, senza testo aggiuntivo, con questa forma esatta: "
    '{"recommendation":"refund_full|refund_partial|reject","refund_pct":<intero 0-100>,'
    '"confidence":<numero 0-1>,"rationale":"<breve motivazione in italiano>"}'
)


def _fallback(reason_code: str) -> dict:
    heavy = {"NOT_PERFORMED", "NO_SHOW"}
    if reason_code in heavy:
        return {"recommendation": "refund_full", "refund_pct": 100, "confidence": 0.4,
                "rationale": "Analisi automatica non disponibile; il motivo indica mancata esecuzione."}
    return {"recommendation": "refund_partial", "refund_pct": 50, "confidence": 0.3,
            "rationale": "Analisi automatica non disponibile; proposta di rimborso parziale prudenziale."}


async def ai_analyze(dispute: dict, booking: dict) -> dict:
    payload = {
        "reason_code": dispute.get("reason_code"),
        "reason_meaning": REASON_CODES.get(dispute.get("reason_code"), "Altro"),
        "client_description": dispute.get("description", ""),
        "provider_response": dispute.get("provider_response", ""),
        "amount_eur": booking.get("total"),
        "labor_eur": booking.get("labor_cost"),
        "category": booking.get("category"),
        "checked_in_on_time": booking.get("check_in_on_time", False),
    }
    if not EMERGENT_LLM_KEY:
        return _fallback(dispute.get("reason_code", "OTHER"))
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"dispute-{dispute.get('dispute_id')}",
            system_message=SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=json.dumps(payload, ensure_ascii=False)))
        text = resp if isinstance(resp, str) else str(resp)
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip() if text.split("```")[1:] else text
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        rec = data.get("recommendation")
        if rec not in ("refund_full", "refund_partial", "reject"):
            raise ValueError("bad recommendation")
        pct = int(data.get("refund_pct", 0))
        pct = max(0, min(100, pct))
        if rec == "refund_full":
            pct = 100
        if rec == "reject":
            pct = 0
        return {"recommendation": rec, "refund_pct": pct,
                "confidence": float(data.get("confidence", 0.5)),
                "rationale": str(data.get("rationale", ""))[:600]}
    except Exception as e:
        logger.warning("ai_analyze failed: %s", e)
        return _fallback(dispute.get("reason_code", "OTHER"))
