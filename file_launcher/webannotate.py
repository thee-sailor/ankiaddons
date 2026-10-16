"""
In-browser PDF annotator.

Renders PDF pages with Qt's built-in QtPdf (no external install needed) and
serves a drawing viewer that opens as a tab in the embedded browser. You draw on
a canvas overlay (pen, highlighter, eraser, text; colour, size, undo); the marks
are saved to a per-file sidecar (reliable, instant) on Save and on tab/app close,
and are re-drawn every time you reopen the file here.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import threading
import time
import urllib.parse

from aqt import mw
from aqt.qt import QApplication, QBuffer, QByteArray, QIODevice, QSize

try:
    from aqt.qt import QPdfDocument
except Exception:
    try:
        from PyQt6.QtPdf import QPdfDocument
    except Exception:
        QPdfDocument = None

RENDER_SCALE = 2.0

_server = None
_port = None
_docs: dict[str, str] = {}          # id -> pdf path
_qt_docs: dict[str, object] = {}    # path -> QPdfDocument (main thread only)
_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def available() -> bool:
    return QPdfDocument is not None


def _dlock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _register(path: str) -> str:
    did = hashlib.md5(path.encode("utf-8")).hexdigest()[:12]
    _docs[did] = path
    return did


def _run_on_main(fn, timeout=30):
    res = {}
    ev = threading.Event()

    def run():
        try:
            res["v"] = fn()
        except Exception as e:  # noqa: BLE001
            res["e"] = e
        finally:
            ev.set()

    mw.taskman.run_on_main(run)
    if not ev.wait(timeout):
        raise TimeoutError("render timed out")
    if "e" in res:
        raise res["e"]
    return res.get("v")


# ── Qt rendering (MAIN THREAD only) ────────────────────────────────────────────

def _get_doc(path: str):
    d = _qt_docs.get(path)
    if d is None:
        d = QPdfDocument(mw)
        d.load(path)
        for _ in range(60):                       # PDF load can be briefly async
            if d.status() == QPdfDocument.Status.Ready:
                break
            QApplication.processEvents()
            time.sleep(0.02)
        _qt_docs[path] = d
    return d


def _meta_main(path: str):
    d = _get_doc(path)
    n = d.pageCount()
    pages = []
    for i in range(n):
        ps = d.pagePointSize(i)
        pages.append({"w": max(1, int(ps.width() * RENDER_SCALE)),
                      "h": max(1, int(ps.height() * RENDER_SCALE))})
    return n, pages


def _render_main(path: str, n: int) -> bytes:
    d = _get_doc(path)
    ps = d.pagePointSize(n)
    size = QSize(max(1, int(ps.width() * RENDER_SCALE)),
                max(1, int(ps.height() * RENDER_SCALE)))
    img = d.render(n, size)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


# ── stroke sidecar (reliable persistence) ──────────────────────────────────────

def _strokes_path(path: str) -> str:
    d = os.path.join(os.path.dirname(__file__), "user_files", "annotations")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.md5(path.encode("utf-8")).hexdigest() + ".json")


def _load_strokes(path: str) -> dict:
    try:
        with open(_strokes_path(path), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_strokes(path: str, pages: dict) -> bool:
    try:
        with open(_strokes_path(path), "w", encoding="utf-8") as f:
            json.dump(pages, f)
        return True
    except Exception:
        return False


# ── HTTP server ────────────────────────────────────────────────────────────────

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
        if u.path == "/viewer":
            self._send(200, "text/html; charset=utf-8", _VIEWER_HTML.encode("utf-8"))
            return
        did = q.get("id", [""])[0]
        path = _docs.get(did)
        if not path:
            self._send(404, "text/plain", b"not found")
            return
        if u.path == "/meta":
            try:
                n, pages = _run_on_main(lambda: _meta_main(path))
            except Exception as exc:
                self._send(200, "application/json",
                           json.dumps({"error": str(exc)}).encode())
                return
            self._send(200, "application/json", json.dumps({
                "n": n, "pages": pages, "scale": RENDER_SCALE,
                "name": os.path.basename(path), "dir": os.path.dirname(path),
                "strokes": _load_strokes(path),
            }).encode())
        elif u.path == "/page":
            try:
                n = int(q.get("n", ["0"])[0])
                png = _run_on_main(lambda: _render_main(path, n))
            except Exception:
                png = b""
            self._send(200, "image/png", png)
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/save":
            did = q.get("id", [""])[0]
            path = _docs.get(did)
            try:
                ln = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(ln) or b"{}")
            except Exception:
                data = {}
            ok = bool(path) and _save_strokes(path, data.get("pages", {}))
            self._send(200, "application/json", json.dumps({"ok": ok}).encode())
        else:
            self._send(404, "text/plain", b"not found")


def _ensure_server():
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


def viewer_url(path: str):
    if not available():
        return None
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
  #save{margin-left:auto;background:#7c3aed;color:#fff;border:none;border-radius:6px;
        padding:6px 16px;font-weight:700;cursor:pointer}
  #status{color:#9a9ac0;font-size:12px;margin-left:8px}
  #head{padding:8px 12px;background:#0f0f17;border-bottom:1px solid #22223a}
  #head b{color:#c9b8ff} #head span{color:#7a7a9a;font-size:12px}
  #pages{padding:16px;display:flex;flex-direction:column;align-items:center;gap:16px}
  .page{position:relative;box-shadow:0 2px 12px rgba(0,0,0,.5);background:#fff;max-width:980px;width:100%}
  .page img{display:block;width:100%}
  .page canvas{position:absolute;left:0;top:0;width:100%;height:100%;touch-action:none;cursor:crosshair}
  #msg{padding:40px;text-align:center;color:#9a9ac0}
</style></head>
<body>
<div id="bar">
  <button class="tool on" data-t="pen" title="Pen">✏️</button>
  <button class="tool" data-t="highlighter" title="Highlighter">🖍️</button>
  <button class="tool" data-t="eraser" title="Eraser">🧽</button>
  <button class="tool" data-t="text" title="Text">T</button>
  <input type="color" id="color" value="#ff3b30">
  <label style="color:#9a9ac0;font-size:12px">Size <input type="range" id="size" min="1" max="40" value="4"></label>
  <button class="tool" id="undo" title="Undo (Ctrl+Z)" style="width:auto;padding:0 10px">↶</button>
  <button id="save">Save</button><span id="status"></span>
</div>
<div id="head"></div>
<div id="msg">Loading…</div>
<div id="pages"></div>
<script>
const ID=new URLSearchParams(location.search).get('id');
let TOOL='pen',COLOR='#ff3b30',SIZE=4;
const strokes={}, undoStack=[], canvases={};
document.querySelectorAll('.tool[data-t]').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tool[data-t]').forEach(x=>x.classList.remove('on'));b.classList.add('on');TOOL=b.dataset.t;});
color.oninput=e=>COLOR=e.target.value; size.oninput=e=>SIZE=+e.target.value;
undo.onclick=doUndo; save.onclick=()=>saveAll(true);
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key.toLowerCase()==='z'){e.preventDefault();doUndo();}});
function setStatus(t){status.textContent=t;}
function drawStroke(ctx,s){
  if(s.type==='text'){ctx.fillStyle=s.color;ctx.font='bold '+Math.max(14,s.width*6)+'px sans-serif';ctx.fillText(s.text,s.x,s.y);return;}
  ctx.strokeStyle=s.color;ctx.lineCap='round';ctx.lineJoin='round';
  ctx.globalAlpha=s.tool==='highlighter'?0.35:1;ctx.lineWidth=s.tool==='highlighter'?s.width*3:s.width;
  const p=s.points;if(!p||!p.length){ctx.globalAlpha=1;return;}
  ctx.beginPath();ctx.moveTo(p[0][0],p[0][1]);for(let i=1;i<p.length;i++)ctx.lineTo(p[i][0],p[i][1]);ctx.stroke();ctx.globalAlpha=1;}
function draw(page){const c=canvases[page];if(!c)return;c.ctx.clearRect(0,0,c.canvas.width,c.canvas.height);
  for(const s of (strokes[page]||[]))drawStroke(c.ctx,s);}
function pushUndo(page){undoStack.push({page,snap:JSON.stringify(strokes[page]||[])});if(undoStack.length>80)undoStack.shift();}
function doUndo(){const u=undoStack.pop();if(!u)return;strokes[u.page]=JSON.parse(u.snap);draw(u.page);}
function toXY(c,e){const r=c.getBoundingClientRect();return[(e.clientX-r.left)/r.width*c.width,(e.clientY-r.top)/r.height*c.height];}
function erase(page,x,y){const r=Math.max(8,SIZE*2);let rm=false;
  strokes[page]=(strokes[page]||[]).filter(s=>{if(s.type==='text'){if(Math.abs(s.x-x)<120&&Math.abs(s.y-y)<40){rm=true;return false;}return true;}
    const hit=s.points.some(p=>Math.abs(p[0]-x)<=r&&Math.abs(p[1]-y)<=r);if(hit)rm=true;return !hit;});if(rm)draw(page);}
function wire(page){const c=canvases[page].canvas;let cur=null;
  c.addEventListener('pointerdown',e=>{c.setPointerCapture(e.pointerId);const[x,y]=toXY(c,e);pushUndo(page);
    if(TOOL==='text'){const t=prompt('Text:');if(t){(strokes[page]=strokes[page]||[]).push({type:'text',text:t,x,y,color:COLOR,width:SIZE});draw(page);}else undoStack.pop();return;}
    if(TOOL==='eraser'){erase(page,x,y);return;}cur={points:[[x,y]],color:COLOR,width:SIZE,tool:TOOL};});
  c.addEventListener('pointermove',e=>{if(TOOL==='eraser'&&(e.buttons&1)){const[x,y]=toXY(c,e);erase(page,x,y);return;}
    if(!cur)return;const[x,y]=toXY(c,e);cur.points.push([x,y]);drawStroke(canvases[page].ctx,cur);});
  const end=()=>{if(cur){(strokes[page]=strokes[page]||[]).push(cur);cur=null;draw(page);}};
  c.addEventListener('pointerup',end);c.addEventListener('pointercancel',end);}
async function saveAll(explicit){try{
  const r=await fetch('/save?id='+ID,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pages:strokes})});
  const j=await r.json();setStatus(j.ok?'Saved ✓':'Save failed');}catch(e){setStatus('Save failed');}}
function beacon(){try{navigator.sendBeacon('/save?id='+ID,JSON.stringify({pages:strokes}));}catch(e){}}
window.addEventListener('pagehide',beacon);window.addEventListener('beforeunload',beacon);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')beacon();});
(async function(){
  let meta;try{meta=await(await fetch('/meta?id='+ID)).json();}catch(e){document.getElementById('msg').textContent='Could not reach the renderer.';return;}
  if(meta.error){document.getElementById('msg').textContent='Render error: '+meta.error;return;}
  document.title='Annotate — '+(meta.name||'PDF');
  document.getElementById('head').innerHTML='<b>📄 '+(meta.name||'')+'</b><br><span>'+(meta.dir||'')+'</span>';
  document.getElementById('msg').remove();
  Object.assign(strokes, meta.strokes||{});
  const pagesEl=document.getElementById('pages');
  const io=new IntersectionObserver(es=>es.forEach(en=>{if(en.isIntersecting){const img=en.target;if(!img.src)img.src='/page?id='+ID+'&n='+img.dataset.n;io.unobserve(img);}}),{rootMargin:'800px'});
  for(let i=0;i<meta.n;i++){const pg=meta.pages[i];
    const div=document.createElement('div');div.className='page';div.style.aspectRatio=pg.w+'/'+pg.h;
    const img=document.createElement('img');img.dataset.n=i;
    const cv=document.createElement('canvas');cv.width=pg.w;cv.height=pg.h;
    div.appendChild(img);div.appendChild(cv);pagesEl.appendChild(div);
    canvases[i]={canvas:cv,ctx:cv.getContext('2d')};if(!strokes[i])strokes[i]=[];wire(i);draw(i);io.observe(img);}
})();
</script></body></html>
"""
