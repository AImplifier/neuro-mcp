"""Standalone HTML builders that reproduce the NEUROII views faithfully.

Each returns a complete self-contained HTML document with Plotly.js embedded and
custom JavaScript that reproduces NEUROII's interactions exactly:

  * raw_html      — RawView: page navigation (start/back/fwd/end + page length),
                    scroll-to-zoom amplitude, grid toggle
  * evoked_html   — EvokedView: stacked channels + green cursor + topomap, time
                    slider, and the summary sidebar (nave / peak / tmin / tmax)
  * esi_html      — EsiView: canvas brain slices (crosshair, L/R + MNI labels,
                    black-blue-white-red overlay) recentred per frame, the ERP
                    butterfly with red cursor + blue half-peak marker, a time
                    slider, global/frame scale toggle, and a mask-threshold slider

The ESI canvas renderer is a direct port of NEUROII's BrainSlices.jsx
(renderCanvas / getCrosshair / activationRGB).
"""

from __future__ import annotations

import json
import math

from plotly.offline import get_plotlyjs

_PLOTLYJS = None


def _san(o):
    """Recursively replace non-finite floats (NaN/Inf) with None so the embedded
    JSON is valid — Plotly reads null as a gap (e.g. topomap head-circle clip)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _san(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_san(v) for v in o]
    return o


def _plotlyjs() -> str:
    global _PLOTLYJS
    if _PLOTLYJS is None:
        _PLOTLYJS = get_plotlyjs()
    return _PLOTLYJS


_CSS = """
:root{
  --bg:#f5f5fa; --surface:#fff; --surface-2:#eeeef6; --border:#dddde8; --border-soft:#e8e8f2;
  --text:#33344a; --muted:#6b7280; --accent:#6264A7; --accent-dark:#464775;
  --r-sm:6px; --r-md:10px;
  --shadow-xs:0 1px 3px rgba(0,0,0,.08);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.app-header{height:56px;display:flex;align-items:center;gap:12px;padding:0 18px;
  background:linear-gradient(135deg,#6264A7 0%,#464775 100%);
  box-shadow:0 2px 10px rgba(98,100,167,.22)}
.app-header .logo{width:34px;height:34px;border-radius:var(--r-sm);background:#fff;
  display:flex;align-items:center;justify-content:center;font-size:18px;
  border:1px solid rgba(255,255,255,.4)}
.brand{font-family:Georgia,'Times New Roman',serif;font-size:1.2rem;font-weight:700;
  letter-spacing:.14em;color:#fff;text-shadow:0 1px 4px rgba(0,0,0,.12)}
.subtitle{font-size:.78rem;color:rgba(255,255,255,.82);margin-left:2px}
.badge{margin-left:auto;font-size:.62rem;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;padding:3px 9px;border-radius:5px}
.badge-raw{background:#fff3cd;color:#7a5700;border:1px solid #ffd97a}
.badge-evoked{background:#d4f4e2;color:#1a5c3a;border:1px solid #6ddba4}
.badge-esi{background:#ede8ff;color:#4a1d96;border:1px solid #b89eff}
.viz-wrap{display:flex;align-items:stretch;background:var(--surface)}
.viz-wrap.fill-height{height:calc(100vh - 56px)}
.viz-wrap.fill-height .viz-main{height:100%}
.card.grow{flex:1;min-height:0;display:flex;flex-direction:column}
.card.grow>div{flex:1;min-height:0}
.viz-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px;padding:10px}
.viz-side{width:285px;flex-shrink:0;border-left:1px solid var(--border);
  background:var(--surface-2);padding:12px;display:flex;flex-direction:column;gap:10px}
.card{background:var(--surface);border:1px solid var(--border-soft);
  border-radius:var(--r-md);box-shadow:var(--shadow-xs);padding:6px}
table.summary{width:100%;border-collapse:collapse}
table.summary th{text-align:left;color:var(--muted);font-weight:500;font-size:.78rem;
  padding:3px 6px 3px 0;white-space:nowrap}
table.summary td{text-align:right;font-size:.78rem;padding:3px 0;font-variant-numeric:tabular-nums}
table.summary tr:not(:last-child) th,table.summary tr:not(:last-child) td{
  border-bottom:1px solid var(--border-soft)}
.btn{font-size:.78rem;padding:4px 10px;border:1px solid var(--border);background:var(--surface);
  border-radius:var(--r-sm);color:var(--text);cursor:pointer;
  transition:background .12s,color .12s,border-color .12s}
.btn:hover{background:var(--surface-2)}
.btn.active{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.active:hover{background:var(--accent-dark)}
.icon-btn{display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:28px;
  border:1px solid var(--border);background:var(--surface);border-radius:var(--r-sm);
  color:var(--text);cursor:pointer;font-size:12px;transition:background .12s}
.icon-btn:hover{background:var(--surface-2);color:var(--accent)}
.navbar{display:flex;gap:5px;align-items:center;justify-content:center;padding:8px 6px 2px}
.pos{font-size:.78rem;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums;padding:0 4px}
.numin{width:64px;height:28px;text-align:center;border:1px solid var(--border);
  border-radius:var(--r-sm);background:var(--surface);color:var(--text);font-size:.8rem}
.slices{display:flex;gap:8px}
.slices .col{flex:1;min-width:0;text-align:center}
.slices canvas{width:100%;height:auto;display:block;background:#000;
  border:1px solid var(--border);border-radius:var(--r-sm)}
.slabel{font-size:.70rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;
  font-weight:500;margin-bottom:3px}
.section-label{font-size:.72rem;color:var(--muted);font-weight:600;margin-bottom:4px}
.legend{height:12px;border-radius:4px;border:1px solid var(--border)}
.pane-divider{flex:0 0 12px;align-self:stretch;position:relative;cursor:col-resize;touch-action:none}
.pane-divider::after{content:'';position:absolute;top:14px;bottom:14px;left:5px;width:2px;background:var(--border);border-radius:1px;transition:background .12s}
.pane-divider:hover::after,.pane-divider.dragging::after{background:var(--accent)}
.split-row{display:flex;align-items:stretch}
.sm{font-size:.72rem;color:var(--muted)}
input[type=range]{width:100%;accent-color:var(--accent)}
.tlabels{display:flex;justify-content:space-between;font-size:.72rem;color:var(--muted);padding:2px 60px}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:#c8cdd6;border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:#a0a8b5}
"""


def _page(title: str, body: str, data: dict, script: str,
          subtitle: str = "", badge: str = "", badge_cls: str = "") -> str:
    badge_html = f'<span class="badge {badge_cls}">{badge}</span>' if badge else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title}</title>
<style>{_CSS}</style></head><body>
<div class="app-header">
  <div class="logo">🧠</div>
  <span class="brand">NEUROII</span>
  <span class="subtitle">{subtitle}</span>
  {badge_html}
</div>
{body}
<script id="vizdata" type="application/json">{json.dumps(_san(data))}</script>
<script>{_plotlyjs()}</script>
<script>{script}</script>
</body></html>"""


# --------------------------------------------------------------------------- #
# Raw: paging + scroll-amplitude + grid toggle
# --------------------------------------------------------------------------- #
def raw_html(title, fig_dict, duration, page_len, favicon="🧠"):
    body = """
<div class="viz-wrap fill-height">
  <div class="viz-main">
    <div class="card grow"><div id="plot" style="width:100%;height:100%"></div></div>
    <div class="navbar">
      <button class="icon-btn" id="b-start" title="Jump to start">⏮</button>
      <button class="icon-btn" id="b-back" title="Previous page">◀</button>
      <span class="pos" id="pos"></span>
      <input class="numin" id="pagelen" type="number" min="0.5" step="0.5"/>
      <span class="sm">s/page</span>
      <button class="icon-btn" id="b-fwd" title="Next page">▶</button>
      <button class="icon-btn" id="b-end" title="Jump to end">⏭</button>
      <button class="btn active" id="b-grid" title="Toggle gridlines" style="margin-left:6px">grid</button>
    </div>
    <div class="sm" style="text-align:center">scroll over the plot to change amplitude</div>
  </div>
</div>"""
    script = """
const D = JSON.parse(document.getElementById('vizdata').textContent);
const fig = D.fig; const gd = document.getElementById('plot');
let tmin=0, pageLen=D.page_len, duration=D.duration, gridOn=true;
// Baseline y-axis ranges (per channel) for amplitude gain about zero.
const baseRanges={}; Object.keys(fig.layout).forEach(k=>{if(/^yaxis\\d*$/.test(k)&&fig.layout[k].range)baseRanges[k]=fig.layout[k].range.slice();});
let gain=1;
Plotly.newPlot(gd, fig.data, fig.layout, {responsive:true,displaylogo:false}).then(()=>Plotly.Plots.resize(gd));
window.addEventListener('resize',()=>Plotly.Plots.resize(gd));
function applyView(){
  const up={'xaxis.range':[tmin, Math.min(tmin+pageLen,duration)]};
  for(const k in baseRanges){up[k+'.range']=[baseRanges[k][0]/gain, baseRanges[k][1]/gain];}
  Plotly.relayout(gd, up);
  document.getElementById('pos').textContent=tmin.toFixed(2)+'–'+Math.min(tmin+pageLen,duration).toFixed(2)+'s / '+duration.toFixed(0)+'s';
}
document.getElementById('pagelen').value=pageLen;
document.getElementById('b-start').onclick=()=>{tmin=0;applyView();};
document.getElementById('b-back').onclick=()=>{tmin=Math.max(0,tmin-pageLen);applyView();};
document.getElementById('b-fwd').onclick=()=>{tmin=Math.min(tmin+pageLen,Math.max(0,duration-pageLen));applyView();};
document.getElementById('b-end').onclick=()=>{tmin=Math.max(0,duration-pageLen);applyView();};
document.getElementById('pagelen').onchange=(e)=>{pageLen=Math.max(0.5,parseFloat(e.target.value)||pageLen);applyView();};
document.getElementById('b-grid').onclick=(e)=>{gridOn=!gridOn;e.target.classList.toggle('active',gridOn);
  Plotly.relayout(gd,{'xaxis.showgrid':gridOn,'xaxis.minor.showgrid':gridOn});};
gd.addEventListener('wheel',(ev)=>{ev.preventDefault();gain*=(ev.deltaY<0?1.15:1/1.15);gain=Math.max(0.05,Math.min(50,gain));applyView();},{passive:false});
applyView();
"""
    data = {"fig": fig_dict, "duration": duration, "page_len": page_len}
    return _page(title, body, data, script, subtitle=title,
                 badge="Raw", badge_cls="badge-raw"), favicon


# --------------------------------------------------------------------------- #
# Evoked: Plotly figure (works natively) + summary sidebar
# --------------------------------------------------------------------------- #
def evoked_html(title, ch_fig, topo_fig, tframes, summary, favicon="🧠"):
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in summary.items())
    # Inset the slider + labels to the channel figure's data area (left margin
    # 64 for channel labels, right margin 10) so t-min/t-max line up with the axis.
    pad = "padding-left:64px;padding-right:10px"
    body = f"""
<div class="viz-wrap fill-height">
  <div class="viz-main">
    <div class="split-row" style="flex:1;min-height:0">
      <div id="leftpane" style="flex:0 0 50%;min-width:220px;display:flex;flex-direction:column;min-height:0">
        <div class="card grow"><div id="chplot" style="width:100%;height:100%"></div></div>
        <div style="{pad};margin-top:6px"><input id="tslider" type="range" min="0" step="1" style="width:100%"/></div>
        <div class="tlabels" style="{pad}"><span id="lmin"></span>
          <span id="lcur" style="color:var(--text);font-weight:600"></span><span id="lmax"></span></div>
      </div>
      <div id="divider" class="pane-divider" title="Drag to resize"></div>
      <div id="rightpane" style="flex:1;min-width:220px;display:flex;flex-direction:column;min-height:0">
        <div class="card grow"><div id="topoplot" style="width:100%;height:100%"></div></div>
      </div>
    </div>
  </div>
  <div class="viz-side">
    <div class="section-label">Summary</div>
    <table class="summary"><tbody>{rows}</tbody></table>
    <div class="sm">Drag the divider to resize the panes — the topomap scales to fill its side.</div>
  </div>
</div>"""
    script = """
const D=JSON.parse(document.getElementById('vizdata').textContent);
const CFG={responsive:true,displaylogo:false};
function fit(){Plotly.Plots.resize('chplot');Plotly.Plots.resize('topoplot');}
// Scroll-to-zoom amplitude on the stacked channel plot (scale y-axes about zero).
function ampZoom(id){var gd=document.getElementById(id);var base={};var fl=gd._fullLayout||{};
  Object.keys(fl).forEach(function(k){if(/^yaxis\d*$/.test(k)&&fl[k].range)base[k]=fl[k].range.slice();});
  var gain=1;gd.addEventListener('wheel',function(e){e.preventDefault();
    gain*=(e.deltaY<0?1.15:1/1.15);gain=Math.max(0.05,Math.min(50,gain));var up={};
    for(var k in base){up[k+'.range']=[base[k][0]/gain,base[k][1]/gain];}Plotly.relayout(gd,up);},{passive:false});}
Promise.all([
  Plotly.newPlot('chplot', D.ch.data, D.ch.layout, CFG),
  Plotly.newPlot('topoplot', D.topo.data, D.topo.layout, CFG)
]).then(function(){fit();ampZoom('chplot');});
window.addEventListener('resize',fit);
const frames=D.frames, times=frames.map(f=>f.t);
const sl=document.getElementById('tslider'); sl.max=frames.length-1;
let s0=0,bd=1e9; times.forEach((t,i)=>{const d=Math.abs(t);if(d<bd){bd=d;s0=i;}}); sl.value=s0;
document.getElementById('lmin').textContent=times[0].toFixed(3)+'s';
document.getElementById('lmax').textContent=times[times.length-1].toFixed(3)+'s';
function draw(i){const f=frames[i];
  Plotly.relayout('chplot',{'shapes[0].x0':f.t,'shapes[0].x1':f.t});
  Plotly.restyle('topoplot',{z:[f.z],zmin:-f.vmax,zmax:f.vmax},[0]);
  document.getElementById('lcur').textContent='t = '+f.t.toFixed(3)+' s';
}
sl.oninput=()=>draw(parseInt(sl.value)); draw(s0);
// ── Draggable pane divider (resizes the flex panes; both charts reflow) ──
const div=document.getElementById('divider'), left=document.getElementById('leftpane');
const row=div.parentElement; let drag=false;
div.addEventListener('mousedown',e=>{drag=true;div.classList.add('dragging');e.preventDefault();});
window.addEventListener('mouseup',()=>{if(drag){drag=false;div.classList.remove('dragging');}});
window.addEventListener('mousemove',e=>{
  if(!drag)return;
  const r=row.getBoundingClientRect();
  let f=(e.clientX-r.left)/r.width; f=Math.max(0.2,Math.min(0.8,f));
  left.style.flex='0 0 '+(f*100)+'%';
  fit();
});
"""
    return _page(title, body, {"ch": ch_fig, "topo": topo_fig, "frames": tframes},
                 script, subtitle=title), favicon


# --------------------------------------------------------------------------- #
# ESI: canvas slices (BrainSlices.jsx port) + butterfly + controls + sidebar
# --------------------------------------------------------------------------- #
def esi_html(title, payload, butterfly_fig, t_half, favicon="🧠"):
    body = """
<div class="viz-wrap">
  <div class="viz-main">
    <div class="card"><div class="slices">
      <div class="col"><div class="slabel">Sagittal</div><canvas id="c0"></canvas></div>
      <div class="col"><div class="slabel">Coronal</div><canvas id="c1"></canvas></div>
      <div class="col"><div class="slabel">Axial</div><canvas id="c2"></canvas></div>
    </div></div>
    <div class="card"><div id="butterfly" style="width:100%;height:210px"></div></div>
    <div style="padding-left:60px;padding-right:20px"><input id="tslider" type="range" min="0" step="1" style="width:100%"/></div>
    <div class="tlabels" style="padding-left:60px;padding-right:20px"><span id="lmin"></span><span id="lcur" style="color:var(--text);font-weight:600"></span><span id="lmax"></span></div>
  </div>
  <div class="viz-side">
    <div class="section-label">Summary</div>
    <table class="summary"><tbody>
      <tr><th>tmin</th><td id="s-tmin"></td></tr>
      <tr><th>tmax</th><td id="s-tmax"></td></tr>
      <tr><th>½-max GFP</th><td id="s-half"></td></tr>
      <tr><th>current</th><td id="s-cur"></td></tr>
      <tr><th>n_times</th><td id="s-nt"></td></tr>
      <tr><th>peak act.</th><td id="s-vmax"></td></tr>
      <tr><th>cut voxel</th><td id="s-vox"></td></tr>
    </tbody></table>
    <div><div class="section-label">Activation (blue-white-red)</div><div class="legend"></div>
      <div class="tlabels" style="padding:2px 0"><span>0</span><span id="s-leg"></span></div></div>
    <div><div class="section-label">Colormap scale</div>
      <div style="display:flex;gap:5px">
        <button class="btn active" id="sc-global" style="flex:1">Global max</button>
        <button class="btn" id="sc-frame" style="flex:1">Frame max</button></div></div>
    <div><div class="section-label">Mask threshold: <span id="mv">5.0</span>% of peak</div>
      <input id="mask" type="range" min="0" max="60" step="0.5" value="5"/></div>
  </div>
</div>"""
    script = r"""
const D=JSON.parse(document.getElementById('vizdata').textContent);
const P=D.payload, frames=P.frames;
const CB=[0,0,0],CBL=[0x1f,0x77,0xb4],CW=[255,255,255],CR=[0xd6,0x27,0x28];
function actRGB(t){let c0,c1,l;if(t<0.25){c0=CB;c1=CBL;l=t/0.25}else if(t<0.5){c0=CBL;c1=CW;l=(t-0.25)/0.25}else{c0=CW;c1=CR;l=(t-0.5)/0.5}
  return [Math.round(c0[0]+(c1[0]-c0[0])*l),Math.round(c0[1]+(c1[1]-c0[1])*l),Math.round(c0[2]+(c1[2]-c0[2])*l)];}
function decodeF32(b64){const bin=atob(b64);const buf=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)buf[i]=bin.charCodeAt(i);return new Float32Array(buf.buffer);}
function getCross(view,rows,cols,peak){const [cx,cy,cz]=peak;
  if(view==0)return{row:cy,col:cz};if(view==1)return{row:cy,col:cols-1-cx};return{row:rows-1-cz,col:cols-1-cx};}
function render(canvas,mriB,actB,rows,cols,vmax,cross,showLR,coord,thr){
  canvas.width=cols;canvas.height=rows;const ctx=canvas.getContext('2d');const img=ctx.createImageData(cols,rows);const px=img.data;
  const mri=decodeF32(mriB),act=decodeF32(actB);
  for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const i4=(r*cols+c)*4;const g=Math.round(Math.max(0,Math.min(1,mri[r*cols+c]))*210);
    const t=Math.abs(act[r*cols+c])/vmax;
    if(t>thr){const rel=Math.min(1,(t-thr)/(1-thr));const tc=0.25+0.75*rel;const a=0.60+0.35*rel;const[rC,gC,bC]=actRGB(tc);
      px[i4]=Math.round(a*rC+(1-a)*g);px[i4+1]=Math.round(a*gC+(1-a)*g);px[i4+2]=Math.round(a*bC+(1-a)*g);}
    else{px[i4]=g;px[i4+1]=g;px[i4+2]=g;}px[i4+3]=255;}
  ctx.putImageData(img,0,0);
  if(cross.row!=null){const gap=2;ctx.save();ctx.strokeStyle='rgba(255,255,255,0.8)';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(0,cross.row+0.5);ctx.lineTo(cross.col-gap,cross.row+0.5);ctx.moveTo(cross.col+gap,cross.row+0.5);ctx.lineTo(cols,cross.row+0.5);
    ctx.moveTo(cross.col+0.5,0);ctx.lineTo(cross.col+0.5,cross.row-gap);ctx.moveTo(cross.col+0.5,cross.row+gap);ctx.lineTo(cross.col+0.5,rows);ctx.stroke();ctx.restore();}
  if(showLR){const fs=Math.max(10,Math.round(cols*0.06));const y=Math.round(rows*0.06);ctx.save();ctx.font='bold '+fs+'px sans-serif';ctx.fillStyle='rgba(255,255,255,0.85)';ctx.textBaseline='top';
    ctx.textAlign='left';ctx.fillText('L',Math.round(cols*0.04),y);ctx.textAlign='right';ctx.fillText('R',cols-Math.round(cols*0.04),y);ctx.restore();}
  if(coord){const fs=Math.max(9,Math.round(cols*0.055));ctx.save();ctx.font=fs+'px monospace';ctx.fillStyle='rgba(255,255,255,0.9)';ctx.textBaseline='bottom';ctx.textAlign='left';
    ctx.fillText(coord,Math.round(cols*0.03),rows-Math.round(rows*0.02));ctx.restore();}
}
const VIEWS=['sagittal','coronal','axial'],SHOWLR=[false,true,true],MM=[0,1,2];
let scaleMode='global', maskPct=5;
function draw(idx){const fr=frames[idx];const vmaxG=P.global_vmax;
  for(let v=0;v<3;v++){const m=fr.mri[VIEWS[v]],a=fr.act[VIEWS[v]];const vmax=(scaleMode=='global'?vmaxG:fr.vmax_frame);
    const cross=getCross(v,m.rows,m.cols,fr.peak);const coord=(['x','y','z'][v])+' = '+Math.round(fr.peak_mm[MM[v]]);
    render(document.getElementById('c'+v),m.data,a.data,m.rows,m.cols,vmax,cross,SHOWLR[v],coord,maskPct/100);}
  // sidebar + cursor
  document.getElementById('s-cur').textContent=fr.t.toFixed(3)+'s';
  document.getElementById('lcur').textContent=fr.t.toFixed(3)+'s';
  document.getElementById('s-vmax').textContent=(scaleMode=='global'?vmaxG:fr.vmax_frame).toExponential(2);
  document.getElementById('s-leg').textContent=(scaleMode=='global'?vmaxG:fr.vmax_frame).toExponential(1);
  document.getElementById('s-vox').textContent=fr.peak.join(', ');
  const shapes=[{type:'line',x0:fr.t,x1:fr.t,xref:'x',y0:0,y1:1,yref:'paper',line:{color:'rgba(220,50,50,0.85)',width:1.5,dash:'dot'}}];
  if(D.tHalf!=null)shapes.push({type:'line',x0:D.tHalf,x1:D.tHalf,xref:'x',y0:0,y1:1,yref:'paper',line:{color:'rgba(40,120,220,0.7)',width:1.5,dash:'dash'}});
  Plotly.relayout('butterfly',{shapes:shapes});
}
// Scroll-to-zoom amplitude: scale every y-axis range about zero (MNE-style).
function ampZoom(id){var gd=document.getElementById(id);var base={};var fl=gd._fullLayout||{};
  Object.keys(fl).forEach(function(k){if(/^yaxis\d*$/.test(k)&&fl[k].range)base[k]=fl[k].range.slice();});
  var gain=1;gd.addEventListener('wheel',function(e){e.preventDefault();
    gain*=(e.deltaY<0?1.15:1/1.15);gain=Math.max(0.05,Math.min(50,gain));var up={};
    for(var k in base){up[k+'.range']=[base[k][0]/gain,base[k][1]/gain];}Plotly.relayout(gd,up);},{passive:false});}
// butterfly + scroll-to-zoom amplitude
Plotly.newPlot('butterfly', D.butterfly.data, D.butterfly.layout, {responsive:true,displaylogo:false}).then(function(){ampZoom('butterfly');});
// sidebar static
document.getElementById('s-tmin').textContent=P.tmin.toFixed(3)+'s';
document.getElementById('s-tmax').textContent=P.tmax.toFixed(3)+'s';
document.getElementById('s-half').textContent=(D.tHalf!=null?D.tHalf.toFixed(3)+'s':'—');
document.getElementById('s-nt').textContent=P.n_times;
document.getElementById('lmin').textContent=P.tmin.toFixed(3)+'s';
document.getElementById('lmax').textContent=P.tmax.toFixed(3)+'s';
// slider
const sl=document.getElementById('tslider');sl.max=frames.length-1;
let start=0,bd=1e9;frames.forEach((f,i)=>{const d=Math.abs(f.t-(D.tHalf!=null?D.tHalf:P.peak_time));if(d<bd){bd=d;start=i;}});
sl.value=start;sl.oninput=()=>draw(parseInt(sl.value));
document.getElementById('sc-global').onclick=(e)=>{scaleMode='global';e.target.classList.add('active');document.getElementById('sc-frame').classList.remove('active');draw(parseInt(sl.value));};
document.getElementById('sc-frame').onclick=(e)=>{scaleMode='frame';e.target.classList.add('active');document.getElementById('sc-global').classList.remove('active');draw(parseInt(sl.value));};
document.getElementById('mask').oninput=(e)=>{maskPct=parseFloat(e.target.value);document.getElementById('mv').textContent=maskPct.toFixed(1);draw(parseInt(sl.value));};
draw(start);
"""
    data = {"payload": payload, "butterfly": butterfly_fig, "tHalf": t_half}
    return _page(title, body, data, script, subtitle=title,
                 badge="ESI", badge_cls="badge-esi"), favicon
