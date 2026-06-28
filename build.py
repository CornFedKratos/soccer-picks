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
  .reelbox iframe{width:100%; aspect-ratio:16/9; max-height:86vh; border-radius:12px; background:#000; display:block; border:0}
  .reelclose{position:absolute; top:-12px; right:-6px; width:36px; height:36px; border-radius:50%; border:0; background:var(--panel2); color:var(--ink); font-size:22px; line-height:1; cursor:pointer}
  /* ---- Standings: Alive contention status + per-team LIVE indicator ---- */
  .st-alive{background:rgba(244,194,75,.12); color:var(--gold); border:1px solid rgba(244,194,75,.34); font-weight:800}
  .livetag{display:inline-flex; align-items:center; gap:4px; margin-left:7px; font-size:9px; font-weight:800; letter-spacing:.5px; color:var(--live); vertical-align:middle}
  .livetag i{width:6px; height:6px; border-radius:50%; background:var(--live); box-shadow:0 0 0 0 rgba(255,59,87,.5); animation:pulse2 1.2s infinite; flex:0 0 auto}
  @media(prefers-reduced-motion:reduce){ .livetag i{animation:none} }
  /* ---- Leaderboard: clickable rows, testing note, per-player picks modal ---- */
  .lbrow.clk{cursor:pointer}
  .lbrow.clk:hover{background:rgba(56,189,248,.08)}
  .lbrow .lbchev{color:var(--faint); font-size:18px; line-height:1; margin-left:2px}
  .lbnote{font-size:11.5px; color:var(--gold); line-height:1.45; padding:9px 15px; border-top:1px solid rgba(36,49,80,.4); background:rgba(244,194,75,.06)}
  .picksbox{position:relative; width:min(560px,96vw); max-height:86vh; overflow:auto; background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:18px}
  .picksbox .ph{font-family:'Archivo',sans-serif; font-weight:800; font-size:18px; color:var(--ink); display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; padding-right:30px}
  .picksbox .pscore{font-family:'Inter',sans-serif; font-weight:700; font-size:12.5px; color:var(--cyan)}
  .picksbox .pnote{font-size:12px; color:var(--gold); margin:8px 0 6px; line-height:1.45}
  .picksbox .psec{font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--faint); font-weight:800; margin:14px 0 2px}
  .picksbox .srow:first-of-type{border-top:0}
