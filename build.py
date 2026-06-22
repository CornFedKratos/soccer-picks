#!/usr/bin/env python3
"""
Phase-1 build: assemble the production World Cup board (index.html) from the
Claude Design bundle, wiring the Supabase prediction backend + new sign-up flow
into the approved design. Re-runnable. Source of truth for the design is the
bundled "World Cup 2026 Board.html"; backend logic is ported from
_handoff/worldcup-board.html.
"""
import re, json, sys, pathlib

ROOT = pathlib.Path(__file__).parent
BUNDLE = ROOT / "World Cup 2026 Board.html"

def fail(msg):
    print("BUILD ERROR:", msg); sys.exit(1)

# 1) Extract the real HTML template from the design bundle ---------------------
bundle = BUNDLE.read_text(encoding="utf-8")
m = re.search(r'<script type="__bundler/template">\s*(.*?)\s*</script>', bundle, re.S)
if not m: fail("could not find __bundler/template in design bundle")
tpl = json.loads(m.group(1))

def require(anchor):
    if anchor not in tpl: fail(f"anchor not found: {anchor[:60]!r}")

# 2) Swap self-hosted @font-face block for Google Fonts link -------------------
FONT_START = '<style>/* vietnamese */'
require(FONT_START)
i0 = tpl.index(FONT_START)
i1 = tpl.index('</style>', i0) + len('</style>')
GFONTS = ('<link href="https://fonts.googleapis.com/css2?'
          'family=Archivo:wght@400;600;800;900&family=Archivo+Expanded:wght@700;800;900&'
          'family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">')
tpl = tpl[:i0] + GFONTS + tpl[i1:]

# 3) New auth / sign-up / Telegram CSS (only classes the design lacks) ---------
NEW_CSS = r"""
  /* ---- Predict: sign-up, auth, Telegram (Phase 1) ---- */
  .authcard{background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:18px; margin-bottom:14px}
  .authh{font-family:'Archivo',sans-serif; font-weight:800; font-size:18px; color:var(--ink); margin-bottom:4px}
  .authsub{color:var(--muted); font-size:13px; line-height:1.5; margin-bottom:14px; max-width:64ch}
  .surow{display:flex; gap:8px; margin-bottom:8px}
  .surow input,.addrow input{flex:1; min-width:0; font-family:'Inter',sans-serif; font-size:14px; color:var(--ink);
    background:var(--panel2); border:1px solid var(--line); border-radius:9px; padding:11px 12px; outline:none}
  .surow input:focus,.addrow input:focus{border-color:var(--cyan)}
  .surow input.bad,.addrow input.bad{border-color:var(--loss); animation:shake .25s}
  @keyframes shake{25%{transform:translateX(-3px)}75%{transform:translateX(3px)}}
  .authmsg{color:var(--muted); font-size:12.5px; margin-top:10px; min-height:16px}
  .authbar{display:flex; flex-wrap:wrap; align-items:center; gap:12px; background:var(--panel); border:1px solid var(--line);
    border-radius:14px; padding:14px 16px; margin-bottom:14px}
  .authwho{font-size:13px; color:var(--muted)} .authwho b{color:var(--ink)}
  .authbar .pname{display:flex; align-items:center; gap:8px; margin:0}
  .authbar .pname label{font-size:12px; color:var(--faint)}
  .authbar .pname input{font-family:'Inter',sans-serif; font-size:13px; color:var(--ink); background:var(--panel2);
    border:1px solid var(--line); border-radius:8px; padding:8px 10px; outline:none}
  .authbar .pname input:focus{border-color:var(--cyan)}
  .authbar .pbtn{margin-left:auto}
  .tgcard{background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:14px}
  .tgcard.on{border-color:var(--win)}
  .tgh{display:flex; align-items:center; gap:9px; font-family:'Archivo',sans-serif; font-weight:800; font-size:15px; color:var(--ink)}
  .tgcard.on .tgh{color:var(--win)}
  .tgi{font-size:18px; line-height:1} .tgcard.on .tgi{font-size:15px}
  .tgsub{color:var(--muted); font-size:13px; line-height:1.5; margin:6px 0 0}
  .tgsteps{margin:12px 0 14px 18px; padding:0; color:var(--ink); font-size:13px; line-height:1.7}
  .tgsteps b{color:var(--ink)}
  .tgmini{margin-bottom:14px}
  .pbtn.ghost{background:transparent}
  .pkstat{display:block; font-size:11.5px; font-weight:700; color:var(--muted); margin-top:8px; min-height:15px; letter-spacing:.2px}
  .pkstat.saved{color:var(--win)}
  .pkstat.err{color:var(--loss)}
  .authalt{margin-top:12px; font-size:12.5px; color:var(--muted)}
  .linkbtn{background:none; border:0; color:var(--cyan); font:inherit; font-weight:700; cursor:pointer; padding:0}
  .linkbtn:hover{text-decoration:underline}
  .reelbtn{margin-top:10px; width:100%; font-family:'Inter',sans-serif; font-weight:800; font-size:13px; color:var(--bg); background:var(--cyan); border:0; border-radius:9px; padding:9px; cursor:pointer}
  .reelbtn:hover{filter:brightness(1.08)}
  .reelmodal{position:fixed; inset:0; z-index:200; background:rgba(0,0,0,.86); display:flex; align-items:center; justify-content:center; padding:16px}
  .reelbox{position:relative; width:min(960px,96vw)}
  .reelbox video{width:100%; max-height:86vh; border-radius:12px; background:#000; display:block}
  .reelclose{position:absolute; top:-12px; right:-6px; width:36px; height:36px; border-radius:50%; border:0; background:var(--panel2); color:var(--ink); font-size:22px; line-height:1; cursor:pointer}
"""
CLOSE = '</style>'
if CLOSE not in tpl: fail("no </style> after font swap")
ci = tpl.index(CLOSE)  # now the only style block is the main one
tpl = tpl[:ci] + NEW_CSS + tpl[ci:]

