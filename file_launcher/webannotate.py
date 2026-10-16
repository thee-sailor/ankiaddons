"""
In-browser PDF annotator.

Serves a drawing viewer on 127.0.0.1 that opens as a tab in the embedded
browser. Pages are rendered by PyMuPDF; you draw on a canvas overlay (pen,
highlighter, eraser, text, colour, size, undo); strokes are POSTed back and
baked into the PDF as annotations (on Save and on tab/app close). Because the
browser shows rendered PNGs — not the file — the PDF is never locked, so saving
back is reliable.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import threading
import urllib.parse

from .annotate import _ensure_fitz

RENDER_SCALE = 2.0

_server = None
_port = None
_docs: dict[str, str] = {}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _dlock(did: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(did, threading.Lock())


def _register(path: str) -> str:
    did = hashlib.md5(path.encode("utf-8")).hexdigest()[:12]
    _docs[did] = path
    return did


def _hex01(hexstr: str):
    h = (hexstr or "#ff0000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
    except Exception:
        return (1.0, 0.0, 0.0)


def _save(did: str, data: dict) -> bool:
    fitz = _ensure_fitz()
    path = _docs.get(did)
    if not fitz or not path or not os.path.isfile(path):
        return False
    pages = data.get("pages", {})
    with _dlock(did):
        doc = fitz.open(path)
        wrote = False
        for ns, strokes in pages.items():
            try:
                n = int(ns)
            except Exception:
                continue
            if n < 0 or n >= doc.page_count:
                continue
            page = doc[n]
            for s in strokes:
                try:
                    if s.get("type") == "text":
                        x = s["x"] / RENDER_SCALE
                        y = s["y"] / RENDER_SCALE
                        fs = max(8, s.get("width", 4) * 3) / RENDER_SCALE
                        page.add_freetext_annot(
                            fitz.Rect(x, y, x + 340, y + fs + 8), s.get("text", ""),
                            fontsize=fs, text_color=_hex01(s.get("color")))
                    else:
                        pts = [fitz.Point(p[0] / RENDER_SCALE, p[1] / RENDER_SCALE)
                               for p in s.get("points", [])]
                        if not pts:
                            continue
                        a = page.add_ink_annot([pts])
                        a.set_colors(stroke=_hex01(s.get("color")))
                        a.set_border(width=max(0.5, s.get("width", 4) / RENDER_SCALE))
                        if s.get("tool") == "highlighter":
                            a.set_opacity(0.4)
                        a.update()
                    wrote = True
                except Exception as exc:
                    print("[web annotate] stroke failed:", exc)
        if wrote:
            try:
                doc.saveIncr()
            except Exception:
                try:
                    tmp = path + ".__w.pdf"
                    doc.save(tmp, garbage=3, deflate=True)
                    doc.close()
                    os.replace(tmp, path)
                    return True
                except Exception as exc:
                    print("[web annotate] save failed:", exc)
                    try:
                        doc.close()
                    except Exception:
                        pass
                    return False
        doc.close()
    return True


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        fitz = _ensure_fitz()
        if u.path == "/viewer":
            self._send(200, "text/html; charset=utf-8", _VIEWER_HTML.encode("utf-8"))
            return
        did = q.get("id", [""])[0]
        path = _docs.get(did)
        if not path or not fitz:
            self._send(404, "text/plain", b"not found")
            return
        if u.path == "/meta":
            with _dlock(did):
                doc = fitz.open(path)
                pages = [{"w": int(doc[i].rect.width * RENDER_SCALE),
                          "h": int(doc[i].rect.height * RENDER_SCALE)}
                         for i in range(doc.page_count)]
                doc.close()
            self._send(200, "application/json",
                       json.dumps({"n": len(pages), "pages": pages,
                                   "scale": RENDER_SCALE,
                                   "name": os.path.basename(path)}).encode())
        elif u.path == "/page":
            try:
                n = int(q.get("n", ["0"])[0])
            except Exception:
                n = 0
            with _dlock(did):
                doc = fitz.open(path)
                if 0 <= n < doc.page_count:
                    pix = doc[n].get_pixmap(
                        matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE), alpha=False)
                    png = pix.tobytes("png")
                else:
                    png = b""
                doc.close()
            self._send(200, "image/png", png)
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/save":
            did = q.get("id", [""])[0]
            try:
                ln = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(ln) or b"{}")
            except Exception:
                data = {}
            ok = _save(did, data)
            self._send(200, "application/json", json.dumps({"ok": ok}).encode())
        else:
            self._send(404, "text/plain", b"not found")


def _ensure_server() -> int | None:
    global _server, _port
    if _server is not None:
        return _port
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    except Exception:
        return None
    _port = srv.server_address[1]
    _server = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return _port


def viewer_url(path: str) -> str | None:
    port = _ensure_server()
    if port is None:
        return None
    did = _register(path)
    return "http://127.0.0.1:%d/viewer?id=%s" % (port, did)


_VIEWER_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Annotate PDF</title>
<style>
  :root{color-scheme:dark}
  html,body{margin:0;background:#15151f;color:#e8e8f0;font-family:Segoe UI,system-ui,sans-serif}
  #bar{position:sticky;top:0;z-index:10;display:flex;gap:6px;align-items:center;
       padding:7px 10px;background:#12121f;border-bottom:1px solid #2a2a4a;flex-wrap:wrap}
  .tool{width:34px;height:30px;border:none;border-radius:6px;background:#2d2d4e;color:#fff;
        font-size:15px;cursor:pointer}
  .tool.on{background:#7c3aed}
  #bar input[type=color]{width:30px;height:28px;border:none;background:none;cursor:pointer}
  #bar input[type=range]{width:110px}
  #save{margin-left:auto;background:#7c3aed;color:#fff;border:none;border-radius:6px;
        padding:6px 16px;font-weight:700;cursor:pointer}
  #status{color:#9a9ac0;font-size:12px;margin-left:8px}
  #pages{padding:16px;display:flex;flex-direction:column;align-items:center;gap:16px}
  .page{position:relative;box-shadow:0 2px 12px rgba(0,0,0,.5);background:#fff;max-width:980px;width:100%}
  .page img{display:block;width:100%}
  .page canvas{position:absolute;left:0;top:0;width:100%;height:100%;touch-action:none;cursor:crosshair}
  .lbl{color:#8a8ab0;font-size:12px}
</style></head>
<body>
<div id="bar">
  <button class="tool on" data-t="pen" title="Pen">✏️</button>
  <button class="tool" data-t="highlighter" title="Highlighter">🖍️</button>
  <button class="tool" data-t="eraser" title="Eraser">🧽</button>
  <button class="tool" data-t="text" title="Text">T</button>
  <input type="color" id="color" value="#ff3b30">
  <label class="lbl">Size <input type="range" id="size" min="1" max="40" value="4"></label>
  <button class="tool" id="undo" title="Undo (Ctrl+Z)" style="width:auto;padding:0 10px">↶</button>
  <button id="save">Save</button><span id="status"></span>
</div>
<div id="pages"></div>
<script>
const ID = new URLSearchParams(location.search).get('id');
let TOOL='pen', COLOR='#ff3b30', SIZE=4, SCALE=2;
const strokes={};            // page -> [stroke]
const undoStack=[];          // {page, snapshot}
const canvases={};           // page -> {canvas, ctx}

document.querySelectorAll('.tool[data-t]').forEach(b=>{
  b.onclick=()=>{ document.querySelectorAll('.tool[data-t]').forEach(x=>x.classList.remove('on'));
                  b.classList.add('on'); TOOL=b.dataset.t; };
});
color.oninput=e=>COLOR=e.target.value;
size.oninput=e=>SIZE=+e.target.value;
undo.onclick=doUndo;
save.onclick=()=>saveAll(true);
document.addEventListener('keydown',e=>{ if(e.ctrlKey&&e.key.toLowerCase()==='z'){e.preventDefault();doUndo();} });

function setStatus(t){ status.textContent=t; }

function draw(page){
  const c=canvases[page]; if(!c) return;
  const ctx=c.ctx; ctx.clearRect(0,0,c.canvas.width,c.canvas.height);
  for(const s of (strokes[page]||[])) drawStroke(ctx,s);
}
function drawStroke(ctx,s){
  if(s.type==='text'){ ctx.fillStyle=s.color; ctx.font=('bold '+Math.max(14,s.width*6)+'px sans-serif');
    ctx.fillText(s.text, s.x, s.y); return; }
  ctx.strokeStyle=s.color; ctx.lineCap='round'; ctx.lineJoin='round';
  ctx.globalAlpha = s.tool==='highlighter'?0.35:1;
  ctx.lineWidth = s.tool==='highlighter'? s.width*3 : s.width;
  ctx.beginPath();
  const p=s.points; if(!p.length){ctx.globalAlpha=1;return;}
  ctx.moveTo(p[0][0],p[0][1]); for(let i=1;i<p.length;i++) ctx.lineTo(p[i][0],p[i][1]);
  ctx.stroke(); ctx.globalAlpha=1;
}
function pushUndo(page){ undoStack.push({page, snap: JSON.stringify(strokes[page]||[])});
  if(undoStack.length>80) undoStack.shift(); }
function doUndo(){ const u=undoStack.pop(); if(!u) return;
  strokes[u.page]=JSON.parse(u.snap); draw(u.page); }

function toCanvasXY(canvas,e){ const r=canvas.getBoundingClientRect();
  return [ (e.clientX-r.left)/r.width*canvas.width, (e.clientY-r.top)/r.height*canvas.height ]; }

function wire(page){
  const c=canvases[page].canvas; let cur=null;
  c.addEventListener('pointerdown',e=>{
    c.setPointerCapture(e.pointerId);
    const [x,y]=toCanvasXY(c,e); pushUndo(page);
    if(TOOL==='text'){ const t=prompt('Text:'); if(t){ (strokes[page]=strokes[page]||[]).push({type:'text',text:t,x,y,color:COLOR,width:SIZE}); draw(page);} else undoStack.pop(); return; }
    if(TOOL==='eraser'){ erase(page,x,y); return; }
    cur={points:[[x,y]],color:COLOR,width:SIZE,tool:TOOL};
  });
  c.addEventListener('pointermove',e=>{
    if(TOOL==='eraser' && (e.buttons&1)){ const [x,y]=toCanvasXY(c,e); erase(page,x,y); return; }
    if(!cur) return; const [x,y]=toCanvasXY(c,e); cur.points.push([x,y]);
    const ctx=canvases[page].ctx; drawStroke(ctx,cur);
  });
  const end=()=>{ if(cur){ (strokes[page]=strokes[page]||[]).push(cur); cur=null; draw(page);} };
  c.addEventListener('pointerup',end); c.addEventListener('pointercancel',end);
}
function erase(page,x,y){ const r=Math.max(8,SIZE*2); const arr=strokes[page]||[]; let rm=false;
  strokes[page]=arr.filter(s=>{ if(s.type==='text'){ if(Math.abs(s.x-x)<120&&Math.abs(s.y-y)<40){rm=true;return false;} return true; }
    const hit=s.points.some(p=>Math.abs(p[0]-x)<=r&&Math.abs(p[1]-y)<=r); if(hit)rm=true; return !hit; });
  if(rm) draw(page); }

async function saveAll(explicit){
  try{
    const r=await fetch('/save?id='+ID,{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({pages:strokes})});
    const j=await r.json();
    if(j.ok){ if(explicit){ setStatus('Saved ✓'); // bake: clear overlays and reload page images
        for(const n in canvases){ strokes[n]=[]; draw(n);
          const img=canvases[n].canvas.previousElementSibling;
          if(img) img.src='/page?id='+ID+'&n='+n+'&t='+Date.now(); }
      } }
    else setStatus('Save failed');
  }catch(e){ setStatus('Save failed'); }
}
function beacon(){ try{ navigator.sendBeacon('/save?id='+ID, JSON.stringify({pages:strokes})); }catch(e){} }
window.addEventListener('pagehide', beacon);
window.addEventListener('beforeunload', beacon);
document.addEventListener('visibilitychange',()=>{ if(document.visibilityState==='hidden') beacon(); });

(async function(){
  const meta=await (await fetch('/meta?id='+ID)).json();
  SCALE=meta.scale||2; document.title='Annotate — '+(meta.name||'PDF');
  const pagesEl=document.getElementById('pages');
  const io=new IntersectionObserver((ents)=>{ ents.forEach(en=>{ if(en.isIntersecting){
      const img=en.target; if(!img.src){ img.src='/page?id='+ID+'&n='+img.dataset.n; } io.unobserve(img); } }); },
      {rootMargin:'800px'});
  for(let i=0;i<meta.n;i++){
    const pg=meta.pages[i];
    const div=document.createElement('div'); div.className='page'; div.style.aspectRatio=pg.w+'/'+pg.h;
    const img=document.createElement('img'); img.dataset.n=i;
    const cv=document.createElement('canvas'); cv.width=pg.w; cv.height=pg.h;
    div.appendChild(img); div.appendChild(cv); pagesEl.appendChild(div);
    canvases[i]={canvas:cv, ctx:cv.getContext('2d')}; strokes[i]=[]; wire(i); io.observe(img);
  }
})();
</script></body></html>
"""
