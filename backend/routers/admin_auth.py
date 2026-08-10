"""RITIRATO nel Blocco 7 (migrazione Emergent -> Supabase/Render) — non più
importato/esposto da server.py, su conferma esplicita dell'utente (login
bcrypt+TOTP custom sostituito dal login/SSO nativo di Retool, come già
segnalato nella spec del Blocco 6). `server.py` non chiama più
`admin_auth.seed_admin()` nello startup. File lasciato nel repo come
riferimento storico (Mongo, non funzionante senza MONGO_URL). Docstring
originale sotto, invariata.

---

JOBBY — Autenticazione del backoffice WEB (admin).

Sostituisce il token statico con un vero login:
  • email + password (bcrypt)
  • 2FA TOTP compatibile con Google Authenticator / Authy (pyotp + QR)
  • sessione server-side in cookie httponly (`jobby_admin`) su collection `admin_sessions`

Protegge la pagina HTML `/api/admin/ui` e tutte le API `/api/admin/*`
(la dependency `require_admin` accetta il cookie di sessione OPPURE, per i test
automatici, l'header legacy `X-Admin-Token`).
"""
import os
import io
import base64
import secrets
from datetime import timedelta

import bcrypt
import pyotp
import qrcode
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from core import db, now_utc

router = APIRouter()

ADMIN_EMAIL = os.environ.get("ADMIN_LOGIN_EMAIL", "hello@jobbyfree.it")
ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "Jobby!Admin2026")
COOKIE = "jobby_admin"
SESSION_HOURS = 12
ISSUER = "JOBBY Admin"
MAX_FAILS = 8
LOCK_MINUTES = 15


# ---------------- password / session helpers ----------------
def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False


async def seed_admin():
    """Crea (idempotente) l'account admin unico."""
    existing = await db.admin_users.find_one({"email": ADMIN_EMAIL})
    if not existing:
        await db.admin_users.insert_one({
            "email": ADMIN_EMAIL,
            "password_hash": _hash(ADMIN_INITIAL_PASSWORD),
            "otp_secret": None,
            "otp_configured": False,
            "must_change_password": True,
            "created_at": now_utc().isoformat(),
        })


async def _new_session(email: str) -> str:
    sid = secrets.token_urlsafe(32)
    await db.admin_sessions.insert_one({
        "sid": sid, "email": email,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(hours=SESSION_HOURS),
    })
    return sid


async def current_admin(request: Request):
    sid = request.cookies.get(COOKIE)
    if not sid:
        return None
    sess = await db.admin_sessions.find_one({"sid": sid})
    if not sess:
        return None
    exp = sess["expires_at"]
    from datetime import timezone
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc():
        return None
    return await db.admin_users.find_one({"email": sess["email"]}, {"_id": 0, "password_hash": 0})


# ---------------- rate limiting (brute force) ----------------
async def _check_lock(ip: str):
    rec = await db.admin_login_attempts.find_one({"ip": ip})
    if rec and rec.get("fails", 0) >= MAX_FAILS:
        exp = rec.get("locked_until")
        if exp and exp > now_utc():
            raise HTTPException(status_code=429, detail="too_many_attempts")


async def _register_fail(ip: str):
    await db.admin_login_attempts.update_one(
        {"ip": ip},
        {"$inc": {"fails": 1}, "$set": {"locked_until": now_utc() + timedelta(minutes=LOCK_MINUTES)}},
        upsert=True)


async def _reset_fail(ip: str):
    await db.admin_login_attempts.delete_one({"ip": ip})


# ---------------- HTML ----------------
PAGE_CSS = """
*{box-sizing:border-box;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
body{margin:0;background:#0E1F3D;color:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:18px;padding:32px;width:380px;max-width:92vw;box-shadow:0 20px 60px rgba(0,0,0,.35)}
h1{font-size:22px;margin:0 0 4px;letter-spacing:1px} .sub{color:#8A8781;font-size:14px;margin:0 0 20px}
label{display:block;font-size:13px;color:#555;margin:12px 0 4px;font-weight:600}
input{width:100%;padding:12px;border:1px solid #e6e4de;border-radius:10px;font-size:15px}
button{width:100%;margin-top:20px;cursor:pointer;border:0;border-radius:10px;padding:13px;font-size:15px;font-weight:700;background:#FC5A2E;color:#fff}
.err{background:#FBE0DD;color:#DE4B3F;padding:10px 12px;border-radius:10px;font-size:13px;margin-bottom:8px}
.qr{text-align:center;margin:16px 0} .qr img{width:200px;height:200px} .mono{font-family:monospace;font-size:12px;word-break:break-all;color:#555;text-align:center}
.logo{width:40px;height:40px;background:#0E1F3D;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:800;margin-bottom:12px}
"""