# 4) Replace the Predict section markup ---------------------------------------
NEW_SECTION = ('<section id="predict" class="page" hidden="">\n'
    '    <div class="sec-head"><h2>Predict</h2>\n'
    '      <div class="sub">Sign up, pick the winners, climb the shared leaderboard</div>\n'
    '    </div>\n'
    '    <div id="predAuth"></div>\n'
    '    <div id="predTg"></div>\n'
    '    <div id="predBoard"></div>\n'
    '    <div id="predList"></div>\n'
    '  </section>')
new_tpl, n = re.subn(r'<section id="predict".*?</section>', lambda _:NEW_SECTION, tpl, count=1, flags=re.S)
if n != 1: fail(f"predict section replace count={n}")
tpl = new_tpl

# 5) Add the Supabase JS library before the main script -----------------------
SUPA_CDN = '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>'
if tpl.count('<script>') != 1: fail(f"expected 1 inline <script>, found {tpl.count('<script>')}")
tpl = tpl.replace('<script>', SUPA_CDN + '\n<script>', 1)

# 6) Repoint the drawer auth chip (renderShell) from PRED.name to ME/MYNAME ----
OLD_CHIP = ("    if(PRED&&PRED.name&&PRED.name.trim()){\n"
    "      const nm=PRED.name.trim();\n"
    "      da.innerHTML='<div class=\"who\"><span class=\"ava\">'+nm.charAt(0).toUpperCase()+'</span><div style=\"min-width:0\"><div class=\"nm\">'+nm+'</div><div class=\"sub\">Signed in to pick\\u2019em</div></div></div><a class=\"signout\" href=\"#/predict\">Manage my picks</a>';\n"
    "    } else {\n"
    "      da.innerHTML='<a class=\"authlink solid\" href=\"#/predict\">Sign in to play \\u2192</a>';\n"
    "    }")
