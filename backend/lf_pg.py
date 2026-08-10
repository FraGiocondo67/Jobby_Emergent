"""Blocco 3 (Wallet/pagamenti/escrow) — registro Libretto Famiglia (binario
`persona_lf` di Pulizie/Babysitting). Decisione presa con l'utente: NON un
vero escrow — i compensi Libretto Famiglia si muovono fuori JOBBY tramite
voucher INPS, mai attraverso un gateway di pagamento reale (stesso
comportamento del sistema Emergent: `lf_uses_voucher_not_psp`). Qui serve solo
un registro dei massimali annui (euro nominali + ore) sulla tabella
public.lf_ledger, per bloccare nuove richieste che sforerebbero i tetti prima
che vengano confermate — niente di più.

Il registro è per coppia famiglia-lavoratore ed è condiviso tra Pulizie e
Babysitting (il vincolo è dell'INPS sulla relazione, non per singola
verticale JOBBY): ogni router passa qui i propri valori di soglia (diversi
tra richieste_config.py e babysitting_config.py) invece che questo modulo
abbia soglie proprie.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from core_pg import db


def _year() -> int:
    return datetime.now(timezone.utc).year


def get_couple_totals(family_id: str, worker_id: str, year: Optional[int] = None) -> dict:
    y = year or _year()
    res = (
        db.table("lf_ledger").select("nominale_used, hours_used")
        .eq("year", y).eq("family_id", family_id).eq("worker_id", worker_id).limit(1).execute()
    )
    row = res.data[0] if res.data else {"nominale_used": 0, "hours_used": 0}
    return {"nominale_used": float(row.get("nominale_used") or 0), "hours_used": float(row.get("hours_used") or 0)}


def get_family_total(family_id: str, year: Optional[int] = None) -> float:
    y = year or _year()
    res = db.table("lf_ledger").select("nominale_used").eq("year", y).eq("family_id", family_id).execute()
    return sum(float(r.get("nominale_used") or 0) for r in (res.data or []))


def get_worker_totals(worker_id: str, year: Optional[int] = None) -> dict:
    y = year or _year()
    res = db.table("lf_ledger").select("nominale_used, hours_used").eq("year", y).eq("worker_id", worker_id).execute()
    rows = res.data or []
    return {"nominale_used": sum(float(r.get("nominale_used") or 0) for r in rows),
            "hours_used": sum(float(r.get("hours_used") or 0) for r in rows)}


def check_ceilings(family_id: str, worker_id: str, add_nominale: float, add_hours: float, *,
                   couple_ceiling_eur: float, family_ceiling_eur: Optional[float] = None,
                   worker_ceiling_eur: Optional[float] = None, worker_ceiling_hours: Optional[float] = None,
                   year: Optional[int] = None) -> dict:
    """Verifica che aggiungere (add_nominale, add_hours) non sfori nessun
    massimale. Solleva HTTPException(400, 'lf_ceiling_exceeded:<quale>') se sì
    — non scala nulla (usare record_usage() dopo, solo se il confirm va a
    buon fine). Ritorna i totali proiettati per mostrarli al cliente."""
    couple = get_couple_totals(family_id, worker_id, year)
    proj_couple_nominale = couple["nominale_used"] + add_nominale
    proj_couple_hours = couple["hours_used"] + add_hours
    if proj_couple_nominale > couple_ceiling_eur:
        raise HTTPException(status_code=400, detail="lf_ceiling_exceeded:couple_eur")

    proj_family = None
    if family_ceiling_eur is not None:
        family_total = get_family_total(family_id, year)
        proj_family = family_total + add_nominale
        if proj_family > family_ceiling_eur:
            raise HTTPException(status_code=400, detail="lf_ceiling_exceeded:family_eur")

    worker_totals = None
    if worker_ceiling_eur is not None or worker_ceiling_hours is not None:
        worker_totals = get_worker_totals(worker_id, year)
        proj_worker_nominale = worker_totals["nominale_used"] + add_nominale
        proj_worker_hours = worker_totals["hours_used"] + add_hours
        if worker_ceiling_eur is not None and proj_worker_nominale > worker_ceiling_eur:
            raise HTTPException(status_code=400, detail="lf_ceiling_exceeded:worker_eur")
        if worker_ceiling_hours is not None and proj_worker_hours > worker_ceiling_hours:
            raise HTTPException(status_code=400, detail="lf_ceiling_exceeded:worker_hours")

    return {
        "couple_projected": {"nominale": round(proj_couple_nominale, 2), "hours": round(proj_couple_hours, 2)},
        "family_projected_eur": round(proj_family, 2) if proj_family is not None else None,
        "worker_projected": (
            {"nominale": round(worker_totals["nominale_used"] + add_nominale, 2),
             "hours": round(worker_totals["hours_used"] + add_hours, 2)}
            if worker_totals is not None else None
        ),
    }


def record_usage(family_id: str, worker_id: str, nominale: float, hours: float, year: Optional[int] = None) -> dict:
    """Registra l'uso effettivo (chiamare SOLO dopo che il confirm è andato a
    buon fine — non prima). Atomico via RPC (vedi migrazione
    blocco3_lf_ledger: lf_ledger_increment)."""
    y = year or _year()
    res = db.rpc("lf_ledger_increment", {
        "p_year": y, "p_family_id": family_id, "p_worker_id": worker_id,
        "p_nominale": round(float(nominale), 2), "p_hours": round(float(hours), 2),
    }).execute()
    return res.data
