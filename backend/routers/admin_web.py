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
        "business_name": u.get("business_name", ""), "vat_number": u.get("vat_number", ""),
        "created_at": u.get("created_at", ""),
    } for u in users]


@router.get("/admin/users/{user_id}/documents")
async def admin_user_documents(user_id: str, _=Depends(require_admin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="not_found")
    return {
        "business_name": u.get("business_name", ""), "vat_number": u.get("vat_number", ""),
        "address": u.get("address", ""), "phone": u.get("phone", ""),
        "license_document": u.get("license_document", ""), "business_photos": u.get("business_photos", []),
    }


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
  .pill{padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;display:inline-block}
  .p-approved{background:#E4F6EC;color:var(--green)} .p-pending{background:#FDF0DD;color:#E8912A}
  .p-suspended{background:#FDE7E4;color:var(--orange)} .p-rejected{background:#FBE0DD;color:#DE4B3F}
  .act{display:flex;gap:6px}
  .act button{padding:6px 10px;font-size:12px}
  .b-approve{background:var(--green);color:#fff}.b-suspend{background:#E8912A;color:#fff}.b-reject{background:#DE4B3F;color:#fff}
  .stat.rev{background:linear-gradient(135deg,#0E1F3D,#20325a);color:#fff}.stat.rev .l{color:#c9d3e8}
  .filters{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}.filters .tab{padding:6px 12px;font-size:13px}
  .row{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:8px}
  .row .em{font-size:22px}
  .row .t{flex:1}
  .sw{width:46px;height:26px;border-radius:999px;background:#ccc;position:relative;transition:.2s}
  .sw.on{background:var(--green)}
  .sw:after{content:'';position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.2s}
  .sw.on:after{left:23px}
  .muted{color:var(--muted)}
  .comm{margin-top:6px;font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
  .comm input{width:70px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;font-size:13px}
  .hidden{display:none!important}
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
      <div class="tab" data-t="disputes" onclick="go('disputes')">Disputes</div>
      <div class="tab" data-t="pulizie" onclick="go('pulizie')">Pulizie</div>
      <div class="tab" data-t="babysitting" onclick="go('babysitting')">Babysitting</div>
      <div class="tab" data-t="driver" onclick="go('driver')">Driver</div>
      <div class="tab" data-t="artigiani" onclick="go('artigiani')">Artigiani</div>
      <div class="tab" data-t="spec4" onclick="go('spec4')">Regole</div>
      <div class="tab" data-t="verifiche" onclick="go('verifiche')">Verifiche</div>
      <div class="tab" data-t="onboarding" onclick="go('onboarding')">Onboarding</div>
    </div>

    <div id="dashboard"></div>
    <div id="categories" class="hidden"></div>
    <div id="users" class="hidden"></div>
    <div id="bookings" class="hidden"></div>
    <div id="disputes" class="hidden"></div>
    <div id="pulizie" class="hidden"></div>
    <div id="babysitting" class="hidden"></div>
    <div id="driver" class="hidden"></div>
    <div id="artigiani" class="hidden"></div>
    <div id="spec4" class="hidden"></div>
    <div id="verifiche" class="hidden"></div>
    <div id="onboarding" class="hidden"></div>
  </div>
</div>
<div id="docModal" class="hidden" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;padding:20px;z-index:9">
  <div style="background:#fff;border-radius:14px;max-width:520px;width:100%;max-height:85vh;overflow:auto;padding:20px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <b id="docTitle" style="font-size:18px"></b>
      <button class="ghost" onclick="document.getElementById('docModal').classList.add('hidden')">✕</button>
    </div>
    <div id="docBody"></div>
  </div>
</div>
<script>
async function viewDocs(id){
  const d=await api('/admin/users/'+id+'/documents');
  document.getElementById('docTitle').textContent=d.business_name||'Business';
  let html='<div class="muted" style="margin:8px 0">P.IVA: <b>'+(d.vat_number||'—')+'</b><br>Tel: '+(d.phone||'—')+'<br>Indirizzo: '+(d.address||'—')+'</div>';
  html+='<div class="sec">Visura / Licenza</div>';
  html+= d.license_document?'<img src="'+d.license_document+'" style="width:100%;border-radius:10px;border:1px solid var(--line)"/>':'<div class="muted">Nessun documento</div>';
  html+='<div class="sec">Foto attività</div>';
  if((d.business_photos||[]).length){html+='<div style="display:flex;gap:8px;flex-wrap:wrap">'+d.business_photos.map(p=>'<img src="'+p+'" style="width:110px;height:110px;object-fit:cover;border-radius:10px;border:1px solid var(--line)"/>').join('')+'</div>';}
  else{html+='<div class="muted">Nessuna foto</div>';}
  document.getElementById('docBody').innerHTML=html;
  document.getElementById('docModal').classList.remove('hidden');
}
</script>
<div id="fieldsModal" class="hidden" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;padding:16px;z-index:9">
  <div style="background:#fff;border-radius:14px;max-width:620px;width:100%;max-height:88vh;overflow:auto;padding:20px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <b id="fldTitle" style="font-size:18px"></b>
      <button class="ghost" onclick="document.getElementById('fieldsModal').classList.add('hidden')">✕</button>
    </div>
    <div class="muted" style="margin:6px 0 12px">Configure the request-form fields shown to clients.</div>
    <div id="fldList"></div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="ghost" onclick="addField()">+ Add field</button>
      <button class="primary" onclick="saveFields()">Save fields</button>
    </div>
  </div>
</div>
<style>
  .fld{border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:8px}
  .fld input,.fld select,.fld textarea{width:100%;padding:7px;border:1px solid var(--line);border-radius:8px;font-size:13px;margin-top:4px}
  .fld .g{display:flex;gap:8px}.fld .g>div{flex:1}
  .fld label{font-size:11px;color:var(--muted);text-transform:uppercase}
  .opt{display:flex;gap:6px;margin-top:4px}
</style>
<script>
let EDIT_CAT=''; let EF=[];
function moveField(i,dir){const j=i+dir;if(j<0||j>=EF.length)return;const tmp=EF[i];EF[i]=EF[j];EF[j]=tmp;renderFields();}
function editFields(id){
  EDIT_CAT=id;
  const c=(window.__CATS||[]).find(x=>x.cat_id===id);
  document.getElementById('fldTitle').textContent=(c&&c.label.en)||id;
  EF=((c&&c.questions)||[]).map(q=>({
    id:q.id||'', type:q.type||'text',
    li:(q.label&&q.label.it)||'', le:(q.label&&q.label.en)||'',
    pi:(q.placeholder&&q.placeholder.it)||'', pe:(q.placeholder&&q.placeholder.en)||'',
    min:q.min!=null?q.min:1, max:q.max!=null?q.max:10, def:q.default!=null?q.default:1,
    opts:(q.options||[]).map(o=>({id:o.id||'',li:(o.label&&o.label.it)||'',le:(o.label&&o.label.en)||''}))
  }));
  renderFields();
  document.getElementById('fieldsModal').classList.remove('hidden');
}
function renderFields(){
  let h='';
  EF.forEach((f,i)=>{
    h+='<div class="fld"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><b class="muted">#'+(i+1)+'</b>'+
       '<div style="display:flex;gap:4px"><button class="ghost" '+(i===0?'disabled':'')+' onclick="moveField('+i+',-1)">&uarr;</button>'+
       '<button class="ghost" '+(i===EF.length-1?'disabled':'')+' onclick="moveField('+i+',1)">&darr;</button></div></div>'+
       '<div class="g"><div><label>Field id</label><input value="'+f.id+'" oninput="EF['+i+'].id=this.value"/></div>'+
       '<div><label>Type</label><select onchange="EF['+i+'].type=this.value;renderFields()">'+
       ['text','number','select','date','time'].map(t=>'<option value="'+t+'" '+(f.type===t?'selected':'')+'>'+t+'</option>').join('')+'</select></div></div>'+
       '<div class="g"><div><label>Label IT</label><input value="'+f.li+'" oninput="EF['+i+'].li=this.value"/></div>'+
       '<div><label>Label EN</label><input value="'+f.le+'" oninput="EF['+i+'].le=this.value"/></div></div>';
    if(f.type==='text'){
      h+='<div class="g"><div><label>Placeholder IT</label><input value="'+f.pi+'" oninput="EF['+i+'].pi=this.value"/></div>'+
         '<div><label>Placeholder EN</label><input value="'+f.pe+'" oninput="EF['+i+'].pe=this.value"/></div></div>';
    }
    if(f.type==='number'){
      h+='<div class="g"><div><label>Min</label><input type="number" value="'+f.min+'" oninput="EF['+i+'].min=this.value"/></div>'+
         '<div><label>Max</label><input type="number" value="'+f.max+'" oninput="EF['+i+'].max=this.value"/></div>'+
         '<div><label>Default</label><input type="number" value="'+f.def+'" oninput="EF['+i+'].def=this.value"/></div></div>';
    }
    if(f.type==='select'){
      h+='<label style="margin-top:6px;display:block">Options (id · IT · EN)</label>';
      f.opts.forEach((o,j)=>{h+='<div class="opt"><input placeholder="id" value="'+o.id+'" oninput="EF['+i+'].opts['+j+'].id=this.value"/>'+
        '<input placeholder="IT" value="'+o.li+'" oninput="EF['+i+'].opts['+j+'].li=this.value"/>'+
        '<input placeholder="EN" value="'+o.le+'" oninput="EF['+i+'].opts['+j+'].le=this.value"/>'+
        '<button class="ghost" onclick="EF['+i+'].opts.splice('+j+',1);renderFields()">✕</button></div>';});
      h+='<button class="ghost" style="margin-top:6px" onclick="EF['+i+'].opts.push({id:\\'\\',li:\\'\\',le:\\'\\'});renderFields()">+ option</button>';
    }
    h+='<div style="text-align:right;margin-top:8px"><button class="b-reject" onclick="EF.splice('+i+',1);renderFields()">Remove field</button></div></div>';
  });
  document.getElementById('fldList').innerHTML=h||'<div class="muted">No fields yet.</div>';
}
function addField(){EF.push({id:'',type:'text',li:'',le:'',pi:'',pe:'',min:1,max:10,def:1,opts:[]});renderFields();}
async function saveFields(){
  const qs=EF.filter(f=>f.id.trim()).map(f=>{
    const q={id:f.id.trim(),label:{it:f.li,en:f.le},type:f.type};
    if(f.type==='text'){q.placeholder={it:f.pi,en:f.pe};}
    if(f.type==='number'){q.min=Number(f.min);q.max=Number(f.max);q.default=Number(f.def);}
    if(f.type==='select'){q.options=f.opts.filter(o=>o.id.trim()).map(o=>({id:o.id.trim(),label:{it:o.li,en:o.le}}));}
    return q;
  });
  await api('/admin/categories/'+EDIT_CAT+'/questions',{method:'PUT',body:JSON.stringify({questions:qs})});
  document.getElementById('fieldsModal').classList.add('hidden');
  loadCats();
}
</script>
<script>
let TOKEN='';
let USERFILTER='all';
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
  ['dashboard','categories','users','bookings','disputes','pulizie','babysitting','driver','artigiani','spec4','verifiche','onboarding'].forEach(x=>document.getElementById(x).classList.add('hidden'));
  document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('active',el.dataset.t===t));
  document.getElementById(t).classList.remove('hidden');
  if(t==='dashboard')loadDash(); if(t==='categories')loadCats(); if(t==='users')loadUsers(); if(t==='bookings')loadBookings(); if(t==='disputes')loadDisputes(); if(t==='pulizie')loadPulizie(); if(t==='babysitting')loadBabysitting(); if(t==='driver')loadDriver(); if(t==='artigiani')loadArtigiani(); if(t==='spec4')loadSpec4(); if(t==='verifiche')loadVerifiche(); if(t==='onboarding')loadOnboarding();
}
async function loadDash(){
  const s=await api('/admin/stats');
  const rev=[['Revenue (JOBBY fees €)',s.revenue],['GMV (€)',s.gmv],['Top-ups (€)',s.topups_volume],['Payments vol (€)',s.payments_volume]];
  const ops=[['Users',s.users],['Clients',s.clients],['Providers',s.providers],['Online now',s.providers_online],
   ['Pending approvals',s.pending_approvals],['Missions',s.missions],['Bookings',s.bookings],['Completed',s.completed],
   ['Payments',s.payments_count],['Categories active',s.categories_active+'/'+s.categories_total]];
  document.getElementById('dashboard').innerHTML=
   '<div class="sec">Revenue monitoring</div><div class="grid">'+rev.map(i=>`<div class="stat rev"><div class="n">${i[1]}</div><div class="l">${i[0]}</div></div>`).join('')+'</div>'+
   '<div class="sec">Operations</div><div class="grid">'+ops.map(i=>`<div class="stat"><div class="n">${i[1]}</div><div class="l">${i[0]}</div></div>`).join('')+'</div>'+
   '<div style="margin-top:16px"><button class="ghost" onclick="recalc()">↻ Recalculate Trust Scores</button></div>';
}
async function recalc(){const r=await api('/admin/trust/recalc',{method:'POST'});alert('Recalculated '+r.recalculated+' users');}
async function loadCats(){
  const c=await api('/admin/categories');
  window.__CATS=c;
  const groups={standard:'Standard Services',proximity:'Proximity Businesses',payment:'Payment Services'};
  let html='';
  for(const k in groups){
    html+='<div class="sec">'+groups[k]+'</div>';
    c.filter(x=>x.kind===k).forEach(x=>{
      const comm=(k!=='payment')?`<div class="comm">Commission %
        <input type="number" min="0" max="100" step="0.5" value="${x.commission_pct!=null?x.commission_pct:10}" id="comm-${x.cat_id}" onchange="setCommission('${x.cat_id}',this.value)"/></div>`:'';
      html+=`<div class="row"><span class="em">${x.emoji||'🧩'}</span><div class="t"><b>${x.label.en}</b><div class="muted">${x.cat_id} · ${(x.questions||[]).length} fields</div>${comm}</div>
        <button class="ghost" onclick="editFields('${x.cat_id}')">Fields</button>
        <div class="sw ${x.active?'on':''}" onclick="toggleCat('${x.cat_id}',this)"></div></div>`;
    });
  }
  document.getElementById('categories').innerHTML=html;
}
async function setCommission(id,val){
  const pct=parseFloat(val);if(isNaN(pct))return;
  try{await api('/admin/categories/'+id+'/commission',{method:'POST',body:JSON.stringify({commission_pct:pct})});}
  catch(e){alert('Invalid commission');}
}
async function toggleCat(id,el){const desired=!el.classList.contains('on');const r=await api('/admin/categories/'+id+'/set',{method:'POST',body:JSON.stringify({active:desired})});el.classList.toggle('on',r.active);}
async function loadUsers(){
  const u=await api('/admin/users');
  const filtered=u.filter(x=>USERFILTER==='all'?true:USERFILTER==='pending'?(x.approval_status==='pending'&&x.role!=='client'):x.role===USERFILTER);
  const chips=[['all','All'],['pending','Pending'],['provider','Providers'],['business','Business'],['client','Clients']];
  let bar='<div class="filters">'+chips.map(c=>`<div class="tab ${USERFILTER===c[0]?'active':''}" onclick="setUF('${c[0]}')">${c[1]}</div>`).join('')+'</div>';
  let rows=filtered.map(x=>{
    const st=x.approval_status||'approved';
    const needs=(x.role==='provider'||x.role==='business');
    const actions=needs?`<div class="act">
      ${x.role==='business'?`<button class="ghost" onclick="viewDocs('${x.user_id}')">Docs</button>`:''}
      ${st!=='approved'?`<button class="b-approve" onclick="setStatus('${x.user_id}','approved')">Approve</button>`:''}
      ${st!=='suspended'?`<button class="b-suspend" onclick="setStatus('${x.user_id}','suspended')">Suspend</button>`:''}
      ${st!=='rejected'?`<button class="b-reject" onclick="setStatus('${x.user_id}','rejected')">Reject</button>`:''}
    </div>`:'<span class="muted">auto</span>';
    return `<tr>
      <td>${x.business_name||x.name||''}${x.is_bot?' 🤖':''}<div class="muted">${x.email||''}${x.phone?' · '+x.phone:''}</div></td>
      <td><span class="pill" style="background:#eee">${x.role}</span></td>
      <td><span class="pill p-${st}">${st}</span></td>
      <td>${x.role==='client'?(x.client_trust_score||0):(x.trust_score||0)}</td>
      <td>€${(x.wallet_balance||0).toFixed(2)}</td>
      <td>${actions}</td></tr>`;}).join('');
  document.getElementById('users').innerHTML=bar+'<table><tr><th>User</th><th>Role</th><th>Status</th><th>Trust</th><th>Wallet</th><th>Actions</th></tr>'+rows+'</table>';
}
function setUF(f){USERFILTER=f;loadUsers();}
async function setStatus(id,status){
  if(status!=='approved'&&!confirm('Set user to '+status+'?'))return;
  await api('/admin/users/'+id+'/status',{method:'POST',body:JSON.stringify({status})});
  loadUsers();
}
async function loadBookings(){
  const b=await api('/admin/bookings');
  let rows=b.map(x=>`<tr><td>${x.category}</td><td>${x.customer_name}</td><td>${x.provider_name}</td>
    <td><span class="pill" style="background:#eee">${x.status}</span></td><td>€${(x.total||0).toFixed(2)}</td><td>${x.date} ${x.time}</td></tr>`).join('');
  document.getElementById('bookings').innerHTML='<table><tr><th>Service</th><th>Client</th><th>Provider</th><th>Status</th><th>Total</th><th>When</th></tr>'+rows+'</table>';
}
const RECLABEL={refund_full:'Full refund',refund_partial:'Partial refund',reject:'No refund'};
async function loadDisputes(){
  const list=await api('/admin/disputes');
  if(!list.length){document.getElementById('disputes').innerHTML='<div class="muted" style="padding:20px">No disputes yet.</div>';return;}
  let html='<div class="sec">Contestazioni / Disputes</div>';
  list.forEach(d=>{
    const ai=d.ai_recommendation||{};
    const conf=Math.round((ai.confidence||0)*100);
    const resolved=['resolved_mutual','resolved_jobby','rejected'].includes(d.status);
    const defPct=ai.refund_pct!=null?ai.refund_pct:50;
    const msgs=(d.messages||[]).map(m=>`<div style="margin:2px 0"><b>${m.from}:</b> ${m.text||''}</div>`).join('');
    html+=`<div class="row" style="flex-direction:column;align-items:stretch;gap:10px">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="em">⚖️</span>
        <div class="t"><b>${d.reason_code}</b> · €${(d.amount||0).toFixed(2)}
          <div class="muted">${d.dispute_id} · booking ${d.booking_id}</div></div>
        <span class="pill" style="background:#eee">${d.status}</span>
      </div>
      ${d.description?`<div class="muted">Cliente: ${d.description}</div>`:''}
      ${d.provider_response?`<div class="muted">Fornitore: ${d.provider_response}</div>`:''}
      <div style="background:#F5F1FF;border:1px solid #E0D4FF;border-radius:10px;padding:10px">
        <div style="color:var(--purple);font-weight:700;font-size:12px;text-transform:uppercase">AI proposal · ${conf}% confidence</div>
        <div style="font-weight:700;margin-top:4px">${RECLABEL[ai.recommendation]||'—'}${ai.recommendation==='refund_partial'?' · '+ai.refund_pct+'%':''}</div>
        <div class="muted" style="margin-top:4px">${ai.rationale||''}</div>
      </div>
      ${msgs?`<div style="font-size:13px">${msgs}</div>`:''}
      ${resolved?`<div class="muted">Resolved: ${d.resolution?(RECLABEL[d.resolution.decision]||(d.resolution.refund_pct>=100?'Full refund':d.resolution.refund_pct>0?('Partial '+d.resolution.refund_pct+'%'):'No refund')):''} ${d.resolution&&d.resolution.refund_amount!=null?('· €'+d.resolution.refund_amount.toFixed(2)):''}</div>`:
      `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <input id="pct-${d.dispute_id}" type="number" min="0" max="100" value="${defPct}" style="width:70px;padding:6px;border:1px solid var(--line);border-radius:8px"/>
        <input id="note-${d.dispute_id}" placeholder="Note (optional)" style="flex:1;min-width:140px;padding:6px;border:1px solid var(--line);border-radius:8px"/>
        <button class="b-approve" onclick="resolveDispute('${d.dispute_id}','refund_full',100)">Confirm full refund</button>
        <button class="b-suspend" onclick="resolveDispute('${d.dispute_id}','refund_partial',document.getElementById('pct-${d.dispute_id}').value)">Partial %</button>
        <button class="b-reject" onclick="resolveDispute('${d.dispute_id}','reject',0)">Reject</button>
      </div>`}
    </div>`;
  });
  document.getElementById('disputes').innerHTML=html;
}
async function resolveDispute(id,decision,pct){
  if(!confirm('Apply resolution: '+decision+(decision==='refund_partial'?(' '+pct+'%'):'')+'?'))return;
  const note=(document.getElementById('note-'+id)||{}).value||'';
  await api('/admin/disputes/'+id+'/resolve',{method:'POST',body:JSON.stringify({decision,refund_pct:Number(pct)||0,note})});
  loadDisputes();
}
async function loadPulizie(){
  const list=await api('/admin/pulizie/richieste');
  if(!list.length){document.getElementById('pulizie').innerHTML='<div class="muted" style="padding:20px">No open cleaning requests.</div>';return;}
  let html='<div class="sec">Richieste Pulizie · matching manuale</div>';
  list.forEach(r=>{
    const c=r.config||{};
    const comps=(r.compatible||[]);
    let rows=comps.map(p=>`<label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)">
      <input type="checkbox" data-rid="${r.richiesta_id}" value="${p.provider_id}" ${p.invited?'checked disabled':''}/>
      <span style="flex:1"><b>${p.nome}</b> <span class="muted">· ${p.distance}km · ⭐${(p.rating||0).toFixed(1)} · Trust ${Math.round(p.trust||0)}</span></span>
      <b>€${(p.price||0).toFixed(2)}</b> ${p.invited?'<span class="pill" style="background:#E4F6EC;color:#1E9E5B">invited</span>':''}
    </label>`).join('') || '<div class="muted">Nessun professionista compatibile in zona.</div>';
    html+=`<div class="row" style="flex-direction:column;align-items:stretch;gap:10px">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="em">🧹</span>
        <div class="t"><b>${c.tipo_pulizia} · ${(c.mq_band||'').replace('_','–')} m² · ${c.durata_ore}h</b>
          <div class="muted">${r.binario} · ${r.data_ora||''} · ${r.indirizzo||''}</div></div>
        <span class="pill" style="background:#eee">${r.stato}</span>
      </div>
      ${c.extra&&c.extra.length?`<div class="muted">Extra: ${c.extra.join(', ')}</div>`:''}
      <div><b class="muted">Professionisti compatibili (${comps.length})</b>${rows}</div>
      <button class="b-approve" onclick="invitePulizie('${r.richiesta_id}')">Invita selezionati</button>
    </div>`;
  });
  document.getElementById('pulizie').innerHTML=html;
}
async function invitePulizie(rid){
  const ids=[...document.querySelectorAll('input[type=checkbox][data-rid="'+rid+'"]:checked:not(:disabled)')].map(x=>x.value);
  if(!ids.length){alert('Seleziona almeno un professionista');return;}
  await api('/admin/pulizie/richieste/'+rid+'/invite',{method:'POST',body:JSON.stringify({provider_ids:ids})});
  loadPulizie();
}
async function loadBabysitting(){
  const list=await api('/admin/babysitting/richieste');
  if(!list.length){document.getElementById('babysitting').innerHTML='<div class="muted" style="padding:20px">No open babysitting requests.</div>';return;}
  let html='<div class="sec">Richieste Babysitting · matching manuale (urgenze in cima)</div>';
  list.forEach(r=>{
    const c=r.config||{};
    const comps=(r.compatible||[]);
    let rows=comps.map(p=>`<label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)">
      <input type="checkbox" data-brid="${r.richiesta_id}" value="${p.provider_id}" ${p.invited?'checked disabled':''}/>
      <span style="flex:1"><b>${p.nome}</b> <span class="muted">· ${p.distance}km · ⭐${(p.rating||0).toFixed(1)} · ${p.esperienza_anni||0}y ${p.casellario_ok?'· 🛡️':''} ${(p.certificazioni||[]).includes('primo_soccorso_pediatrico')?'· 🩹':''}</span></span>
      <b>€${(p.price||0).toFixed(2)}</b> ${p.invited?'<span class="pill" style="background:#E4F6EC;color:#1E9E5B">invited</span>':''}
    </label>`).join('') || '<div class="muted">Nessuna babysitter compatibile in zona.</div>';
    const gen=(r.bambini_generic||[]).map(x=>x.eta_band_it+(x.esigenza?(' ⚠️'+x.esigenza):'')).join(', ');
    html+=`<div class="row" style="flex-direction:column;align-items:stretch;gap:10px">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="em">🧸</span>
        <div class="t"><b>${c.durata_ore}h · ${c.n_bambini} bimbi${r.urgente?' ⚡ URGENTE':''}</b>
          <div class="muted">${r.binario} · ${r.data_ora||''} · zona ${(r.lat||0).toFixed(3)},${(r.lng||0).toFixed(3)}</div></div>
        <span class="pill" style="background:${r.urgente?'#FDE2E1':'#eee'}">${r.stato}</span>
      </div>
      <div class="muted">Bambini: ${gen||'—'}${c.ripetizioni_attiva?(' · 📚 ripetizioni '+c.ripetizioni_ore+'h '+c.ripetizioni_livello):''}</div>
      <div><b class="muted">Babysitter compatibili (${comps.length})</b>${rows}</div>
      <button class="b-approve" onclick="inviteBabysitting('${r.richiesta_id}')">Invita selezionate</button>
    </div>`;
  });
  document.getElementById('babysitting').innerHTML=html;
}
async function inviteBabysitting(rid){
  const ids=[...document.querySelectorAll('input[type=checkbox][data-brid="'+rid+'"]:checked:not(:disabled)')].map(x=>x.value);
  if(!ids.length){alert('Seleziona almeno una babysitter');return;}
  await api('/admin/babysitting/richieste/'+rid+'/invite',{method:'POST',body:JSON.stringify({provider_ids:ids})});
  loadBabysitting();
}
async function loadDriver(){
  const list=await api('/admin/driver/richieste');
  if(!list.length){document.getElementById('driver').innerHTML='<div class="muted" style="padding:20px">No open driver requests.</div>';return;}
  let html='<div class="sec">Richieste Driver (NCC/Taxi) · matching manuale</div>';
  list.forEach(r=>{
    const c=r.config||{};
    const comps=(r.compatible||[]);
    let rows=comps.map(p=>`<label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)">
      <input type="checkbox" data-drid="${r.richiesta_id}" value="${p.provider_id}" ${p.invited?'checked disabled':''}/>
      <span style="flex:1"><b>${p.nome}</b> <span class="muted">· ${p.distance}km · ⭐${(p.rating||0).toFixed(1)} · affid. ${p.affidabilita||100}% ${p.auth_ok?'· 🛡️':''}</span></span>
      <b>€${(p.price||0).toFixed(2)}</b> ${p.invited?'<span class="pill" style="background:#E4F6EC;color:#1E9E5B">invited</span>':''}
    </label>`).join('') || '<div class="muted">Nessun driver compatibile in zona.</div>';
    html+=`<div class="row" style="flex-direction:column;align-items:stretch;gap:10px">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="em">${c.tipo==='taxi'?'🚕':'🚘'}</span>
        <div class="t"><b>${(r.partenza&&r.partenza.label)||''} → ${(r.destinazione&&r.destinazione.label)||''}</b>
          <div class="muted">${(c.tipo||'ncc').toUpperCase()} · ${c.classe} · ${r.pickup_at||''} · ${(c.route&&c.route.distance_km)||0} km${c.flight_number?(' · ✈️ '+c.flight_number):''}</div></div>
        <span class="pill">${r.stato}</span>
      </div>
      <div><b class="muted">Driver compatibili (${comps.length})</b>${rows}</div>
      <button class="b-approve" onclick="inviteDriver('${r.richiesta_id}')">Invita selezionati</button>
    </div>`;
  });
  document.getElementById('driver').innerHTML=html;
}
async function inviteDriver(rid){
  const ids=[...document.querySelectorAll('input[type=checkbox][data-drid="'+rid+'"]:checked:not(:disabled)')].map(x=>x.value);
  if(!ids.length){alert('Seleziona almeno un driver');return;}
  await api('/admin/driver/richieste/'+rid+'/invite',{method:'POST',body:JSON.stringify({provider_ids:ids})});
  loadDriver();
}
async function loadSpec4(){
  const cfg=await api('/admin/spec4/config');
  const mod=await api('/admin/spec4/moderation');
  const rel=await api('/admin/spec4/reliability');
  let html='<div class="sec">Soglie configurabili</div><div class="row" style="flex-wrap:wrap;gap:10px">';
  const fields=[['cancel_free_hours','Ore rimborso pieno'],['cancel_fee_only_hours','Ore solo-fee'],['cancel_late_labor_pct','% lavoro indennizzo'],['lf_free_hours','Libretto ore gratis'],['client_strike_threshold','Strike soglia'],['client_strike_window_days','Finestra strike (gg)'],['review_window_days','Finestra recensione (gg)'],['new_provider_reviews','Recensioni badge "Nuovo"']];
  fields.forEach(f=>{html+=`<label style="font-size:13px;color:var(--muted)">${f[1]}<br><input id="s4_${f[0]}" type="number" value="${cfg[f[0]]}" style="width:120px;padding:6px;border:1px solid var(--line);border-radius:8px"/></label>`;});
  html+=`</div><button class="b-approve" style="margin-top:10px" onclick="saveSpec4()">Salva soglie</button>`;
  html+='<div class="sec" style="margin-top:18px">Recensioni da moderare ('+mod.length+')</div>';
  if(!mod.length){html+='<div class="muted">Nessuna recensione in coda.</div>';}
  mod.forEach(m=>{const rv=m.recensione||{};html+=`<div class="row"><div class="t"><b>${'★'.repeat(rv.rating||0)}</b> <span class="muted">${(m.cliente_nome||'')} → ${(m.provider_nome||'')} · ${m.categoria||''}</span><div>${(rv.comment||'').replace(/</g,'&lt;')}</div></div><button class="b-approve" onclick="moderate('${m.richiesta_id}','approve')">Pubblica</button> <button class="b-reject" onclick="moderate('${m.richiesta_id}','hide')">Nascondi</button></div>`;});
  html+='<div class="sec" style="margin-top:18px">Affidabilità</div>';
  if(!rel.length){html+='<div class="muted">Nessun evento.</div>';}
  rel.forEach(u=>{html+=`<div class="row"><div class="t"><b>${u.name||u.user_id}</b> <span class="pill">${u.role}</span><div class="muted">Strike cliente: <b style="color:${u.over_threshold?'#DE4B3F':'inherit'}">${u.client_strikes}</b>${u.over_threshold?' ⚠️':''} · Eventi provider: ${u.provider_events} · Punteggio privato: ${u.private_avg!=null?u.private_avg+' ('+u.private_count+')':'—'}</div></div></div>`;});
  document.getElementById('spec4').innerHTML=html;
}
async function saveSpec4(){
  const body={};['cancel_free_hours','cancel_fee_only_hours','cancel_late_labor_pct','lf_free_hours','client_strike_threshold','client_strike_window_days','review_window_days','new_provider_reviews'].forEach(k=>{body[k]=Number(document.getElementById('s4_'+k).value);});
  await api('/admin/spec4/config',{method:'POST',body:JSON.stringify(body)});
  alert('Soglie salvate'); loadSpec4();
}
async function moderate(rid,action){ await api('/admin/spec4/moderation/'+rid,{method:'POST',body:JSON.stringify({action})}); loadSpec4(); }
async function loadVerifiche(){
  const idv=await api('/admin/idv-trigger');
  const ren=await api('/admin/renewals');
  let html='<div class="sec">Trigger IDV automatico</div>';
  const badge=idv.triggered?'<span class="pill" style="background:#FBE9E7;color:#DE4B3F">SOGLIA RAGGIUNTA</span>':'<span class="pill" style="background:#E4F6EC;color:#1E9E5B">Manuale OK</span>';
  html+=`<div class="row"><div class="t"><b>${badge}</b><div class="muted">${idv.recommendation}</div><div style="margin-top:6px">Fornitore IDV attuale: <b>${idv.current_idv_provider}</b> · Soglia: ${idv.config.weekly_threshold}/sett × ${idv.config.consecutive_weeks} sett</div></div></div>`;
  html+='<div class="row" style="gap:14px">'+idv.weeks.map(w=>`<div class="t"><b style="font-size:20px">${w.count}</b><div class="muted">${w.week}</div></div>`).join('')+'</div>';
  html+=`<label style="font-size:13px;color:var(--muted)">Espansione oltre la prima area <input id="idv_multi" type="checkbox" ${idv.multi_area?'checked':''} onchange="saveIdv()"/></label>`;
  html+='<div class="sec" style="margin-top:18px">Rinnovi in scadenza ('+ren.items.length+', entro '+ren.horizon_days+'gg)</div>';
  if(!ren.items.length){html+='<div class="muted">Nessun rinnovo imminente.</div>';}
  ren.items.forEach(it=>{const col=it.expired?'#DE4B3F':(it.days_left<15?'#E8A33D':'inherit');html+=`<div class="row"><div class="t"><b>${it.name||it.user_id}</b> <span class="pill">${it.type}</span><div class="muted" style="color:${col}">${it.expired?'SCADUTO':it.days_left+' giorni'} · scade ${(it.expires_at||'').slice(0,10)}</div></div></div>`;});
  document.getElementById('verifiche').innerHTML=html;
}
async function saveIdv(){ await api('/admin/idv-config',{method:'POST',body:JSON.stringify({multi_area:document.getElementById('idv_multi').checked})}); loadVerifiche(); }
async function loadArtigiani(){
  const list=await api('/admin/artigiani/richieste');
  if(!list.length){document.getElementById('artigiani').innerHTML='<div class="muted" style="padding:20px">No open artigiani requests.</div>';return;}
  let html='<div class="sec">Richieste Artigiani · matching manuale (urgenze in cima)</div>';
  list.forEach(r=>{
    const c=r.config||{};
    const comps=(r.compatible||[]);
    let rows=comps.map(p=>`<label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)">
      <input type="checkbox" data-arid="${r.richiesta_id}" value="${p.provider_id}" ${p.invited?'checked disabled':''}/>
      <span style="flex:1"><b>${p.nome}</b> <span class="muted">· ${p.distance}km · ⭐${(p.rating||0).toFixed(1)} ${p.abilitazione_ok?'· 🛡️ abilitato':''}</span></span>
      ${p.invited?'<span class="pill" style="background:#E4F6EC;color:#1E9E5B">invited</span>':''}
    </label>`).join('') || '<div class="muted">Nessun artigiano compatibile in zona.</div>';
    html+=`<div class="row" style="flex-direction:column;align-items:stretch;gap:10px">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="em">🔧</span>
        <div class="t"><b>${(c.mestiere||'').toUpperCase()} · ${c.modalita==='diagnosi'?'Chiamata-diagnosi':'Paniere'}</b>
          <div class="muted">${r.binario||''} · ${(c.descrizione||'').slice(0,80)}${r.urgente?' · ⚡ urgente':''}</div></div>
        <span class="pill">${r.stato}</span>
      </div>
      <div><b class="muted">Artigiani compatibili (${comps.length})</b>${rows}</div>
      <button class="b-approve" onclick="inviteArtigiani('${r.richiesta_id}')">Invita selezionati</button>
    </div>`;
  });
  document.getElementById('artigiani').innerHTML=html;
}
async function inviteArtigiani(rid){
  const ids=[...document.querySelectorAll('input[type=checkbox][data-arid="'+rid+'"]:checked:not(:disabled)')].map(x=>x.value);
  if(!ids.length){alert('Seleziona almeno un artigiano');return;}
  await api('/admin/artigiani/richieste/'+rid+'/invite',{method:'POST',body:JSON.stringify({provider_ids:ids})});
  loadArtigiani();
}
function img(src,label){return src?('<div style="text-align:center"><div class="muted" style="font-size:11px">'+label+'</div><img src="'+src+'" style="width:90px;height:64px;object-fit:cover;border-radius:6px;border:1px solid var(--line)"/></div>'):'';}
async function loadOnboarding(){
  const list=await api('/admin/onboarding/pending');
  if(!list.length){document.getElementById('onboarding').innerHTML='<div class="muted" style="padding:20px">No providers pending approval.</div>';return;}
  let html='<div class="sec">Approvazione provider ('+list.length+')</div>';
  list.forEach(u=>{
    const imgs=[img(u.id_document_front,'ID fronte'),img(u.id_document_back,'ID retro'),img(u.selfie_document,'Selfie'),img(u.presentation_photo,'Logo/Foto')].join('');
    html+=`<div class="row" style="flex-direction:column;align-items:stretch;gap:10px">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="em">${u.provider_profile_type==='impresa'?'🏢':u.provider_profile_type==='piva'?'🧾':'🧍'}</span>
        <div class="t"><b>${u.business_name||u.name||'—'}</b>
          <div class="muted">${u.provider_profile_type||''} · ${u.contact_email||u.email||'no email'} ${u.email_verified?'✅':'❌'}</div></div>
        <span class="pill" style="background:#eee">${u.provider_state}</span>
      </div>
      <div class="muted">P.IVA: ${u.vat_number||'—'} · CF: ${u.codice_fiscale||'—'} · IBAN: ${u.iban||'—'}</div>
      <div class="muted">${u.address||''} ${u.condizione_soggettiva?('· '+u.condizione_soggettiva):''}</div>
      ${u.bio?('<div class="muted">"'+u.bio+'"</div>'):''}
      ${u.provider_profile_type==='persona_lf'?('<div class="muted">Delega: '+(u.lf_delega_signed?'firmata ✅':'no')+' · INPS: '+(u.lf_inps_registered?'registrato ✅':'in corso')+'</div>'):''}
      <div style="display:flex;gap:8px;flex-wrap:wrap">${imgs||'<span class="muted">Nessun documento caricato</span>'}${u.casellario_doc?img(u.casellario_doc,'Casellario'):''}</div>
      ${u.casellario_doc?('<div class="muted">Casellario: '+(u.casellario_verified?'verificato ✅':'da verificare')+'</div>'):''}
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="b-approve" onclick="onbDecision('${u.user_id}','approve')">Approva</button>
        <button class="b-suspend" onclick="onbDecision('${u.user_id}','waitlist')">Lista d'attesa</button>
        <button class="b-suspend" onclick="onbDecision('${u.user_id}','convert_lf')">Converti in Libretto</button>
        <button class="b-reject" onclick="onbDecision('${u.user_id}','reject')">Rifiuta</button>
        ${u.casellario_doc&&!u.casellario_verified?('<button class="b-approve" onclick="verifyCasellario(&#39;'+u.user_id+'&#39;)">🛡️ Verifica casellario</button>'):''}
        ${u.driver_auth_doc&&!u.driver_auth_verified?('<button class="b-approve" onclick="verifyDriverAuth(&#39;'+u.user_id+'&#39;)">🚘 Verifica autorizzazione</button>'):''}
        ${u.art_abilitazione_doc&&!u.art_abilitazione_verified?('<button class="b-approve" onclick="verifyAbilitazione(&#39;'+u.user_id+'&#39;)">🔧 Verifica abilitazione</button>'):''}
      </div>
    </div>`;
  });
  document.getElementById('onboarding').innerHTML=html;
}
async function onbDecision(uid,action){
  if(!confirm(action+' this provider?'))return;
  await api('/admin/onboarding/'+uid+'/decision',{method:'POST',body:JSON.stringify({action})});
  loadOnboarding();
}
async function verifyCasellario(uid){
  await api('/admin/babysitting/'+uid+'/casellario',{method:'POST',body:JSON.stringify({verified:true})});
  loadOnboarding();
}
async function verifyDriverAuth(uid){
  await api('/admin/driver/'+uid+'/authorization',{method:'POST',body:JSON.stringify({verified:true})});
  loadOnboarding();
}
async function verifyAbilitazione(uid){
  await api('/admin/artigiani/'+uid+'/abilitazione',{method:'POST',body:JSON.stringify({verified:true})});
  loadOnboarding();
}
(function(){const t=localStorage.getItem('jobby_admin_token');if(t){document.getElementById('token').value=t;connect();}})();
</script>
</body>
</html>
"""
