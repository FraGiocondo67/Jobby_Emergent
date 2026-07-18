# JOBBY — Guida ai Secrets di Produzione

Questo documento elenca TUTTE le variabili/segreti necessari per andare live e
DOVE inserirli. Al Publish su Emergent li incolli nel pannello
**Deployment → Secrets / Environment Variables**. Modello: `backend/.env.production.example`.

## Cosa incollare (in ordine di priorità)

| Variabile | Obbligatoria | Dove ottenerla | Note |
|---|---|---|---|
| `ADMIN_TOKEN` | ✅ | La scegli tu | Usa 32+ caratteri casuali. Serve per `/api/admin/ui` e la console Netlify. **Ruota quello di test.** |
| `STRIPE_API_KEY` | ✅ (per pagamenti reali) | Stripe Dashboard → Developers → API keys | In produzione usa `sk_live_...`. In test resta la chiave gestita da Emergent. |
| `STRIPE_WEBHOOK_SECRET` | Consigliata | Stripe → Developers → Webhooks → Signing secret | Per verificare i webhook in produzione (`whsec_...`). |
| `SUMSUB_APP_TOKEN` | Solo per KYC reale | Sumsub Dashboard → Dev space → App tokens | KYC ora è **MOCKED**: serve al passo di integrazione Sumsub. |
| `SUMSUB_SECRET_KEY` | Solo per KYC reale | Sumsub Dashboard | idem |
| `SUMSUB_BASE_URL` | No | — | Default `https://api.sumsub.com`. |
| `MONGO_URL`, `DB_NAME` | ✅ | **Gestite da Emergent** | Non modificarle: le inietta la piattaforma. |
| `EMERGENT_SESSION_URL` | No | — | Default già corretto (Google Login Emergent). |

## Passi al Publish
1. Clicca **Publish/Deploy** (in alto a destra) nel task Mobile di JOBBY.
2. Apri il pannello **Deployment → Secrets** e incolla i valori sopra.
3. Deploya. Ottieni l'URL pubblico del backend.
4. (Opzionale) Pubblica la console statica `admin-web/` su Netlify e inserisci lì
   l'URL del backend + `ADMIN_TOKEN`.

## Stato integrazioni (importante)
- 💳 **Stripe**: il **top-up del wallet** usa Stripe reale (ora in *test mode* via proxy Emergent).
  Per usare la TUA chiave `sk_live_` e per far passare anche i **pagamenti delle prenotazioni**
  end-to-end serve un passo di integrazione dedicato (posso farlo su richiesta).
- 🪪 **Sumsub (KYC)**: attualmente **SIMULATO**. Le chiavi qui sopra servono quando faremo
  l'integrazione reale (passo separato).
- 🏦 **IBAN / 🪙 Crypto payout**: al momento vengono solo **salvati** (nessun trasferimento reale).

> Nota: questo file è un *modello*. L'`.env` in esecuzione non è stato modificato,
> così l'app in sviluppo continua a funzionare. In produzione i valori vivono nei
> Secrets di Emergent, non nel repo.
