# JOBBY — Backend Console (Web App)

A standalone, static web app to manage the JOBBY backend from any browser.
It connects to your JOBBY FastAPI backend using the **Admin Token** and shows:

- **Dashboard** — revenue monitoring (JOBBY fees, GMV, top-ups, payments) + operations stats
- **Users** — full user list with **Approve / Suspend / Reject** (clients are auto-approved; providers & businesses require approval)
- **Categories** — activate/deactivate services & businesses
- **Bookings** — recent bookings

## Run locally
Just open `index.html` in a browser, or serve the folder:
```bash
cd admin-web
python3 -m http.server 5500
# open http://localhost:5500
```
Then enter your **Backend URL** (e.g. `https://your-app.preview.emergentagent.com`) and your **Admin Token**.

## Deploy to Netlify
This is a pure static site (no build step).

**Option A — Drag & drop:** go to https://app.netlify.com/drop and drop the `admin-web` folder.

**Option B — Connect the repo:**
1. New site → Import from Git → pick this repository.
2. Set **Base directory:** `admin-web`
3. **Build command:** *(leave empty)*
4. **Publish directory:** `admin-web` (or `.` if base directory is already `admin-web`)
5. Deploy.

`netlify.toml` is already configured (publish `.`, no build).

## Backend requirements (CORS)
The backend must allow requests from your Netlify domain. JOBBY's FastAPI already
uses permissive CORS (`allow_origins=["*"]`). If you lock CORS down later, add your
Netlify URL to the allowed origins.

## Security
- The Admin Token is stored only in your browser's `localStorage` for convenience.
- Never commit real tokens. Use the token from `/app/memory/test_credentials.md`.
