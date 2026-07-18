from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core import db
from deps import require_admin
from trust import recalc_provider_trust, recalc_client_trust

router = APIRouter()


@router.get("/admin/stats")
async def admin_stats(_=Depends(require_admin)):
    users = await db.users.count_documents({})
    clients = await db.users.count_documents({"role": "client"})
    providers = await db.users.count_documents({"role": {"$in": ["provider", "business"]}})
    online = await db.users.count_documents({"role": {"$in": ["provider", "business"]}, "online": True})
    pending = await db.users.count_documents({"role": {"$in": ["provider", "business"]}, "approval_status": "pending"})
    missions = await db.missions.count_documents({})
    bookings = await db.bookings.find({}, {"_id": 0}).to_list(5000)
    completed = len([b for b in bookings if b.get("status") == "completed"])
    gmv = round(sum(b.get("total", 0) for b in bookings), 2)
    fees = round(sum(b.get("jobby_fee", 0) for b in bookings), 2)
    payments = await db.service_requests.find({"kind": "payment"}, {"_id": 0}).to_list(5000)
    pay_vol = round(sum(p.get("amount", 0) for p in payments), 2)
    topups = await db.transactions.find({"type": "topup", "status": "paid"}, {"_id": 0}).to_list(5000)
    topup_vol = round(sum(t.get("amount", 0) for t in topups), 2)
    cats_total = await db.categories.count_documents({})
    cats_active = await db.categories.count_documents({"active": True})
    return {
        "users": users, "clients": clients, "providers": providers, "providers_online": online,
        "pending_approvals": pending,
        "missions": missions, "bookings": len(bookings), "completed": completed,
        "gmv": gmv, "jobby_fees": fees, "payments_count": len(payments), "payments_volume": pay_vol,
        "topups_volume": topup_vol, "revenue": round(fees, 2),
        "categories_total": cats_total, "categories_active": cats_active,
    }


