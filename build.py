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
const PICK_GRACE_DAY='2026-06-21'; // Central calendar day (YYYY-MM-DD) whose matches stay pickable even after kickoff; matches on later days lock at their own kickoff
let sb=null;
try{ sb = window.supabase.createClient(SB_URL, SB_KEY, { db:{schema:'worldcup'}, auth:{ persistSession:true, autoRefreshToken:true, detectSessionInUrl:true } }); }catch(e){ console.warn('supabase init failed', e); }
let ME=null, MYNAME='', MYPICKS={}, ALLPICKS=[], PLAYERS={}, MYSUB=false, predRefreshTimer=null, nameTimer=null, realtimeSub=null, rtDebounce=null, TG_DISMISSED=false;
try{ TG_DISMISSED = localStorage.getItem('wc_tg_dismissed')==='1'; }catch(e){}

const outcomeOf=e=> e.hs>e.as?'h':(e.as>e.hs?'a':'d');
function pickable(e){ return KNOWN.has(e.home)&&KNOWN.has(e.away); }
function pickOpen(e){ return e.state==='pre' || dayNum(new Date(e.utc))===PICK_GRACE_DAY; }
function scorePicksMap(map){ let pts=0,correct=0,total=0; map=map||{};
  DATA.events.forEach(e=>{ if(e.state!=='post'||!pickable(e)) return; const p=map[e.id]; if(!p) return;
    const o=outcomeOf(e); if(e.ko&&o==='d') return; total++; if(p===o){correct++; pts+=3;} });
  return {pts,correct,total};
}

async function initPredictAuth(){
  renderAuth(sb?'':'Sign-up unavailable (could not load Supabase).');
  if(!sb) return;
  try{ const { data:{ session } } = await sb.auth.getSession(); await onSession(session);
       sb.auth.onAuthStateChange((_e,sess)=>{ onSession(sess); }); }
  catch(e){ console.warn('auth init', e); }
}
async function onSession(session){
  ME = (session&&session.user&&session.user.email) ? session.user.email.toLowerCase() : null;
  if(ME){
    const md=(session.user&&session.user.user_metadata)||{};
    MYNAME = md.name || [md.first_name,md.last_name].filter(Boolean).join(' ').trim() || MYNAME || ME.split('@')[0];
    await ensurePlayer(); await loadPredData();
    if(!predRefreshTimer) predRefreshTimer=setInterval(()=>{ if(!document.hidden&&ME) loadPredData(); },60000);
    if(!realtimeSub){ try{ realtimeSub = sb.channel('wc_picks')
      .on('postgres_changes',{event:'*',schema:'worldcup',table:'picks'}, ()=>{ clearTimeout(rtDebounce); rtDebounce=setTimeout(loadPredData,800); })
      .subscribe(); }catch(e){ console.warn('realtime', e); } }
  } else { MYPICKS={}; ALLPICKS=[]; }
  renderAuth(); renderPredict();
}
async function sendMagicLink(){
  if(!sb) return;
  const fn=document.getElementById('suFirst'), ln=document.getElementById('suLast'), em=document.getElementById('predEmail');
  const first=((fn&&fn.value)||'').trim(), last=((ln&&ln.value)||'').trim();
  const email=((em&&em.value)||'').trim().toLowerCase();
  const st=document.getElementById('predAuthMsg');
  if(!first){ if(fn){fn.classList.add('bad'); setTimeout(()=>fn.classList.remove('bad'),1200);} if(st) st.textContent='Please enter your first name.'; return; }
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)){ if(em){em.classList.add('bad'); setTimeout(()=>em.classList.remove('bad'),1200);} if(st) st.textContent='Please enter a valid email.'; return; }
  const name=[first,last].filter(Boolean).join(' ').slice(0,40);
  if(st) st.textContent='Sending your sign-in link...';
  const { error } = await sb.auth.signInWithOtp({ email, options:{ emailRedirectTo: location.href.split('#')[0], data:{ name, first_name:first, last_name:last } } });
  if(st) st.textContent = error ? ('Error: '+error.message) : ('Link sent. Check '+email+', tap the link, then come back to this tab.');
}
async function signOut(){ if(realtimeSub&&sb){ try{ sb.removeChannel(realtimeSub); }catch(e){} realtimeSub=null; } if(sb) await sb.auth.signOut(); ME=null; MYNAME=''; MYPICKS={}; ALLPICKS=[]; renderAuth(); renderPredict(); }

async function ensurePlayer(){ if(!sb||!ME) return;
  try{ await sb.from('players').upsert({ email:ME, display_name:(MYNAME||ME.split('@')[0]).slice(0,40) }, { onConflict:'email' }); }catch(e){ console.warn('ensurePlayer', e); } }
async function saveDisplayName(){ const inp=document.getElementById('predNameInput'); if(!inp||!ME||!sb) return;
  MYNAME=(inp.value||'').slice(0,40)||ME.split('@')[0];
  try{ await sb.from('players').upsert({ email:ME, display_name:MYNAME }, { onConflict:'email' }); }catch(e){ console.warn('saveName', e); }
  if(PLAYERS[ME]!==undefined) PLAYERS[ME]=MYNAME; renderPredictBoard(); if(typeof renderShell==='function') renderShell(); }
function queueName(){ clearTimeout(nameTimer); nameTimer=setTimeout(saveDisplayName,700); }