"""
CLOSE = '</style>'
if CLOSE not in tpl: fail("no </style> after font swap")
ci = tpl.index(CLOSE)  # now the only style block is the main one
tpl = tpl[:ci] + NEW_CSS + tpl[ci:]

# 4) Replace the Predict section markup ---------------------------------------
NEW_SECTION = ('<section id="predict" class="page" hidden="">\n'
    '    <div class="sec-head"><h2>Predict</h2>\n'
    '      <div class="sub">Sign up, pick the winners, climb the shared leaderboard</div>\n'
    '      <button class="linkbtn" style="margin-top:6px;font-size:13px" onclick="openRulesModal()">ℹ️ How it works</button>\n'
    '    </div>\n'
    '    <div id="predAuth"></div>\n'
    '    <div id="predTg"></div>\n'
    '    <div id="predNotify"></div>\n'
    '    <div id="predBoard"></div>\n'
    '    <div id="predList"></div>\n'
    '  </section>')
new_tpl, n = re.subn(r'<section id="predict".*?</section>', lambda _:NEW_SECTION, tpl, count=1, flags=re.S)
if n != 1: fail(f"predict section replace count={n}")
tpl = new_tpl

# 4b) Inject favicon / app-icon set (World Cup trophy) into <head> ------------
FAVICON = (
  '</title>\n'
  '<link rel="icon" href="/favicon.ico" sizes="any">\n'
  '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">\n'
  '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">\n'
  '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
  '<link rel="manifest" href="/site.webmanifest">\n'
  '<meta name="theme-color" content="#080B14">'
)
if '</title>' in tpl: tpl = tpl.replace('</title>', FAVICON, 1)

# 4c) Bracket redesign (polished cards, connector feed, trophy image, winner highlight)
def swap(old, new, what):
    global tpl
    if old not in tpl: fail(f"bracket swap miss: {what}")
    tpl = tpl.replace(old, new, 1)

swap(
  """  .bracket-scroll{overflow-x:auto; padding-bottom:16px}
  .bracket{display:flex; gap:26px; min-width:920px; padding:4px}
  .round{display:flex; flex-direction:column; justify-content:space-around; gap:10px; min-width:172px}
  .round-h{font-family:'Archivo',sans-serif; font-weight:800; font-size:11px; letter-spacing:.8px; text-transform:uppercase; color:var(--muted); text-align:center; margin-bottom:4px}
  .tie{background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:7px 9px; font-size:12px}
  .tie .slot{display:flex; align-items:center; gap:7px; padding:3px 0}
  .tie .slot .flag{font-size:13px; width:18px; text-align:center}
  .tie .slot .nm{flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
  .tie .slot.tbd .nm{color:var(--faint); font-style:italic; font-size:11px; font-weight:400}
  .tie .slot.locked .nm{font-weight:700; color:#fff}
  .tie .vs{height:1px; background:var(--line); margin:3px 0}
  .tie .mid{font-size:9.5px; color:var(--faint); text-align:center; letter-spacing:.3px; margin-top:3px}
  .champ{align-self:center; margin:auto 0}
  .champ .trophy{font-size:34px; text-align:center}
  .champ .lbl{font-family:'Archivo Expanded'; font-weight:800; font-size:11px; letter-spacing:1px; text-transform:uppercase; color:var(--gold); text-align:center; margin-top:4px}""",
  """  .bracket-scroll{overflow-x:auto; padding-bottom:18px}
  .bracket{display:flex; gap:22px; min-width:1160px; padding:8px 2px; align-items:stretch}
  .round{display:flex; flex-direction:column; min-width:182px}
  .round-h{font-family:'Archivo',sans-serif; font-weight:800; font-size:10.5px; letter-spacing:1.3px; text-transform:uppercase; color:var(--gold); text-align:center; margin-bottom:10px; padding-bottom:7px; border-bottom:1px solid rgba(244,194,75,.22)}
  .ties{display:flex; flex-direction:column; flex:1 1 auto}
  .tie{flex:1 1 0; display:flex; align-items:center; position:relative; min-height:82px}
  .mcard{position:relative; width:100%; background:linear-gradient(158deg,#16213c,#0d1322); border:1px solid var(--line); border-radius:12px; padding:8px 12px 8px 14px; font-size:12px; box-shadow:0 3px 10px rgba(0,0,0,.30)}
  .mcard::before{content:''; position:absolute; left:0; top:9px; bottom:9px; width:3px; border-radius:0 3px 3px 0; background:linear-gradient(var(--cyan),var(--gold)); opacity:.55}
  .mcard.done::before{background:var(--gold); opacity:.9}
  .tie .slot{display:flex; align-items:center; gap:8px; padding:4px 0}
  .tie .slot .flag{font-size:15px; width:20px; text-align:center}
  .tie .slot .nm{flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:600}
  .tie .slot .chk{font-size:11px; font-weight:800; color:var(--cyan); opacity:0}
  .tie .slot.tbd .nm{color:var(--faint); font-style:italic; font-size:11px; font-weight:400}
  .tie .slot.locked .nm{font-weight:700; color:#fff}
  .tie .slot.win .nm{color:#fff; font-weight:800}
  .tie .slot.win .chk{opacity:1}
  .tie .vs{height:1px; background:linear-gradient(90deg,transparent,var(--line) 25%,var(--line) 75%,transparent); margin:3px 0}
  .tie .mid{font-size:9.5px; color:var(--faint); text-align:center; letter-spacing:.3px; margin-top:3px}
  @media(min-width:821px){
    .round:nth-last-child(n+3) .tie::after{content:''; position:absolute; left:100%; top:50%; width:23px; height:2px; background:#46577d}
    .round:nth-last-child(n+3) .ties .tie:nth-child(odd)::before{content:''; position:absolute; left:calc(100% + 22px); top:50%; width:2px; height:100%; background:#46577d}
  }
  .champ-col{min-width:150px}
  .champ{margin:auto 0; text-align:center; position:relative; padding:6px 4px}
  .champ::before{content:''; position:absolute; left:50%; top:50%; width:150px; height:150px; transform:translate(-50%,-50%); background:radial-gradient(circle,rgba(244,194,75,.26),transparent 68%); pointer-events:none}
  .champ .trophy{position:relative; width:90px; height:auto; display:block; margin:0 auto; filter:drop-shadow(0 6px 16px rgba(244,194,75,.45))}
  .champ .lbl{position:relative; font-family:'Archivo Expanded'; font-weight:800; font-size:11px; letter-spacing:1.5px; text-transform:uppercase; color:var(--gold); text-align:center; margin-top:10px}
  .champ .who{position:relative; font-size:12.5px; font-weight:700; color:#fff; margin-top:3px}""",
  "desktop bracket css")

swap(
  """    .tie{font-size:14.5px; padding:12px 14px; border-radius:11px}
    .tie .slot{padding:6px 0}
    .tie .slot .flag{font-size:17px; width:22px}
    .tie .slot.tbd .nm{font-size:13px}
    .tie .vs{margin:5px 0}
    .champ{margin:18px 0 4px}
    .champ .trophy{font-size:40px}
  }""",
  """    .ties{display:block}
    .tie{display:block; flex:none; min-height:0; margin-bottom:11px}
    .mcard{padding:12px 14px 12px 16px; border-radius:13px; font-size:14.5px}
    .tie .slot{padding:7px 0}
    .tie .slot .flag{font-size:18px; width:24px}
    .tie .slot.tbd .nm{font-size:13px}
    .tie .vs{margin:5px 0}
    .champ-col{min-width:0}
    .champ{margin:20px 0 6px}
    .champ .trophy{width:104px}
    .champ::before{width:180px; height:180px}
  }""",
  "mobile bracket css")

swap(
  """function bslot(name){
  if(KNOWN.has(norm(name))) return '<div class="slot filled"><span class="flag">'+flag(name)+'</span><span class="nm">'+norm(name)+'</span></div>';
  return '<div class="slot tbd"><span class="flag">\\u00B7</span><span class="nm">'+koLabel(name)+'</span></div>';
}""",
  """function bslot(name, win){
  if(KNOWN.has(norm(name))) return '<div class="slot filled'+(win?' win':'')+'"><span class="flag">'+flag(name)+'</span><span class="nm">'+norm(name)+'</span><span class="chk">✓</span></div>';
  return '<div class="slot tbd"><span class="flag">·</span><span class="nm">'+koLabel(name)+'</span></div>';
}""",
  "bslot")

swap(
  """function tbdTie(){return '<div class="tie"><div class="slot tbd"><span class="flag">\\u00B7</span><span class="nm">TBD</span></div><div class="vs"></div><div class="slot tbd"><span class="flag">\\u00B7</span><span class="nm">TBD</span></div></div>';}""",
  """function tbdTie(){return '<div class="tie"><div class="mcard"><div class="slot tbd"><span class="flag">·</span><span class="nm">TBD</span></div><div class="vs"></div><div class="slot tbd"><span class="flag">·</span><span class="nm">TBD</span></div></div></div>';}""",
  "tbdTie")

swap(
  """const col=(label,arr,want,key)=>{ let t=arr.map(bracketTie).join(''); if(arr.length<want) t+=Array.from({length:want-arr.length}).map(tbdTie).join(''); return '<div class="round" data-r="'+key+'"><div class="round-h">'+label+'</div>'+t+'</div>'; };""",
  """const col=(label,arr,want,key)=>{ let t=arr.map(bracketTie).join(''); if(arr.length<want) t+=Array.from({length:want-arr.length}).map(tbdTie).join(''); return '<div class="round" data-r="'+key+'"><div class="round-h">'+label+'</div><div class="ties">'+t+'</div></div>'; };""",
  "col")

swap(
  """function bracketTie(e){ return '<div class="tie">'+bslot(e.home)+'<div class="vs"></div>'+bslot(e.away)+'</div>'; }""",
  """function bracketTie(e){ var done=e.state==='post'; var hw=done&&(e.win?e.win==='h':e.hs>e.as), aw=done&&(e.win?e.win==='a':e.as>e.hs); return '<div class="tie"><div class="mcard'+(done?' done':'')+'">'+bslot(e.home,hw)+'<div class="vs"></div>'+bslot(e.away,aw)+'</div></div>'; }
function champWho(f){ if(!f||f.state!=='post') return ''; var w=(f.win==='h'||(!f.win&&f.hs>f.as))?f.home:((f.win==='a'||(!f.win&&f.as>f.hs))?f.away:''); return (w&&KNOWN.has(norm(w)))?'<div class="who">'+norm(w)+'</div>':''; }""",
  "bracketTie")

swap(
  """+'<div class="round" data-r="F"><div class="round-h">Final</div>'+(R.F.length?bracketTie(R.F[0]):tbdTie())+'<div class="champ"><div class="trophy">\\uD83C\\uDFC6</div><div class="lbl">Champion</div></div></div>';""",
  """+'<div class="round" data-r="F"><div class="round-h">Final</div><div class="ties">'+(R.F.length?bracketTie(R.F[0]):tbdTie())+'</div></div>'+'<div class="round champ-col" data-r="F"><div class="round-h" style="visibility:hidden">Final</div><div class="champ"><img class="trophy" src="assets/wc-trophy.png" alt="Champion" width="90" height="90"><div class="lbl">Champion</div>'+champWho(R.F[0])+'</div></div>';""",
  "renderBracket champ")

# 4d) Standings: mirror ESPN's official standings feed (rank order + note status) + per-team LIVE dot.
# Authoritative: ESPN applies FIFA's full tiebreakers; we map note -> IN/ALIVE/OUT.
swap(
  """const SB='https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard';""",
  """const SB='https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard';
const STAND='https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings';
let ESPN_STAT={};
async function fetchStandings(){
  try{
    const r=await fetch(STAND); if(!r.ok) return;
    const d=await r.json(); const map={};
    (d.children||[]).forEach(function(g){ (((g.standings||{}).entries)||[]).forEach(function(e){
      const key=norm(((e.team||{}).displayName)||''); if(!key) return;
      const stx={}; (e.stats||[]).forEach(function(s){ stx[s.name]=s; });
      const rank=stx.rank?Math.round(stx.rank.value):9;
      const note=((e.note||{}).description)||'';
      const adv=stx.advanced?Math.round(stx.advanced.value):0;
      let st='alive', shown=note;
      if(adv===1){
        // IN only when ESPN flags the team as mathematically CLINCHED (not merely currently top-2)
        st='in'; shown=note||'Clinched a knockout spot';
      } else if(/eliminat/i.test(note)){
        // ESPN marks every 4th-place team 'Eliminated' by current position; a team is only truly out
        // once it can no longer reach 4 points (4 pts all but guarantees a best third-place spot).
        const gp=stx.gamesPlayed?Math.round(stx.gamesPlayed.value):3, pts=stx.points?Math.round(stx.points.value):0;
        const mx=pts+3*(3-gp);
        if(mx<4){ st='out'; }
        else { st='alive'; shown='Still alive — can reach '+mx+' pts and contend for a best third-place spot'; }
      }
      // otherwise ALIVE: currently advancing but not yet clinched, or 3rd in the best-8 hunt
      map[key]={rank:rank, note:shown, st:st};
    }); });
    if(Object.keys(map).length){ ESPN_STAT=map; if(typeof renderGroups==='function') renderGroups(); }
  }catch(e){ console.warn('standings', e); }
}""",
  "fetchStandings")

swap(
  """  finally{ fetchLeaders(); clearTimeout(liveTimer); liveTimer=setTimeout(liveTick, liveCount()>0?30000:120000); }""",
  """  finally{ fetchLeaders(); fetchStandings(); clearTimeout(liveTimer); liveTimer=setTimeout(liveTick, liveCount()>0?30000:120000); }""",
  "liveTick fetchStandings hook")

swap(
  """function statusBadge(k){
  if(k==='in')  return '<span class="st st-in">IN</span>';
  if(k==='out') return '<span class="st st-out">OUT</span>';
  if(k==='in3') return '<span class="st st-in3" title="Provisionally through via best 3rd place">IN*</span>';
  if(k==='out3')return '<span class="st st-out" title="3rd place, outside the best 8 (provisional)">OUT*</span>';
  return '<span class="st st-live">live</span>';
}""",
  """function statusBadge(k, note){
  var ttl = note ? (' title="'+String(note).replace(/"/g,'&quot;')+'"') : '';
  if(k==='out') return '<span class="st st-out"'+ttl+'>OUT</span>';
  if(k==='alive') return '<span class="st st-alive"'+ttl+'>ALIVE</span>';
  return '<span class="st st-in"'+ttl+'>IN</span>';
}""",
  "statusBadge")

swap(
  """  document.getElementById('groupsBox').innerHTML=sorted.map(s=>{
    const sts=statuses(s), teams=s.teams; const games=Math.round(teams.reduce((a,t)=>a+t.p,0)/2);
    const rows=teams.map((t,i)=>{const qual=i<2, st=sts[i], out=(st==='out'||st==='out3');
      return '<tr class="'+(qual?'qual':'')+(out?' elim':'')+'"><td class="team"><span class="pos">'+(i+1)+'</span><span class="flag">'+flag(t.t)+'</span><span class="nm">'+t.t+'</span></td>'
       +'<td>'+t.p+'</td><td>'+(t.gd>0?'+':'')+t.gd+'</td><td class="pts">'+t.pts+'</td>'
       +'<td class="stcell">'+statusBadge(st)+'</td></tr>';}).join('');""",
  """  const liveTeams=new Set(); DATA.events.filter(e=>e.state==='in'&&!e.ko).forEach(e=>{liveTeams.add(e.home); liveTeams.add(e.away);});
  document.getElementById('groupsBox').innerHTML=sorted.map(s=>{
    const sts=statuses(s), teams=s.teams; const games=Math.round(teams.reduce((a,t)=>a+t.p,0)/2);
    const rows=teams.map((t,i)=>{const qual=i<2, st=sts[i], out=(st==='out'); const lv=liveTeams.has(t.t)?'<span class="livetag"><i></i>LIVE</span>':''; const note=(ESPN_STAT[t.t]||{}).note||'';
      return '<tr class="'+(qual?'qual':'')+(out?' elim':'')+'"><td class="team"><span class="pos">'+(i+1)+'</span><span class="flag">'+flag(t.t)+'</span><span class="nm">'+t.t+'</span>'+lv+'</td>'
       +'<td>'+t.p+'</td><td>'+(t.gd>0?'+':'')+t.gd+'</td><td class="pts">'+t.pts+'</td>'
       +'<td class="stcell">'+statusBadge(st,note)+'</td></tr>';}).join('');""",
  "groups row live+status")

# order each group by ESPN's official rank (full tiebreakers), falling back to pts/gd/wins pre-feed
swap(
  """  const sorted=GROUPS.map(g=>({g:g.g, teams:[...g.teams].sort((a,b)=> b.pts-a.pts || b.gd-a.gd || b.w-a.w)}));""",
  """  const sorted=GROUPS.map(g=>({g:g.g, teams:[...g.teams].sort((a,b)=>{ var ra=(ESPN_STAT[a.t]||{}).rank||9, rb=(ESPN_STAT[b.t]||{}).rank||9; return ra-rb || (b.pts-a.pts) || (b.gd-a.gd) || (b.w-a.w); })}));""",
  "sorted by ESPN rank")

# statuses() now just reads ESPN's note-derived status (IN / ALIVE / OUT)
swap(
  """  function statuses(s){
    const teams=s.teams, N=teams.length;
    if(teams.every(t=>t.p>=3)) return teams.map((t,i)=> i<2?'in':(i===3?'out':(top8.has(s.g)?'in3':'out3')));
    const names=new Set(teams.map(t=>t.t)); const rem=remOf(names);
    const idx={}; teams.forEach((t,i)=>idx[t.t]=i); const base=teams.map(t=>t.pts);
    const k=rem.length, total=Math.pow(3,k);
    const clinch=Array(N).fill(true), third=Array(N).fill(false);
    for(let scn=0;scn<total;scn++){
      const pts=base.slice(); let c=scn;
      for(let r=0;r<k;r++){const o=c%3;c=(c/3)|0;const hi=idx[rem[r][0]],ai=idx[rem[r][1]];
        if(o===0)pts[hi]+=3; else if(o===1){pts[hi]++;pts[ai]++;} else pts[ai]+=3;}
      for(let x=0;x<N;x++){let ge=0,ab=0;for(let y=0;y<N;y++){if(y===x)continue;if(pts[y]>=pts[x])ge++;if(pts[y]>pts[x])ab++;}
        if(ge>1)clinch[x]=false; if(ab<=2)third[x]=true;}
    }
    return teams.map((t,x)=> clinch[x]?'in':(!third[x]?'out':'alive'));
  }""",
  """  function statuses(s){
    return s.teams.map(function(t){ var e=ESPN_STAT[t.t]; return (e&&e.st)||'alive'; });
  }""",
  "statuses from ESPN")

# legend wording
swap(
  """      <div class="sub">Top 2 of each group advance, plus the 8 best third-place teams · <b style="color:var(--win)">IN</b> clinched · <b style="color:var(--loss)">OUT</b> eliminated · <span style="color:var(--faint)">* = provisional via 3rd</span></div>""",
  """      <div class="sub">Top 2 of each group advance, plus the 8 best third-place teams · <b style="color:var(--win)">IN</b> clinched · <b style="color:var(--gold)">ALIVE</b> in the hunt · <b style="color:var(--loss)">OUT</b> eliminated · <span style="color:var(--faint)">status per official standings</span></div>""",
  "legend")

# 4e) Golden Boot from authoritative play-by-play (ESPN's aggregate leaders endpoint lags badly
# mid-tournament). Capture each scorer's full name, then merge a live tally over the leaders feed.
swap(
  """      m.ev=(c.details||[]).map(dt=>{const ai=(dt.athletesInvolved||[])[0];
        return {min:(dt.clock||{}).displayValue||'', t:(dt.type||{}).text||'', side:idmap[(dt.team||{}).id]||'',
          g:!!dt.scoringPlay, og:!!dt.ownGoal, pen:!!dt.penaltyKick, r:!!dt.redCard, y:!!dt.yellowCard,
          who:ai?(ai.shortName||ai.displayName||''):''};});""",
  """      m.ev=(c.details||[]).map(dt=>{const ai=(dt.athletesInvolved||[])[0];
        return {min:(dt.clock||{}).displayValue||'', t:(dt.type||{}).text||'', side:idmap[(dt.team||{}).id]||'',
          g:!!dt.scoringPlay, og:!!dt.ownGoal, pen:!!dt.penaltyKick, r:!!dt.redCard, y:!!dt.yellowCard,
          who:ai?(ai.shortName||ai.displayName||''):'', nm:ai?(ai.displayName||ai.shortName||''):''};});""",
  "ev scorer full name")

# Overlay authoritative play-by-play tallies (goals, yellow & red cards) onto STATS.leaders so the
# boot, per-stat cards, AND the big leaderboard table are all real-time, not subject to ESPN leaders lag.
swap(
  """function renderBoot(){
  const rows=sortPinned(STATS.leaders.goals||[]).slice(0,8); const max=rows.length?Math.max(1,rows[0].v):1;""",
  """const nmKey=s=>String(s||'').trim().toLowerCase();
function liveTallies(){
  const g={},y={},r={};
  DATA.events.forEach(e=>{ if(!e.ev) return;
    e.ev.forEach(x=>{ const nm=String(x.nm||x.who||'').trim(); if(!nm) return;
      const tm=x.side==='a'?e.away:e.home, k=nmKey(nm);
      const bump=m=>{ if(!m[k]) m[k]={n:nm,tm:tm,v:0}; m[k].v++; };
      if(x.g&&!x.og) bump(g); if(x.y) bump(y); if(x.r) bump(r); });
  });
  return {goals:g, yellowCards:y, redCards:r};
}
// merge our live counts over ESPN's (laggy) leaders feed, taking the higher per player; names match (ESPN displayName both sides)
function applyLiveLeaders(){
  const t=liveTallies(); const idx={};
  Object.keys(STATS.leaders||{}).forEach(cat=>{ (STATS.leaders[cat]||[]).forEach(rr=>{ const k=nmKey(rr.n); if(k&&!idx[k]) idx[k]={id:rr.id,pos:rr.pos,ab:rr.ab}; }); });
  ['goals','yellowCards','redCards'].forEach(cat=>{
    const m=t[cat], arr=(STATS.leaders[cat]||[]).slice(), byName={}; arr.forEach(rr=>{ byName[nmKey(rr.n)]=rr; });
    Object.keys(m).forEach(k=>{ const lv=m[k], ex=byName[k];
      if(ex){ if(lv.v>ex.v) ex.v=lv.v; if(!ex.tm) ex.tm=lv.tm; }
      else { const meta=idx[k]||{}; arr.push({id:meta.id||('live-'+cat+'-'+k), n:lv.n, tm:lv.tm, ab:meta.ab, pos:meta.pos, v:lv.v}); } });
    arr.sort((a,b)=>b.v-a.v); STATS.leaders[cat]=arr;
  });
}
function renderBoot(){
  const rows=sortPinned(STATS.leaders.goals||[]).slice(0,8); const max=rows.length?Math.max(1,rows[0].v):1;""",
  "live leaders overlay")

swap(
  """function renderStats(){ renderPulse();""",
  """function renderStats(){ try{ applyLiveLeaders(); }catch(_){} renderPulse();""",
  "renderStats applyLiveLeaders")

# overlay the worker's authoritative per-match stats snapshot (assists/shots/saves/fouls/cards) over the
# laggy ESPN leaders feed; accuratePasses has no per-match source so it stays from ESPN.
swap(
  """    if(Object.keys(out).length){ STATS.leaders=out; STATS.fetched=new Date().toISOString(); renderStats(); }
  }catch(e){ console.warn('leaders refresh failed, using baked',e); }
}""",
  """    try{ if(typeof sb!=='undefined' && sb){ const sr=await sb.rpc('wc_stats'); const sl=sr&&sr.data&&sr.data.leaders; if(sl){ Object.keys(sl).forEach(cat=>{ if((sl[cat]||[]).length) out[cat]=sl[cat]; }); } } }catch(_){ }
    if(Object.keys(out).length){ STATS.leaders=out; STATS.fetched=new Date().toISOString(); renderStats(); }
  }catch(e){ console.warn('leaders refresh failed, using baked',e); }
}""",
  "fetchLeaders snapshot overlay")

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
let ME=null, MYNAME='', CODE='', MYID='', MYPICKS={}, MYSCORES={}, PLAYERS={}, PICKLIST=[], MYSUB=false, predRefreshTimer=null, TG_DISMISSED=false, PICK_FLASH={}, MY_COUNTRIES=null, MY_BRIEF=true, TEAMS=null;
try{ TG_DISMISSED = localStorage.getItem('wc_tg_dismissed')==='1'; }catch(e){}

const outcomeOf=e=> e.hs>e.as?'h':(e.as>e.hs?'a':'d');
function pickable(e){ return KNOWN.has(e.home)&&KNOWN.has(e.away); }
function groupsDone(){ return !DATA.events.some(x=>!x.ko && x.state!=='post'); } // every group match finished
function pickOpen(e){ if(e.ko && !groupsDone()) return false; return new Date(e.utc).getTime() > Date.now(); } // R32+ frozen until the group stage ends; all picks lock at kickoff
// Knockout result = the team that ACTUALLY advanced (incl. penalties; from ESPN's winner flag),
// so a 1-1 game won on PKs still credits whoever picked that team. Group stage = win/draw/loss.
function koOut(e){ return e.ko ? (e.win||'') : outcomeOf(e); }
function isFinalEvent(e){ return !!(e.ko && typeof koRound==='function' && koRound(e)==='F'); }
function scorePicksMap(pmap, smap){ let pts=0,correct=0,total=0; pmap=pmap||{}; smap=smap||{};
  const reset=groupsDone();                                           // group stage was practice — once it ends, only the knockouts count toward the $100
  DATA.events.forEach(e=>{ if(e.state!=='post'||!pickable(e)) return;
    if(reset && !e.ko) return;
    const p=pmap[e.id]; if(!p) return;
    const o=koOut(e); if(!o) return;                                  // knockout with no winner yet -> not scored
    total++;
    if(p===o){ correct++;
      const exact = isFinalEvent(e) && smap[e.id] && smap[e.id]===(e.hs+'-'+e.as);  // Final: nail the score
      pts += exact ? 5 : 3; }
  });
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
  const fn=document.getElementById('suFirst'), ln=document.getElementById('suLast'), em=document.getElementById('predEmail'), cd=document.getElementById('predCode'), pn=document.getElementById('suPin');
  const first=((fn&&fn.value)||'').trim(), last=((ln&&ln.value)||'').trim();
  const email=((em&&em.value)||'').trim().toLowerCase(), code=((cd&&cd.value)||'').trim(), pin=((pn&&pn.value)||'').trim();
  const st=document.getElementById('predAuthMsg');
  const bad=(el,m)=>{ if(el){el.classList.add('bad'); setTimeout(()=>el.classList.remove('bad'),1200);} if(st) st.textContent=m; };
  if(!first) return bad(fn,'Enter your first name.');
  if(!last) return bad(ln,'Enter your last name.');
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return bad(em,'Enter a valid email.');
  if(!code) return bad(cd,'Enter the league code.');
  if(!/^\d{4}$/.test(pin)) return bad(pn,'Choose a 4-digit PIN.');
  if(st) st.textContent='Joining…';
  let res; try{ res=await sb.rpc('wc_join',{ p_code:code, p_email:email, p_first:first, p_last:last, p_pin:pin }); }catch(e){ if(st) st.textContent='Something went wrong, try again.'; return; }
  if(res&&res.error){ if(st) st.textContent='Something went wrong, try again.'; return; }
  const status=res&&res.data;
  if(status==='bad_code') return bad(cd,'That league code is not correct.');
  if(status==='bad_email') return bad(em,'Enter a valid email.');
  if(status==='bad_name') return bad(fn,'Enter your name.');
  if(status==='bad_pin') return bad(pn,'PIN must be exactly 4 digits.');
  if(status!=='ok'){ if(st) st.textContent='Could not join, try again.'; return; }
  ME=email; MYNAME=[first,last].filter(Boolean).join(' ').slice(0,40); CODE=code; saveJoin();
  renderAuth(); await loadPredData(); startPoll(); renderPredict();
}
async function loginByEmail(){
  if(!sb) return;
  const em=document.getElementById('loginEmail'), pe=document.getElementById('loginPin'), st=document.getElementById('predAuthMsg');
  const email=((em&&em.value)||'').trim().toLowerCase(), pin=((pe&&pe.value)||'').trim();
  const bad=(el,m)=>{ if(el){el.classList.add('bad'); setTimeout(()=>el.classList.remove('bad'),1200);} if(st) st.textContent=m; };
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return bad(em,'Enter a valid email.');
  if(!/^\d{4}$/.test(pin)) return bad(pe,'Enter your 4-digit PIN.');
  if(st) st.textContent='Logging in…';
  let res; try{ res=await sb.rpc('wc_login',{ p_email:email, p_pin:pin }); }catch(e){ if(st) st.textContent='Something went wrong, try again.'; return; }
  const d=res&&res.data;
  if(!d || d.error){
    if(d&&d.error==='not_found') return bad(em,'No sign-up found for that email — use Join the pool above.');
    if(d&&d.error==='wrong_pin') return bad(pe,'Wrong PIN. Try again, or ask Don if you forgot it.');
    if(d&&d.error==='set_pin') return bad(pe,'First time on this device — pick a 4-digit PIN to set it.');
    return bad(em,'Could not log in, try again.');
  }
  ME=email; MYNAME=d.name||email.split('@')[0]; CODE=d.code; saveJoin();
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
    PICKLIST=d.picks||[]; MYPICKS={}; MYSCORES={}; PICKLIST.forEach(x=>{ if(x.id===MYID){ MYPICKS[x.m]=x.p; if(x.s) MYSCORES[x.m]=x.s; } });
    const pf=d.prefs||{}; MY_COUNTRIES=(pf.countries==null?null:pf.countries); MY_BRIEF=(pf.brief!==false);
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
    PICK_FLASH[id]= status==='locked' ? 'err:Locked — kickoff passed' : status==='closed' ? 'err:Opens after the group stage' : 'err:Not saved — tap to retry';
    renderPredict();
  } else {
    PICK_FLASH[id]='saved';
    renderPredict();
    setTimeout(()=>{ if(PICK_FLASH[id]==='saved'){ delete PICK_FLASH[id]; renderPredict(); } }, 2500);
  }
}

async function setFinalScore(id){
  if(!ME||!sb) return;
  const e=DATA.events.find(x=>x.id===id); if(!e||!pickOpen(e)) return;
  const hi=document.getElementById('fs_h_'+id), ai=document.getElementById('fs_a_'+id);
  const h=((hi&&hi.value)||'').trim(), a=((ai&&ai.value)||'').trim();
  if(!/^\d{1,2}$/.test(h)||!/^\d{1,2}$/.test(a)){ PICK_FLASH[id]='err:Enter both scores'; renderPredict(); return; }
  if(!MYPICKS[id]){ PICK_FLASH[id]='err:Pick the winner first'; renderPredict(); return; }
  const sc=h+'-'+a; MYSCORES[id]=sc; PICK_FLASH[id]='saving'; renderPredict();
  let status=null; try{ const r=await sb.rpc('wc_set_pick',{ p_code:CODE, p_email:ME, p_match:id, p_pick:MYPICKS[id], p_score:sc }); status=r&&r.data; }catch(x){}
  if(status==='ok'){ PICK_FLASH[id]='saved'; renderPredict(); setTimeout(()=>{ if(PICK_FLASH[id]==='saved'){ delete PICK_FLASH[id]; renderPredict(); } },2500); }
  else { PICK_FLASH[id]='err:Score not saved — tap Save score to retry'; renderPredict(); }
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
      +'<div class="authsub">Enter your name, email, the league code your host gave you, and a 4-digit PIN you will remember. No password, nothing to click in your inbox.</div>'
      +'<div class="surow"><input id="suFirst" type="text" maxlength="24" placeholder="First name" autocomplete="given-name" /><input id="suLast" type="text" maxlength="24" placeholder="Last name" autocomplete="family-name" /></div>'
      +'<div class="surow"><input id="predEmail" type="email" inputmode="email" autocomplete="email" placeholder="you@email.com" /><input id="predCode" type="text" inputmode="numeric" maxlength="6" placeholder="League code" /></div>'
      +'<div class="surow"><input id="suPin" type="text" inputmode="numeric" maxlength="4" placeholder="Choose a 4-digit PIN" autocomplete="off" /></div>'
      +'<div class="addrow"><button class="pbtn solid" style="flex:1" onclick="joinLeague()">Join the pool</button></div>'
      +'<div style="text-align:center;color:#6b7a99;font-size:12px;font-weight:700;margin:15px 0 9px">— already signed up? email + your PIN —</div>'
      +'<div class="surow"><input id="loginEmail" type="email" inputmode="email" autocomplete="email" placeholder="you@email.com" /><input id="loginPin" type="text" inputmode="numeric" maxlength="4" placeholder="PIN" autocomplete="off" style="max-width:84px" /></div>'
      +'<div class="addrow"><button class="pbtn" style="flex:1" onclick="loginByEmail()">Log back in</button></div>'
      +'<div id="predAuthMsg" class="authmsg">'+(msg||'')+'</div></div>';
  }
}
function renderPredictBoard(){
  const box=document.getElementById('predBoard'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  const byP={}, byS={}; PICKLIST.forEach(r=>{ (byP[r.id]=byP[r.id]||{})[r.m]=r.p; if(r.s)(byS[r.id]=byS[r.id]||{})[r.m]=r.s; });
  const ids=Object.keys(PLAYERS).length?Object.keys(PLAYERS):Object.keys(byP);
  const rows=ids.map(pid=>{ const s=scorePicksMap(byP[pid], byS[pid]); return { pid:pid, name:(PLAYERS[pid]||'Player'), me:pid===MYID, pts:s.pts, correct:s.correct, total:s.total }; });
  rows.sort((a,b)=> b.pts-a.pts || b.correct-a.correct);
  const lb=rows.map((r,i)=>'<div class="lbrow clk'+(r.me?' me':'')+'" onclick="openPicks(\''+r.pid+'\')"><span class="rk">'+(i+1)+'</span><span class="who">'+String(r.name).replace(/</g,'&lt;')+(r.me?' <span class="youtag">you</span>':'')+'</span><span class="rec">'+r.correct+'/'+r.total+'</span><span class="pp">'+r.pts+'<span class="u">pts</span></span><span class="lbchev">›</span></div>').join('')
    || '<div class="lbrow"><span class="who" style="color:var(--faint)">No players yet — be the first to pick</span></div>';
  box.innerHTML='<div class="lbcard"><div class="lbhead">Leaderboard <span class="hint">3 pts per correct result · tap a name for picks</span></div>'
    +'<div class="lbnote">🧪 The group stage is for testing. The real tournament starts at the Round of 32 — the leaderboard resets to zero then.</div>'+lb
    +'<div class="pbtns"><button class="pbtn" onclick="loadPredData()">Refresh</button></div></div>';
}
// Picks modal: tap a leaderboard name to see all of that player's picks with right/wrong.
function picksEsc(e){ if(e.key==='Escape') closePicks(); }
function closePicks(){ const m=document.getElementById('picksModal'); if(m) m.remove(); document.removeEventListener('keydown', picksEsc, true); document.body.style.overflow=''; }
function openPicks(pid){
  closePicks();
  const byP={}, byS={}; PICKLIST.forEach(r=>{ (byP[r.id]=byP[r.id]||{})[r.m]=r.p; if(r.s)(byS[r.id]=byS[r.id]||{})[r.m]=r.s; });
  const mine=byP[pid]||{}; const name=PLAYERS[pid]||'Player'; const s=scorePicksMap(mine, byS[pid]||{});
  const has=e=>mine[e.id]!==undefined;
  const settled=DATA.events.filter(e=>e.state==='post'&&pickable(e)&&has(e)).sort((a,b)=>new Date(b.utc)-new Date(a.utc));
  const upcoming=DATA.events.filter(e=>e.state!=='post'&&pickable(e)&&has(e)).sort((a,b)=>new Date(a.utc)-new Date(b.utc));
  const pl=(e,p)=>p==='d'?'Draw':(p==='h'?norm(e.home):norm(e.away));
  const settledRow=e=>{ const p=mine[e.id], o=koOut(e), pend=!o, ok=!pend&&p===o;
    return '<div class="srow '+(pend?'':(ok?'ok':'no'))+'"><span class="sc">'+norm(e.home)+' '+e.hs+'–'+e.as+' '+norm(e.away)+'</span><span class="mypick">picked '+pl(e,p)+'</span><span class="mark">'+(pend?'·':(ok?'✓':'✗'))+'</span></div>'; };
  const upRow=e=>'<div class="srow"><span class="sc">'+norm(e.home)+' v '+norm(e.away)+'</span><span class="mypick">picked '+pl(e,mine[e.id])+'</span><span class="mark" style="color:var(--faint)">·</span></div>';
  let body='';
  if(settled.length) body+='<div class="psec">Settled</div>'+settled.map(settledRow).join('');
  if(upcoming.length) body+='<div class="psec">Upcoming</div>'+upcoming.map(upRow).join('');
  if(!body) body='<div class="note" style="padding:12px 0">No picks yet.</div>';
  const ov=document.createElement('div'); ov.className='reelmodal'; ov.id='picksModal';
  ov.innerHTML='<div class="picksbox"><button class="reelclose" onclick="closePicks()" aria-label="Close">×</button>'
    +'<div class="ph">'+String(name).replace(/</g,'&lt;')+(pid===MYID?' <span class="youtag">you</span>':'')+'<span class="pscore">'+s.pts+' pts · '+s.correct+'/'+s.total+'</span></div>'
    +'<div class="pnote">🧪 Group stage = practice. Scores reset for the Round of 32.</div>'
    +'<div class="plist">'+body+'</div></div>';
  ov.addEventListener('click', function(e){ if(e.target===ov) closePicks(); });
  document.body.appendChild(ov); document.addEventListener('keydown', picksEsc, true); document.body.style.overflow='hidden';
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
  const sc=(MYSCORES[e.id]||'').split('-');
  const scoreUI = isFinalEvent(e)
    ? '<div style="margin-top:9px;padding-top:9px;border-top:1px solid var(--line)">'
      +'<div style="font-size:12px;color:#9fb3d1;margin-bottom:7px">Predict the final score for <b style="color:var(--gold)">5 pts</b> (winner alone = 3)</div>'
      +'<div style="display:flex;align-items:center;gap:8px"><input id="fs_h_'+e.id+'" inputmode="numeric" maxlength="2" placeholder="0" value="'+(sc[0]||'')+'" style="width:48px;text-align:center" /><span style="color:var(--faint)">–</span><input id="fs_a_'+e.id+'" inputmode="numeric" maxlength="2" placeholder="0" value="'+(sc[1]||'')+'" style="width:48px;text-align:center" /><button class="pbtn" style="margin-left:auto" onclick="setFinalScore(\''+e.id+'\')">Save score</button></div></div>'
    : '';
  return '<div class="pmatch"><div class="pm-top"><span class="stage">'+stage+'</span><span class="time">'+when+'</span></div>'+ctrl+scoreUI+stat+'</div>';
}
function renderPredictList(){
  const box=document.getElementById('predList'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  try{ if(!localStorage.getItem('wc_rules_seen')){ var ps=document.getElementById('predict'); if(ps && !ps.hidden){ localStorage.setItem('wc_rules_seen','1'); setTimeout(openRulesModal,450); } } }catch(e){}
  const up=DATA.events.filter(e=>pickable(e)&&pickOpen(e)).sort((a,b)=>new Date(a.utc)-new Date(b.utc));
  const days={}; up.forEach(e=>{const k=dayNum(new Date(e.utc)); (days[k]=days[k]||[]).push(e);});
  const keys=Object.keys(days).sort(); let html='';
  if(!groupsDone()) html+='<div style="background:rgba(244,194,75,.08);border:1px solid rgba(244,194,75,.34);border-radius:10px;padding:11px 13px;margin-bottom:12px;color:#f4c24b;font-weight:700;font-size:13px;line-height:1.45">🔒 Round of 32 pool — $100 to the winner. Picks open once the group stage wraps.</div>';
  if(!keys.length) html+='<div class="note">No upcoming matches to pick right now.</div>';
  keys.forEach(k=>{ html+='<div class="pday"><div class="daylabel">'+dayLabel(new Date(days[k][0].utc))+'<span></span></div>'+days[k].map(predMatchCard).join('')+'</div>'; });
  const locked=DATA.events.filter(e=>e.ko && pickable(e) && !pickOpen(e) && e.state!=='post').sort((a,b)=>new Date(a.utc)-new Date(b.utc));
  if(locked.length){
    html+='<div class="pday"><div class="daylabel">🔒 Knockout — locked until the group stage ends<span></span></div>'
      + locked.map(e=>'<div class="pmatch" style="opacity:.55"><div class="pm-top"><span class="stage">Knockout</span><span class="time" style="color:var(--gold);font-weight:700">🔒 Locked</span></div><div class="pkrow ko"><span class="pk" style="cursor:default;pointer-events:none">'+norm(e.home)+'</span><span class="pk" style="cursor:default;pointer-events:none">'+norm(e.away)+'</span></div></div>').join('')
      +'</div>';
  }
  const settled=DATA.events.filter(e=>e.state==='post'&&pickable(e)&&MYPICKS[e.id]&&!pickOpen(e)).sort((a,b)=>new Date(b.utc)-new Date(a.utc));
  if(settled.length){
    const rows=settled.map(e=>{ const o=koOut(e); const p=MYPICKS[e.id]; const pend=!o; const ok=!pend&&p===o;
      const pl=p==='d'?'Draw':(p==='h'?norm(e.home):norm(e.away));
      return '<div class="srow '+(pend?'':(ok?'ok':'no'))+'"><span class="sc">'+norm(e.home)+' '+e.hs+'–'+e.as+' '+norm(e.away)+'</span><span class="mypick">picked '+pl+'</span><span class="mark">'+(pend?'·':(ok?'✓':'✗'))+'</span></div>'; }).join('');
    html+='<details class="settled"><summary>Your settled picks <span class="cnt">'+settled.length+'</span></summary>'+rows+'</details>';
  }
  box.innerHTML=html;
}
/* Notification preferences: follow specific countries (or all/none) + daily-brief toggle. */
function loadTeams(){ if(TEAMS||!sb) return; sb.rpc('wc_teams').then(r=>{ TEAMS=(r&&r.data)||[]; renderNotify(); }).catch(()=>{}); }
function toggleTeamI(i){ if(!TEAMS) return; const t=TEAMS[i]; if(MY_COUNTRIES==null) MY_COUNTRIES=TEAMS.slice(); const j=MY_COUNTRIES.indexOf(t); if(j>=0) MY_COUNTRIES.splice(j,1); else MY_COUNTRIES.push(t); renderNotify(); }
function followAllTeams(){ MY_COUNTRIES=null; renderNotify(); }
function followNoTeams(){ MY_COUNTRIES=[]; renderNotify(); }
function toggleBrief(){ MY_BRIEF=!MY_BRIEF; renderNotify(); }
async function saveNotify(){ if(!ME||!sb) return; const st=document.getElementById('notifyMsg'); if(st) st.textContent='Saving…';
  let status=null; try{ const r=await sb.rpc('wc_set_prefs',{ p_code:CODE, p_email:ME, p_countries:MY_COUNTRIES, p_brief:MY_BRIEF }); status=r&&r.data; }catch(e){}
  if(st){ st.textContent = status==='ok' ? 'Saved ✓' : 'Could not save — try again.'; st.style.color = status==='ok' ? 'var(--win)' : 'var(--loss)'; }
}
function renderNotify(){
  const box=document.getElementById('predNotify'); if(!box) return;
  if(!ME){ box.innerHTML=''; return; }
  if(!TEAMS){ loadTeams(); box.innerHTML='<div class="tgcard"><div class="tgh">🔔 Notifications</div><div class="tgsub">Loading teams…</div></div>'; return; }
  const all=MY_COUNTRIES==null, sel=all?null:MY_COUNTRIES;
  const summary=all?'You follow <b>all teams</b>.':(sel.length?('Following <b>'+sel.length+'</b> team'+(sel.length>1?'s':'')+'.'):'<b>Muted</b> — no match alerts.');
  const chips=TEAMS.map((t,i)=>{ const on=all||sel.indexOf(t)>=0; return '<button class="pk'+(on?' sel':'')+'" style="font-size:12px;padding:6px 10px" onclick="toggleTeamI('+i+')">'+(typeof flag==='function'?'<span class="flag">'+flag(t)+'</span> ':'')+String(t).replace(/</g,'&lt;')+'</button>'; }).join('');
  box.innerHTML='<div class="tgcard"><div class="tgh">🔔 Notifications</div>'
    +'<div class="tgsub">'+summary+' Goal alerts, clips &amp; full-time recaps come for your followed teams — tap to choose, or follow all.</div>'
    +'<div style="display:flex;gap:8px;margin:11px 0 9px"><button class="pbtn" onclick="followAllTeams()">Follow all</button><button class="pbtn ghost" onclick="followNoTeams()">Follow none</button></div>'
    +'<div style="display:flex;flex-wrap:wrap;gap:7px">'+chips+'</div>'
    +'<label style="display:flex;align-items:center;gap:9px;margin-top:14px;font-size:13px;cursor:pointer"><input type="checkbox" '+(MY_BRIEF?'checked':'')+' onclick="toggleBrief()"> Daily fixtures brief (one message a day)</label>'
    +'<div style="display:flex;align-items:center;gap:12px;margin-top:13px"><button class="pbtn solid" onclick="saveNotify()">Save preferences</button><span id="notifyMsg" class="authmsg" style="margin:0"></span></div></div>';
}
function renderPredict(){ renderTelegram(); renderNotify(); renderPredictBoard(); renderPredictList(); if(typeof renderShell==='function') renderShell(); }

/* ===================== Full-game highlight reels (View Highlights) ===================== */
window.REELS = {};
async function loadReels(){ if(!sb) return; try{ const r=await sb.rpc('wc_reels'); const a=(r&&r.data)||[]; const m={}; a.forEach(x=>{ if(x&&x.m&&x.u) m[x.m]=x.u; }); window.REELS=m; if(typeof renderMatches==='function') renderMatches(); }catch(e){ console.warn('loadReels', e); } }
function reelEsc(e){ if(e.key==='Escape') closeReel(); }
function closeReel(){ const md=document.getElementById('reelModal'); if(md){ const v=md.querySelector('video'); if(v){ try{ v.pause(); }catch(_){} } md.remove(); } document.removeEventListener('keydown', reelEsc, true); document.body.style.overflow=''; }
function ytId(u){ var m=String(u||'').match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/); return m?m[1]:null; }
function openReel(url){ if(!url) return; closeReel(); var yt=ytId(url); var media = yt ? '<iframe src="https://www.youtube.com/embed/'+yt+'?autoplay=1&rel=0&playsinline=1" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>' : '<video src="'+url+'" controls autoplay playsinline></video>'; const ov=document.createElement('div'); ov.className='reelmodal'; ov.id='reelModal'; ov.innerHTML='<div class="reelbox"><button class="reelclose" onclick="closeReel()" aria-label="Close">×</button>'+media+'</div>'; ov.addEventListener('click', function(e){ if(e.target===ov) closeReel(); }); document.body.appendChild(ov); document.addEventListener('keydown', reelEsc, true); document.body.style.overflow='hidden'; }
loadReels(); setInterval(loadReels, 300000);
/* Knockout Pool — "How it works" modal (Predict page) */
function closeRulesModal(){ var m=document.getElementById('rulesModal'); if(m) m.remove(); document.body.style.overflow=''; }
function openRulesModal(){ closeRulesModal();
  var ov=document.createElement('div'); ov.id='rulesModal';
  ov.style.cssText='position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.78);display:flex;align-items:center;justify-content:center;padding:16px';
  ov.innerHTML='<div style="position:relative;width:min(440px,96vw);max-height:88vh;overflow:auto;background:var(--panel,#0f1626);border:1px solid var(--line,#243150);border-radius:16px;padding:22px 20px;color:var(--ink,#eaf2ff);font-family:Inter,system-ui,sans-serif">'
    +'<button onclick="closeRulesModal()" aria-label="Close" style="position:absolute;top:10px;right:12px;background:none;border:0;color:#9fb3d1;font-size:22px;line-height:1;cursor:pointer">×</button>'
    +'<h3 style="margin:0 0 6px;font-size:19px;font-weight:800">Welcome to the Knockout Pool 🏆</h3>'
    +'<p style="margin:0 0 14px;color:#9fb3d1;font-size:13px">Here is how it works:</p>'
    +'<div style="display:flex;flex-direction:column;gap:11px;font-size:14px;line-height:1.5">'
    +'<div>⚽ <b>Pick the winner</b> of every match for the rest of the 2026 World Cup. Each correct pick = <b>3 points</b>.</div>'
    +'<div>🥅 In the <b>Final</b>, you will also call the score — nail the result <b>and</b> the score for <b>5 points</b>.</div>'
    +'<div>💵 Most points at the end takes the <b style="color:var(--gold,#f4c24b)">$100 cash</b> — from Don, due on sight.</div>'
    +'</div>'
    +'<p style="margin:16px 0 0;font-size:13px;color:#9fb3d1;font-style:italic">May the most knowledgeable futbol fan win… or not. Good luck! ⚽</p>'
    +'<button onclick="closeRulesModal()" style="margin-top:18px;width:100%;background:var(--cyan,#38bdf8);color:#08111c;border:0;border-radius:10px;padding:11px;font-weight:800;font-size:14px;cursor:pointer">Got it</button>'
    +'</div>';
  ov.addEventListener('click',function(ev){ if(ev.target===ov) closeRulesModal(); });
  document.body.appendChild(ov); document.body.style.overflow='hidden';
}
/* $100 Round-of-32 pool announcement — dismissible sitewide banner */
(function(){ try{ if(localStorage.getItem('wc_pool_banner')==='off') return; }catch(e){}
  var b=document.createElement('div');
  b.style.cssText='position:relative;z-index:60;background:linear-gradient(90deg,#0f2a44,#0f3a2e);border-bottom:1px solid #1c3b33;color:#eaf2ff;font:600 13px/1.45 Inter,system-ui,sans-serif;padding:9px 38px 9px 14px;text-align:center';
  b.innerHTML='👋 Welcome friends! New <b>$100 knockout pool</b> starts at the Round of 32 — winner takes $100 cash. Picks open after the group stage finishes. ⚽<button aria-label="Dismiss" style="position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:0;color:#9fb3d1;font-size:19px;line-height:1;cursor:pointer;padding:4px 8px">×</button>';
  b.querySelector('button').onclick=function(){ b.remove(); try{ localStorage.setItem('wc_pool_banner','off'); }catch(e){} };
  document.body.insertBefore(b, document.body.firstChild);
})();"""

tpl = tpl[:s] + NEW_PRED_JS + tpl[e:]

# 7a) processEvents: capture the actual winner (incl. penalties) from ESPN's competitor.winner flag,
# so knockout picks score by who advanced — not the raw 90/120-min scoreline.
PE_OLD = "m.hs=+(H.score||0); m.as=+(A.score||0);"
PE_NEW = "m.hs=+(H.score||0); m.as=+(A.score||0); m.win=(H.winner===true?'h':(A.winner===true?'a':''));"
if PE_OLD not in tpl: fail("processEvents score anchor not found")
tpl = tpl.replace(PE_OLD, PE_NEW, 1)

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