@router.get("/admin/users")
async def admin_users(_=Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [{
        "user_id": u["user_id"], "name": u.get("name"), "email": u.get("email"), "role": u.get("role"),
        "verification_status": u.get("verification_status", "unverified"),
        "approval_status": u.get("approval_status", "approved"),
        "trust_score": u.get("trust_score", 0), "client_trust_score": u.get("client_trust_score", 0),
        "rating": u.get("rating", 0), "wallet_balance": u.get("wallet_balance", 0),
        "is_bot": u.get("is_bot", False), "services": u.get("services", []),
        "online": u.get("online", False), "phone": u.get("phone", ""), "address": u.get("address", ""),
        "business_name": u.get("business_name", ""), "created_at": u.get("created_at", ""),
    } for u in users]


class UserStatusIn(BaseModel):
    status: str  # approved | suspended | rejected


@router.post("/admin/users/{user_id}/status")
async def admin_set_user_status(user_id: str, body: UserStatusIn, _=Depends(require_admin)):
    if body.status not in ("approved", "suspended", "rejected"):
        raise HTTPException(status_code=400, detail="invalid_status")
    upd = {"approval_status": body.status}
    if body.status == "approved":
        upd["provider_approved"] = True
    res = await db.users.update_one({"user_id": user_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="not_found")
    return {"user_id": user_id, "approval_status": body.status}


@router.get("/admin/bookings")
async def admin_bookings(_=Depends(require_admin)):
    return await db.bookings.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/admin/ui", response_class=HTMLResponse)
async def admin_ui():
    return HTMLResponse(ADMIN_HTML)


ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>JOBBY · Admin</title>
<style>
  :root{--bg:#0E1F3D;--card:#fff;--muted:#8A8781;--line:#e6e4de;--green:#1E9E5B;--orange:#FC5A2E;--purple:#6D3BEA;}
  *{box-sizing:border-box;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  body{margin:0;background:#f5f4f1;color:#1a1a1a}
  header{background:var(--bg);color:#fff;padding:18px 24px;display:flex;align-items:center;gap:12px}
  header b{font-size:20px;letter-spacing:1px}
  .badge{margin-left:auto;font-size:12px;background:rgba(255,255,255,.15);padding:4px 10px;border-radius:999px}
  .wrap{max-width:1100px;margin:0 auto;padding:20px}
  .tokbar{display:flex;gap:8px;margin-bottom:16px}
  .tokbar input{flex:1;padding:12px;border:1px solid var(--line);border-radius:10px;font-size:15px}
  button{cursor:pointer;border:0;border-radius:10px;padding:12px 16px;font-size:14px;font-weight:600}
  .primary{background:var(--orange);color:#fff}
  .ghost{background:#fff;border:1px solid var(--line)}
  .tabs{display:flex;gap:8px;margin:16px 0}
  .tab{background:#fff;border:1px solid var(--line);border-radius:999px;padding:8px 16px;font-weight:600}
  .tab.active{background:var(--bg);color:#fff;border-color:var(--bg)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
  .stat{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px}
  .stat .n{font-size:26px;font-weight:800}
  .stat .l{color:var(--muted);font-size:13px;margin-top:4px}
  table{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;border:1px solid var(--line)}
  th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);font-size:14px}
  th{background:#faf9f6;color:var(--muted);font-size:12px;text-transform:uppercase}
  .pill{padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600}
  .row{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:8px}
  .row .em{font-size:22px}
  .row .t{flex:1}
  .sw{width:46px;height:26px;border-radius:999px;background:#ccc;position:relative;transition:.2s}
  .sw.on{background:var(--green)}
  .sw:after{content:'';position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.2s}
  .sw.on:after{left:23px}
  .muted{color:var(--muted)}
  .hidden{display:none}
  .sec{font-size:13px;text-transform:uppercase;color:var(--muted);margin:18px 0 8px;font-weight:700}
  .err{color:#DE4B3F;font-size:14px;margin:8px 0}
</style>
</head>
<body>
<header><b>JOBBY</b> <span>Admin Dashboard</span><span class="badge" id="conn">not connected</span></header>
<div class="wrap">
  <div class="tokbar">
    <input id="token" type="password" placeholder="X-Admin-Token"/>
    <button class="primary" onclick="connect()">Connect</button>
  </div>
  <div id="err" class="err"></div>

  <div id="app" class="hidden">
    <div class="tabs">
      <div class="tab active" data-t="dashboard" onclick="go('dashboard')">Dashboard</div>
      <div class="tab" data-t="categories" onclick="go('categories')">Categories</div>
      <div class="tab" data-t="users" onclick="go('users')">Users</div>
      <div class="tab" data-t="bookings" onclick="go('bookings')">Bookings</div>
    </div>

    <div id="dashboard"></div>
    <div id="categories" class="hidden"></div>
    <div id="users" class="hidden"></div>
    <div id="bookings" class="hidden"></div>
  </div>
</div>
<script>
let TOKEN='';
const H=()=>({'X-Admin-Token':TOKEN,'Content-Type':'application/json'});
async function api(path,opts={}){const r=await fetch('/api'+path,{...opts,headers:H()});if(!r.ok)throw new Error(r.status);return r.json();}

async function connect(){
  TOKEN=document.getElementById('token').value.trim();
  document.getElementById('err').textContent='';
  try{ await api('/admin/stats'); localStorage.setItem('jobby_admin_token',TOKEN);
    document.getElementById('conn').textContent='connected'; document.getElementById('app').classList.remove('hidden');
    go('dashboard'); }
  catch(e){ document.getElementById('err').textContent='Invalid admin token'; }
}
function go(t){
  ['dashboard','categories','users','bookings'].forEach(x=>document.getElementById(x).classList.add('hidden'));
  document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('active',el.dataset.t===t));
  document.getElementById(t).classList.remove('hidden');
  if(t==='dashboard')loadDash(); if(t==='categories')loadCats(); if(t==='users')loadUsers(); if(t==='bookings')loadBookings();
}
async function loadDash(){
  const s=await api('/admin/stats');
  const items=[['Users',s.users],['Clients',s.clients],['Providers',s.providers],['Online now',s.providers_online],
   ['Missions',s.missions],['Bookings',s.bookings],['Completed',s.completed],['GMV (€)',s.gmv],
   ['JOBBY fees (€)',s.jobby_fees],['Payments',s.payments_count],['Payments vol (€)',s.payments_volume],
   ['Categories active',s.categories_active+'/'+s.categories_total]];
  document.getElementById('dashboard').innerHTML='<div class="grid">'+items.map(i=>
   `<div class="stat"><div class="n">${i[1]}</div><div class="l">${i[0]}</div></div>`).join('')+
   '</div><div style="margin-top:16px"><button class="ghost" onclick="recalc()">↻ Recalculate Trust Scores</button></div>';
}
async function recalc(){const r=await api('/admin/trust/recalc',{method:'POST'});alert('Recalculated '+r.recalculated+' users');}
async function loadCats(){
  const c=await api('/admin/categories');
  const groups={standard:'Standard Services',proximity:'Proximity Businesses',payment:'Payment Services'};
  let html='';
  for(const k in groups){
    html+='<div class="sec">'+groups[k]+'</div>';
    c.filter(x=>x.kind===k).forEach(x=>{
      html+=`<div class="row"><span class="em">${x.emoji||'🧩'}</span><div class="t"><b>${x.label.en}</b><div class="muted">${x.cat_id}</div></div>
        <div class="sw ${x.active?'on':''}" onclick="toggleCat('${x.cat_id}',this)"></div></div>`;
    });
  }
  document.getElementById('categories').innerHTML=html;
}
async function toggleCat(id,el){const desired=!el.classList.contains('on');const r=await api('/admin/categories/'+id+'/set',{method:'POST',body:JSON.stringify({active:desired})});el.classList.toggle('on',r.active);}
async function loadUsers(){
  const u=await api('/admin/users');
  let rows=u.map(x=>`<tr><td>${x.name||''}${x.is_bot?' 🤖':''}<div class="muted">${x.email||''}</div></td>
    <td><span class="pill" style="background:#eee">${x.role}</span></td>
    <td>${x.verification_status}</td><td>${x.trust_score||0}</td><td>${x.client_trust_score||0}</td>
    <td>€${(x.wallet_balance||0).toFixed(2)}</td></tr>`).join('');
  document.getElementById('users').innerHTML='<table><tr><th>User</th><th>Role</th><th>KYC</th><th>Provider Trust</th><th>Client Trust</th><th>Wallet</th></tr>'+rows+'</table>';
}
async function loadBookings(){
  const b=await api('/admin/bookings');
  let rows=b.map(x=>`<tr><td>${x.category}</td><td>${x.customer_name}</td><td>${x.provider_name}</td>
    <td><span class="pill" style="background:#eee">${x.status}</span></td><td>€${(x.total||0).toFixed(2)}</td><td>${x.date} ${x.time}</td></tr>`).join('');
  document.getElementById('bookings').innerHTML='<table><tr><th>Service</th><th>Client</th><th>Provider</th><th>Status</th><th>Total</th><th>When</th></tr>'+rows+'</table>';
}
(function(){const t=localStorage.getItem('jobby_admin_token');if(t){document.getElementById('token').value=t;connect();}})();
</script>
</body>
</html>
"""