async function loadPredData(){ if(!sb||!ME) return;
  try{
    const r1=await sb.from('picks').select('player_email,match_id,pick');
    const r2=await sb.from('players').select('email,display_name');
    try{ const r3=await sb.from('tg_subscribers').select('active').eq('email',ME).maybeSingle(); MYSUB=!!(r3.data&&r3.data.active); }catch(_){}
    ALLPICKS=r1.data||[]; PLAYERS={}; (r2.data||[]).forEach(p=>{ PLAYERS[p.email]=p.display_name; });
    if(PLAYERS[ME]) MYNAME=PLAYERS[ME];
    MYPICKS={}; ALLPICKS.forEach(x=>{ if(x.player_email===ME) MYPICKS[x.match_id]=x.pick; });
    renderPredict();
  }catch(e){ console.warn('loadPredData', e); }
}
async function setPick(id,o){
  if(!ME){ const a=document.getElementById('suFirst')||document.getElementById('predEmail'); if(a) a.focus(); return; }
  const e=DATA.events.find(x=>x.id===id); if(!e||!sb||!pickOpen(e)) return;
  MYPICKS[id]=o;
  const ix=ALLPICKS.findIndex(x=>x.player_email===ME&&x.match_id===id);
  if(ix>=0) ALLPICKS[ix].pick=o; else ALLPICKS.push({player_email:ME,match_id:id,pick:o});
  renderPredict();
  try{ await sb.from('picks').upsert({ player_email:ME, match_id:id, pick:o }, { onConflict:'player_email,match_id' }); }catch(err){ console.warn('setPick', err); }
}

/* Telegram opt-in: optional guided step after sign-up */
async function subscribeTelegram(){
  if(!ME||!sb) return;
  const token=(window.crypto&&crypto.randomUUID)?crypto.randomUUID():(Date.now().toString(36)+Math.random().toString(36).slice(2));
  try{ const { error }=await sb.from('tg_links').insert({ token, email:ME }); if(error){ console.warn('tg_links', error); return; } }catch(e){ console.warn('tg_links', e); return; }
  window.open('https://t.me/'+TG_BOT+'?start='+encodeURIComponent(token),'_blank');
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
    box.innerHTML='<div class="authbar"><div class="authwho">Signed in as <b>'+ME+'</b></div>'
      +'<div class="pname"><label>Display name</label><input id="predNameInput" type="text" maxlength="40" value="'+(MYNAME||'').replace(/"/g,'&quot;')+'" oninput="queueName()" /></div>'
      +'<button class="pbtn" onclick="signOut()">Sign out</button></div>';
  } else {
    box.innerHTML='<div class="authcard"><div class="authh">Sign up to play</div>'
      +'<div class="authsub">No password. Enter your name and email and we’ll send a one-tap sign-in link. Your email is your identity, so only you can set your picks.</div>'
      +'<div class="surow"><input id="suFirst" type="text" maxlength="24" placeholder="First name" autocomplete="given-name" /><input id="suLast" type="text" maxlength="24" placeholder="Last name" autocomplete="family-name" /></div>'
      +'<div class="addrow"><input id="predEmail" type="email" inputmode="email" autocomplete="email" placeholder="you@email.com" /><button class="pbtn solid" onclick="sendMagicLink()">Send link</button></div>'
      +'<div id="predAuthMsg" class="authmsg">'+(msg||'')+'</div></div>';
  }
}
function renderPredictBoard(){
  const box=document.getElementById('predBoard'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  const byP={}; ALLPICKS.forEach(r=>{ (byP[r.player_email]=byP[r.player_email]||{})[r.match_id]=r.pick; });
  const emails=Object.keys(PLAYERS).length?Object.keys(PLAYERS):Object.keys(byP);
  const rows=emails.map(em=>{ const s=scorePicksMap(byP[em]); return { name:PLAYERS[em]||em.split('@')[0], me:em===ME, pts:s.pts, correct:s.correct, total:s.total }; });
  rows.sort((a,b)=> b.pts-a.pts || b.correct-a.correct);
  const lb=rows.map((r,i)=>'<div class="lbrow'+(r.me?' me':'')+'"><span class="rk">'+(i+1)+'</span><span class="who">'+r.name+(r.me?' <span class="youtag">you</span>':'')+'</span><span class="rec">'+r.correct+'/'+r.total+'</span><span class="pp">'+r.pts+'<span class="u">pts</span></span></div>').join('')
    || '<div class="lbrow"><span class="who" style="color:var(--faint)">No players yet — be the first to pick</span></div>';
  box.innerHTML='<div class="lbcard"><div class="lbhead">Leaderboard <span class="hint">3 pts per correct result · shared live</span></div>'+lb
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
  return '<div class="pmatch"><div class="pm-top"><span class="stage">'+stage+'</span><span class="time">'+when+'</span></div>'+ctrl+'</div>';
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
function renderPredict(){ renderTelegram(); renderPredictBoard(); renderPredictList(); if(typeof renderShell==='function') renderShell(); }"""

tpl = tpl[:s] + NEW_PRED_JS + tpl[e:]

# 8) Bootstrap: swap loadPred() for initPredictAuth() -------------------------
if "\nloadPred();" not in tpl: fail("bootstrap loadPred() not found")
tpl = tpl.replace("\nloadPred();", "\ninitPredictAuth();", 1)

# sanity: no stray references to removed functions
for dead in ['predName(', 'shareMyPicks(', 'addFriendFromInput(', 'removeFriend(', 'loadPred(', 'PRED.', 'FRIENDS']:
    if dead in tpl: fail(f"leftover reference to removed predict code: {dead!r}")

(ROOT / "index.html").write_text(tpl, encoding="utf-8")
print("OK wrote index.html  bytes:", len(tpl), " lines:", tpl.count(chr(10))+1)