def _wrap(inner: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>JOBBY · Admin Login</title><style>{PAGE_CSS}</style></head><body><div class='card'><div class='logo'>J</div>{inner}</div></body></html>"


def _login_form(err: str = "", need_otp: bool = False, email: str = "") -> str:
    e = f"<div class='err'>{err}</div>" if err else ""
    otp = "<label>Codice 2FA (Google Authenticator)</label><input name='otp' inputmode='numeric' autocomplete='one-time-code' placeholder='6 cifre'/>" if need_otp else ""
    return _wrap(f"""
    <h1>JOBBY Admin</h1><p class='sub'>Accedi al backoffice</p>{e}
    <form method='post' action='/api/admin/login'>
      <label>Email</label><input name='email' type='email' value='{email}' required/>
      <label>Password</label><input name='password' type='password' required/>
      {otp}
      <button type='submit'>Accedi</button>
    </form>""")


def _enroll_page(secret: str, uri: str, email: str, err: str = "") -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    e = f"<div class='err'>{err}</div>" if err else ""
    return _wrap(f"""
    <h1>Attiva la 2FA</h1><p class='sub'>Inquadra il QR con Google Authenticator, poi inserisci il codice.</p>{e}
    <div class='qr'><img src='data:image/png;base64,{b64}'/><div class='mono'>{secret}</div></div>
    <form method='post' action='/api/admin/login'>
      <input type='hidden' name='email' value='{email}'/>
      <input type='hidden' name='password' value='__ENROLL__'/>
      <input type='hidden' name='enroll_secret' value='{secret}'/>
      <label>Codice a 6 cifre</label><input name='otp' inputmode='numeric' autocomplete='one-time-code' required/>
      <button type='submit'>Conferma e accedi</button>
    </form>""")


def _change_pw_page(err: str = "") -> str:
    e = f"<div class='err'>{err}</div>" if err else ""
    return _wrap(f"""
    <h1>Cambia password</h1><p class='sub'>Imposta una nuova password sicura.</p>{e}
    <form method='post' action='/api/admin/change-password'>
      <label>Password attuale</label><input name='current' type='password' required/>
      <label>Nuova password</label><input name='new1' type='password' required/>
      <label>Ripeti nuova password</label><input name='new2' type='password' required/>
      <button type='submit'>Salva</button>
    </form>""")


# ---------------- routes ----------------
@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if await current_admin(request):
        return RedirectResponse("/api/admin/ui", status_code=303)
    return HTMLResponse(_login_form())


@router.post("/admin/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...),
                otp: str = Form(None), enroll_secret: str = Form(None)):
    ip = request.client.host if request.client else "unknown"
    await _check_lock(ip)
    admin = await db.admin_users.find_one({"email": email.strip().lower()}) or await db.admin_users.find_one({"email": email.strip()})
    if not admin:
        await _register_fail(ip)
        return HTMLResponse(_login_form("Credenziali non valide.", email=email))

    # Enrollment confirmation step (password field carries sentinel)
    if enroll_secret and password == "__ENROLL__":
        if not otp or not pyotp.TOTP(enroll_secret).verify(otp, valid_window=1):
            uri = pyotp.TOTP(enroll_secret).provisioning_uri(name=email, issuer_name=ISSUER)
            return HTMLResponse(_enroll_page(enroll_secret, uri, email, "Codice errato, riprova."))
        await db.admin_users.update_one({"email": admin["email"]},
                                        {"$set": {"otp_secret": enroll_secret, "otp_configured": True}})
        await _reset_fail(ip)
        return await _finish_login(admin)

    # Normal login: verify password
    if not _verify(password, admin["password_hash"]):
        await _register_fail(ip)
        return HTMLResponse(_login_form("Credenziali non valide.", email=email))

    # First login → start 2FA enrollment
    if not admin.get("otp_configured"):
        secret = pyotp.random_base32()
        uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)
        return HTMLResponse(_enroll_page(secret, uri, email))

    # 2FA required
    if not otp or not pyotp.TOTP(admin["otp_secret"]).verify(otp, valid_window=1):
        await _register_fail(ip)
        return HTMLResponse(_login_form("Codice 2FA errato.", need_otp=True, email=email))

    await _reset_fail(ip)
    return await _finish_login(admin)


async def _finish_login(admin: dict):
    sid = await _new_session(admin["email"])
    target = "/api/admin/change-password" if admin.get("must_change_password") else "/api/admin/ui"
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=True, max_age=SESSION_HOURS * 3600)
    return resp


@router.get("/admin/change-password", response_class=HTMLResponse)
async def change_pw_page(request: Request):
    if not await current_admin(request):
        return RedirectResponse("/api/admin/login", status_code=303)
    return HTMLResponse(_change_pw_page())


@router.post("/admin/change-password")
async def change_pw(request: Request, current: str = Form(...), new1: str = Form(...), new2: str = Form(...)):
    admin = await current_admin(request)
    if not admin:
        return RedirectResponse("/api/admin/login", status_code=303)
    full = await db.admin_users.find_one({"email": admin["email"]})
    if not _verify(current, full["password_hash"]):
        return HTMLResponse(_change_pw_page("Password attuale errata."))
    if new1 != new2 or len(new1) < 8:
        return HTMLResponse(_change_pw_page("Le password non coincidono o sono troppo corte (min 8)."))
    await db.admin_users.update_one({"email": admin["email"]},
                                    {"$set": {"password_hash": _hash(new1), "must_change_password": False}})
    return RedirectResponse("/api/admin/ui", status_code=303)


@router.get("/admin/logout")
async def logout(request: Request):
    sid = request.cookies.get(COOKIE)
    if sid:
        await db.admin_sessions.delete_one({"sid": sid})
    resp = RedirectResponse("/api/admin/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