NEW_CHIP = ("    if(typeof ME!=='undefined' && ME){\n"
    "      const nm=(typeof MYNAME!=='undefined'&&MYNAME)? MYNAME : ME.split('@')[0];\n"
    "      da.innerHTML='<div class=\"who\"><span class=\"ava\">'+nm.charAt(0).toUpperCase()+'</span><div style=\"min-width:0\"><div class=\"nm\">'+nm+'</div><div class=\"sub\">Signed in to pick\\u2019em</div></div></div><a class=\"signout\" href=\"#/predict\">Manage my picks</a>';\n"
    "    } else {\n"
    "      da.innerHTML='<a class=\"authlink solid\" href=\"#/predict\">Sign up to play \\u2192</a>';\n"
    "    }")
require(OLD_CHIP)
tpl = tpl.replace(OLD_CHIP, NEW_CHIP, 1)

# 7) Replace the old friend-code Predict JS block with the Supabase module -----
JS_START = "let PRED={name:'',picks:{}}, FRIENDS=[];"
JS_END = "function renderPredict(){ renderPredictBoard(); renderPredictList(); if(typeof renderShell==='function') renderShell(); }"
require(JS_START); require(JS_END)
s = tpl.index(JS_START); e = tpl.index(JS_END) + len(JS_END)

