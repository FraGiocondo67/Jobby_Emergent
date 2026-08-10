"""AI dispute-arbitration agent.

BLOCCO 4 (migrazione Emergent -> Supabase/Render): sostituito il wrapper
`emergentintegrations.llm.chat.LlmChat` (chiave `EMERGENT_LLM_KEY`, non più
disponibile fuori dall'ambiente Emergent — vedi requirements.txt) con una
chiamata diretta all'SDK ufficiale `anthropic`, usando `ANTHROPIC_API_KEY`
(chiave propria JOBBY). Stesso identico prompt/parsing JSON di prima, stesso
fallback euristico invariato come rete di sicurezza in caso di errore o
chiave mancante. Modello: `claude-sonnet-5` (vedi .env.example).

Produce una raccomandazione NON vincolante. L'admin JOBBY conferma prima di
applicarla (vedi routers/disputes.py, admin_resolve()).
"""
import os
import json
import logging

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

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
    "Considera: motivo del claim, descrizione del cliente, importo, categoria, fase della "
    "missione (pre/durante/post esecuzione, pagato o no). Favorisci la mediazione ma tutela "
    "il cliente quando il servizio non è stato eseguito o è gravemente carente. "
    "Rispondi SOLO con un oggetto JSON valido, senza testo aggiuntivo, con questa forma esatta: "
    '{"recommendation":"refund_full|refund_partial|reject","refund_pct":<intero 0-100>,'
    '"confidence":<numero 0-1>,"rationale":"<breve motivazione in italiano>"}'
)


def _fallback(reason: str) -> dict:
    heavy = {"NOT_PERFORMED", "NO_SHOW"}
    if reason in heavy:
        return {"recommendation": "refund_full", "refund_pct": 100, "confidence": 0.4,
                "rationale": "Analisi automatica non disponibile; il motivo indica mancata esecuzione."}
    return {"recommendation": "refund_partial", "refund_pct": 50, "confidence": 0.3,
            "rationale": "Analisi automatica non disponibile; proposta di rimborso parziale prudenziale."}


async def ai_analyze(dispute: dict, mission: dict) -> dict:
    """dispute: riga public.disputes (+ campo 'reason' testuale libero, non più un
    reason_code chiuso come nel modello Emergent — vedi routers/disputes.py).
    mission: riga public.missions collegata (per importo/categoria/stato)."""
    payload = {
        "reason": dispute.get("reason", ""),
        "evidence_urls": dispute.get("evidence_urls") or [],
        "amount_eur": mission.get("price_agreed"),
        "payment_status": mission.get("payment_status"),
        "mission_status": mission.get("status"),
    }
    if not ANTHROPIC_API_KEY:
        return _fallback(_infer_reason_bucket(dispute.get("reason", "")))
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text").strip()
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
        return _fallback(_infer_reason_bucket(dispute.get("reason", "")))


def _infer_reason_bucket(reason_text: str) -> str:
    """Il modello Emergent aveva un reason_code chiuso (usato dal fallback
    euristico); il nuovo public.claims/disputes usa un campo 'reason' testuale
    libero. Approssimazione lessicale solo per scegliere il ramo del fallback
    quando l'AI non è raggiungibile — non influisce quando l'AI risponde."""
    t = (reason_text or "").lower()
    if any(k in t for k in ("non presentat", "no show", "non è arrivat", "non si è present")):
        return "NO_SHOW"
    if any(k in t for k in ("non eseguit", "non consegnat", "mai arrivat", "non fatto")):
        return "NOT_PERFORMED"
    return "OTHER"
