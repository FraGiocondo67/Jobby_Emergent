"""BLOCCO 5 (migrazione Emergent -> Supabase/Render) — helper cross-cutting
condivisi dalle 4 verticali per le due componenti "Spec4" genuinamente
mancanti (decisione esplicita dell'utente: NON riportare cancellazione/
recensioni già implementate per-verticale nel Blocco 2/3/4 —
richieste.py/artigiani.py/babysitting.py/driver.py fanno già un rimborso
100% incondizionato su cancellazione post-conferma e hanno già un review()
proprio con trust score — qui si aggiunge solo ciò che mancava davvero):

1. RIMBORSO PARZIALE A SCAGLIONI (banding per ore-al-servizio, come nel
   vecchio routers/spec4.py "Fase A") — sostituisce il rimborso 100%
   incondizionato delle 4 verticali con tier basati su `missions.scheduled_at`
   (colonna disponibile solo da questo Blocco 5 — vedi il fix critico NOT
   NULL in core_pg.py):
     - >= cancel_free_hours prima del servizio: rimborso pieno
     - tra cancel_fee_only_hours e cancel_free_hours: il cliente perde solo
       la fee JOBBY (`missions.platform_fee`), il resto rimborsato
     - < cancel_fee_only_hours: il cliente perde anche un indennizzo per il
       provider (percentuale `cancel_late_labor_pct` di
       `missions.provider_payout`), oltre alla fee

   LIMITE NOTO: le RPC `refund_escrow`/`release_escrow` (Blocco 3) operano
   sempre sull'INTERO importo dell'hold — non esiste un'RPC per uno split
   (parte rimborsata al cliente + parte trasferita al provider come
   indennizzo, dalla stessa transazione). `_write_settlement_ledger` scrive
   quindi a mano le righe di `public.payments` che quelle RPC scriverebbero
   per l'intero importo, ma per gli importi parziali — stesso schema/enum,
   stessa logica di aggiornamento di `missions.payment_status` e dei totali
   su `profiles_provider`/`profiles_client`. Se in futuro serve isolare
   questa logica in una RPC SQL dedicata (`partial_settle_escrow`), è un
   miglioramento pulito da fare a parte; per ora la scrittura applicativa
   qui è corretta e sufficiente.

   Binario `persona_lf`: nessun gateway reale (mai lo è stato, vedi
   stripe_pg.py) — qui solo lo storno del registro `public.lf_ledger`
   (`lf_pg.record_usage` con importi negativi). Il vecchio Mongo aveva anche
   una "fee di prenotazione" separata trattenuta in caso di cancellazione
   tardiva LF; quel concetto non esiste nello schema Postgres attuale
   (persona_lf ha sempre `platform_fee=0`, vedi richieste.py confirm()), per
   cui qui la sola conseguenza di una cancellazione tardiva LF è lo strike
   di affidabilità (nessun importo trattenuto — semplificazione consapevole
   rispetto al vecchio comportamento, coerente con quanto lo schema attuale
   può effettivamente rappresentare).

2. PUNTEGGIO PRIVATO CLIENTE + AFFIDABILITÀ — il provider valuta privatamente
   il cliente a fine lavoro (mai visibile al cliente). A differenza del
   vecchio Mongo (`users.client_private_scores`/`reliability_events`, campi
   ad-hoc), qui si riusa `public.client_trust_events` (già "sbloccato" nel
   Blocco 4) con `event_type='private_rating'`/`'cancel_late'` — l'aggregato
   "affidabilità" è semplicemente `profiles_client.trust_score`, calcolato
   automaticamente dal trigger esistente. Nessuna tabella nuova.

Fuori scope per decisione esplicita dell'utente: coda di moderazione
recensioni (rimandata al Blocco 6, lavoro Retool admin), no-show/ritardo/
pausa-ricorrenza del vecchio spec4.py (mai portati nelle 4 verticali
Postgres, non tra i due pezzi richiesti in questo blocco).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe_pg as SP
from core_pg import db, now_iso, now_utc, record_client_trust_event

SPEC4_DEFAULTS = {
    "cancel_free_hours": 48,        # >= : rimborso pieno
    "cancel_fee_only_hours": 24,    # tra fee_only e free: perde solo la fee JOBBY
    "cancel_late_labor_pct": 50,    # < fee_only: perde fee + questa % del lavoro (indennizzo al provider)
    "lf_free_hours": 48,            # persona_lf: gratis fino a queste ore (poi solo strike, vedi docstring)
    "client_strike_window_days": 180,
    "client_strike_threshold": 3,   # cancel_late nella finestra che attivano l'alert admin
}
_CONFIG_KEY = "spec4_config"


def spec4_config() -> dict:
    res = db.table("app_settings").select("value").eq("key", _CONFIG_KEY).limit(1).execute()
    cfg = dict(SPEC4_DEFAULTS)
    if res.data and isinstance(res.data[0].get("value"), dict):
        cfg.update(res.data[0]["value"])
    return cfg


def set_spec4_config(patch: dict) -> dict:
    cfg = spec4_config()
    cfg.update({k: v for k, v in patch.items() if k in SPEC4_DEFAULTS})
    db.table("app_settings").upsert({"key": _CONFIG_KEY, "value": cfg}).execute()
    return cfg


def hours_until(scheduled_at: Optional[str]) -> Optional[float]:
    if not scheduled_at:
        return None
    try:
        dt = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
    except Exception:
        return None


def cancel_tier(scheduled_at: Optional[str], binario: str, cfg: dict):
    """Ritorna (tier, hours_until). tier in free|fee_only|late (persona_lf: solo free|late)."""
    h = hours_until(scheduled_at)
    if binario == "persona_lf":
        tier = "free" if (h is None or h >= cfg["lf_free_hours"]) else "late"
    elif h is None or h >= cfg["cancel_free_hours"]:
        tier = "free"
    elif h >= cfg["cancel_fee_only_hours"]:
        tier = "fee_only"
    else:
        tier = "late"
    return tier, h


def write_settlement_ledger(mission_id: str, client_id: str, provider_id: Optional[str],
                             refund_amount: float, indennizzo: float, platform_fee_kept: float,
                             refund_gateway_id: str, indennizzo_gateway_id: str, tier: str) -> None:
    """Vedi LIMITE NOTO nel docstring del modulo: replica a mano l'effetto di
    refund_escrow()/release_escrow() ma per importi parziali."""
    db.table("payments").update({"status": "refunded", "refunded_at": now_iso(), "updated_at": now_iso()}) \
        .eq("mission_id", mission_id).eq("type", "escrow_hold").execute()

    if refund_amount > 0:
        db.table("payments").insert({
            "mission_id": mission_id, "type": "refund", "status": "refunded", "amount": round(refund_amount, 2),
            "currency": "EUR", "from_user_id": provider_id, "to_user_id": client_id, "gateway_name": "stripe",
            "refunded_at": now_iso(),
            "metadata": {"reason": f"cancellazione_bandata_{tier}", "gateway_transaction_id": refund_gateway_id},
        }).execute()

    if indennizzo > 0:
        db.table("payments").insert({
            "mission_id": mission_id, "type": "escrow_release", "status": "released", "amount": round(indennizzo, 2),
            "currency": "EUR", "from_user_id": client_id, "to_user_id": provider_id, "gateway_name": "stripe",
            "released_at": now_iso(),
            "metadata": {"gateway_transaction_id": indennizzo_gateway_id, "note": "Indennizzo cancellazione tardiva"},
        }).execute()

    if platform_fee_kept > 0:
        db.table("payments").insert({
            "mission_id": mission_id, "type": "platform_fee", "status": "released", "amount": round(platform_fee_kept, 2),
            "currency": "EUR", "from_user_id": client_id, "gateway_name": "stripe", "released_at": now_iso(),
            "metadata": {"note": "Commissione JOBBY trattenuta su cancellazione"},
        }).execute()

    db.table("missions").update({
        "payment_status": "released" if indennizzo > 0 else "refunded", "updated_at": now_iso(),
    }).eq("id", mission_id).execute()

    if provider_id and (indennizzo > 0 or platform_fee_kept > 0):
        prov = db.table("profiles_provider").select("total_earned").eq("user_id", provider_id).limit(1).execute()
        if prov.data:
            cur = float(prov.data[0].get("total_earned") or 0)
            db.table("profiles_provider").update({"total_earned": round(cur + indennizzo, 2)}).eq("user_id", provider_id).execute()
        cli = db.table("profiles_client").select("total_spent").eq("user_id", client_id).limit(1).execute()
        if cli.data:
            cur = float(cli.data[0].get("total_spent") or 0)
            db.table("profiles_client").update(
                {"total_spent": round(cur + indennizzo + platform_fee_kept, 2)}
            ).eq("user_id", client_id).execute()


def refund_gateway_holds(pagamento: dict, refund_amount: float) -> str:
    """Alcune verticali (richieste.py/babysitting.py) tengono un unico hold
    Stripe in `pagamento["payment_intent_id"]`; altre (artigiani.py/
    driver.py, e babysitting.py per binario piva) accumulano più hold — uno
    per fase (chiamata/preventivo/extra) — in `pagamento["holds"]` (lista di
    {payment_intent_id, amount}). Qui il rimborso parziale viene distribuito
    proporzionalmente su ciascun hold, fino a coprire `refund_amount`
    (l'ultimo hold toccato assorbe l'arrotondamento residuo). Ritorna
    l'ultimo `refund_id` Stripe (stesso valore usato come
    `p_gateway_transaction_id` dalle RPC Blocco 3, solo a scopo di log)."""
    if refund_amount <= 0:
        return ""
    holds = pagamento.get("holds")
    if holds:
        total_held = sum(float(h.get("amount") or 0) for h in holds if h.get("payment_intent_id")) or 1.0
        remaining = refund_amount
        last_id = ""
        eligible = [h for h in holds if h.get("payment_intent_id")]
        for i, h in enumerate(eligible):
            if remaining <= 0:
                break
            share = round(refund_amount * (float(h.get("amount") or 0) / total_held), 2)
            if i == len(eligible) - 1:
                share = round(remaining, 2)
            share = min(share, remaining)
            if share <= 0:
                continue
            last_id = SP.refund_payment_intent(h["payment_intent_id"], amount_eur=share)["refund_id"]
            remaining = round(remaining - share, 2)
        return last_id
    pi = pagamento.get("payment_intent_id")
    if pi:
        return SP.refund_payment_intent(pi, amount_eur=refund_amount)["refund_id"]
    return ""


def settle_gateway_cancellation(mission: dict, pagamento: dict, refund_amount: float, indennizzo: float,
                                fee_kept: float, tier_label: str) -> dict:
    """Primitiva di basso livello: esegue il refund/transfer Stripe per gli
    importi già decisi dal chiamante e scrive il ledger. Usata sia da
    `apply_banded_cancellation` (soglie generiche spec4_config) sia da
    driver.py (che ha le proprie fasce di dominio, driver_config.CANCELLATION
    — 4h/30min — invece di quelle generiche, vedi il suo docstring). Ritorna
    {refund_amount, indennizzo, pagamento_updates} — nessun accesso a
    `stato`/`holds` qui: il chiamante deve aver già verificato che
    `pagamento.get("stato") == "held"` e che esista un hold reale."""
    refund_id = refund_gateway_holds(pagamento, refund_amount)
    transfer_id = ""
    if indennizzo > 0:
        acct = db.table("profiles_provider").select("stripe_connect_account_id") \
            .eq("user_id", mission["provider_id"]).limit(1).execute()
        acct_id = acct.data[0].get("stripe_connect_account_id") if acct.data else None
        if acct_id:
            transfer_id = SP.transfer_to_provider(
                acct_id, indennizzo, {"mission_id": mission["id"], "reason": f"cancellazione_{tier_label}"}
            )["transfer_id"]
        else:
            # Provider non onboardato su Stripe Connect: nessun indennizzo possibile,
            # l'importo resta semplicemente non rimborsato sul saldo JOBBY.
            indennizzo = 0.0

    write_settlement_ledger(mission["id"], mission["client_id"], mission.get("provider_id"),
                             refund_amount, indennizzo, fee_kept, refund_id, transfer_id, tier_label)
    return {"refund_amount": refund_amount, "indennizzo": indennizzo,
            "pagamento_updates": {"stato": "refunded" if indennizzo == 0 else "released",
                                  "refund_amount": refund_amount, "indennizzo": indennizzo,
                                  "cancel_tier": tier_label}}


def apply_banded_cancellation(mission: dict, binario: str, pagamento: dict) -> dict:
    """Applica il rimborso a scaglioni su una missione confermata/in corso,
    con le soglie generiche di spec4_config() (usato da richieste.py,
    artigiani.py, babysitting.py — driver.py usa invece le proprie fasce di
    dominio, vedi `settle_gateway_cancellation` sopra e il docstring di
    driver.py). `pagamento` è il dict di stato-pagamento del chiamante (la
    chiave dentro `brief_answers` cambia da verticale a verticale —
    `pagamento_lavoro` per richieste.py/babysitting.py, `pagamento` per
    artigiani.py — è compito del chiamante estrarlo/reinserirlo nel punto
    giusto).

    Ritorna {tier, hours_until, refund_amount, indennizzo, strike, note?,
    pagamento_updates}: il chiamante fa
    `pagamento.update(result["pagamento_updates"])` e poi salva `brief` come
    fa già oggi — nessun'altra modifica al proprio codice di persistenza.
    Non tocca `missions.brief_answers`/`status` — stesso pattern di
    `_apply_money_resolution` in routers/disputes.py."""
    cfg = spec4_config()
    tier, h = cancel_tier(mission.get("scheduled_at"), binario, cfg)
    result = {"tier": tier, "hours_until": round(h, 1) if h is not None else None,
              "refund_amount": 0.0, "indennizzo": 0.0, "strike": tier == "late", "pagamento_updates": {}}

    if binario in ("impresa", "piva"):
        if pagamento.get("stato") != "held" or not (pagamento.get("holds") or pagamento.get("payment_intent_id")):
            result["note"] = "Nessun hold Stripe attivo — nessuna azione gateway."
            return result
        price_agreed = float(mission.get("price_agreed") or 0)
        platform_fee = float(mission.get("platform_fee") or 0)
        provider_payout = float(mission.get("provider_payout") or 0)

        if tier == "free":
            refund_amount, indennizzo, fee_kept = price_agreed, 0.0, 0.0
        elif tier == "fee_only":
            refund_amount, indennizzo, fee_kept = round(price_agreed - platform_fee, 2), 0.0, platform_fee
        else:  # late
            indennizzo = round(provider_payout * float(cfg["cancel_late_labor_pct"]) / 100.0, 2)
            refund_amount = round(price_agreed - platform_fee - indennizzo, 2)
            fee_kept = platform_fee

        settled = settle_gateway_cancellation(mission, pagamento, refund_amount, indennizzo, fee_kept, tier)
        result.update({"refund_amount": settled["refund_amount"], "indennizzo": settled["indennizzo"],
                       "pagamento_updates": settled["pagamento_updates"]})

    elif binario == "persona_lf":
        import lf_pg as LF
        nominale = float(pagamento.get("lf_nominale") or pagamento.get("totale_bloccato") or 0)
        ore = float(pagamento.get("lf_ore") or 0)
        if nominale and mission.get("provider_id"):
            LF.record_usage(mission["client_id"], mission["provider_id"], -nominale, -ore)
        result["note"] = "Libretto Famiglia: nessun gateway reale, solo storno del registro LF (vedi docstring)."
        result["pagamento_updates"] = {"stato": "annullato", "cancel_tier": tier}
    else:
        result["note"] = f"binario sconosciuto: {binario}"

    return result


def record_strike_if_late(client_id: str, mission_id: str, tier: str, cfg: dict) -> Optional[int]:
    """Se la cancellazione è nel tier "late", registra lo strike come
    client_trust_event e, se la soglia nella finestra è superata, apre un
    admin_actions come alert (stesso riuso pragmatico già usato altrove nel
    Blocco 2/3, es. artigiani.py `garanzia`/babysitting.py emergenza)."""
    if tier != "late":
        return None
    record_client_trust_event(client_id, "cancel_late", -3.0, dimension="reliability",
                              notes=f"Cancellazione tardiva missione {mission_id}")
    since = (now_utc() - timedelta(days=cfg["client_strike_window_days"])).isoformat()
    res = (
        db.table("client_trust_events").select("id", count="exact")
        .eq("client_id", client_id).eq("event_type", "cancel_late").gte("created_at", since).execute()
    )
    n = res.count or 0
    if n >= cfg["client_strike_threshold"]:
        db.table("admin_actions").insert({
            "admin_id": client_id, "action": "client_low_reliability", "target_type": "user", "target_id": client_id,
            "notes": f"{n} cancellazioni tardive negli ultimi {cfg['client_strike_window_days']}g "
                    f"(soglia {cfg['client_strike_threshold']}).",
        }).execute()
    return n