NEW_PRED_JS = r"""/* ===================== PREDICT (Supabase magic-link sign-up) ===================== */
const SB_URL='https://ckldrmyzmwnujzpxxjpt.supabase.co';
const SB_KEY='sb_publishable_bsmzithS3xRk2_VLdBKFKg_97YqazB6';
const TG_BOT='SCHM1NK_SoccerPicks_Bot';
let sb=null;
try{ sb = window.supabase.createClient(SB_URL, SB_KEY, { db:{schema:'worldcup'}, auth:{ persistSession:true, autoRefreshToken:true, detectSessionInUrl:true } }); }catch(e){ console.warn('supabase init failed', e); }
let ME=null, MYNAME='', CODE='', MYID='', MYPICKS={}, PLAYERS={}, PICKLIST=[], MYSUB=false, predRefreshTimer=null, TG_DISMISSED=false, PICK_FLASH={};
try{ TG_DISMISSED = localStorage.getItem('wc_tg_dismissed')==='1'; }catch(e){}

const outcomeOf=e=> e.hs>e.as?'h':(e.as>e.hs?'a':'d');
function pickable(e){ return KNOWN.has(e.home)&&KNOWN.has(e.away); }
function pickOpen(e){ return new Date(e.utc).getTime() > Date.now(); } // locked at kickoff, no exceptions
function scorePicksMap(map){ let pts=0,correct=0,total=0; map=map||{};
  DATA.events.forEach(e=>{ if(e.state!=='post'||!pickable(e)) return; const p=map[e.id]; if(!p) return;
    const o=outcomeOf(e); if(e.ko&&o==='d') return; total++; if(p===o){correct++; pts+=3;} });
  return {pts,correct,total};
}

const JOIN_KEY='wc_join';
function loadStoredJoin(){ try{ const s=JSON.parse(localStorage.getItem(JOIN_KEY)||'null'); if(s&&s.email&&s.code) return s; }catch(e){} return null; }
function saveJoin(){ try{ localStorage.setItem(JOIN_KEY, JSON.stringify({ email:ME, name:MYNAME, code:CODE })); }catch(e){} }
function startPoll(){ if(predRefreshTimer) return; predRefreshTimer=setInterval(()=>{ if(!document.hidden&&ME) loadPredData(); }, 25000); }
function stopPoll(){ if(predRefreshTimer){ clearInterval(predRefreshTimer); predRefreshTimer=null; } }
async function initPredictAuth(){
  if(!sb){ renderAuth('Predict is unavailable (could not load Supabase).'); return; }
  const s=loadStoredJoin();
  if(s){ ME=s.email; MYNAME=s.name||ME.split('@')[0]; CODE=s.code; renderAuth(); await loadPredData(); startPoll(); }
  else { renderAuth(); }
  renderPredict();
}
async function joinLeague(){
  if(!sb) return;
  const fn=document.getElementById('suFirst'), ln=document.getElementById('suLast'), em=document.getElementById('predEmail'), cd=document.getElementById('predCode');
  const first=((fn&&fn.value)||'').trim(), last=((ln&&ln.value)||'').trim();
  const email=((em&&em.value)||'').trim().toLowerCase(), code=((cd&&cd.value)||'').trim();
  const st=document.getElementById('predAuthMsg');
  const bad=(el,m)=>{ if(el){el.classList.add('bad'); setTimeout(()=>el.classList.remove('bad'),1200);} if(st) st.textContent=m; };
  if(!first) return bad(fn,'Enter your first name.');
  if(!last) return bad(ln,'Enter your last name.');
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return bad(em,'Enter a valid email.');
  if(!code) return bad(cd,'Enter the league code.');
  if(st) st.textContent='Joining…';
  let res; try{ res=await sb.rpc('wc_join',{ p_code:code, p_email:email, p_first:first, p_last:last }); }catch(e){ if(st) st.textContent='Something went wrong, try again.'; return; }
  if(res&&res.error){ if(st) st.textContent='Something went wrong, try again.'; return; }
  const status=res&&res.data;
  if(status==='bad_code') return bad(cd,'That league code is not correct.');
  if(status==='bad_email') return bad(em,'Enter a valid email.');
  if(status==='bad_name') return bad(fn,'Enter your name.');
  if(status!=='ok'){ if(st) st.textContent='Could not join, try again.'; return; }
  ME=email; MYNAME=[first,last].filter(Boolean).join(' ').slice(0,40); CODE=code; saveJoin();
  renderAuth(); await loadPredData(); startPoll(); renderPredict();
}
function leaveLeague(){ stopPoll(); ME=null; MYNAME=''; CODE=''; MYID=''; MYPICKS={}; PICKLIST=[]; PLAYERS={}; try{ localStorage.removeItem(JOIN_KEY); }catch(e){} renderAuth(); renderPredict(); }
async function loadPredData(){ if(!sb||!ME||!CODE) return;
  try{
    const r=await sb.rpc('wc_load',{ p_code:CODE, p_email:ME });
    if(r&&r.error){ console.warn('wc_load', r.error); return; }
    const d=r&&r.data;
    if(!d || d.error){ if(d&&d.error==='bad_code') leaveLeague(); return; }
    MYID=d.me||''; PLAYERS={}; (d.players||[]).forEach(p=>{ PLAYERS[p.id]=p.name; });
    PICKLIST=d.picks||[]; MYPICKS={}; PICKLIST.forEach(x=>{ if(x.id===MYID) MYPICKS[x.m]=x.p; });
    renderPredict();
  }catch(e){ console.warn('loadPredData', e); }
}
async function setPick(id,o){
  if(!ME){ const a=document.getElementById('suFirst'); if(a) a.focus(); return; }
  const e=DATA.events.find(x=>x.id===id); if(!e||!sb||!pickOpen(e)) return;
  const prev=MYPICKS[id]; if(prev===o) return;
  // optimistic update + "saving" state
  MYPICKS[id]=o; PICK_FLASH[id]='saving';
  const ix=PICKLIST.findIndex(x=>x.id===MYID&&x.m===id);
  if(ix>=0) PICKLIST[ix].p=o; else if(MYID) PICKLIST.push({id:MYID,m:id,p:o});
  renderPredict();
  let status=null, err=null;
  try{ const r=await sb.rpc('wc_set_pick',{ p_code:CODE, p_email:ME, p_match:id, p_pick:o }); err=r&&r.error; status=r&&r.data; }
  catch(x){ err=x; }
  if(err || status!=='ok'){
    console.warn('setPick failed', err||status);
    if(prev===undefined){ delete MYPICKS[id]; const j=PICKLIST.findIndex(x=>x.id===MYID&&x.m===id); if(j>=0) PICKLIST.splice(j,1); }
    else { MYPICKS[id]=prev; const j=PICKLIST.findIndex(x=>x.id===MYID&&x.m===id); if(j>=0) PICKLIST[j].p=prev; }
    PICK_FLASH[id]= status==='locked' ? 'err:Locked — kickoff passed' : 'err:Not saved — tap to retry';
    renderPredict();
  } else {
    PICK_FLASH[id]='saved';
    renderPredict();
    setTimeout(()=>{ if(PICK_FLASH[id]==='saved'){ delete PICK_FLASH[id]; renderPredict(); } }, 2500);
  }
}

/* Telegram opt-in: optional guided step after sign-up */
async function subscribeTelegram(){
  if(!ME||!sb||!CODE) return;
  let tok=null;
  try{ const r=await sb.rpc('wc_tg_link',{ p_code:CODE, p_email:ME }); tok=r&&r.data; }catch(e){ console.warn('tg_link', e); return; }
  if(!tok) return;
  window.open('https://t.me/'+TG_BOT+'?start='+encodeURIComponent(tok),'_blank');
}
function dismissTg(){ TG_DISMISSED=true; try{ localStorage.setItem('wc_tg_dismissed','1'); }catch(e){} renderTelegram(); }
function renderTelegram(){
  const box=document.getElementById('predTg'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  if(MYSUB){ box.innerHTML='<div class="tgcard on"><div class="tgh"><span class="tgi">✓</span>Goal alerts are on</div><div class="tgsub">We’ll DM you on Telegram the moment a goal goes in — with the clip when it’s available. Send <b>/stop</b> to the bot anytime to turn them off.</div></div>'; return; }
  if(TG_DISMISSED){ box.innerHTML='<div class="tgmini"><button class="pbtn" onclick="subscribeTelegram()">Get goal alerts on Telegram</button></div>'; return; }
  box.innerHTML='<div class="tgcard"><div class="tgh"><span class="tgi">📣</span>Get goal alerts on Telegram</div>'
    +'<div class="tgsub">Optional. Get a personal DM the instant any match scores — with the highlight clip when it’s available.</div>'
    +'<ol class="tgsteps"><li>Tap <b>Open the bot</b> below (it opens Telegram).</li><li>Press <b>Start</b> in the chat with @'+TG_BOT+'.</li><li>Done — you’ll get a confirmation DM, then alerts from then on.</li></ol>'
    +'<div class="pbtns"><button class="pbtn solid" onclick="subscribeTelegram()">Open the bot</button><button class="pbtn ghost" onclick="dismissTg()">Maybe later</button></div></div>';
}

function renderAuth(msg){
  const box=document.getElementById('predAuth'); if(!box) return;
  if(ME){
    box.innerHTML='<div class="authbar"><div class="authwho">Playing as <b>'+(MYNAME||ME).replace(/</g,'&lt;')+'</b></div>'
      +'<button class="pbtn" onclick="leaveLeague()">Leave</button></div>';
  } else {
    box.innerHTML='<div class="authcard"><div class="authh">Join the pool</div>'
      +'<div class="authsub">Enter your name, email, and the league code your host gave you. No password, nothing to click in your inbox.</div>'
      +'<div class="surow"><input id="suFirst" type="text" maxlength="24" placeholder="First name" autocomplete="given-name" /><input id="suLast" type="text" maxlength="24" placeholder="Last name" autocomplete="family-name" /></div>'
      +'<div class="surow"><input id="predEmail" type="email" inputmode="email" autocomplete="email" placeholder="you@email.com" /><input id="predCode" type="text" inputmode="numeric" maxlength="6" placeholder="League code" /></div>'
      +'<div class="addrow"><button class="pbtn solid" style="flex:1" onclick="joinLeague()">Join the pool</button></div>'
      +'<div id="predAuthMsg" class="authmsg">'+(msg||'')+'</div></div>';
  }
}
function renderPredictBoard(){
  const box=document.getElementById('predBoard'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  const byP={}; PICKLIST.forEach(r=>{ (byP[r.id]=byP[r.id]||{})[r.m]=r.p; });
  const ids=Object.keys(PLAYERS).length?Object.keys(PLAYERS):Object.keys(byP);
  const rows=ids.map(pid=>{ const s=scorePicksMap(byP[pid]); return { name:(PLAYERS[pid]||'Player'), me:pid===MYID, pts:s.pts, correct:s.correct, total:s.total }; });
  rows.sort((a,b)=> b.pts-a.pts || b.correct-a.correct);
  const lb=rows.map((r,i)=>'<div class="lbrow'+(r.me?' me':'')+'"><span class="rk">'+(i+1)+'</span><span class="who">'+String(r.name).replace(/</g,'&lt;')+(r.me?' <span class="youtag">you</span>':'')+'</span><span class="rec">'+r.correct+'/'+r.total+'</span><span class="pp">'+r.pts+'<span class="u">pts</span></span></div>').join('')
    || '<div class="lbrow"><span class="who" style="color:var(--faint)">No players yet — be the first to pick</span></div>';
  box.innerHTML='<div class="lbcard"><div class="lbhead">Leaderboard <span class="hint">3 pts per correct result · shared</span></div>'+lb
    +'<div class="pbtns"><button class="pbtn" onclick="loadPredData()">Refresh</button></div></div>';
}
function predMatchCard(e){
  const d=new Date(e.utc); const when=new Intl.DateTimeFormat('en-US',{timeZone:TZ,weekday:'short',hour:'numeric',minute:'2-digit'}).format(d);
  const stage=e.ko?'Knockout':('Group '+(e.group||''));
  const pk=MYPICKS[e.id];
  const btn=(o,label,fl)=>'<button class="pk '+(pk===o?'sel':'')+'" onclick="setPick(\''+e.id+'\',\''+o+'\')">'+(fl?'<span class="flag">'+flag(fl)+'</span>':'')+'<span class="pl">'+label+'</span></button>';
  const ctrl = e.ko
    ? '<div class="pkrow ko">'+btn('h',norm(e.home),e.home)+btn('a',norm(e.away),e.away)+'</div>'
    : '<div class="pkrow">'+btn('h',norm(e.home),e.home)+btn('d','Draw',null)+btn('a',norm(e.away),e.away)+'</div>';
  const fst=PICK_FLASH[e.id];
  const stat = fst==='saving' ? '<span class="pkstat">Saving…</span>'
    : fst==='saved' ? '<span class="pkstat saved">Saved ✓</span>'
    : (fst&&fst.indexOf('err:')===0) ? '<span class="pkstat err">'+fst.slice(4)+'</span>'
    : (pk?'<span class="pkstat saved">Saved ✓</span>':'<span class="pkstat"></span>');
  return '<div class="pmatch"><div class="pm-top"><span class="stage">'+stage+'</span><span class="time">'+when+'</span></div>'+ctrl+stat+'</div>';
}
function renderPredictList(){
  const box=document.getElementById('predList'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  const up=DATA.events.filter(e=>pickable(e)&&pickOpen(e)).sort((a,b)=>new Date(a.utc)-new Date(b.utc));
  const days={}; up.forEach(e=>{const k=dayNum(new Date(e.utc)); (days[k]=days[k]||[]).push(e);});
  const keys=Object.keys(days).sort(); let html='';
  if(!keys.length) html+='<div class="note">No upcoming matches to pick right now.</div>';
  keys.forEach(k=>{ html+='<div class="pday"><div class="daylabel">'+dayLabel(new Date(days[k][0].utc))+'<span></span></div>'+days[k].map(predMatchCard).join('')+'</div>'; });
  const settled=DATA.events.filter(e=>e.state==='post'&&pickable(e)&&MYPICKS[e.id]&&!pickOpen(e)).sort((a,b)=>new Date(b.utc)-new Date(a.utc));
  if(settled.length){
    const rows=settled.map(e=>{ const o=outcomeOf(e); const p=MYPICKS[e.id]; const skip=e.ko&&o==='d'; const ok=!skip&&p===o;
      const pl=p==='d'?'Draw':(p==='h'?norm(e.home):norm(e.away));
      return '<div class="srow '+(skip?'':(ok?'ok':'no'))+'"><span class="sc">'+norm(e.home)+' '+e.hs+'–'+e.as+' '+norm(e.away)+'</span><span class="mypick">picked '+pl+'</span><span class="mark">'+(skip?'–':(ok?'✓':'✗'))+'</span></div>'; }).join('');
    html+='<details class="settled"><summary>Your settled picks <span class="cnt">'+settled.length+'</span></summary>'+rows+'</details>';
  }
  box.innerHTML=html;
}
function renderPredict(){ renderTelegram(); renderPredictBoard(); renderPredictList(); if(typeof renderShell==='function') renderShell(); }

/* ===================== Full-game highlight reels (View Highlights) ===================== */
window.REELS = {};
async function loadReels(){ if(!sb) return; try{ const r=await sb.rpc('wc_reels'); const a=(r&&r.data)||[]; const m={}; a.forEach(x=>{ if(x&&x.m&&x.u) m[x.m]=x.u; }); window.REELS=m; if(typeof renderMatches==='function') renderMatches(); }catch(e){ console.warn('loadReels', e); } }
function reelEsc(e){ if(e.key==='Escape') closeReel(); }
function closeReel(){ const md=document.getElementById('reelModal'); if(md){ const v=md.querySelector('video'); if(v){ try{ v.pause(); }catch(_){} } md.remove(); } document.removeEventListener('keydown', reelEsc, true); document.body.style.overflow=''; }
function openReel(url){ if(!url) return; closeReel(); const ov=document.createElement('div'); ov.className='reelmodal'; ov.id='reelModal'; ov.innerHTML='<div class="reelbox"><button class="reelclose" onclick="closeReel()" aria-label="Close">×</button><video src="'+url+'" controls autoplay playsinline></video></div>'; ov.addEventListener('click', function(e){ if(e.target===ov) closeReel(); }); document.body.appendChild(ov); document.addEventListener('keydown', reelEsc, true); document.body.style.overflow='hidden'; }
loadReels(); setInterval(loadReels, 300000);"""

tpl = tpl[:s] + NEW_PRED_JS + tpl[e:]

# 7b) "View Highlights" button on completed match cards (reel modal)
CARD_OLD = r"""+(showScore?'':oddsBlock(o))+detail+'</div>';"""
CARD_NEW = r"""+(showScore?'':oddsBlock(o))+((done&&window.REELS&&window.REELS[o.id])?'<button class="reelbtn" onclick="openReel(\''+window.REELS[o.id]+'\')">▶ View Highlights</button>':'')+detail+'</div>';"""
if CARD_OLD not in tpl: fail("card() oddsBlock/detail anchor not found")
tpl = tpl.replace(CARD_OLD, CARD_NEW, 1)

# 8) Bootstrap: swap loadPred() for initPredictAuth() -------------------------
if "\nloadPred();" not in tpl: fail("bootstrap loadPred() not found")
tpl = tpl.replace("\nloadPred();", "\ninitPredictAuth();", 1)

# sanity: no stray references to removed functions
for dead in ['predName(', 'shareMyPicks(', 'addFriendFromInput(', 'removeFriend(', 'loadPred(', 'PRED.', 'FRIENDS']:
    if dead in tpl: fail(f"leftover reference to removed predict code: {dead!r}")

(ROOT / "index.html").write_text(tpl, encoding="utf-8")
print("OK wrote index.html  bytes:", len(tpl), " lines:", tpl.count(chr(10))+1)
